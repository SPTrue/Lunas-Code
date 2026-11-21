# Luna Control: start here

This is an **additive update to SPTrue/Lunas-Code**, not a new robot project.
The original `luna_control.py`, story data, calibration file, requirements file,
and startup scripts are unchanged. The phone uses a new companion Pi service.
**Never run both controller programs at the same time:** both access the PCA9685.

Supported first target: Raspberry Pi 4 Model B, Raspberry Pi OS Trixie / Debian 13,
PCA9685 at its default I2C address (0x40), and Android 12+ (the intended test phone
is a Samsung Galaxy A03s on Android 13). No Wi-Fi is needed for normal operation.
Downloads and first-time dependency installation do require internet.

## What has and has not been verified

The included automated tests exercise the control rules without hardware.
The Android debug APK has been compiled and checked with Android Lint.
These are **not evidence of a successful connection to a physical Pi or phone**.
Real BLE pairing, simultaneous PS4/BLE operation, Trixie hardware dependencies,
audio-device selection, servo direction/travel, and mechanical safety need the
supervised commissioning checks below. This is a first implementation, not a
hardware-certified controller.

## 1. Choose patch OR source archive

Start with **the servo wall adapter unplugged**. Leave the Pi powered via USB-C.
Support the head and other parts that can fall when servos have no power.

If you already cloned the original repository, copy `luna-phone-control.patch`
onto the Pi, then run this from the repository folder (adjust the patch path):

```bash
git status --short
git apply --check ~/Downloads/luna-phone-control.patch
```

`--check` changes no files. If it succeeds, apply the update explicitly:

```bash
git apply ~/Downloads/luna-phone-control.patch
```

The patch was based on upstream commit
`51456bdd63183240b2586fdef53b440427e202c5`. It does not modify
`calibration.json`. If the check fails, **do not force it or reset local files**.
Use the complete source archive in a separate folder, or review the conflicting
files first. Do not apply the patch inside the already-updated source archive.

Alternatively, unpack `luna-phone-source.zip` into a new folder and use that
folder directly. It contains the complete original files plus this update, but
no `.git` directory, virtual environment, or build output. Nothing in either
download installs, starts, or changes the Pi automatically.

To remove an applied patch later, stop the new service first, then:

```bash
git apply --reverse --check ~/Downloads/luna-phone-control.patch
git apply --reverse ~/Downloads/luna-phone-control.patch
```

This removes the added source files. It does **not** undo calibration performed
afterward, remove dependencies, or erase local calibration backups.

## 2. Prepare the fresh Pi

Run the following **in the updated repository folder**. These commands install
dependencies; read them before executing. Do not use the old `requirements.txt`
for the new service: its old NumPy pin is unsuitable for the new Python version.

```bash
sudo apt update
sudo apt install -y \
  bluez python3-venv python3-dev build-essential python3-dbus python3-gi \
  python3-numpy python3-scipy python3-pyaudio python3-libgpiod i2c-tools
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-phone.txt
```

The venv deliberately uses the OS-provided PyAudio, NumPy, SciPy, D-Bus, and
PyGObject packages, rather than attempting to compile older pins on Python 3.13.
Blinka is pinned to 10.2.0; its Raspberry Pi GPIO backend uses libgpiod rather
than the older RPi.GPIO backend. The other Adafruit packages resolve compatible
versions within their declared major versions. A physical Trixie installation
must still be verified.

Enable I2C in `sudo raspi-config` → Interface Options → I2C, then reboot if asked.
Check the Pi's user has access to I2C and the joystick:

```bash
groups
ls -l /dev/i2c-1
```

If needed, add your user (then log out and back in):

```bash
sudo usermod -aG i2c,input,bluetooth,gpio "$USER"
```

Check that `/dev/i2c-1` exists; verify the exact wiring against the original
README. The Pi's I2C logic power and servo supply must share ground.
**Do not plug in servo power yet.**

## 3. Test the Bluetooth service with no hardware access

```bash
.venv/bin/python -m luna_app.service --dry-run --no-ps4
```

This advertises real BLE but opens neither servos nor the microphone. The app
will show **DRY RUN · NO MOTORS**. Calibration can be tried in memory; dry-run
saves never mark real hardware calibrated and do not change calibration files.
Stop with Ctrl+C after testing.

