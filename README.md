# Linux Fan Speed Controller (`fancontrol.py`)

A lightweight, stdlib-only Python 3.10 fan speed controller designed for ASUS laptops and other Linux hardware exposing `hwmon` temperature and fan sensors.

## Features
- **Dynamic Sensor Discovery**: Automatically detects `k10temp` (or temperature sensors) and `asus` (or fan controllers) without hardcoding `hwmonN` numbers.
- **Hardware-Adaptive Control**:
  - Supports hardware with direct PWM control (`pwm1`).
  - Supports ASUS laptops where only `pwm1_enable` (0=full speed, 1=manual, 2=auto) is available using robust temperature hysteresis.
- **Subcommands**:
  - `status`: Display CPU temperature, fan RPM, and current PWM mode.
  - `set full|auto`: Set fan mode to full speed (0) or automatic (2).
  - `set <0-100>`: Set manual speed percentage (if `pwm1` file is supported).
  - `daemon`: Run continuous fan control loop with temperature thresholds / curves.
- **Safety**:
  - Automatically restores fan to `auto` mode (2) on exit (`SIGINT`, `SIGTERM`, or normal exit).
  - Switches fan to full speed if temperature sensor read fails.
  - Enforces root checks (`sudo`) before any sysfs write operations.

## Usage

```bash
# Check status (works without root)
python3 fancontrol.py status

# Set fan to full speed (requires sudo)
sudo python3 fancontrol.py set full

# Set fan to auto mode (requires sudo)
sudo python3 fancontrol.py set auto

# Run daemon in dry-run mode
python3 fancontrol.py daemon --dry-run

# Run daemon normally (requires root)
sudo python3 fancontrol.py daemon --interval 2 --high 75 --low 65
```

## Installation & Systemd Setup

1. **Copy files to `/opt/fancontrol`**:
   ```bash
   sudo mkdir -p /opt/fancontrol
   sudo cp fancontrol.py /opt/fancontrol/
   sudo chmod +x /opt/fancontrol/fancontrol.py
   ```

2. **Install systemd service**:
   ```bash
   sudo cp fancontrol.service /etc/systemd/system/fancontrol.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now fancontrol.service
   ```

3. **Check service status**:
   ```bash
   sudo systemctl status fancontrol.service
   ```
