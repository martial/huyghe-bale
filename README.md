# Pierre Huyghe – Bâle: Fan Controller

GPIO timeline controller for art installation. A web interface to design automation timelines (PWM curves over time) for two output channels (A/B), streamed via OSC to Raspberry Pi units driving L298N motor controllers.

## Architecture

```
┌─────────────────────┐    OSC/UDP     ┌──────────────────┐
│   Admin Interface   │ ──────────────▶│  Raspberry Pi(s) │
│  (Flask + Vue 3)    │   /gpio/a 0–1  │  GPIO PWM → L298N│
│  localhost:5001     │   /gpio/b 0–1  │  → Fans          │
└─────────────────────┘                └──────────────────┘
```

- **Backend:** Flask API, JSON storage, interpolation & OSC playback engine.
- **Frontend:** Vue 3, TypeScript, Tailwind CSS v4, Pinia.
- **Node (RPi):** Python OSC listener to Hardware PWM (GPIO 12/13).

## Hardware Node Setup (Raspberry Pi)

👉 **[See detailed RPi documentation (OSC, Wiring, Webhooks)](docs/RPI_OSC.md)**

```bash
# Push to Pi and run installer
scp -r rpi-controller/ pi@<RPI_IP>:~
ssh pi@<RPI_IP> "sudo bash ~/rpi-controller/install.sh"
```
*Installs and auto-starts the `gpio-osc` systemd service.*

## Local Development

**Prerequisites:** Python 3.10+, Node.js 18+, macOS.

Use the helper script (opens iTerm2 with both servers):
```bash
./start_dev.sh
```

**Manual start:**
- **Backend (:5001):** `cd admin/backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m flask --app app run --port 5001 --debug`
- **Frontend (:5173):** `cd admin/frontend && npm install && npm run dev`
- **Tests:** `cd admin/backend && .venv/bin/pytest tests/ -v`

## Standalone Mac Build

Bundles Flask and Vue into a native macOS app using `PyInstaller` and `pywebview`.

```bash
bash admin/build_mac_app.sh
```
- **Output:** `admin/backend/dist/PIERRE HUYGHE BALE.app`
- **Storage:** Saved locally to `~/Library/Application Support/PierreHuygheBale/data/`
- *Note: App is unsigned. Users must Right-click → Open on first launch.*

## Core Concepts

- **Timelines:** Two lanes (A/B) mapping values (0.0–1.0) over time with 8 curve interpolation types (linear, step, bezier, sine, etc.).
- **Orchestrations:** Sequences of timelines with per-step delays and specific device targeting.
- **Playback Engine:** Evaluates curves at 1-120 Hz (configurable, default 30 Hz) and streams OSC.
- **Data Storage:** Flat JSON files inside `admin/backend/data/`.