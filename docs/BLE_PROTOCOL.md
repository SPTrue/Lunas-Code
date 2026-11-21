# Luna BLE protocol v1

All commands fit the default 20-byte ATT payload; no MTU negotiation or
fragmented JSON writes are needed. The Pi is the peripheral; the phone is the
central. Native Android code owns Bluetooth; the local WebView sends byte arrays
through the `Luna` bridge. No network/cloud service is involved.

| Role | UUID | Properties |
|---|---|---|
| Service | `41750001-71bd-4d43-8c75-326c756e6100` | Primary |
| Commands | `41750002-71bd-4d43-8c75-326c756e6100` | Write with response, encrypted |
| Status | `41750003-71bd-4d43-8c75-326c756e6100` | Read (encrypted), notify |

Every command begins with `[version=1, opcode]`.

| Opcode | Payload | Behavior |
|---|---|---|
| 1 | none | Phone heartbeat; does not take control |
| 2 | none | Explicitly take phone control; another phone cannot steal a live lease |
| 3 | none | Release to neutral + idle + microphone |
| 4 | `headX:i8, headY:i8, eyesX:i8, eyesY:i8, jaw:u8, lids:u8, wide:u8` | Four axes −100…100; triggers 0…100; wide 0/1 |
| 5 | enabled:u8 | Microphone on/off; requires detected mic to enable |
| 6 | enabled:u8 | Idle animations on/off |
| 7 | step:u8 | Begin one calibration position (0…12) |
| 8 | delta:i8 | −1 or +1 → −0.5° or +0.5° |
| 9 | none | Explicitly save current position |
| 10 | none | Discard unsaved adjustment, release calibration |
| 11 | enabled:u8 | Legacy story start from beginning / stop |

After claiming, only that peer may command the Pi until it releases, disconnects,
loses its 0.9-second heartbeat lease, or the PS4 explicitly takes over. Other
commands do not substitute for heartbeat. The **WebView JavaScript** generates
heartbeat every 250 ms: a stalled UI cannot keep a stale stick alive merely
because the native Bluetooth thread is still running. On Android background,
screen lock, or destruction, the GATT connection closes.

Status is 13 bytes, little endian, Python layout `<BBBBBBhBBHB`:

| Byte | Field |
|---|---|
| 0 | Protocol version (1) |
| 1 | Owner: 0 neutral, 1 phone, 2 PS4 |
| 2 | Microphone detected (0/1) |
| 3 | Microphone enabled (0/1) |
| 4 | Idle enabled (0/1) |
| 5 | Calibration step, or 255 for none |
| 6–7 | Signed angle in tenths of a degree, or −1 |
| 8 | Latest command error code |
| 9 | Last received valid opcode (diagnostic, not a reliable per-command ACK) |
| 10–11 | Calibration completion bitmask (8191 means all 13 saved) |
| 12 | Bit 0: legacy story active; bit 1: dry-run |

Notifications are sent every 200 ms. The UI uses authoritative status for
toggles, control ownership, and calibration progress; it does not claim a
physical action succeeded merely because a BLE write was accepted.

Errors: 0 OK; 1 malformed/range-invalid; 2 not owner; 3 uncalibrated;
4 calibration active; 5 microphone absent; 6 another phone owns control.

## Source layout

- `luna_app/control.py`: independent control rules, calibration, smoothing,
  automatic blinking, 6.5-second neck/jaw breathing, 5-second tail cycle,
  microphone/manual priorities, heartbeat and ownership.
- `luna_app/hardware.py`: PCA9685 output and USB microphone sampling.
- `luna_app/service.py`: BlueZ GATT, single-writer GLib loop, lifecycle, lock.
- `luna_app/ps4.py`: optional backup controller, marshalled to the same loop.
- `luna_app/legacy_story.py`: isolated pre-recorded jaw timeline. Removing the
  feature later means removing this adapter, its command/UI, and its data load;
  it is not the primary application workflow.
- `android/app/src/main/java/.../MainActivity.java`: Android BLE and lifecycle.
- `android/app/src/main/assets/`: shared local control interface.
- `tests/test_phone_control.py`: hardware-free regression tests.

The behavior follows the original controller's channel mapping, calibration
schema, per-axis smoothing ratios, blink shape/rate, breathing amplitudes and
period, tail amplitude/period, jaw range and microphone thresholds. The new
controller intentionally adds release-to-center, exclusive input ownership,
calibration gating, timed failover, and disables idle jaw writes while manual
jaw input is held. Audio RMS is calculated in floating point to avoid int16
overflow in the older implementation.

The original controller remains untouched. Physical behavior must be checked
on Luna: preserving formulas is not a claim of hardware verification.
