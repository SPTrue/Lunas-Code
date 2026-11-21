"""Run with python -m luna_app.service --dry-run OR --enable-motion."""

import argparse
from pathlib import Path
import signal
import threading
import traceback

from .control import Control, SERVICE_UUID, COMMAND_UUID, STATUS_UUID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Real BLE, no servo or microphone access")
    mode.add_argument("--enable-motion", action="store_true", help="Allow supervised calibration and calibrated movement")
    parser.add_argument("--no-ps4", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()

    from gi.repository import GLib
    from bluezero import adapter, peripheral
    from .hardware import Microphone, Servos
    from . import ps4

    control = Control(args.root, dry_run=args.dry_run)
    stop = threading.Event()
    motors = mic = None
    lock = (args.root / ".phone-service.lock").open("w")
    import fcntl
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Luna phone service is already running")
    tx = None
    failed = False

    def schedule(function, *values):
        def invoke():
            function(*values)
            return False
        GLib.idle_add(invoke)

    def notify(enabled, characteristic):
        nonlocal tx
        tx = characteristic if enabled else None

    def write(value, options):
        nonlocal failed
        peer = str(options.get("device", ""))
        if not peer:
            control.error = 1
            return
        try:
            control.command(bytes(value), peer)
        except Exception:
            failed = True
            traceback.print_exc()
            ble.mainloop.quit()

    def disconnected(_adapter, address):
        peer = control.phone
        if peer and peer.endswith("dev_" + address.replace(":", "_")):
            control.disconnect(peer)

    try:
        if args.enable_motion:
            motors = Servos(control.mapping)
            mic = Microphone(control.config["audio_input_settings"])
            if mic.stream:
                control.microphone_found()
        adapters = list(adapter.Adapter.available())
        if not adapters:
            raise RuntimeError("No Bluetooth adapter found. Check rfkill and bluetooth.service.")
        ble = peripheral.Peripheral(adapters[0].address, local_name="Luna")
        ble.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)
        ble.add_characteristic(
            srv_id=1, chr_id=1, uuid=COMMAND_UUID, value=[], notifying=False,
            flags=["write", "encrypt-write"], write_callback=write)
        ble.add_characteristic(
            srv_id=1, chr_id=2, uuid=STATUS_UUID, value=list(control.status()),
            notifying=False, flags=["read", "notify", "encrypt-read"],
            read_callback=lambda: list(control.status()), notify_callback=notify)
        ble.on_disconnect = disconnected

        def tick():
            nonlocal failed
            try:
                if mic:
                    mic.poll(control)
                angles = control.tick()
                if motors:
                    motors.write(angles)
            except Exception:
                failed = True
                traceback.print_exc()
                ble.mainloop.quit()
                return False
            return True

        def status():
            if tx:
                tx.set_value(list(control.status()))
            return True

        def shutdown(*_):
            stop.set()
            ble.mainloop.quit()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        GLib.timeout_add(20, tick)
        GLib.timeout_add(200, status)
        if not args.no_ps4:
            ps4.start(control, schedule, stop)
        print("Luna BLE ready. " + ("DRY RUN: no hardware access." if args.dry_run else
              "Unconfirmed calibration keeps normal servo outputs locked."))
        ble.publish()
    finally:
        stop.set()
        if motors:
            motors.close()
        if mic:
            mic.close()
        lock.close()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
