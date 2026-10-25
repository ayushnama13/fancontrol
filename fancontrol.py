#!/usr/bin/env python3
"""
Linux fan speed controller for ASUS and compatible laptops (stdlib only).
"""

import argparse
import os
import signal
import sys
import time
from pathlib import Path

# Default curve points: (temp_C, percent)
DEFAULT_CURVE = [(50, 30), (60, 50), (70, 75), (80, 100)]


def find_hwmon(target_name=None, required_file=None):
    hwmon_dir = Path("/sys/class/hwmon")
    if not hwmon_dir.exists():
        return None

    candidates = []
    for d in hwmon_dir.glob("hwmon*"):
        name_file = d / "name"
        name = ""
        if name_file.exists():
            try:
                name = name_file.read_text().strip()
            except OSError:
                pass

        if target_name and name.lower() == target_name.lower():
            if required_file and not (d / required_file).exists():
                continue
            return d
        candidates.append((d, name))

    # Fallback: search by required file if target_name didn't match or wasn't specified
    if required_file:
        for d, name in candidates:
            if (d / required_file).exists():
                return d

    # If target_name was specified but not found strictly, try substring match
    if target_name:
        for d, name in candidates:
            if target_name.lower() in name.lower():
                if required_file and not (d / required_file).exists():
                    continue
                return d

    return None


def get_sensors():
    # Find CPU temperature sensor (k10temp or any hwmon with temp1_input)
    temp_hwmon = find_hwmon(target_name="k10temp", required_file="temp1_input")
    if not temp_hwmon:
        temp_hwmon = find_hwmon(required_file="temp1_input")

    # Find fan controller sensor (asus or any hwmon with fan1_input or pwm1_enable)
    fan_hwmon = find_hwmon(target_name="asus", required_file="fan1_input")
    if not fan_hwmon:
        fan_hwmon = find_hwmon(required_file="pwm1_enable") or find_hwmon(required_file="fan1_input")

    return temp_hwmon, fan_hwmon


def read_temp(temp_hwmon):
    if not temp_hwmon:
        raise FileNotFoundError("CPU temperature sensor (hwmon) not found.")
    temp_file = temp_hwmon / "temp1_input"
    if not temp_file.exists():
        raise FileNotFoundError(f"Temperature file not found at {temp_file}")
    content = temp_file.read_text().strip()
    return int(content) / 1000.0


def read_fan_rpm(fan_hwmon):
    if not fan_hwmon:
        return None
    fan_file = fan_hwmon / "fan1_input"
    if not fan_file.exists():
        return None
    try:
        return int(fan_file.read_text().strip())
    except OSError:
        return None


def read_pwm_enable(fan_hwmon):
    if not fan_hwmon:
        return None
    pwm_enable_file = fan_hwmon / "pwm1_enable"
    if not pwm_enable_file.exists():
        return None
    try:
        return int(pwm_enable_file.read_text().strip())
    except OSError:
        return None


