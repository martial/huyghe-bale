# RPi Controllers — master overview

The `rpi-controller/` directory contains a single Python codebase that runs
on every Raspberry Pi in the installation. At install time, each Pi is
assigned a **personality** — either `vents` or `trolley` — which determines
which physical hardware it drives and which OSC namespace it answers to.

This document covers what's *shared* between the two personalities (entry
point, identity, OSC discovery handshake, status broadcasts, install flow,
auto-update, webhooks). For the per-personality details, see:

- **[VENTS.md](VENTS.md)** — Peltier cabinet (3 Peltiers + 2 PWM fans + 4
  tachos + 2 DS18B20 probes).
- **[TROLLEY.md](TROLLEY.md)** — dual-stepper rail gantry (closed-loop CL86Y
  drivers + 2 limit switches).

---

## 1. The two personalities at a glance

|  | **vents** | **trolley** |
|---|---|---|
| Hardware | 3 Peltier modules, 2 PWM fans, 4 tachos, 2 DS18B20 probes | 2 NEMA-34 closed-loop steppers (lockstep), 2 limit switches |
| OSC namespace | `/vents/*` | `/trolley/*` |
| Status address | `/vents/status` (16 args) | `/trolley/status` (5 args) |
| Status rate | 5 Hz (`VENTS_STATUS_HZ`) | 5 Hz (`TROLLEY_STATUS_HZ`) |
| Persistent prefs file | `~/.config/gpio-osc/vents_prefs.json` | `~/.config/gpio-osc/device.json` (`trolley` block) |
| Background threads | temp-poll (1 Hz), auto-loop (4 Hz) | motion-thread (queue-driven) |
| Modes / state | `mode ∈ raw, auto`; `state ∈ idle, heating, cooling, holding, sensor_error, over_temp` | `state ∈ idle, homing, following` |
| Hardware-id prefix | `vents_<8hex>` | `trolley_<8hex>` |
| Systemd unit | `gpio-osc-vents.service` | `gpio-osc-trolley.service` |
| Auto-home on boot? | n/a | `TROLLEY_AUTO_HOME_ON_BOOT = False` (commit-time default) |
| Bench tool | (none) | `scripts/test_trolley.py` (direct GPIO), `scripts/calibrate_trolley_osc.py` (OSC) |

Both personalities share the same Pi-side runtime (entry point, OSC server,
status broadcaster, ping handshake, install scaffolding, auto-update).

---

## 2. Repo layout (`rpi-controller/`)

```
rpi-controller/
├── gpio_osc.py             # entry point — boots a controller by personality
├── identity.py             # device.json — persisted {type, id}
├── config.py               # all GPIO pin maps and timing constants
├── webhooks.py             # async POST notifier (start/stop/crash/error)
├── trolley_settings.py     # trolley-only persisted settings (config_set/save)
├── controllers/
│   ├── __init__.py         # personality dispatch (vents vs trolley)
│   ├── vents.py            # 778 lines — full vents implementation
│   └── trolley.py          # 779 lines — full trolley implementation
├── scripts/
│   ├── test_trolley.py     # direct-GPIO bench tool (runs ON the Pi)
│   └── calibrate_trolley_osc.py   # OSC-driven config CLI (runs anywhere)
├── tests/
│   ├── conftest.py         # GPIO mock fixtures
│   ├── test_vents.py
│   └── test_trolley.py
├── install.sh              # one-shot installer (--type=vents|trolley)
├── auto_update.sh          # boot-time `git pull` + pip install
└── requirements.txt
```

---

## 3. Shared architecture

### 3.1 Boot sequence

`gpio_osc.py:main` (line 331+):

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. identity.load_or_create()                                     │
│    → reads ~/.config/gpio-osc/device.json or generates a new one │
│    → returns {"type": "vents"|"trolley", "id": "<type>_<8hex>"}  │
├──────────────────────────────────────────────────────────────────┤
│ 2. controllers.load(IDENTITY["type"])                            │
│    → imports controllers.vents OR controllers.trolley            │
├──────────────────────────────────────────────────────────────────┤
│ 3. controller.setup(webhooks)                                    │
│    → pin config, ISR registration, background threads start      │
├──────────────────────────────────────────────────────────────────┤
│ 4. Thread A: HTTP status server on :9001 (StatusHandler)         │
│ 5. Thread B: OSC server on :9000 (dispatcher.map per controller) │
│ 6. Thread C: status broadcaster — gated on first /sys/ping       │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Identity

