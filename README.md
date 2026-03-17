# PIERRE HUYGHE BALE

GPIO timeline controller for art installation. A web admin interface to design automation timelines (PWM curves over time) for two output channels (A/B), played back via OSC to Raspberry Pis driving L298N motor controllers and fans.

## Architecture

```
┌─────────────────────┐    OSC/UDP     ┌──────────────────┐
│   Admin Interface   │ ──────────────▶│  Raspberry Pi(s) │
│  (Flask + Vue 3)    │   /gpio/a 0–1  │  GPIO PWM → L298N│
│  localhost:5001     │   /gpio/b 0–1  │  → fans/motors   │
└─────────────────────┘                └──────────────────┘
```

- **Backend** — Flask API, JSON file storage, interpolation engine, playback engine (OSC sender)
- **Frontend** — Vue 3 + TypeScript + Tailwind CSS v4 + Pinia
- **RPi Controller** — Python OSC listener → hardware PWM on GPIO 12/13

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- macOS (dev scripts use iTerm2)

### Development

```bash
# Backend
cd admin/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m flask --app app run --port 5001 --debug

# Frontend (separate terminal)
cd admin/frontend
npm install
npm run dev
```

Or use the helper script (opens iTerm2 with both):

```bash
./start_dev.sh
```

Backend runs on `:5001`, Vite dev server on `:5173` with proxy to Flask.

### Tests

```bash
cd admin/backend
.venv/bin/pytest tests/ -v
```

### Build & Deploy

```bash
# Build frontend only
cd admin/frontend && npm run build

# Build Mac .app (includes frontend build)
bash admin/build_mac_app.sh
```

### Mac App

The standalone Mac app bundles Flask + Vue into a native macOS window using **PyInstaller** and **pywebview**. Flask runs on `127.0.0.1:5001` in a background thread; pywebview opens a native WebKit window pointing at it.

**Prerequisites:** Python venv with `requirements.txt` installed, Node.js 18+.

The build script (`admin/build_mac_app.sh`) builds the Vue frontend, installs `pywebview` and `pyinstaller` into the venv, then runs PyInstaller to produce:

```
admin/backend/dist/PIERRE HUYGHE BALE.app
```

**Data storage (bundled mode):** When running as a `.app`, timeline/device/orchestration data is stored in:

```
~/Library/Application Support/PierreHuygheBale/data/
```

**Distribution:** Zip the `.app` and send it. Recipients must right-click → Open on first launch since the app is unsigned.

```bash
cd admin/backend
zip -r "PIERRE HUYGHE BALE.zip" "dist/PIERRE HUYGHE BALE.app"
```

## RPi Setup

👉 **[Voir la Documentation détaillée du Raspberry Pi (OSC, Câblage, Webhooks)](docs/RPI_OSC.md)**

```bash
# Copy controller to RPi
scp -r rpi-controller/ pi@<RPI_IP>:~

# SSH in and install
ssh pi@<RPI_IP>
sudo bash ~/rpi-controller/install.sh
```

Installs as systemd service `gpio-osc` at `/opt/gpio-osc/`, auto-starts on boot.

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
| Devices | `GET/POST /devices`, `GET/PUT/DELETE /devices/:id`, `POST /devices/:id/ping`, `POST /devices/scan` |
| Orchestrations | `GET/POST /orchestrations`, `GET/PUT/DELETE /orchestrations/:id` |
| Playback | `POST /playback/start`, `POST /playback/stop`, `GET /playback/status` |
| Export | `GET /export/timeline/:id`, `GET /export/orchestration/:id`, `POST /import/timeline` |
| Settings | `GET/PUT /settings` |

## Key Concepts

**Timelines** have two lanes (A/B), each with control points. Points define value (0–1) at a time, with 8 interpolation curve types: linear, step, ease-in, ease-out, ease-in-out, sine, exponential, bezier.

**Orchestrations** sequence multiple timelines with per-step device targeting and delays. Optional looping.

**Playback** evaluates curves at configurable frequency (default 30 Hz) and sends OSC messages to all targeted devices.

**Settings** configure the OSC send frequency (1–120 Hz).

## Data Storage

JSON files in `admin/backend/data/`:

```
data/
├── timelines/     # tl_*.json
├── devices/       # dev_*.json
├── orchestrations/ # orch_*.json
└── settings.json
```

## Stack

- Flask 3, Python-OSC, Pytest
- Vue 3.5, Vue Router 5, Pinia 3, Tailwind CSS 4, TypeScript 5.9, Vite 7
- RPi.GPIO, systemd
