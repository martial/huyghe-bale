# PIERRE HUYGHE BALE

[![Build App](https://github.com/martial/huyghe-bale/actions/workflows/build.yml/badge.svg)](https://github.com/martial/huyghe-bale/actions/workflows/build.yml)

Show-controller for an art installation. A web admin designs automation timelines and plays them back over OSC to a fleet of Raspberry Pis. Each Pi runs one of two personalities: **vents** (Peltier-cell thermal stacks + PWM fans + DS18B20 probes, with a bang-bang regulator) or **trolley** (stepper-driven cart on a rail with a homing limit switch).

## Architecture

```
                                   ┌──────────────────┐  /vents/* /trolley/*
   external OSC source         ┌──▶│  Raspberry Pi    │◀──── (UDP 9000)
   (Max, TouchDesigner, …)     │   │  vents OR trolley│
       │ UDP 9002              │   │  status broadcast│──── /vents/status,
       ▼                       │   └──────────────────┘     /trolley/status
   ┌──────────────────┐  fanout │                            (UDP 9001)
   │   OSC Bridge     │─────────┤
   └──────────────────┘         │
              ▲                  │
              │                  ▼
   ┌─────────────────────────────────────────┐
   │   Admin (Flask + React)                  │
   │   localhost:5001 (bundled .app /  .exe)  │
   └─────────────────────────────────────────┘
```

- **Backend** — Flask, JSON file storage, interpolation engine, OSC sender + receiver, OSC bridge.
- **Frontend** — React 19 + TypeScript + Tailwind 4 + Zustand.
- **RPi controller** — single Python codebase; personality is selected at install time (`--type=vents|trolley`) and lives at `~/.config/gpio-osc/device.json`.
- **OSC Bridge** — optional UDP listener on the admin (port 9002) that fans incoming messages out to devices. Supports per-device targeting via `/to/<name|id|ip|hwid>/<real-address>`.

## Installing on a Raspberry Pi

One-liner pulls and runs the installer from GCS, sets up venv, writes a systemd unit, generates an identity, and starts the service:

```bash
# vents (Peltier + fans)
curl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \
  | sudo bash -s -- --type=vents

# trolley (stepper + limit switch)
curl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \
  | sudo bash -s -- --type=trolley
```

Service: `gpio-osc-vents` or `gpio-osc-trolley`. Inspect with `journalctl -u gpio-osc-<type> -f`.

Re-running the installer is idempotent — it `git pull`s and re-installs. The Devices page in the admin can also push updates remotely.

### Hardware pins (BCM)

**Vents** (Peltier cells + PWM fans + 4 tacho inputs + 1-wire DS18B20):

| Pin | Function |
|-----|----------|
| 26  | Peltier cell 1 |
| 25  | Peltier cell 2 |
| 24  | Peltier cell 3 |
| 20  | Fan 1 PWM (cold side, 1 kHz) |
| 18  | Fan 2 PWM (hot side, 1 kHz) |
| 27 / 17 | Fan 1 tachos A / B |
| 23 / 22 | Fan 2 tachos A / B |
| 4 (1-wire) | DS18B20 temperature probes |

**Trolley** (stepper driver + limit switch):

| Pin | Function |
|-----|----------|
| 25  | DIR |
| 24  | PUL |
| 23  | ENA (active LOW) |
| 21  | Limit switch (PUD\_DOWN, HIGH at limit) |

## Dev setup

Requires Python 3.10+ and Node.js 18+.

```bash
# Backend
cd admin/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py

# Frontend (separate terminal)
cd admin/frontend
npm install
npm run dev
```

Backend listens on `:5001`, OSC receiver on `:9001`, optional bridge on `:9002`. Vite dev server runs on `:5173` and proxies `/api` to Flask. `./start_dev.sh` opens both in iTerm2 tabs.

### Tests

```bash
# Backend
cd admin/backend && .venv/bin/pytest tests/ -v

# Pi controller
cd rpi-controller && python3 -m pytest tests/ -v

# Frontend type check
cd admin/frontend && npx tsc --noEmit
```

### Build & release

```bash
# Local build of the macOS .app — signs + notarizes via Developer ID
./compile_app.sh

# Full local release: tag, build, GitHub release, upload DMG + install.sh to GCS
./deploy.sh                # patch bump
./deploy.sh v2.0.0         # explicit

# CI release: tags, GitHub Actions builds mac + Windows, attaches both to a release
./release.sh
```

CI also runs on pushes to `main` (see [`.github/workflows/build.yml`](.github/workflows/build.yml)).

When running as a bundle, persistent data lives at:

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/PierreHuygheBale/` |
| Windows | `%APPDATA%\PierreHuygheBale\` |

with `data/` (timelines, devices, orchestrations, settings, trolley\_timelines) and `logs/backend.log` (5 × 5 MB rotating). The launcher pops a native error window when Flask fails to bind so a hung port (5001) is visible instead of a blank webview.

## Concepts

**Timelines** — Two lanes (A → fan 1, B → fan 2) of control points. Each point has a value (0–1), a time, and a curve type for interpolation arriving at it. Eight curves: linear, step, ease-in, ease-out, ease-in-out, sine, exponential, bezier.

**Trolley timelines** — Sparse event list (`enable`, `dir`, `speed`, `position`, `step`, `home`, `stop`) fired at scheduled times. Played back as bangs, not interpolated.

**Orchestrations** — Sequence of timelines with per-step device targeting and delays. Optional looping.

**Playback** — Evaluates curves at a configurable rate (default 30 Hz) and sends OSC to the chosen devices. Crashes in a playback thread surface in the admin's status banner instead of silently leaving the UI lying about a stopped show.

**Vents safety** — Each Pi tracks `max_temp` (persisted in `~/.config/gpio-osc/vents_prefs.json`). When the average of both probes crosses it, the controller flips to `over_temp`: Peltiers forced off, auto leaves fan PWM untouched. The admin shows a red banner and lists every device currently in over-temp. Default editable in Settings.

**OSC Bridge** — Listens on UDP 9002 and rebroadcasts to devices. Three routing modes:
* `type-match` — `/vents/*` to vents, `/trolley/*` to trolley, `/sys/*` to all.
* `passthrough` — every message to every device.
* `none` — log-only tap.

Always supported regardless of mode: `/to/<identifier>/<real-address>` targets a single device by id, name, IP, or hardware\_id (e.g. `/to/circadian.home/vents/fan/1 0.5`).

**Protocol Quick Test** — The Docs page (`/docs`) is a live reference: every documented OSC address and HTTP endpoint has a "Send test" button that fires through the admin's protocol-test API to the chosen device.

## API

All endpoints under `/api/v1/`:

| Resource | Endpoints |
|----------|-----------|
| Timelines | `GET/POST /timelines`, `GET/PUT/DELETE /timelines/:id`, `POST /timelines/:id/duplicate` |
| Trolley timelines | `GET/POST /trolley-timelines`, `GET/PUT/DELETE /trolley-timelines/:id` |
| Devices | `GET/POST /devices`, `GET/PUT/DELETE /devices/:id`, `POST /devices/scan` (SSE), `GET /devices/status` (SSE — statuses, versions, last-seen), `POST /devices/:id/update` |
| Orchestrations | `GET/POST /orchestrations`, `GET/PUT/DELETE /orchestrations/:id` |
| Playback | `POST /playback/start`, `POST /playback/stop`, `POST /playback/pause/resume`, `POST /playback/seek`, `GET /playback/status` |
| Vents control | `GET /vents-control/:id/status`, `POST /vents-control/:id/peltier|fan|mode|target|max_temp` |
| Trolley control | `GET /trolley-control/:id/status`, `POST /trolley-control/:id/enable|dir|speed|step|stop|home|position` |
| Bridge | `GET /bridge/state`, `GET /bridge/stream` (SSE), `POST /bridge/clear` |
| Protocol test | `POST /protocol-test/{osc,http,bridge}` (powers Docs Quick Test) |
| Export / Import | `GET /export/{timeline\|orchestration}/:id`, `POST /import/timeline` |
| Settings | `GET/PUT /settings` |
| Health | `GET /health` — `osc_receiver`, `bridge`, `playback`, `vents_over_temp`, `log_path` |

## Data

JSON files. Atomic writes (write-to-temp + `os.replace`); a corrupt file on boot is quarantined to `*.corrupted` rather than crashing startup.

Dev: `admin/backend/data/`. Bundled: see "Build & release" above.

```
data/
├── timelines/         # tl_*.json
├── trolley_timelines/ # trtl_*.json
├── devices/           # dev_*.json
├── orchestrations/    # orch_*.json
└── settings.json
```

## Stack

- Flask 3, python-osc, pytest
- React 19, Zustand, Tailwind CSS 4, TypeScript 5.9, Vite 7
- pywebview (bundled native shell), PyInstaller (sign + notarize via `xcrun notarytool`)
- rpi-lgpio (drop-in `RPi.GPIO` replacement for Pi 5), systemd