`identity.py:47` — `load_or_create()`:
- File: `~/.config/gpio-osc/device.json`
- Schema: `{"type": "vents"|"trolley", "id": "<type>_<8hex>"}`
- `id` is `secrets.token_hex(4)` (32 random bits) — collision-resistant
  across an installation of any practical size.
- On first boot the type is resolved in this order:
  1. `$GPIO_OSC_TYPE` (set by the systemd unit, see §4)
  2. `--type=<value>` CLI arg
  3. Fallback: `"vents"` (so existing Pis keep working if never re-installed)
- If the file exists but is malformed or has an unknown type, the loader
  logs a warning and **regenerates** — but only the type is reset; you'd
  also lose the persisted id. To force a clean reset, delete the file.

### 3.3 OSC discovery handshake — `/sys/ping` ↔ `/sys/pong`

The Pi listens on UDP **9000**. The backend's reply listener is on UDP
**9001**.

```
admin → Pi   /sys/ping   <reply_port:int>
Pi → admin   /sys/pong   [origin_ip:str, type:str, hardware_id:str]
                          (sent to the IP the ping came from, on reply_port)
```

`gpio_osc.py:267-282` — every ping the Pi receives also updates
`last_pinger = (origin_ip, return_port)`. The status broadcaster uses that
tuple to know where to send `/<personality>/status` frames.

**Legacy compatibility**: very old firmware would reply with a 1-arg pong
(`[origin_ip]` only). The backend's `osc_receiver._handle_pong` accepts
either shape, defaulting `type` to `"vents"` when missing. Modern firmware
always sends all three fields.

### 3.4 Status broadcast — gated, 5 Hz

`gpio_osc.py:285-307` — `run_status_broadcaster`:

- Reads `controller.STATUS_BROADCAST_ADDRESS` and
  `controller.STATUS_BROADCAST_HZ` (each personality module declares both at
  the top of its file).
- Loops at `1/HZ` seconds. Only emits when `last_pinger is not None` — i.e.
  the Pi has already received at least one `/sys/ping` and knows where to
  send.
- Calls `controller.get_status_osc_args()` for the arg list each tick.
- Sends to the most recent pinger.

Why gated? Until the admin pings, the Pi has no idea where to send replies.
Broadcasting blindly to a hard-coded port would only work in trivial network
setups; the ping/pong handshake makes it NAT/firewall-friendly and keeps the
network quiet when nobody's listening.

### 3.5 HTTP status / debug surface — :9001

`gpio_osc.py:144-264` — small built-in HTTP server (no Flask), routes:

| Route | Method | Purpose |
|---|---|---|
| `GET /status` | — | uptime, memory/CPU/disk, identity, git version |
| `POST /update` | — | run `auto_update.sh`, restart service if successful |
| `POST /gpio/test` | — | direct probe to `controller.handle_http_test(body)` — mirrors the OSC surface for debugging without needing OSC tooling |

This surface is mostly used by the admin's "Devices" page health checks and
the `/gpio/test` button in the dev tools, not in production playback.

### 3.6 Webhooks

`webhooks.py` — async POST notifier. Reads `webhooks.json` next to the
script. Schema:

```json
{
  "webhooks": [
    {"url": "https://hooks.example/foo", "token": "Bearer xyz", "events": ["start", "stop"]}
  ]
}
```

Event types fired by the runtime:
- `"start"` — service came up
- `"stop"` — clean shutdown (SIGTERM/SIGINT)
- `"crash"` — unhandled exception (via `sys.excepthook`)
- `"error"` — non-fatal subsystem error: `{"source": "...", "error": "..."}`

Worker is a single daemon thread; failures are logged but never block the
caller. If `webhooks.json` is missing, the notifier silently no-ops — no
config required for normal operation.

### 3.7 Cleanup on SIGTERM/SIGINT

`gpio_osc.py:310-328` — sets `shutdown_event`, fires `"stop"` webhook,
calls `controller.cleanup()` (each personality zeroes its outputs and joins
its threads), then `GPIO.cleanup()`, and exits 0. Idempotent.

---

## 4. Install & auto-update — at a glance

Quick install on a fresh Pi:
```bash
curl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \
    | sudo bash -s -- --type=vents
```
That clones the repo into the target user's home and hands off to
`rpi-controller/install.sh`, which is **Pi-model-aware** (Pi 5 → `rpi-lgpio`,
Pi 3/4/Zero → `RPi.GPIO`), bootstraps `~/.config/gpio-osc/device.json`,
writes `/etc/systemd/system/gpio-osc-<type>.service` with `Restart=always`
and `ExecStartPre=auto_update.sh`, and starts the service.

