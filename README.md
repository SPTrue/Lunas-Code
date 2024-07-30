# Luna the Animatronic Alebrije
## Introduction (TODO)

## Hardware and Requirements (TODO)

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

## Calibration (TODO)
