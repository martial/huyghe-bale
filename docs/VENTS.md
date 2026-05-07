# Vents — full functional reference

The vents personality drives a thermoelectric (Peltier) cabinet: three Peltier
stacks for heat-pumping, two PWM fans (cold-side and hot-side), four tacho
inputs (two per fan), and two DS18B20 1-wire temperature probes. It runs the
"vents" personality of `gpio-osc` on a Raspberry Pi.

For the master architecture and what's *shared* between vents and trolley
(install flow, identity, OSC discovery, status broadcast gating, auto-update,
webhooks), see **[RPI_CONTROLLERS.md](RPI_CONTROLLERS.md)**.

Source of truth for everything in this document:
- `rpi-controller/controllers/vents.py`
- `rpi-controller/config.py:7-37`
- `admin/backend/api/vents_control.py`
- `admin/backend/engine/osc_receiver.py:118-214`

---

## 1. Hardware overview

| Component | Count | Pi pins (BCM) | Drive |
|---|---|---|---|
| Peltier modules | 3 | 26, 25, 24 | digital out, **active HIGH** |
| PWM fan, cold-side | 1 | 20 | hardware PWM, 1 kHz |
| PWM fan, hot-side | 1 | 18 | hardware PWM, 1 kHz |
| Tacho input fan-1 | 2 (A/B) | 27, 17 | input, falling-edge ISR |
| Tacho input fan-2 | 2 (A/B) | 23, 22 | input, falling-edge ISR |
| DS18B20 probes | 2 | 1-wire | `/sys/bus/w1/devices/28*/w1_slave` |

**Datasheet** (in `docs/`): `Peltier Thermocoolers.pdf`.

Each Peltier module has a cold face and a hot face — when ON it pumps heat
from one face to the other. Which face is which depends on how the module is
physically mounted in the rig; the firmware doesn't know or care. The two
fans typically vent the cold air into the conditioned volume (fan 1) and
exhaust the hot side (fan 2), but the firmware also doesn't care — it just
gives you two PWM channels.

The two DS18B20 probes are auto-discovered on boot from the 1-wire bus
(`dtoverlay=w1-gpio` must be in `/boot/firmware/config.txt`). The discovery
order maps to `temp1_c` and `temp2_c` in the status broadcast — by convention
one tracks the cold path and one the hot path.

