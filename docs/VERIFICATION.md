# Verification and delivery scope

This package is an Android-first implementation for supervised commissioning.
It is not a claim that the new Pi or physical robot has been tested remotely.

## Passed in the development sandbox

- 23 Python regression tests, using a temporary calibration folder and a
  controllable clock. They cover normal-output locking, explicit takeover,
  input bounds, one-motor calibration, save/discard, preserved configuration
  and backups, completed-step persistence, calibration invalidation on external
  changes, dry-run isolation, manual/microphone priority, held-stick activity,
  idle movement, PS4 ownership, legacy story timing, disconnect recovery,
  heartbeat expiration, and explicit resumption.
- Python source compilation.
- Android `assembleDebug` and `lintDebug` with SDK 35 / Gradle 8.13 / JDK 21.
  Lint reported no errors; warnings concern the landscape preference and
  Android's newer data-extraction-rules recommendation. This offline app
  requests only Bluetooth Nearby devices permissions.
- APK signing verification using Android SDK `apksigner verify`.
- Browser checks against the same local assets used in the APK: offline
  controls, settings and collapsed legacy menu, 13-position calibration
  selector, offline calibration locking, portrait overflow, and joystick
  keyboard spring return. Connected-state checks used explicitly injected test
  status; they did not connect to a robot.

## Not yet verified on physical devices

- Native app installation and Android 13 permission/pairing prompts.
- BlueZ GATT registration, encrypted writes and reconnect behavior on the Pi.
- Hardware package installation on Raspberry Pi OS Trixie.
- USB microphone identity, sample-rate support, and practical jaw sensitivity.
- Actual servo wiring, direction, mechanical travel and calibration.
- Concurrent Bluetooth PS4 and BLE operation and physical controller-loss
  behavior.
- iPhone support: the reusable protocol/interface path is documented, but no
  iOS binary or native iOS bridge is included.

Follow `PHONE_SETUP.md`, beginning with servo power disconnected and
`--dry-run --no-ps4`. No GitHub push, pull request, Pi installation, system
service enablement, or physical motion was performed by this delivery.