If BlueZ reports NotPermitted or a D-Bus authorization error, check that you are
running in the Pi's local logged-in session and that `bluetooth.service` is
running. Resolve the local BlueZ policy rather than running the control process
as root or weakening D-Bus security globally.

## 4. Install the Android APK

Transfer `luna-control-debug.apk` to the Galaxy A03s and open it. Android may
require **Install unknown apps** permission for the specific browser or file
manager you use. Enable that permission only for the installation, then turn it
off again. This is a debug build for local testing, not a Play Store release.

The app requests **Nearby devices** for Bluetooth scanning and connecting.
It requests no internet, location, or phone microphone permission. The UI
prefers landscape, with a portrait fallback for other form factors.

Do not compare an APK's signing key to the robot's pairing: they are unrelated.
A future APK built with a different signing identity cannot update this one in
place; uninstall the debug app first. Pi calibration lives on the Pi and is not
deleted by uninstalling the phone app.

## 5. Pair once, deliberately

In a **second Pi terminal**, while the service is running:

```bash
bluetoothctl
```

At the `bluetoothctl` prompt:

```text
power on
agent KeyboardDisplay
default-agent
pairable on
discoverable on
```

Keep this terminal open. On the phone, open Luna Control → Connect →
Search nearby → Pair / connect. Approve matching pairing prompts on both
devices. The exact passkey/confirmation prompt depends on the BlueZ and Android
versions; never approve an unfamiliar device.

Once paired, close the pairing window **in the Pi terminal**:

```text
pairable off
discoverable off
```

Bonding persists. Keep an agent running for the session if BlueZ asks for
authorization on later encrypted connections. The GATT command characteristic
requires an encrypted Bluetooth link; this service does not silently accept
unpaired writes. Pairing/discoverability and BLE service advertising are
different: the paired phone can still find the advertised Luna service with
discoverability off.

Use one paired phone at a time. The Pi rejects command ownership from a second
phone while one owns control. Pair only trusted phones and remove lost phones'
bonds using `bluetoothctl remove <device-address>`.

## 6. Commission the actual hardware

1. Stop dry-run. Leave servo power unplugged.
2. Start `.venv/bin/python -m luna_app.service --enable-motion`.
3. Connect the phone and tap **Take control**. Fresh installations have all
   normal servo outputs locked, even though baseline angles exist in the repo.
4. Open Settings → Joint calibration. Read the warning. Only the activated
   motor receives PWM; the other motors are released, not held. Mechanically
   support moving parts before activating any joint.
5. With everyone clear, connect the separate servo supply. Activate the first
   joint. **Activation can immediately move it to its stored angle.** If that
   is not safe for the mechanism, do not continue: disconnect servo power and
   mechanically align/detach the linkage before commissioning.
6. Adjust using ±0.5° buttons. Save the center or endpoint requested, then
   activate the next position. There are 13 positions across the 10 servos.
   The numeric servo direction may be reversed on a linkage; do not assume
   “+” always means physically up or open.
7. The wizard preserves the existing eye/neck/tail travel spans; it is not an
   automatic travel-limit detector. Review `angle_span` in `calibration.json`
   with power off and reduce it if Luna cannot safely traverse that range.
8. **Saving the final outstanding position enables normal idle motion.**
   Keep the mechanism supported and clear before that final save.

The first real calibration save preserves `calibration.before-app.json`.
Saves update the existing schema atomically. Completion is stored separately
in ignored `app-calibration.json`; changing the servo mapping externally
invalidates completion and requires rechecking. Discard or disconnect never
saves an unfinished adjustment. Already-saved steps remain saved.

After completing calibration, supervise these checks:

- Head and eyes follow the two sticks and return to center when released.
- Jaw opens progressively; release returns toward closed, then mic input can
  take over. Eyelid slider returns to open; the wide-eye control is held.
- Mic lip-sync defaults on when the configured microphone is found at startup.
- Disable mic and idle in the UI, then disconnect: idle returns and mic is
  forced on if available. Speak and verify the jaw still responds.
- Hold a control, then lock the phone or leave radio range. The Pi should
  clear phone commands after at most approximately 0.9 seconds without
  heartbeat, plus physical motion-settling time. It should idle, not freeze.
- Reconnect: control remains neutral until **Take control** is tapped.
- In legacy settings, Story starts only the jaw track, not audio or video;
  Stop and disconnect both end it.

