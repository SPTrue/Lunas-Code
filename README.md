# Luna the Animatronic Alebrije
Animatronic Ambassador for the Living Text Project at Monterey County Office of Education

## Hardware and Requirements
- Raspberry Pi 4, running Raspbian OS
    - python3 should come pre-installed on Raspbian
- [PCA9685 Servo Driver Board](https://www.amazon.com/PCA9685-Controller-Interface-Arduino-Raspberry/dp/B07WS5XY63)
- PS4 Dulshock 4 Controller (or PS4-compatible off-brand)
- [Wireless USB Microphone](https://www.amazon.com/Lococo-Wireless-Microphone-Rechargeable-Amplifier/dp/B0C2VBH26P) (Optional)
- Servos, CAD files, and misc. hardware for the actual animatronic are currently out-of-scope of this repository.

#### Wiring the Raspberry Pi to connect to the Servo Driver Board
| Raspberry Pi GPIO | PCA9685 |
| ----------------- | ------- |
| 3.3v | VCC |
| GPIO 2 | SDA |
| GPIO 3 | SCL |
| Ground | GND |

## Software setup
### First time setup
1. Clone this repository onto a Raspberry Pi 4 (running Raspbian)
2. In a terminal, run these commands (replacing PATH/TO with the actual directory path):
    ```
    cd ~/PATH/TO/Lunas-Code
    sudo apt-get install libasound-dev
    sudo apt-get install portaudio19-dev
    python -m venv .
    source bin/activate
    pip install -r requirements.txt
    ```
3. Ensure I2C output is enabled on the Raspberry Pi's GPIO pins.
    1. Click on the Raspberry menu in the upper-left corner -> Preferences -> Raspberry Pi Configuration
    2. In the "Interfaces" tab of Raspberry Pi Configuration, ensure the switch for I2C is ON.
    
#### Pair the PS4 Controller
1. To Put the controller in Pairing mode, press and hold the Share Button and the PS (center) Button simultaneously, until the light begins flashing quickly.
2. Using the Raspberry Pi (connected to keyboard, mouse, and monitor), select the bluetooth icon in the top right of the taskbar, then select **Add Device...**

    Wait for the Wireless Controller to appear in the list, then select it and click Pair.

### To Auto-run code on boot
1. Ensure Auto login is enabled on Raspberry Pi
    1. Click on the Raspberry menu in the upper-left corner -> Preferences -> Raspberry Pi Configuration
    2. In the "System" tab, ensure "Auto login" is turned ON.
2. Create a cron job to start the monitoring script on boot.
    1. In a terminal, enter this command:
        ```
        crontab -e
        ```
        If this is your first time using crontab on this machine, it will prompt you to choose a text editor. **Choose Nano unless you know what you're doing.**
    2. Use the arrow keys to scroll past the commented-out instructions. At the end, add the following line (replacing PATH/TO with the actual directory path):
        ```
        @reboot /PATH/TO/Lunas-Code/startup_and_monitor.bash
        ```
        If you're using Nano, type **Ctrl + o** to "Write Out" (save) the configuration (accept the default filename), then **Ctrl + x** to exit the editor.

        **NOTE:** When writing the directory path, be aware that `~/` and `/` at the beginning are NOT interchangeable! `~/` is an alias for the home directory: `/home/USERNAME/`. When in doubt you can run the `pwd` command while in the `Lunas-Code` directory to show you the full directory path, which you can then copy and paste as needed.
3. Now the code will auto-start when the Raspberry Pi is turned on, and run in the background. You can see the code's output in `monitor.log` in the same folder as the code. You can watch it in real time with this command (run it from inside the Lunas-Code directory, in a terminal):
    ```
    tail -f monitor.log
    ```
4. If you need to STOP the auto-running code (both the python script and the monitoring script), run this script (assuming you're already in `Lunas-Code` directory)
    ```
    bash kill_monitor.bash
    ```

### Running the code manually
If you haven't set up (or have disabled) the run-on-boot mechanism described above, here is how you launch the code manually.

Every time you open a new terminal, you'll need to run these commands once, to enter the correct directory and activate the python environment (replacing PATH/TO with the actual path):
```
cd ~/PATH/TO/Lunas-Code
source bin/activate
```

Then, to run the code:
```
python luna_control.py
```
## User Guide
### PS4 Controller
#### Normal Operation
| Input | Function |
| ------ | ------ |
| **Right Joystick:** | Eyes |
| **R2 (Trigger):** | Eylids Closing |
| **R1 (Bumper):** | Eyelids Wide Open |
| **Left Joystick:** | Neck / Head |
| **L2 (Trigger):** | Jaw (when not in Lip-Sync Playback mode) |
| **Triangle (△):** | Start Lip-Sync Playback |
| **Square (□):** | Stop Lip-Sync Playback |

#### Lip-Sync Playback Mode
This version of the code includes a pre-recorded lip-sync "track", so that Luna can move her jaw in sync with a pre-recorded
multi-media presentation called "Luna's Story". The operator should press Triangle exactly as the multimedia video file is started.
The presentation starts with about 30 seconds without talking, and the jaw cannot be moved with microphone input or the L2 Trigger
on the PS4 controller while in Lip-Sync Mode.

**If you seem to have lost jaw control**, it's possible that Triangle was accidentally pressed on the PS4 Controller,
in which case normal operation should resume after Square is pressed.

#### Microphone Input for Lip Sync
Luna's Jaw can be controlled with voice input via USB microphone. The current configuration is set for
[this wireless usb microphone](https://www.amazon.com/Lococo-Wireless-Microphone-Rechargeable-Amplifier/dp/B0C2VBH26P).

To use a different microphone or set the sensitivity thresholds, you can edit `calibration.py` in a text editor on the Raspberry Pi,
and the changes will take effect next time the code is started (or the computer is rebooted).
```
  "audio_input_settings": {
    "channels": 1,  # no need to change this, probably
    "rate": 44100,  # no need to change this, probably
    "chunk": 512,   # no need to change this, probably
    "mic_name": "H17H_USB_AUDIO",  # See instructions below to find the name of your mic
    "mic_threshold_low": -38,      # decibel level, anything quieter and the mouth is fully closed
    "mic_threshold_hi": -21        # decibel level, anything louder and the mouth is fully open
  },
```
To see what the device name for your USB mic is, you can uncomment this line in the `luna_control.py`, and be sure to watch the code run in a terminal window.
```
        for i in range(audio.get_device_count()):
            # Uncomment the line below to print out all the audio devices
            # print(f"Audio Input {i}: {audio.get_device_info_by_index(i)['name']}")
```
This will list all audio input and output devices recognized by PyAudio. You can run the code with your mic unplugged, then plugged in to see what changes.

You don't need to copy the full device name into the `calibration.json` field, just enough to distinguish it from other possible devices.

#### Calibration
The servo positions can be calibrated using only the PS4 Controller.

| Servos to Calibrate | How to Enter Calibration Mode | Controls | Save | Reset |
| ------------------- | ----------------------------- | -------- | ---- | ----- |
| Eyes | Options + D-Pad Right<br>(≡ + →) | Left and Right Joysticks to adjust center (rest) position for each eye. | PS (Center) Button to Save and Exit | Circle (◯) |
| Eyelids | Options + D-Pad Left<br>(≡ + ←) | Left and Right Joystick to adjust position for each eyelid | <ol><li>Triangle (△) when both eyelids are in **up / open / resting** position</li><li>Cross (✕) when both eyelids are in **down / closed** position</li><li>PS (Center) Button to Save and Exit</li></ol> | Circle (◯) |
| Jaw | Options + D-Pad Down<br>(≡ + ↓) | Right Joystick to adjust jaw position | <ol><li>Triangle (△) when jaw is in **up / closed / resting** position</li><li>Cross (✕) when jaw is in fully **down / open** position</li><li>PS (Center) Button to Save and Exit</li></ol> | Circle (◯) |
| Neck | Options + D-Pad Up<br>(≡ + ↑) | Left Joystick to adjust center (rest) position | PS (Center) Button to Save and Exit | Circle (◯) |
