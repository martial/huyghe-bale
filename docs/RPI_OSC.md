# Raspberry Pi Controller (OSC to GPIO)

The Raspberry Pi controller (`rpi-controller`) continuously listens for OSC network messages sent by the admin interface and translates them into electrical signals (PWM).

## 1. OSC Protocol

The embedded Python script runs an OSC UDP server with the following specifications:

- **Listening Port:** `9000` (configurable in `config.py`)
- **Supported Addresses:**
  - `/gpio/a` : Controls Channel A
  - `/gpio/b` : Controls Channel B
- **Expected Values:** A floating point number (`float`) between `0.0` and `1.0`.
  - `0.0` = Full stop (0% speed)
  - `1.0` = Maximum speed (100%)

*(Note: Any value outside the 0.0 - 1.0 range is automatically clamped by the script).*

## 2. Installation and Startup

Deployment on the Raspberry Pi is fully automated using the `install.sh` script.

### Prerequisites on the Raspberry Pi:
- Raspberry Pi OS installed
- SSH or terminal access
- Working network connection

### Procedure:
1. Copy the `rpi-controller` folder to your Raspberry Pi.
2. Connect via SSH and run the installer:
   ```bash
   sudo bash install.sh
   ```

### What does the installation script do?
1. Creates a dedicated folder at `/opt/gpio-osc/`.
2. Initializes a Python virtual environment (`venv`) and installs dependencies.
3. Creates and activates a **systemd** service named `gpio-osc.service`.

Thanks to `systemd`, the OSC controller automatically starts as soon as the Raspberry Pi boots up and automatically restarts if it crashes.

### Useful Commands (on the Raspberry Pi)
- Check service status: `systemctl status gpio-osc`
- Read real-time logs: `journalctl -u gpio-osc -f`
- Restart the service manually: `sudo systemctl restart gpio-osc`
- Stop the service: `sudo systemctl stop gpio-osc`
## Auto-Update System

The `gpio-osc.service` includes an automatic update mechanism (`auto_update.sh`) that runs on every boot or service restart.

**Important:** For the auto-update to work, the Raspberry Pi must be able to authenticate with GitHub silently. If the repository is private or requires authentication, you must:

1. Generate an SSH key on the Pi:
   ```bash
   ssh-keygen -t ed25519 -C "rpi-huyghe-bale"
   cat ~/.ssh/id_ed25519.pub
   ```
2. Add this public key to your GitHub repository as a **Deploy Key** (Settings > Deploy Keys) with *Read access*.
3. Change the git remote to use SSH instead of HTTPS:
   ```bash
   cd ~/rpi-controller
   git remote set-url origin git@github.com:martial/huyghe-bale.git
   ```

If the Pi cannot connect to GitHub (no Wi-Fi or no SSH keys), it will simply log an offline warning and start normally with the current local code.
