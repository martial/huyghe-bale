# Pi-side install — full operational reference

Provisioning a Raspberry Pi from a blank SD card to a running
`gpio-osc-{vents|trolley}.service` with auto-update wired in. This is the
operational reference; **[RPI_CONTROLLERS.md](RPI_CONTROLLERS.md)** is the
architectural overview that explains *what* the controllers do, and
**[VENTS.md](VENTS.md)** / **[TROLLEY.md](TROLLEY.md)** cover the per-personality
OSC contracts.

This doc is **Pi-side only**. The admin desktop app build (`compile_app.sh`,
`compile_app_windows.ps1`, `deploy.sh`, `release.sh`, GitHub Actions) is a
separate concern — covered elsewhere when needed.

---

## Fleet model

Each Pi has three keys, related but distinct:

| Key | Format | Set when | Used for |
|---|---|---|---|
| **Hostname** | `v0..v6` (vents), `t0..t1` (trolley) | flash time, in Raspberry Pi Imager | mDNS / SSH (`v0.local`) |
| **`hardware_id`** | `<type>_<8hex>` (e.g. `vents_a3f1b09e`) | first boot, by `identity.py` | OSC `/sys/pong`, admin device-store key |
| **Friendly name** | free-form | by hand in admin UI | scenography (`Vent cellier haut-gauche`) |

Authoritative tables — naming convention, fleet inventory, materials list,
locale + Wi-Fi defaults — live in
**[`docs/sd-protocol/PROTOCOLE_SD_HUYGHE_BALE.md`](sd-protocol/PROTOCOLE_SD_HUYGHE_BALE.md)**
and **[`INVENTAIRE_PI.md`](sd-protocol/INVENTAIRE_PI.md)**. This doc links
there rather than duplicating them.

The fleet for this install: **7 vents + 2 trolley** = 9 Pi 5.

---

## Stage 1 — SD card flash (one-time per Pi)

Done on the Mac with **Raspberry Pi Imager**. For each card:

1. Choose **Raspberry Pi 5** as device.
2. Choose OS — Lite is recommended (no UI, smaller, faster boot). Desktop
   works too if you want a screen for local debug.