Tachos: every fan exposes two tach lines (A and B). The firmware computes RPM
from the falling-edge interval as `(1 / dt) / 2 × 60` — two pulses per rev.
A 5 ms minimum gap (`VENTS_TACHO_MIN_DT_S`) debounces noise. If no edge for
2 s, RPM is forced to 0 (a stalled fan can't keep its last good reading).

---

## 2. OSC contract

All UDP. Pi listens on **port 9000** (raw motion + commands). Backend's reply
listener is on **port 9001**.

### 2.1 Backend → Pi (commands)

| Address | Args | Effect |
|---|---|---|
| `/sys/ping` | `reply_port:int` | Pi answers with `/sys/pong [origin_ip, type, hardware_id]` to the supplied port |
| `/vents/peltier/1` | `int 0\|1` | turn Peltier 1 on/off (raw) |
| `/vents/peltier/2` | `int 0\|1` | turn Peltier 2 on/off (raw) |
| `/vents/peltier/3` | `int 0\|1` | turn Peltier 3 on/off (raw) |
| `/vents/peltier` | `int mask` | bitmask: bit 0 = P1, bit 1 = P2, bit 2 = P3. Bits beyond `0b111` are masked off |
| `/vents/fan/1` | `float 0..1` | fan 1 PWM duty (cold-side). Goes through the [fan pipeline](#5-fan-control-pipeline) |
| `/vents/fan/2` | `float 0..1` | fan 2 PWM duty (hot-side). Same pipeline |
| `/vents/mode` | `string "raw"\|"auto"` | switch regulation mode. Switching to `auto` forces both fans to 0% |
| `/vents/target` | `float °C` | regulation setpoint (auto mode). Clamped to stay below `max_temp_c − hysteresis − margin` |
| `/vents/max_temp` | `float °C` | safety ceiling (per-sensor over-temp threshold). **Persisted** to `vents_prefs.json` |
| `/vents/config/min_fan_pct` | `float 0..100` | PWM floor enforced by `_set_fan`. **Persisted** |
| `/vents/config/max_fan_pct` | `float 0..100` | PWM ceiling (multiplier on every fan command). **Persisted** |
| `/vents/config/over_temp_fan_pct` | `float 0..100` | fan PWM forced on both fans during over-temp. **Persisted** |

Any peltier or fan command issued in `auto` mode auto-switches the mode back
to `raw` (with a log line). This lets a manual override take effect immediately
without the auto loop fighting it on the next tick.

### 2.2 Pi → backend (broadcasts)

| Address | Args | Cadence |
|---|---|---|
| `/sys/pong` | `[ip, type, hardware_id]` | reply to `/sys/ping` |
| `/vents/status` | 16 args (see §6) | unsolicited at 5 Hz once a `/sys/ping` has been received |

The Pi only starts broadcasting `/vents/status` *after* it has received at
least one `/sys/ping` from the admin (so it knows where to send replies).
Broadcasts go to whoever pinged most recently, on the port they specified
(typically 9001).

---

## 3. Persistent settings (per-Pi)

Stored in `~/.config/gpio-osc/vents_prefs.json`. Source of truth:
`controllers/vents.py:175-217`.

| Key | Type | Range | Default | Meaning |
|---|---|---|---|---|
| `max_temp_c` | float | −55 .. 125 | `80.0` (`VENTS_DEFAULT_MAX_TEMP_C`) | per-sensor over-temp threshold. Trips `state=over_temp` if **any** probe exceeds this |
| `min_fan_pct` | float | 0 .. 100 | `20.0` (`VENTS_FAN_PWM_MIN_PCT`) | PWM floor for non-zero fan commands (a stalled fan can't slip through) |
| `max_fan_pct` | float | 0 .. 100 | `100.0` | PWM ceiling — every non-zero fan command is multiplied by `max_fan_pct/100` before the floor |
| `over_temp_fan_pct` | float | 0 .. 100 | `100.0` | fan PWM forced on **both** fans during the over-temp interlock |

**Atomic write**: the prefs save flow writes `vents_prefs.json.tmp` then
renames over the target — corruption-resistant (`_save_prefs`, lines 203–217).

**Forward-compat load**: missing keys keep their compiled-in defaults; bad
values log a warning and use the default (`_load_prefs`, lines 183–200).

**Cross-clamp**: `target_temp_c` and `max_temp_c` are kept strictly separated
by `_BAND_MARGIN_C = 0.05`, so the regulation band can never overlap the
over-temp ceiling (`_clamp_max_vs_target`, `_clamp_target_vs_max`).

---

## 4. Modes & state machine

Two orthogonal concepts:

- **Mode** — what the operator wants: `"raw"` (manual) or `"auto"` (regulation).
- **State** — what the auto loop is actually doing right now (broadcast on
  `/vents/status`).

```
┌─────────┐    /vents/mode "auto"      ┌───────────────────────────────┐
│  raw    │ ───────────────────────►   │  auto loop (4 Hz tick)        │
│  state= │                            │  state ∈ heating | cooling |  │
│  idle   │ ◄─────────────────────     │           holding | over_temp │
└─────────┘  /vents/peltier|fan ...    │                  | sensor_err │
                  (override)            └───────────────────────────────┘
```

Auto-loop decision tree (every 250 ms, `_auto_loop` lines 380–413):

```
mode != "auto"              → state = idle
both probes missing         → state = sensor_error  (peltiers + fans = 0)
any probe > max_temp_c      → state = over_temp     (peltiers = 0; both fans = over_temp_fan_pct)
avg < target − hysteresis   → state = heating       (peltier mask = 0b111)
avg > target + hysteresis   → state = cooling       (peltier mask = 0b000)
otherwise (deadband)        → state = holding       (peltier mask unchanged)
```

`hysteresis = VENTS_HYSTERESIS_C = 0.5 °C`. The deadband is symmetric (±H)
around `target_temp_c`. `holding` deliberately leaves Peltier outputs alone
to avoid chatter at the band edges.

The avg used for `heating`/`cooling`/`holding` is `(t1 + t2) / 2` if both
sensors are valid, otherwise the single valid one. The `over_temp` check is
**per-sensor** — a localised hot spot trips it even if the other probe is
still cool (`_any_temp_over_max`, lines 364–371). This is the safety
behaviour you want when one Peltier face runs away.

Fans are not driven by the regulation loop — only the over-temp branch
touches them. To run fans, send `/vents/fan/*` directly (any time) or set
`auto` mode and rely on the over-temp interlock.

---

## 5. Fan control pipeline

`_set_fan(index, duty_0_1)` (lines 260–277):

```
raw_pct  = clamp(duty_0_1 × 100, 0, VENTS_FAN_PWM_MAX_PCT)
if duty_0_1 > 0:
    final_pct = max(raw_pct × max_fan_pct / 100, min_fan_pct)
else:
    final_pct = 0.0      ← explicit 0 always passes through (lets you fully stop a fan)
```

Three layers:

1. **`max_fan_pct`** — device-side ceiling (multiplier). Replaces the old
   playback-engine `output_cap`; the cap is enforced regardless of who issued
   the command (admin panel, timeline playback, OSC bridge).
2. **`min_fan_pct`** — device-side floor. Stops a fan from being commanded to
   a non-zero duty too low to actually spin (typical brushless DC fans
   stall below ~15–20%).
3. **Explicit zero bypass** — `duty_0_1 == 0.0` always emits 0%, even when
   the floor would otherwise raise it. Lets the operator fully stop a fan.

This pipeline is also what the over-temp branch uses when it pins fans to
`over_temp_fan_pct / 100`.

---

## 6. Status broadcast — wire format

`/vents/status` carries **16 args** in this order
(`get_status_osc_args`, lines 742–759):

| Position | Field | Type | Notes |
|---|---|---|---|
| 0 | `temp1_c` | float | DS18B20 probe 1 in °C, or **`-1.0`** if missing |
| 1 | `temp2_c` | float | DS18B20 probe 2 in °C, or **`-1.0`** if missing |
| 2 | `fan1_0_1` | float | fan 1 last commanded duty, [0, 1] |
| 3 | `fan2_0_1` | float | fan 2 last commanded duty, [0, 1] |
| 4 | `peltier_mask` | int | bits 0–2 = P1, P2, P3 |
| 5 | `rpm1A` | float | fan 1 tacho line A RPM |
| 6 | `rpm1B` | float | fan 1 tacho line B RPM |
| 7 | `rpm2A` | float | fan 2 tacho line A RPM |
| 8 | `rpm2B` | float | fan 2 tacho line B RPM |
| 9 | `target_c` | float | regulation setpoint |
| 10 | `mode` | string | `"raw"` \| `"auto"` |
| 11 | `state` | string | `idle` \| `heating` \| `cooling` \| `holding` \| `sensor_error` \| `over_temp` |
| 12 | `max_temp_c` | float | over-temp ceiling (persisted) |
| 13 | `min_fan_pct` | float | PWM floor (persisted) |
| 14 | `over_temp_fan_pct` | float | fan PWM during over-temp (persisted) |
| 15 | `max_fan_pct` | float | PWM ceiling (persisted) |

Backend parses args 12–15 as **optional** so older firmware that only sends
12 args still works (`osc_receiver.py:118-178`).

---

## 7. Backend RPM alarm system

This is **admin-side only** — the Pi just reports RPM values; the backend
decides when one of those values is suspicious.

`OscReceiver._update_rpm_alarms` (lines 180–214) tracks per-channel state.
A channel is in alarm when, **for 3 seconds continuously**, the fan is
commanded > 0 *and* its tacho RPM is below `min_rpm_alarm` (default `500`,
line 55). Active alarms and recent transitions go into
`OscReceiver.active_alarms` and `OscReceiver.recent_alarms` for the admin UI
to surface.

---

## 8. Threading model

Two background daemon threads, both stopped by `_shutdown_event.set()` in
`cleanup()` (lines 462–476):

- **`_temp_loop`** — polls both DS18B20 probes at `VENTS_TEMP_POLL_HZ = 1 Hz`.
  DS18B20 reads are slow (~750 ms each), so polling faster doesn't help.
- **`_auto_loop`** — auto-regulation tick at `VENTS_AUTO_LOOP_HZ = 4 Hz`.
  Reads `temp_c`, computes `avg` and `_any_temp_over_max`, applies the
  state machine, calls `_tacho_decay_tick`.

The status broadcaster runs in the shared OSC server thread (see
[RPI_CONTROLLERS.md](RPI_CONTROLLERS.md) §3) at 5 Hz.

---

## 9. Admin UI

Live at `Vents page → click a vents → vents test panel`. Component:
`admin/frontend/src/components/vents/VentsTestPanel.tsx`.

The panel lets operators:
- Toggle each Peltier independently (or via mask).
- Drive each fan PWM 0..1 with a slider.
- Switch between `raw` and `auto` modes.
- Set the regulation `target_c`.
- Set `max_temp_c`, `min_fan_pct`, `max_fan_pct`, `over_temp_fan_pct` (each
  persists immediately on the Pi via the matching `/vents/config/*` address).

The page polls `GET /api/v1/vents-control/<id>/status` every 500 ms; that
poll *also* sends `/sys/ping` to keep the Pi's status broadcasts flowing.

---

## 10. Backend API surface

`admin/backend/api/vents_control.py`:

- `POST /api/v1/vents-control/<device_id>/command`
  Body: `{command, value, index?}`. Translates to one OSC send.
  Valid commands: `peltier`, `peltier_mask`, `fan`, `mode`, `target`,
  `max_temp`. (The three `/vents/config/*` addresses are sent separately
  through admin Settings — there's no single dispatch table for them.)
- `GET /api/v1/vents-control/<device_id>/status`
  Returns the last `/vents/status` snapshot + an `online` bool driven by
  `/sys/ping` round-trip (6 s timeout).

The `index` field is one-based for the operator (Peltier 1/2/3, Fan 1/2)
and is decremented in `_route` before being sent on the wire.

---

## 11. Tests

`rpi-controller/tests/test_vents.py` — coverage:
- Setup/cleanup hygiene: PWM init, tacho ISR registration, GPIO cleanup.
- Each raw OSC handler (peltier 1/2/3 + mask, fan 1/2, mode, target,
  max_temp).
- Mode interactions: raw command in auto mode flips mode to raw; `auto`
  forces both fans to 0.
- Over-temp interlock: per-sensor trip; peltier "on" requests ignored;
  fans pinned to `over_temp_fan_pct`.
- Sensor-error branch: both probes missing → peltiers off, fans off.
- Fan pipeline: `min_fan_pct` floor, `max_fan_pct` scaling, explicit-0 bypass.
- Prefs persistence: load/save round-trip, atomic write, missing-key
  forward-compat.
- Status payload: 16-arg shape, `-1.0` for missing temps.
- DS18B20 parser: CRC validation, unit conversion, error handling.
- HTTP test surface mirrors the OSC surface end-to-end.

Run:
```bash
cd rpi-controller && python3 -m pytest tests/test_vents.py -v
```

Backend tests (`admin/backend/tests/test_osc_surfaces.py` `TestVentsPanel`,
`TestVentsTimelinePlayback`) cover the wire shape from the admin route down
to the OSC tuple.

---

## 12. Quick reference — pin map

```
PELTIER_1   (BCM 26)   output  digital, active HIGH
PELTIER_2   (BCM 25)   output  digital, active HIGH
PELTIER_3   (BCM 24)   output  digital, active HIGH
FAN_1_PWM   (BCM 20)   output  hardware PWM @ 1 kHz, cold-side
FAN_2_PWM   (BCM 18)   output  hardware PWM @ 1 kHz, hot-side
TACHO_1A    (BCM 27)   input   falling-edge ISR → RPM
TACHO_1B    (BCM 17)   input   "
TACHO_2A    (BCM 23)   input   "
TACHO_2B    (BCM 22)   input   "
DS18B20     (BCM 4)    1-wire  via dtoverlay=w1-gpio (default 1-wire pin)
```

Constants: `VENTS_FAN_PWM_FREQ = 1000 Hz`, `VENTS_AUTO_LOOP_HZ = 4 Hz`,
`VENTS_TEMP_POLL_HZ = 1 Hz`, `VENTS_STATUS_HZ = 5 Hz`,
`VENTS_HYSTERESIS_C = 0.5 °C`, `VENTS_DEFAULT_TARGET_C = 25 °C`,
`VENTS_DEFAULT_MAX_TEMP_C = 80 °C`.
