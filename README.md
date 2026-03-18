# PIERRE HUYGHE BALE

GPIO timeline controller for art installation. Web admin to design PWM automation curves (two channels A/B), played back via OSC to Raspberry Pis driving L298N motor controllers + fans.

## Architecture

```
┌─────────────────────┐    OSC/UDP     ┌──────────────────┐
│   Admin Interface   │ ──────────────▶│  Raspberry Pi(s) │
│  (Flask + React)    │   /gpio/a 0–1  │  GPIO PWM → L298N│
│  localhost:5001     │   /gpio/b 0–1  │  → fans/motors   │
└─────────────────────┘                └──────────────────┘
```

- **Backend** — Flask API, JSON storage, interpolation engine, OSC playback
- **Frontend** — React + TypeScript + Tailwind CSS v4 + Zustand
- **RPi Controller** — Python OSC listener → hardware PWM on GPIO 12/13

## Dev Setup

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

Backend runs on `:5001`, Vite dev server on `:5173` with proxy to Flask.

There's also `./start_dev.sh` which opens both in iTerm2 tabs.

### Tests

```bash
cd admin/backend
.venv/bin/pytest tests/ -v
```

### Build

```bash
# Frontend only
cd admin/frontend && npm run build

# Mac .app (PyInstaller — bundles Flask + React into native macOS window)
cd admin/backend
../.venv/bin/pyinstaller "PIERRE HUYGHE BALE.spec"
# Output: admin/backend/dist/PIERRE HUYGHE BALE.app
```

When running as `.app`, data is stored in `~/Library/Application Support/PierreHuygheBale/data/`.

The app is unsigned — recipients must right-click → Open on first launch.

## RPi Setup

```bash
git clone https://github.com/martial/huyghe-bale.git
cd huyghe-bale
sudo bash rpi-controller/install.sh
```

Installs as systemd service `gpio-osc` at `/opt/gpio-osc/`. Auto-starts on boot. Includes auto-update via git pull on service restart.

```bash
# Check status
sudo systemctl status gpio-osc

# Live logs
sudo journalctl -u gpio-osc -f

# Restart / stop
sudo systemctl restart gpio-osc
sudo systemctl stop gpio-osc
```

### Hardware Pins (BCM)

| Pin | Function |
|-----|----------|
| 12  | PWM0 — Enable A |
| 13  | PWM1 — Enable B |
| 5   | IN1 (direction) |
| 6   | IN2 (direction) |
| 16  | IN3 (direction) |
| 20  | IN4 (direction) |

## API

All endpoints under `/api/v1/`:

| Resource | Endpoints |
|----------|-----------|
| Timelines | `GET/POST /timelines`, `GET/PUT/DELETE /timelines/:id`, `POST /timelines/:id/duplicate` |
| Devices | `GET/POST /devices`, `GET/PUT/DELETE /devices/:id`, `POST /devices/:id/ping`, `POST /devices/scan`, `GET /devices/status` (SSE) |
| Orchestrations | `GET/POST /orchestrations`, `GET/PUT/DELETE /orchestrations/:id` |
| Playback | `POST /playback/start`, `POST /playback/stop`, `GET /playback/status` |
| Export | `GET /export/timeline/:id`, `GET /export/orchestration/:id`, `POST /import/timeline` |
| Settings | `GET/PUT /settings` |

## Concepts

**Timelines** — Two lanes (A/B) with control points. Each point has a value (0–1), a time, and a curve type for interpolation arriving at it. 8 types: linear, step, ease-in, ease-out, ease-in-out, sine, exponential, bezier.

**Orchestrations** — Sequence of timelines with per-step device targeting and delays. Optional looping.

**Playback** — Evaluates curves at configurable rate (default 30 Hz), sends OSC to targeted devices.

## Data

JSON files in `admin/backend/data/`:

```
data/
├── timelines/      # tl_*.json
├── devices/        # dev_*.json
├── orchestrations/ # orch_*.json
└── settings.json
```

## Stack

- Flask 3, python-osc, pytest
- React 19, Zustand, Tailwind CSS 4, TypeScript 5.9, Vite 7
- rpi-lgpio (drop-in RPi.GPIO replacement for Pi 3/4/5), systemd