`auto_update.sh` runs every service start: `git fetch origin main`, and if
there's an update, tags `last_good_state` → `git pull` → `pip install`. Any
failure rolls back to the tag. Offline-safe — fetch failure logs and the
service starts on the current local code. Log: `/tmp/gpio-osc-updater.log`.

**The full operational reference lives in [INSTALL.md](INSTALL.md)**, including:
the SD-card flashing protocol, the mass-install orchestrator
(`docs/sd-protocol/deploy_pis.sh`), each install step's exact behaviour,
the systemd unit content verbatim, the optional `setup_webhooks.sh`, day-2
operational tasks, SSH deploy-key setup, and troubleshooting.

---

## 5. Persistent state on the Pi

Two files under `~/.config/gpio-osc/`:

| File | Personality | Contents | Updated by |
|---|---|---|---|
| `device.json` | both | `{type, id}` + the entire `trolley` settings block (rail length, microsteps, calibration_direction, accel/decel, soft_limit_pct, permissive_mode, …) | `identity.py` (boot) and `/trolley/config/save` |
| `vents_prefs.json` | vents only | `{max_temp_c, min_fan_pct, max_fan_pct, over_temp_fan_pct}` | `/vents/max_temp` and `/vents/config/*` |

Both writers use the **temp-file-then-rename** pattern, so a power cut
mid-write can't corrupt the file. Load is forward-compat (missing keys
keep their compiled-in defaults).

---

## 6. Probing a Pi by hand (without the admin)

```bash
# Send /sys/ping with a reply port:
oscchief send <pi-ip>:9000 /sys/ping i 9999
# Listen for the pong on 9999:
oscdump 9999
```

For trolley-only interactive sessions there's also
`rpi-controller/scripts/calibrate_trolley_osc.py --host <ip>` (menu over
OSC, see [TROLLEY.md](TROLLEY.md) §11.2).

The full operational playbook — switching personality, regenerating the
hardware id, force-updating, SSH deploy-key setup, replacing a dead Pi,
troubleshooting — lives in **[INSTALL.md](INSTALL.md)** §9–§10.

---

## 7. Backend cross-reference

The admin (Flask + React) handles all OSC traffic to and from the Pis. Key
files:

| Backend file | Role |
|---|---|
| `admin/backend/engine/osc_sender.py` | UDP sender used everywhere (`OscSender.send/send_values`) |
| `admin/backend/engine/osc_receiver.py` | listens on :9001, parses `/sys/pong`, `/vents/status`, `/trolley/status`; tracks `last_seen`, computes RPM alarms |
| `admin/backend/api/vents_control.py` | `POST /api/v1/vents-control/<id>/command` → `/vents/<addr>` send |
| `admin/backend/api/trolley_control.py` | same shape for trolley, plus `_COMMAND_MAP` for accel/decel etc. |
| `admin/backend/engine/playback.py` | timeline playback engine — fans-out OSC to all matching devices at ~30 Hz |
| `admin/backend/engine/osc_bridge.py` | optional UDP bridge for arbitrary external OSC sources |

`admin/backend/tests/test_osc_surfaces.py` is the wire-format matrix —
every admin trigger, asserted against the exact `(ip, port, address, value)`
tuple it produces. Worth reading before you touch anything OSC-related.

---

## 8. References

- **[INSTALL.md](INSTALL.md)** — full Pi-side install + auto-update +
  operational playbook (flashing, mass-deploy, systemd unit content,
  troubleshooting).
- **[VENTS.md](VENTS.md)** — full vents reference (handlers, prefs,
  state machine, fan pipeline, status payload, tests, pin map).
- **[TROLLEY.md](TROLLEY.md)** — full trolley reference (pin map, OSC
  contract, settings, position math, state machine, calibration flow,
  permissive mode, accel/decel ramps, safety guards, tests, CLI tools).
- **`docs/Driver_CL86Y_V2.0_pulse_stepper_driver_manual_V1.0.pdf`** — trolley
  stepper driver manual.
- **`docs/Motor_34HS38-4204D-E1000.pdf`** — trolley NEMA-34 motor datasheet.
- **`docs/Peltier Thermocoolers.pdf`** — vents Peltier datasheet.
- **`docs/SE_Huyghe_V1.pdf`**, **`SE_Huyghe_V2.pdf`** — installation
  schematics.