def write_sysfs(path: Path, value: str):
    if os.geteuid() != 0:
        print("Error: writing to fan control requires root privileges. Please run with sudo.", file=sys.stderr)
        sys.exit(1)
    try:
        path.write_text(str(value))
    except (PermissionError, OSError) as e:
        print(f"Error writing to {path}: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_status(args):
    try:
        temp_hwmon, fan_hwmon = get_sensors()
        temp_c = read_temp(temp_hwmon) if temp_hwmon else None
        rpm = read_fan_rpm(fan_hwmon)
        pwm_enable = read_pwm_enable(fan_hwmon)

        print("Fan Control Status:")
        print(f"  CPU Temperature: {temp_c:.1f}°C" if temp_c is not None else "  CPU Temperature: N/A")
        print(f"  Fan RPM:         {rpm if rpm is not None else 'N/A'}")
        
        mode_map = {0: "full (0)", 1: "manual (1)", 2: "auto (2)"}
        mode_str = mode_map.get(pwm_enable, str(pwm_enable)) if pwm_enable is not None else "N/A"
        print(f"  PWM Enable Mode: {mode_str}")

        if fan_hwmon:
            pwm_file = fan_hwmon / "pwm1"
            if pwm_file.exists():
                try:
                    pwm_val = pwm_file.read_text().strip()
                    print(f"  PWM Speed:       {pwm_val} (0-255)")
                except OSError:
                    pass
            else:
                print("  PWM Speed:       N/A (no pwm1 file, hardware uses full/auto modes)")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_set(args):
    try:
        temp_hwmon, fan_hwmon = get_sensors()
        if not fan_hwmon:
            print("Error: Fan hardware monitor not found.", file=sys.stderr)
            sys.exit(1)

        pwm_enable_path = fan_hwmon / "pwm1_enable"
        pwm_path = fan_hwmon / "pwm1"

        mode_arg = args.mode.lower()
        if mode_arg == "full":
            write_sysfs(pwm_enable_path, "0")
            print("Fan set to FULL speed (pwm1_enable = 0).")
        elif mode_arg == "auto":
            write_sysfs(pwm_enable_path, "2")
            print("Fan set to AUTO mode (pwm1_enable = 2).")
        else:
            try:
                percent = float(mode_arg)
            except ValueError:
                print(f"Error: invalid mode '{args.mode}'. Use 'full', 'auto', or 0-100.", file=sys.stderr)
                sys.exit(1)

            if not (0 <= percent <= 100):
                print("Error: percentage must be between 0 and 100.", file=sys.stderr)
                sys.exit(1)

            if not pwm_path.exists():
                print("Error: pwm1 control file not found. Only 'full' and 'auto' are supported on this hardware.", file=sys.stderr)
                sys.exit(1)

            write_sysfs(pwm_enable_path, "1")
            pwm_val = round((percent / 100.0) * 255)
            write_sysfs(pwm_path, str(pwm_val))
            print(f"Fan set to {percent}% (pwm1 = {pwm_val}, manual mode).")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def interpolate_curve(temp, curve):
    if temp <= curve[0][0]:
        return curve[0][1]
    if temp >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        t1, p1 = curve[i]
        t2, p2 = curve[i + 1]
        if t1 <= temp <= t2:
            if t1 == t2:
                return p1
            return p1 + (temp - t1) * (p2 - p1) / (t2 - t1)
    return curve[-1][1]


def restore_auto(fan_hwmon, dry_run=False):
    if not fan_hwmon:
        return
    pwm_enable_path = fan_hwmon / "pwm1_enable"
    if pwm_enable_path.exists():
        if dry_run:
            print("[Dry-run] Restoring pwm1_enable to 2 (auto)")
        else:
            try:
                pwm_enable_path.write_text("2")
                print("Restored fan pwm_enable to 2 (auto).")
            except Exception as e:
                print(f"Warning: failed to restore auto mode: {e}", file=sys.stderr)


def cmd_daemon(args):
    temp_hwmon, fan_hwmon = get_sensors()
    if not fan_hwmon:
        print("Error: Fan hardware monitor not found.", file=sys.stderr)
        sys.exit(1)

    pwm_enable_path = fan_hwmon / "pwm1_enable"
    pwm_path = fan_hwmon / "pwm1"
    has_pwm1 = pwm_path.exists()

    if not args.dry_run and os.geteuid() != 0:
        print("Error: daemon control requires root privileges. Please run with sudo.", file=sys.stderr)
        sys.exit(1)

    def handle_exit(signum, frame):
        print("\nExiting daemon, restoring auto mode...")
        sys.exit(0)  # the finally block below restores auto

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    print(f"Starting fancontrol daemon (interval={args.interval}s, high={args.high}°C, low={args.low}°C, pwm1={has_pwm1})...")

    last_pwm_enable = None
    last_pwm_val = None
    hysteresis_state = "auto"

    try:
        while True:
            try:
                temp = read_temp(temp_hwmon)
            except Exception as e:
                print(f"Warning: Failed to read CPU temperature: {e}. Switching fan to full speed for safety.", file=sys.stderr)
                if has_pwm1:
                    target_enable, target_pwm = "1", "255"
                else:
                    target_enable = "0"
                    target_pwm = None

                if target_enable != last_pwm_enable:
                    if args.dry_run:
                        print(f"[Dry-run] Set pwm1_enable={target_enable} (sensor error fallback)")
                    else:
                        write_sysfs(pwm_enable_path, target_enable)
                    last_pwm_enable = target_enable

                if has_pwm1 and target_pwm and target_pwm != last_pwm_val:
                    if args.dry_run:
                        print(f"[Dry-run] Set pwm1={target_pwm} (sensor error fallback)")
                    else:
                        write_sysfs(pwm_path, target_pwm)
                    last_pwm_val = target_pwm

                time.sleep(args.interval)
                continue

            if has_pwm1:
                percent = interpolate_curve(temp, DEFAULT_CURVE)
                pwm_val = str(round((percent / 100.0) * 255))
                target_enable = "1"

                if target_enable != last_pwm_enable:
                    if args.dry_run:
                        print(f"[Dry-run] Temp={temp:.1f}°C -> pwm1_enable={target_enable}")
                    else:
                        write_sysfs(pwm_enable_path, target_enable)
                    last_pwm_enable = target_enable

                if pwm_val != last_pwm_val:
                    if args.dry_run:
                        print(f"[Dry-run] Temp={temp:.1f}°C -> pwm1={pwm_val} ({percent:.1f}%)")
                    else:
                        write_sysfs(pwm_path, pwm_val)
                    last_pwm_val = pwm_val
            else:
                if temp >= args.high:
                    target_enable = "0"
                    hysteresis_state = "full"
                elif temp <= args.low:
                    target_enable = "2"
                    hysteresis_state = "auto"
                else:
                    if hysteresis_state == "full":
                        target_enable = "0"
                    else:
                        target_enable = "2"

                if target_enable != last_pwm_enable:
                    mode_name = "full (0)" if target_enable == "0" else "auto (2)"
                    if args.dry_run:
                        print(f"[Dry-run] Temp={temp:.1f}°C -> pwm1_enable={target_enable} ({mode_name})")
                    else:
                        write_sysfs(pwm_enable_path, target_enable)
                    last_pwm_enable = target_enable

            time.sleep(args.interval)

    finally:
        restore_auto(fan_hwmon, args.dry_run)


def main():
    parser = argparse.ArgumentParser(description="Linux ASUS / Generic Fan Speed Controller")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to run")

    subparsers.add_parser("status", help="Print fan RPM, pwm_enable mode, and CPU temp")

    set_parser = subparsers.add_parser("set", help="Set fan speed (full, auto, or 0-100)")
    set_parser.add_argument("mode", help="Mode: 'full', 'auto', or percentage (0-100)")

    daemon_parser = subparsers.add_parser("daemon", help="Run fan control daemon")
    daemon_parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds (default: 2)")
    daemon_parser.add_argument("--high", type=float, default=75.0, help="High temperature threshold for full speed (default: 75)")
    daemon_parser.add_argument("--low", type=float, default=65.0, help="Low temperature threshold for auto mode (default: 65)")
    daemon_parser.add_argument("--dry-run", action="store_true", help="Log decisions without writing to sysfs")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "set":
        cmd_set(args)
    elif args.command == "daemon":
        cmd_daemon(args)


if __name__ == "__main__":
    main()
