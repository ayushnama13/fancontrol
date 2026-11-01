# Linux Fan Speed Controller (`fancontrol.py`)

A lightweight, standard-library-only Linux fan speed controller and daemon for ASUS and compatible hardware via sysfs.

## 1. Overview & Purpose

Many Linux laptops—particularly ASUS models and AMD Ryzen systems—lack dynamic fan curve customization or robust kernel-level fan management. This can result in excessive thermal throttling, high noise levels under light loads, or insufficient cooling during intensive workloads. 

`fancontrol.py` solves this by interfacing directly with the Linux kernel's `hwmon` subsystem to monitor CPU temperatures, report fan speeds, and actively manage fan PWM duty cycles or hardware modes using configurable curves and temperature thresholds.

## 2. Features

- **Dynamic Sensor Discovery**: Automatically scans `/sys/class/hwmon/hwmon*` to detect CPU temperature sensors (`k10temp` or any valid `temp1_input`) and fan controllers (`asus` or any `pwm1_enable` / `fan1_input`) without hardcoded hwmon index paths.
- **Hardware-Adaptive Control**:
  - Supports direct PWM percentage control (`0-100%` mapped to `0-255` `pwm1` values) with linear interpolation across a default fan curve (`DEFAULT_CURVE`).
  - Supports hardware limited to mode-based control (`pwm1_enable`: `0` for full speed, `2` for automatic) using temperature hysteresis.
- **CLI Subcommands**:
  - `status`: Inspect current CPU temperature, fan RPM, PWM enable mode, and PWM duty cycle.
  - `set`: Override fan operation (`full`, `auto`, or a percentage from `0` to `100`).
  - `daemon`: Run continuous temperature monitoring and fan adjustment loop.
- **Built-in Safety**:
  - Automatic restoration of fan `auto` mode (`pwm1_enable = 2`) on exit (handles normal termination, `SIGINT`, and `SIGTERM`).
  - Fail-safe full-speed fallback if temperature sensor reads fail.
  - Root privilege validation (`geteuid() == 0`) before executing any sysfs write operations.

## 3. How It Works / Architecture

### Data Flow
1. **Sensor Discovery**: On startup, `fancontrol.py` searches `/sys/class/hwmon/hwmon*` for device names and required attributes (`temp1_input`, `pwm1_enable`, `fan1_input`, `pwm1`).
2. **Data Acquisition**: Periodically reads temperature (converted from millidegrees Celsius) and fan RPM.
3. **Control Evaluation**:
   - If `pwm1` is supported, temperature is evaluated against `DEFAULT_CURVE` to calculate the target PWM duty cycle (`0-255`).
   - If `pwm1` is not supported, temperature is evaluated against `--high` and `--low` thresholds with hysteresis (`full` vs `auto`).
4. **Sysfs Execution**: Writes integer values (`0`, `1`, `2`, or `0-255`) to kernel sysfs attributes (`pwm1_enable`, `pwm1`).
5. **Safety Cleanup**: Signal handlers and a `finally` block guarantee that the fan mode is restored to `2` (auto) upon daemon termination.

### Architecture Diagram

```
+-------------------------------------------------------------+
|                        fancontrol.py                        |
+-------------------------------------------------------------+
         |                                           |
         v (Read)                                    v (Write / Sysfs)
+-------------------+                      +-------------------+
| /sys/class/hwmon/ |                      | /sys/class/hwmon/ |
|  - temp1_input    |                      |  - pwm1_enable    |
|  - fan1_input     |                      |  - pwm1           |
+-------------------+                      +-------------------+
         |                                           |
         v                                           v
   [CPU Temp & RPM]                          [Fan Controller / PWM]
```

## 4. Project Structure

```text
fancontrol/
├── fancontrol.py      # Main CLI script, daemon, sensor discovery, and control logic
├── fancontrol.service # Systemd service unit configuration for running the daemon
├── .gitignore         # Git ignore rules for Python artifacts and caches
└── README.md          # Project documentation
```

## 5. Tech Stack

- **Language**: Python 3.10 (Standard Library only: `argparse`, `os`, `signal`, `sys`, `time`, `pathlib`)
- **Kernel Interface**: Linux `sysfs` (`/sys/class/hwmon`)
- **Process Management**: Systemd

## 6. Requirements

- **Operating System**: Linux kernel with `hwmon` support enabled.
- **Python**: Python 3.10 or higher.
- **Hardware**: ASUS laptop or compatible hardware exposing temperature sensors and fan PWM controls.
- **Privileges**: Root (`sudo`) privileges required for sysfs write operations (`set` and `daemon` modes). The `status` command can be executed without root privileges.

## 7. Installation & Setup

1. **Copy script to `/opt/fancontrol`**:
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

## 8. Configuration

Configuration is managed via command-line arguments and script constants (no environment variables are used):

| Flag / Constant | Description | Default |
| --------------- | ----------- | ------- |
| `--interval` (daemon) | Daemon polling interval in seconds | `2.0` |
| `--high` | High temperature threshold in °C for full speed (threshold mode) | `75.0` |
| `--low` | Low temperature threshold in °C for auto mode (threshold mode) | `65.0` |
| `--dry-run` | Log control decisions without writing to sysfs | `False` |
| `DEFAULT_CURVE` | Temperature-to-speed curve mapping (`temp_C`, `percent`) | `[(50, 30), (60, 50), (70, 75), (80, 100)]` |

## 9. Usage

```bash
# Check fan status (unprivileged)
python3 fancontrol.py status

# Set fan to full speed (requires root)
sudo python3 fancontrol.py set full

# Set fan to auto mode (requires root)
sudo python3 fancontrol.py set auto

# Set fan speed manually to 60% (requires pwm1 support)
sudo python3 fancontrol.py set 60

# Run daemon in dry-run mode (logs actions without modifying sysfs)
python3 fancontrol.py daemon --dry-run

# Run daemon normally with custom thresholds (requires root)
sudo python3 fancontrol.py daemon --interval 2.0 --high 75.0 --low 65.0
```

### Expected Output (`status` command)
```text
Fan Control Status:
  CPU Temperature: 45.2°C
  Fan RPM:         2400
  PWM Enable Mode: auto (2)
  PWM Speed:       N/A (no pwm1 file, hardware uses full/auto modes)
```

## 10. Testing

*Note*: There is no automated test suite included in this project. Verification is performed manually via `python3 fancontrol.py status` and `python3 fancontrol.py daemon --dry-run`.

## 11. Troubleshooting & Known Limitations

- **Permission Denied / Root Required**: Writing to sysfs (`pwm1_enable`, `pwm1`) requires root privileges. Ensure commands modifying fan speed are run with `sudo`.
- **Sensor Not Found**: If temperature sensors are not detected, verify that required kernel modules (such as `k10temp` or `coretemp`) are loaded (`lsmod`).
- **Binary Hardware Modes**: Some laptop firmwares do not expose a variable `pwm1` duty cycle register, restricting fan control to discrete modes (`pwm1_enable` = `0` for full or `2` for auto).

## 12. Safety, Rate Limits & Privacy

- **Thermal Safety**: The daemon includes automatic exception recovery that forces fans to maximum speed (`pwm1_enable = 0` or `pwm1 = 255`) if temperature sensor reads fail.
- **Graceful Shutdown**: Signal handlers (`SIGINT`, `SIGTERM`) ensure that fans are returned to automatic mode upon exit.
- **Privacy & Telemetry**: The application is 100% local, standalone, and transmits zero telemetry or data.