The software's 0–180° clamp is an electrical command limit, **not proof of safe
mechanical travel**. The UI's Return to idle is not an emergency stop; breathing,
tail, and microphone movements remain possible. Unplug the separate servo
adapter to cut servo power, while supporting the mechanism. This system is not
a safety-rated controller.

## 7. Configure and test the Pi microphone

The configured name substring is currently `H17H_USB_AUDIO`. Find input devices:

```bash
.venv/bin/python - <<'PY'
import pyaudio
audio = pyaudio.PyAudio()
try:
    for i in range(audio.get_device_count()):
        device = audio.get_device_info_by_index(i)
        if device["maxInputChannels"] > 0:
            print(i, device["name"])
finally:
    audio.terminate()
PY
```

With the service stopped, edit `audio_input_settings.mic_name` in
`calibration.json` to an identifying substring if needed, then restart.
Existing low/high loudness thresholds are preserved. Startup detection enables
the microphone automatically; losing its audio stream disables it rather than
holding an old jaw value. **Hot-plugging a new or recovered microphone currently
requires restarting the Pi service.** A missing mic never blocks manual jaw
control. If an input cannot open at the configured sample rate, it is reported
unavailable; check that device's supported rate.

## 8. PS4 backup

Pair the PS4 controller to the Pi using the original README. The new service
looks for `/dev/input/js0` and waits if it is absent. Press the **PS button** to
take control away from the phone; tap **Take control** on the phone to switch
back. The last source to explicitly take control wins; inputs never blend.
Controller loss returns to neutral + mic + idle.

Normal sticks, jaw trigger, eyelid trigger, wide eyes, and Triangle/Square legacy
story controls are retained. Use the phone wizard for calibration in the new
service. The original PS4 calibration interface is still available by stopping
the new service and running the original program with its own compatible
environment. The original old pinned environment is not verified on Trixie.

## 9. Optional auto-start: only after physical tests pass

Do not enable this before confirming that idle and microphone motions are safe.
Do not use the old monitor/cron job alongside the new service.

To create a user service, first create its folder:

```bash
mkdir -p ~/.config/systemd/user
```

Create `~/.config/systemd/user/luna-phone.service` in an editor. Replace
`/absolute/path/to/Lunas-Code` **in both places** with the actual path:

```ini
[Unit]
Description=Luna Bluetooth phone controller

[Service]
WorkingDirectory=/absolute/path/to/Lunas-Code
ExecStart=/absolute/path/to/Lunas-Code/.venv/bin/python -u -m luna_app.service --enable-motion
Restart=no
UMask=0077

[Install]
WantedBy=default.target
```

`Restart=no` is deliberate: a hardware failure should not repeatedly restart
servo outputs. Once you have reviewed the unit and are ready to enable startup:

```bash
systemctl --user daemon-reload
systemctl --user enable --now luna-phone.service
journalctl --user -u luna-phone.service -f
```

This starts in your user session. Running before login requires additional
session/BlueZ authorization setup; this guide does not silently enable lingering.
To stop and disable it:

```bash
systemctl --user disable --now luna-phone.service
```

## 10. Build, test, and future iPhone support

Pi-independent tests:

```bash
python3 -m unittest discover -s tests -v
```

Open `android/` in Android Studio, or use JDK 17+ with Android SDK 35 installed:

```bash
cd android
./gradlew assembleDebug lintDebug
```

Windows: use `gradlew.bat`. The wrapper pins Gradle 8.13 and verifies its
distribution checksum. Build output is
`android/app/build/outputs/apk/debug/app-debug.apk`. No Expo account or cloud
build service is required. No signing secrets are included.

The actual app controls live in `android/app/src/main/assets/`. They are local
HTML/CSS/JavaScript rendered in an Android WebView, **not a browser Bluetooth
workaround**. Native Java handles Android permissions, bonding, GATT, lifecycle,
and the bridge. There are no remote pages, web APIs, or internet permissions.
A future iPhone shell can reuse these assets and the documented BLE protocol,
with a native CoreBluetooth bridge and normal Apple signing. The current
package is Android-only; it does not claim to contain an iOS app.

See [BLE_PROTOCOL.md](BLE_PROTOCOL.md) for the wire protocol and source layout.