3. Click the gear icon → **OS Customization** block:
   - **Hostname**: `v0`, `v1`, …, `t0`, `t1` (lowercase, lookup-friendly)
   - **User**: `pi` (the repo's installer assumes `pi`/`SUDO_USER`)
   - **Password**: shared across the fleet is fine; it's behind the LAN
   - **SSH** → **Authentication: public-key** → paste your Mac's
     `~/.ssh/id_ed25519.pub` (or equivalent). **This is required** — the
     mass-install orchestrator (`deploy_pis.sh`) needs key-based auth.
   - **Wi-Fi**: optional; Ethernet is the nominal path
   - **Locale**: `Europe/Paris` + `fr_FR` keyboard
4. Write the card.

**Label everything**: SD card, Pi case, Ethernet cable. Coloured stickers
help when 9 of them are in a switch.

After flashing all 9 cards, slot each into its labelled Pi, plug Ethernet
into the dedicated switch, and power them up. Wait ~60 s for first boot
(filesystem expansion, SSH key setup, mDNS up).

Sanity check from the Mac:
```bash
for h in v0 v1 v2 v3 v4 v5 v6 t0 t1; do
    ping -c 1 -W 1500 "$h.local" >/dev/null && echo "$h ✓" || echo "$h ✗"
done
```

If any Pi is silent, plug in HDMI + keyboard and check `avahi-daemon` is
running.

---

## Stage 2 — Mass install via `deploy_pis.sh` (recommended path)

`docs/sd-protocol/deploy_pis.sh` walks the entire fleet, runs the curl-pipe
installer on each, collects each Pi's `hardware_id` + IP + MAC, and writes
a CSV inventory.

### Prereqs
- All 9 Pis up and reachable on `<host>.local` (Stage 1 sanity check passed).
- Your SSH key is loaded in the agent (`ssh-add -l`); password auth is **not**
  used.
- The `INSTALL_URL` constant inside the script points at the GCS-hosted
  bootstrap script:
  `https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh`.

### Run
```bash
chmod +x docs/sd-protocol/deploy_pis.sh
./docs/sd-protocol/deploy_pis.sh             # all 9, in parallel
./docs/sd-protocol/deploy_pis.sh v2 t0       # subset (re-run a single Pi)
```

### What it does, per Pi

1. `ping -c 1 -W 1500 <host>.local` — fail-fast on unreachable Pis.
2. SSH to grab `ip` (first `hostname -I`) + default-route MAC. Captures
   these *before* the install in case the install fails (so you still get
   diagnostic data in the inventory).
3. Pipes the install one-liner over SSH:
   ```bash
   curl -sSL $INSTALL_URL | sudo bash -s -- --type=$type
   ```
4. SSH back to read `~/.config/gpio-osc/device.json` for the generated
   `hardware_id`, plus `systemctl is-active gpio-osc-<type>` for the
   service status.
5. Appends a row to the results table; either `OK`, `UNREACHABLE`,
   `INSTALL_FAILED`, or `SERVICE_NOT_ACTIVE`.

### Output

- `docs/sd-protocol/inventaire_pis.csv` — final inventory, one row per Pi:
  `num, hostname, type, status, ip, mac, hardware_id, date`
- `docs/sd-protocol/deploy_logs/<host>.log` — full stdout/stderr of each
  install (useful when one Pi fails).
- Console summary: `✅ N/9 Pi déployés` / `❌ M en erreur`.

### Re-running on one Pi

Idempotent — the installer detects an existing identity and reuses it
unless you change `--type=`. Just pass the hostname as an argument:
```bash
./docs/sd-protocol/deploy_pis.sh v3
```

The CSV is rewritten each run (so don't hand-edit it; copy the values into
**INVENTAIRE_PI.md** for the durable record).

---

## Stage 3 — One-liner install (manual, single Pi)

What the orchestrator runs on each Pi. Run it directly when you're SSH-ed
into a single Pi and want to install (or reinstall) without the wrapper:

```bash
curl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \
    | sudo bash -s -- --type=vents
```

Replace `--type=vents` with `--type=trolley` for a trolley controller. If
`--type=` is omitted, the underlying `rpi-controller/install.sh` will prompt.

### What the GCS bootstrap (`install.sh` at the repo root) does

`install.sh` is a 100-line bootstrap. It:

1. **Refuses to run as non-root** (the curl-pipe must be `| sudo bash`).
2. **Resolves the target user** in this order:
   `$SUDO_USER` → existing `pi` user → fallback to `root` (with warning).
   The repo gets cloned into that user's `$HOME` so the service can run
   without root.
3. **Installs `git` if missing** (`apt-get install -y git`).
4. **Clones or pulls** `https://github.com/martial/huyghe-bale.git` into
   `$HOME/huyghe-bale`. Subsequent runs `git pull origin main`.
5. **Hands off** to `rpi-controller/install.sh`, passing `--type=` through.

This separation keeps the GCS-hosted bootstrap tiny (rarely needs updating)
and lets the real installer evolve in-tree.

---

## Stage 4 — `rpi-controller/install.sh` internals

Where the actual configuration happens. Path: `~/huyghe-bale/rpi-controller/install.sh`.

### Type resolution (lines 6–35)
- `--type=vents` or `--type=trolley` from argv, **or** an interactive prompt
  if neither was supplied.
- Anything else is rejected.

### Pi-model branching (lines 60–95)

Reads `/proc/device-tree/model`. The GPIO library and venv flags differ:

| Pi model | GPIO library | Venv flag | APT deps |
|---|---|---|---|
| **Pi 5** | `rpi-lgpio>=0.4` (pulls in `lgpio`) | none | `swig liblgpio-dev` |
| **Pi 3 / Pi 2** | `RPi.GPIO>=0.7.0` | `--system-site-packages` | `build-essential python3-dev` |
| **Default** (Pi 4, Pi Zero 2, unknown) | `RPi.GPIO>=0.7.0` | `--system-site-packages` | `build-essential python3-dev` |

For Pi 5 the piwheels wheel for `lgpio` is source-only on Python 3.13, hence
the explicit `swig` + `liblgpio-dev` apt step. For Pi 3 the Stretch SSL
chain is broken, so pip gets the `--trusted-host` triplet and skips the
self-upgrade step.

The installer also **re-creates the venv** if `--system-site-packages` was
toggled (the installed flag is in `pyvenv.cfg`).

### Identity bootstrap (lines 132–159)

Path: `~pi/.config/gpio-osc/device.json`.

- **No file** → run `identity.load_or_create()` with
  `GPIO_OSC_TYPE=$DEVICE_TYPE` env so the new id is the right type.
- **File exists, type matches** → keep it (preserves the persisted
  `hardware_id` across reinstalls).
- **File exists, type ≠ requested** → delete and regenerate. This is the
  supported path for **switching personalities** on a Pi; expect the
  hardware id to change.

### Disabling sibling/legacy services (lines 161–178)

- Removes `/etc/systemd/system/gpio-osc.service` (legacy unified unit).
- Removes the *other* personality's unit if present
  (`gpio-osc-trolley.service` is removed when installing as `vents`,
  and vice versa).

### Systemd unit (lines 179–203)

Generated at `/etc/systemd/system/gpio-osc-<type>.service`:

```ini
[Unit]
Description=GPIO OSC Controller (<type>) for HUYGHE
After=network.target

[Service]
Type=simple
User=<APP_USER>
WorkingDirectory=<APP_DIR>
Environment=GPIO_OSC_TYPE=<type>
ExecStartPre=<APP_DIR>/auto_update.sh
ExecStart=<APP_DIR>/venv/bin/python <APP_DIR>/gpio_osc.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Key properties:
- **`Environment=GPIO_OSC_TYPE=…`** so identity resolution picks the right
  type even on a fresh `device.json`.
- **`ExecStartPre=auto_update.sh`** — every service start tries to pull
  newer code; see Stage 5.
- **`Restart=always`** with 5 s back-off — a crash in `gpio_osc.py` is
  always retried; an `auto_update.sh` rollback failure also retries (which
  is fine because rollback is idempotent).

### Sudoers entry (lines 205–211)

Written to `/etc/sudoers.d/gpio-osc-<type>` (mode `0440`):
```
<APP_USER> ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart gpio-osc-<type>
```
Lets the admin Pi-restart button (and any other helper) restart the
service without a password prompt. The legacy unified `gpio-osc` sudoers
entry is removed in the same step.

### Final start (lines 213–222)

```
sudo systemctl daemon-reload
sudo systemctl enable gpio-osc-<type>
sudo systemctl restart gpio-osc-<type>
sudo systemctl status gpio-osc-<type> --no-pager
```

Post-install you should see `Active: active (running)` and the Pi's
identity printed in the journal.

---

## Stage 5 — `auto_update.sh` (boot-time updates)

Path: `~/huyghe-bale/rpi-controller/auto_update.sh`. Runs as `ExecStartPre`
on every service start (and only then — there is **no cron job**).

### Flow

1. `cd` to the git root.
2. `git fetch origin main`. **Offline-safe**: failure → log line, exit 0,
   service starts on the current local code.
3. If `HEAD == origin/main` → log "Already up to date", exit 0.
4. Otherwise:
   - `git tag -f last_good_state <current HEAD>` — the rollback target.
   - `git pull origin main`. Failure → `git reset --hard last_good_state`,
     exit 1 (systemd retries in 5 s).
   - `pip install -r requirements.txt` (with `--trusted-host` for Pi 3).
     Failure → `git reset --hard last_good_state`, **reinstall the
     deps from the rolled-back tree** so the venv is consistent, exit 1.

Why rollback is two-stage: a successful `git pull` followed by a failed
`pip install` would leave you on new code with stale deps — likely
ImportErrors at import time. Rolling back the code *and* repointing the
venv to the previous tree's `requirements.txt` keeps the Pi runnable.

### Log

`/tmp/gpio-osc-updater.log` (timestamped). Lives only as long as the Pi
stays up — it's intentionally ephemeral; the `journal` is the durable
record.

### Common operations

```bash
# Force a check now (instead of waiting for the next boot):
sudo systemctl restart gpio-osc-<type>

# Pause auto-update for a show:
sudo systemctl stop gpio-osc-<type>
# … patch / pin / freeze the tree by hand …
sudo systemctl start gpio-osc-<type>
# (auto_update.sh will run on start. To skip it: edit the unit and
#  comment out ExecStartPre, then daemon-reload. Remember to revert.)
```

To genuinely disable the update step: edit
`/etc/systemd/system/gpio-osc-<type>.service`, comment out the
`ExecStartPre=` line, `sudo systemctl daemon-reload`. Re-running
`install.sh` will overwrite that change.

---

## Stage 6 — Optional `setup_webhooks.sh`

Path: `~/huyghe-bale/rpi-controller/setup_webhooks.sh`. **Run by hand**,
not by `install.sh`. Wires the Pi up to the [Monitory](https://monitory.club)
webhook service so `start` / `stop` / `crash` / `error` events from
`gpio_osc.py` get posted to a remote endpoint.

### Interactive prompts
1. **Super-admin API key** (hidden input).
2. **Base URL** — default `https://monitory.club`.
3. **Device ID** (the Monitory device id, **not** the `hardware_id`).
4. **Event types** — comma-separated, default `start,stop,crash,error`.
5. **Output path** — default `./webhooks.json`.

### Behaviour
- For each event type, POSTs to `<BASE_URL>/api/v1/admin/webhooks` with
  `{deviceId, eventType}`.
- `200/201` → captures the returned `webhookUrl`.
- `409` (already exists) → tries to extract the existing URL from the
  response body and reuses it. If that fails, warns and skips.
- `401` → aborts with "Unauthorized — check your API key."
- `404` → aborts with "Device not found."
- Any other code → warns and continues with the next event.

### Output

`webhooks.json` (default) — same path that `webhooks.py` reads on Pi
start-up. Schema:
```json
{
  "webhooks": [
    {"url": "...", "events": ["start"]},
    {"url": "...", "events": ["error"]}
  ]
}
```

Optional bearer token can be added by hand-editing the entries:
```json
{"url": "...", "token": "Bearer xyz", "events": ["error"]}
```
(see `rpi-controller/webhooks.py` for the worker that consumes this).

If `webhooks.json` is missing the runtime silently no-ops — the Pi keeps
working without any external observability.

---

## Persistent state on the Pi

What the install + runtime put on disk:

| Path | Owner | Purpose |
|---|---|---|
| `/etc/systemd/system/gpio-osc-<type>.service` | root | systemd unit, written by `install.sh` |
| `/etc/sudoers.d/gpio-osc-<type>` | root (`0440`) | password-less restart |
| `~pi/.config/gpio-osc/device.json` | `pi` | `{type, id}` + persisted trolley settings |
| `~pi/.config/gpio-osc/vents_prefs.json` | `pi` | vents-only persisted prefs (`max_temp_c`, fan caps, …) |
| `~pi/huyghe-bale/` | `pi` | git clone of the repo |
| `~pi/huyghe-bale/rpi-controller/venv/` | `pi` | Python venv with deps |
| `~pi/huyghe-bale/rpi-controller/webhooks.json` | `pi` | optional, from `setup_webhooks.sh` |
| `/tmp/gpio-osc-updater.log` | `pi` | auto-update log (ephemeral, cleared on reboot) |

`device.json` and `vents_prefs.json` both use **temp-file-then-rename** for
atomic writes, so a power cut mid-write can't corrupt them.

---

## Day-2 operational tasks

### Inspect a Pi's identity / health
```bash
curl http://<pi-ip>:9001/status | jq        # uptime, identity, git version
ssh pi@<host>.local cat ~/.config/gpio-osc/device.json
```

### Live logs
```bash
ssh pi@<host>.local journalctl -u gpio-osc-<type> -f
```

### Manual service control
```bash
sudo systemctl restart gpio-osc-<type>
sudo systemctl stop    gpio-osc-<type>
sudo systemctl start   gpio-osc-<type>
sudo systemctl status  gpio-osc-<type> --no-pager
```

### Force-update right now
```bash
sudo systemctl restart gpio-osc-<type>
# auto_update.sh runs as ExecStartPre, so a restart pulls newer code.
# Watch the journal:
journalctl -u gpio-osc-<type> -f
# … or the updater log:
tail -f /tmp/gpio-osc-updater.log
```

### Switch personality (vents → trolley or vice versa)
```bash
sudo bash ~/huyghe-bale/rpi-controller/install.sh --type=trolley
```
The installer notices the type changed, regenerates `device.json`
(**new `hardware_id`**), disables the old systemd unit, enables the new
one. The admin treats the Pi as a new device — relabel its friendly name.

### Force-regenerate the hardware id (without changing personality)
```bash
sudo rm ~/.config/gpio-osc/device.json
sudo systemctl restart gpio-osc-<type>      # next boot regenerates it
```
Note: this is rarely what you want. If you're trying to "reset" a Pi for
another show, just relabel it in the admin — the id is meant to be stable.

### SSH deploy-key for private-repo auto-update

If the GitHub repo is private, `git fetch` in `auto_update.sh` will fail
silently (offline-safe → service still starts on stale code, but no
updates land). One-time setup per Pi:

```bash
ssh-keygen -t ed25519 -C "rpi-huyghe-bale"
cat ~/.ssh/id_ed25519.pub
# → paste into GitHub → repo Settings → Deploy Keys, "Read access" only.
cd ~/huyghe-bale
git remote set-url origin git@github.com:martial/huyghe-bale.git
ssh -T git@github.com   # accept the host key
```
Re-run `sudo systemctl restart gpio-osc-<type>` to verify the fetch works.

### Replace a dead Pi

1. Image a fresh SD with the **same hostname** as the dead one (e.g. `v3`).
2. Slot, boot, sanity-check `ping v3.local`.
3. `./docs/sd-protocol/deploy_pis.sh v3` from the Mac.
4. The new Pi's `hardware_id` will be different — the admin sees a new
   device. Relabel its friendly name to match the old one, repoint the
   timeline that referenced the dead Pi.

---

## Troubleshooting

### `gpio-osc-<type>` keeps restarting (5 s loop)
First, get logs:
```bash
journalctl -u gpio-osc-<type> -n 200 --no-pager
```
Common causes:
- **Pi 5 + `RPi.GPIO` ImportError** — installer was run before the Pi-model
  branching landed. Re-run `install.sh` so it picks `rpi-lgpio` instead.
- **GPIO already in use** — the legacy unified `gpio-osc.service` wasn't
  cleaned up. Check `systemctl list-unit-files | grep gpio-osc`; the
  installer disables the old one but a manual `enable` later would
  resurrect it.
- **ImportError after auto-update rollback** — rare; means the rolled-back
  `requirements.txt` doesn't match what's on disk in the venv. Manually:
  ```bash
  cd ~/huyghe-bale/rpi-controller
  ./venv/bin/python -m pip install -r requirements.txt
  sudo systemctl restart gpio-osc-<type>
  ```

### `auto_update.sh` rolled back
Check `/tmp/gpio-osc-updater.log` for the failure line. Recover:
```bash
cd ~/huyghe-bale
git status                 # confirm where you are
git tag -l last_good_state # exists if a rollback ran
# Investigate the bad commit on origin/main, push a fix, then:
sudo systemctl restart gpio-osc-<type>
```
The `last_good_state` tag is force-overwritten on every successful update,
so it always points at the most recent known-good `HEAD`.

### Pi unreachable on `<host>.local` from the Mac
- `avahi-daemon` not running on the Pi: SSH via IP (find it on the switch
  / router), then `sudo systemctl status avahi-daemon`.
- Mac side: `dscacheutil -flushcache` and `sudo killall -HUP mDNSResponder`.
- Last resort: hard-code IPs in your switch's DHCP reservations and stop
  relying on mDNS (more reliable on event networks).

### Device shows offline in the admin but the Pi service is healthy
The admin only marks a device "online" once it has received a `/sys/pong`
within 6 s of pinging. And the Pi only **starts broadcasting**
`/<type>/status` after it has received at least one `/sys/ping`. So:

1. Confirm the admin sees the device in `Devices` (`POST /api/v1/devices`
   created from a manual entry or auto-discovered via the bridge).
2. Confirm the IP saved on the device record matches the Pi's actual IP.
3. From the admin host:
   ```bash
   nc -uvz <pi-ip> 9000      # OSC port reachable?
   ```
4. SSH to the Pi and `tcpdump -i eth0 udp port 9000` while the admin
   polls — should see `/sys/ping` arrive.

### Wrong personality installed (e.g. installed as `vents` but it's a `trolley` rig)
```bash
sudo bash ~/huyghe-bale/rpi-controller/install.sh --type=trolley
```
The installer detects the mismatch, regenerates the identity, swaps the
systemd unit. Hardware id changes; relabel in admin.

---

## Cross-references

- **[RPI_CONTROLLERS.md](RPI_CONTROLLERS.md)** — architectural overview
  of the rpi-controller (boot sequence, OSC discovery handshake, status
  broadcaster, repo layout). This `INSTALL.md` is the *operational*
  counterpart.
- **[VENTS.md](VENTS.md)** / **[TROLLEY.md](TROLLEY.md)** —
  per-personality reference: OSC contract, persisted settings, state
  machine, tests.
- **[`docs/sd-protocol/PROTOCOLE_SD_HUYGHE_BALE.md`](sd-protocol/PROTOCOLE_SD_HUYGHE_BALE.md)** —
  SD-card flashing protocol (French), naming convention, materials list,
  Imager OS_CUSTOMIZATION block.
- **[`docs/sd-protocol/INVENTAIRE_PI.md`](sd-protocol/INVENTAIRE_PI.md)** —
  fleet inventory, filled in as Pis come online.
- **[`docs/sd-protocol/deploy_pis.sh`](sd-protocol/deploy_pis.sh)** —
  mass-flash orchestrator (Mac → 9 Pis over SSH).
