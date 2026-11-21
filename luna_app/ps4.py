"""Optional backup: PS takes control; the phone's Take control button takes it back."""

import os
import threading


def start(control, schedule, stop):
    def run():
        from pyPS4Controller.controller import Controller

        class Backup(Controller):
            def on_playstation_button_press(self):
                schedule(control.ps4_claim)

            def on_triangle_press(self):
                schedule(self.story, True)

            def on_square_press(self):
                schedule(self.story, False)

            def story(self, enabled):
                if control.owner == 2 and control.ready:
                    if enabled:
                        control.story.start(control.clock())
                    else:
                        control.story.stop()

        axes = {"L3": (0, 1), "R3": (2, 3)}
        for stick, (x, y) in axes.items():
            for direction, index in (("left", x), ("right", x), ("up", y), ("down", y)):
                def move(self, value, index=index):
                    schedule(control.ps4_input, index, 0 if abs(value) < 1000 else value / 32767)
                setattr(Backup, f"on_{stick}_{direction}", move)
            for axis, index in (("x", x), ("y", y)):
                def rest(self, index=index):
                    schedule(control.ps4_input, index, 0)
                setattr(Backup, f"on_{stick}_{axis}_at_rest", rest)
        for trigger, index in (("L2", 4), ("R2", 5)):
            def press(self, value, index=index):
                schedule(control.ps4_input, index, (value + 32767) / 65534)
            def release(self, index=index):
                schedule(control.ps4_input, index, 0)
            setattr(Backup, f"on_{trigger}_press", press)
            setattr(Backup, f"on_{trigger}_release", release)
        Backup.on_R1_press = lambda self: schedule(control.ps4_input, 6, 1)
        Backup.on_R1_release = lambda self: schedule(control.ps4_input, 6, 0)
        while not stop.is_set():
            if not os.path.exists("/dev/input/js0"):
                stop.wait(1)
                continue
            try:
                pad = Backup(interface="/dev/input/js0", connecting_using_ds4drv=False)
                print("PS4 backup connected. Press PS to take control.")
                pad.listen(timeout=1)
            except (OSError, SystemExit) as error:
                print(f"PS4 listener ended: {error}")
            finally:
                def release_owner():
                    if control.owner == 2:
                        control.neutral()
                schedule(release_owner)
            stop.wait(1)
    thread = threading.Thread(target=run, daemon=True, name="ps4-backup")
    thread.start()
    return thread
