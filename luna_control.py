import board, json, os, pyaudio, time, threading
import numpy as np
from adafruit_motor import servo
from adafruit_pca9685 import PCA9685
from scipy import signal
from pyPS4Controller.controller import Controller
from random import randint


AUDIO_INPUT_SETTINGS = {
    "channels": 1,
    "rate": 44100,
    "chunk": 512,
    "mic_name": "H17H_USB_AUDIO",
    "mic_threshold_low": -38,  # dba
    "mic_threshold_hi": -21  # dba
}
AUDIO_FORMAT = pyaudio.paInt16


# Controller Input Smoothing
SMOOTHING_SETTINGS = {
    "smoothing_ratio_eye": 0.8,
    "smoothing_ratio_neck": 0.95
}

SERVO_MAPPING = {
    "left_eye_horizontal": {
        "channel": 0,
        "center_angle": 100,
        "angle_span": 105
        },
    "left_eye_vertical": {
        "channel": 1,
        "center_angle": 111,
        "angle_span": 105
        },
    "right_eye_horizontal": {
        "channel": 2,
        "center_angle": 80,
        "angle_span": 105
        },
    "right_eye_vertical": {
        "channel": 3,
        "center_angle": 90,
        "angle_span": 105
        },
    "left_eyelid": {
        "channel": 4,
        "min_angle": 70,
        "max_angle": 135
        },
    "right_eyelid": {
        "channel": 5,
        "min_angle": 75,
        "max_angle": 135
        },
    "jaw": {
        "channel": 6,
        "min_angle": 80,
        "max_angle": 55
        },
    "neck_horizontal": {
        "channel": 7,
        "center_angle": 106,
        "angle_span": 60
        },
    "neck_vertical": {
        "channel": 8,
        "center_angle": 90,
        "min_angle": 60,
        "angle_span": 65
        },
    "tail": {
        "channel": 9,
        "center_angle": 90,
        "angle_span": 135
    }
}


class LunaController(Controller):
    def __init__(self, pca_interface, **kwargs):
        super().__init__(**kwargs)
        
        # Calibration and constants
        self.calibration_filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), "calibration.json")
        self.load_calibration()
        self.calibration_mode = -1

        self.servos = {
            name: servo.Servo(
                pca_interface.channels[self.servo_info[name]["channel"]],
                actuation_range=180
            ) for name in self.servo_info.keys()
        }

        with SupressStdoutStderr():
            audio = pyaudio.PyAudio()
        
        # Find mic input device by name
        device_index = None
        for i in range(audio.get_device_count()):
            # Uncomment the line below to print out all the audio devices
            # print(f"Audio Input {i}: {audio.get_device_info_by_index(i)['name']}")
            if self.audio_input_settings["mic_name"] in audio.get_device_info_by_index(i)["name"]:
                device_index = i
        # create low-pass filter; this filters out high frequences (like the letter 's'), preventing those from making the mouth open
        self.lowpass_sos = signal.butter(6, 5000, 'lp', fs=self.audio_input_settings['rate'], output='sos')
        if device_index is None:
            print(f"\033[1m\033[33mWARNING: Microphone named '{self.audio_input_settings['mic_name']}' not found. Make sure it is plugged in!\033[0m")
        else:
            # Print Mic Input Info
            print(f"{audio.get_device_info_by_index(device_index)['name']}")
            # Initialize Mic Input Stream
            self.stream = audio.open(format=AUDIO_FORMAT,
                                     channels=self.audio_input_settings["channels"],
                                     rate=self.audio_input_settings["rate"],
                                     input=True,
                                     output=False,
                                     input_device_index=device_index,
                                     stream_callback=self.audio_stream_callback,
                                     frames_per_buffer=self.audio_input_settings["chunk"])
                                 
        # Idle Behavior State
        self.idle_timeout_seconds = 5
        self.idle_mode: int = 0  # different modes are represented bitwise
        self.idle_blink_countdown_zero: float = time.monotonic() - self.idle_timeout_seconds
        self.blink_zero_timestamp: float = time.monotonic()
        self.is_blinking: bool = False
        self.idle_breath_countdown_zero: float = time.monotonic() - self.idle_timeout_seconds
        self.breath_period_seconds = 6.5
        self.breath_neck_half_amplitude = (35.0 / 128) * 32767        # in "controller input" units
        self.breath_jaw_half_amplitude = (35.0 / 128) * 32767         # in "controller input" units
        self.breath_jaw_center_value = -32767 + (40.0 / 128) * 32767  # in "controller input" units
        self.tail_half_amplitude = self.servo_info["tail"]["angle_span"] / 2  # degrees
        self.tail_period_seconds = 5.0
        
        # Controller Input State
        self.right_stick_x = 0
        self.right_stick_y = 0
        self.left_stick_x = 0
        self.left_stick_y = 0
        self.right_stick_x_prev = 0
        self.right_stick_y_prev = 0
        self.left_stick_x_prev = 0
        self.left_stick_y_prev = 0
        self.right_arrow_is_pressed = False
        self.left_arrow_is_pressed = False
        self.up_arrow_is_pressed = False
        self.down_arrow_is_pressed = False
        self.triangle_is_pressed = False
        self.square_is_pressed = False
        self.cross_is_pressed = False
        self.circle_is_pressed = False
        self.options_is_pressed = False
        self.playstation_button_is_pressed = False
        self.raised_eyelids = False
        self.jaw_controller_priority = False
        
        # Initiate animation
        self.initialize_servo_positions()
        self.update_thread = threading.Thread(target=self.update_servos)
        self.update_thread.daemon = True
        self.update_thread.start()
        
    def load_calibration(self):
        try:
            with open(self.calibration_filepath, 'r') as calibration_file:
                calibration_data = json.load(calibration_file)
        except FileNotFoundError:
            print("Using default calibration values")
            calibration_data = {}
        self.servo_info = calibration_data.get("servo_mapping", SERVO_MAPPING)
        self.audio_input_settings = calibration_data.get("audio_input_settings", AUDIO_INPUT_SETTINGS)
        self.smoothing_settings = calibration_data.get("smoothing_settings", SMOOTHING_SETTINGS)
    
    def save_calibration(self):
        calibration_data = {
            "servo_mapping": self.servo_info,
            "audio_input_settings": self.audio_input_settings,
            "smoothing_settings": self.smoothing_settings
        }
        with open(self.calibration_filepath, 'w') as calibration_file:
            json.dump(calibration_data, calibration_file, indent=2)
            
    def enter_calibration_mode(self, mode: int):
        self.calibration_mode = mode
        self.set_servos_calibration_ready()
    
    def exit_calibration_mode(self):
        self.calibration_mode = -1
        self.save_calibration()
        print("\nCalibration values saved!")
        self.set_servos_calibration_ready()
    
    def get_idle_mode(self):
        """Each bit in the output corresponds to a different independent idle animation:
        LSB 0: Blinking
            1: Breathing
            2: [unused]
            3: [unused]
            4: [unused]
            5: [unused]
            6: [unused]
        MSB 7: [unused]
        """
        output = 0
        if time.monotonic() - self.idle_breath_countdown_zero >= self.idle_timeout_seconds:
            output = output | 0b10  # Idle mode 00000010: Breathing is automated
        if time.monotonic() - self.idle_blink_countdown_zero >= self.idle_timeout_seconds:
            output = output | 1     # Idle mode 00000001: Blinking is automated
        return output
    
    def initiate_blink(self):
        self.blink_zero_timestamp = time.monotonic()
        self.is_blinking = True
    
    def get_blink_animation_value(self):
        if not self.is_blinking:
            return 0
        blink_values = [[0, 0], [0.05, 0.5], [0.1, 1], [0.15, 1], [0.2, 0.5], [0.25, 0]]
        current_time = time.monotonic() - self.blink_zero_timestamp
        i = 0
        while i < len(blink_values) - 1 and blink_values[i + 1][0] <= current_time:
            i += 1
        if i == len(blink_values) - 1:
            self.is_blinking = False
        return blink_values[i][1]
        
    def audio_stream_callback(self, input_data, frame_count, time_info, flags):
        if flags != 0:
            return None, pyaudio.paContinue
        int_data = np.array([int.from_bytes(input_data[i:i+2], byteorder='little', signed=True) for i in range(0, len(input_data), 2)], dtype=np.int16)
        # use low-pass filter; this filters out high frequences (like the letter 's'), preventing those from making the mouth open
        filtered_data = signal.sosfilt(self.lowpass_sos, int_data)
        squared_values = np.array(filtered_data ** 2)
        # Calculate RMS (Root meen squared) for 'average loudness', on 0.0 to 1.0 scale
        rms = np.sqrt(np.mean(squared_values)) / (2**16)
        
        # Standard conversion equation to dba (loudness scale)
        db = 20 * np.log10(rms) if rms != 0 else -90
        
        if db > self.audio_input_settings["mic_threshold_low"]:
            # Reset the countdown timer to re-initiate idle breathe mode
            self.idle_breath_countdown_zero = time.monotonic()
        
        jaw_value = map_values(
            db,
            self.audio_input_settings["mic_threshold_low"],
            self.audio_input_settings["mic_threshold_hi"],
            self.servo_info["jaw"]["min_angle"],
            self.servo_info["jaw"]["max_angle"],
            clamp=True
        )
        if self.jaw_controller_priority == False and self.get_idle_mode() & 0b10 == 0:
            self.servos["jaw"].angle = jaw_value

        return None, pyaudio.paContinue

    def initialize_servo_positions(self):
        """Set initial positions of servos (useful for joints that don't activate until there is user input)"""
        # Eyelids Open
        self.on_R1_release()
        
        # Mouth Closed
        self.on_L2_release()
        
        # Tail Centered
        self.servos["tail"].angle = self.servo_info["tail"]["center_angle"]
        
    def deadzone(self, inputValue, deadzoneValue=1000):
        """Return joystick values from -32767 to 32767, adding a deadzone around zero"""
        if inputValue < deadzoneValue and inputValue > -deadzoneValue:
            return 0
        return inputValue

    def on_R3_left(self, value):
        self.right_stick_x = self.deadzone(value)
    
    def on_R3_right(self, value):
        self.right_stick_x = self.deadzone(value)

    def on_R3_up(self, value):
        self.right_stick_y = self.deadzone(value)
    
    def on_R3_down(self, value):
        self.right_stick_y = self.deadzone(value)
        
    def on_L3_left(self, value):
        self.left_stick_x = self.deadzone(value)
    
    def on_L3_right(self, value):
        self.left_stick_x = self.deadzone(value)

    def on_L3_up(self, value):
        self.left_stick_y = self.deadzone(value)
    
    def on_L3_down(self, value):
        self.left_stick_y = self.deadzone(value)
        
    def calibrate_eyes(self):
        # Left Eye (Right Stick)
        self.servos["left_eye_horizontal"].angle = constrain(self.servos["left_eye_horizontal"].angle + self.right_stick_x / 32767)
        self.servos["left_eye_vertical"].angle = constrain(self.servos["left_eye_vertical"].angle + self.right_stick_y / 32767)
        # Right Eye (Left Stick)
        self.servos["right_eye_horizontal"].angle = constrain(self.servos["right_eye_horizontal"].angle + self.left_stick_x / 32767)
        self.servos["right_eye_vertical"].angle = constrain(self.servos["right_eye_vertical"].angle - self.left_stick_y / 32767)
        
        for servo_name in ["left_eye_horizontal", "left_eye_vertical", "right_eye_horizontal", "right_eye_vertical"]:
            print(f"{servo_name}: {self.servos[servo_name].angle}", end="\t")
        print("\r", end="")
        
        if self.circle_is_pressed:
            # Reset positions to previously-saved center
            for servo_name in ["left_eye_horizontal", "left_eye_vertical", "right_eye_horizontal", "right_eye_vertical"]:
                self.servos[servo_name].angle = self.servo_info[servo_name]["center_angle"]
        
        if self.playstation_button_is_pressed:
            # Save current position
            for servo_name in ["left_eye_horizontal", "left_eye_vertical", "right_eye_horizontal", "right_eye_vertical"]:
                self.servo_info[servo_name]["center_angle"] = self.servos[servo_name].angle
            self.exit_calibration_mode()
        
        time.sleep(5 / 1000.)
        
    def calibrate_eyelids(self):
        # Left Eyelid (Right Stick)
        self.servos["left_eyelid"].angle = constrain(self.servos["left_eyelid"].angle + self.right_stick_y / (2**16))
        # Right Eyelid (Left Stick)
        self.servos["right_eyelid"].angle = constrain(self.servos["right_eyelid"].angle + self.left_stick_y / (2**16))
        
        for servo_name in ["right_eyelid", "left_eyelid"]:
            print(f"{servo_name}: {self.servos[servo_name].angle}", end="\t")
        print("\r", end="")
                
        if self.triangle_is_pressed:
            # Save open (minimum) position
            print("\nSaving Open Eyelid Positions")
            for servo_name in ["right_eyelid", "left_eyelid"]:
                self.servo_info[servo_name]["min_angle"] = self.servos[servo_name].angle
        
        if self.cross_is_pressed:
            # Save closed (maximum) position
            print("\nSaving Closed Eyelid Positions")
            for servo_name in ["right_eyelid", "left_eyelid"]:
                self.servo_info[servo_name]["max_angle"] = self.servos[servo_name].angle
                
        if self.circle_is_pressed:
            # Reset positions to previously-saved center
            for servo_name in ["right_eyelid", "left_eyelid"]:
                self.servos[servo_name].angle = (self.servo_info[servo_name]["min_angle"] + self.servo_info[servo_name]["max_angle"]) / 2
        
        if self.playstation_button_is_pressed:
            # Exit Calibration, save to disk
            self.exit_calibration_mode()
        
        time.sleep(5 / 1000.)
    
    def calibrate_jaw(self):
        self.servos["jaw"].angle = constrain(self.servos["jaw"].angle - self.right_stick_y / (2**16))
        
        for servo_name in ["jaw"]:
            print(f"{servo_name}: {self.servos[servo_name].angle}", end="\t")
        print("\r", end="")
                
        if self.triangle_is_pressed:
            # Save closed (minimum) position
            print("\nSaving Closed Jaw Positions")
            self.servo_info["jaw"]["min_angle"] = self.servos["jaw"].angle
        
        if self.cross_is_pressed:
            # Save open (maximum) position
            print("\nSaving Open Jaw Positions")
            self.servo_info["jaw"]["max_angle"] = self.servos["jaw"].angle
                
        if self.circle_is_pressed:
            # Reset position to previously-saved center
            self.servos["jaw"].angle = (self.servo_info["jaw"]["max_angle"] + self.servo_info["jaw"]["min_angle"]) / 2
        
        if self.playstation_button_is_pressed:
            # Exit Calibration, save to disk
            self.exit_calibration_mode()
        
        time.sleep(5 / 1000.)
        
    def calibrate_neck(self):
        self.servos["neck_horizontal"].angle = constrain(self.servos["neck_horizontal"].angle - self.left_stick_x / (2**16))
        self.servos["neck_vertical"].angle = constrain(self.servos["neck_vertical"].angle - self.left_stick_y / (2**16))
        
        for servo_name in ["neck_vertical", "neck_horizontal"]:
            print(f"{servo_name}: {self.servos[servo_name].angle}", end="\t")
        print("\r", end="")
        
        if self.circle_is_pressed:
            # Reset positions to previously-saved center
            for servo_name in ["neck_vertical", "neck_horizontal"]:
                self.servos[servo_name].angle = self.servo_info[servo_name]["center_angle"]
        
        if self.playstation_button_is_pressed:
            # Save current position
            for servo_name in ["neck_vertical", "neck_horizontal"]:
                self.servo_info[servo_name]["center_angle"] = self.servos[servo_name].angle
            self.exit_calibration_mode()
        
        time.sleep(5 / 1000.)

    def on_right_arrow_press(self):
        self.right_arrow_is_pressed = True
        if self.options_is_pressed:
            self.enter_calibration_mode(0)  # Mode 0: Eyes

    def on_left_arrow_press(self):
        self.left_arrow_is_pressed = True
        if self.options_is_pressed:
            self.enter_calibration_mode(1)  # Mode 1: Eyelids
            
    def on_left_right_arrow_release(self):
        self.right_arrow_is_pressed = False
        self.left_arrow_is_pressed = False
    
    def on_down_arrow_press(self):
        self.down_arrow_is_pressed = True
        if self.options_is_pressed:
            self.enter_calibration_mode(2)  # Mode 2: Jaw
    
    def on_up_arrow_press(self):
        self.up_arrow_is_pressed = True
        if self.options_is_pressed:
            self.enter_calibration_mode(3)  # Mode 3: Neck
            
    def on_up_down_arrow_release(self):
        self.up_arrow_is_pressed = False
        self.down_arrow_is_pressed = False

    def update_servos(self):
        """At a regular interval, update the positions of servos that use input smoothing, or autonomous functions.
        This function is to run in a separate thread.
        """
        while True:
            # Handle calibration modes first
            if self.calibration_mode == 0:
                self.calibrate_eyes()
                continue
            elif self.calibration_mode == 1:
                self.calibrate_eyelids()
                continue
            elif self.calibration_mode == 2:
                self.calibrate_jaw()
                continue
            elif self.calibration_mode == 3:
                self.calibrate_neck()
                continue

            #### EYES ####
            _eye_x = (self.right_stick_x_prev *  self.smoothing_settings["smoothing_ratio_eye"]) + (self.right_stick_x * (1 - self.smoothing_settings["smoothing_ratio_eye"]))
            self.right_stick_x_prev = _eye_x
            _eye_y = (self.right_stick_y_prev * self.smoothing_settings["smoothing_ratio_eye"]) + (self.right_stick_y * (1 - self.smoothing_settings["smoothing_ratio_eye"]))
            self.right_stick_y_prev = _eye_y
            
            self.servos["right_eye_horizontal"].angle = map_values(
                _eye_x,
                -32767,
                32767,
                self.servo_info["right_eye_horizontal"]["center_angle"] - self.servo_info["right_eye_horizontal"]["angle_span"] / 2,
                self.servo_info["right_eye_horizontal"]["center_angle"] + self.servo_info["right_eye_horizontal"]["angle_span"] / 2
            )
            self.servos["left_eye_horizontal"].angle = map_values(
                _eye_x,
                -32767,
                32767,
                self.servo_info["left_eye_horizontal"]["center_angle"] - self.servo_info["left_eye_horizontal"]["angle_span"] / 2,
                self.servo_info["left_eye_horizontal"]["center_angle"] + self.servo_info["left_eye_horizontal"]["angle_span"] / 2
            )
            self.servos["right_eye_vertical"].angle = map_values(
                _eye_y,
                -32767,
                32767,
                self.servo_info["right_eye_vertical"]["center_angle"] + self.servo_info["right_eye_vertical"]["angle_span"] / 2,
                self.servo_info["right_eye_vertical"]["center_angle"] - self.servo_info["right_eye_vertical"]["angle_span"] / 2
            )
            self.servos["left_eye_vertical"].angle = map_values(
                _eye_y,
                -32767,
                32767,
                self.servo_info["left_eye_vertical"]["center_angle"] - self.servo_info["left_eye_vertical"]["angle_span"] / 2,
                self.servo_info["left_eye_vertical"]["center_angle"] + self.servo_info["left_eye_vertical"]["angle_span"] / 2
            )
            # print(f"Left -- h: {self.servos['left_eye_horizontal'].angle}\tv: {self.servos['left_eye_vertical'].angle}\t\tRight -- h: {self.servos['right_eye_horizontal'].angle}\tv: {self.servos['right_eye_vertical'].angle}\r")

            #### EYELIDS / AUTONOMOUS BLINKING ####
            if self.get_idle_mode() & 1 == 1:
                if self.is_blinking:
                    blink_value = (self.get_blink_animation_value() * (2**16)) - 32767
                    self.handle_blink_input(blink_value)
                elif randint(0, 1000) < 5:
                    self.initiate_blink()

            
            #### NECK  / AUTONOMOUS BREATHING (+jaw) ####
            if self.left_stick_x > 100 or self.left_stick_x < -100 or self.left_stick_y > 100 or self.left_stick_y < -100:
                # Reset the countdown timer to re-initiate idle breathe mode
                self.idle_breath_countdown_zero = time.monotonic()
            
            # Check for breathing idle mode
            if self.get_idle_mode() & 0b10 == 0b10:
                # t should be equal to zero at the moment the idle countdown is zero
                t = time.monotonic() - self.idle_breath_countdown_zero - self.idle_timeout_seconds
                _neck_y = self.breath_neck_half_amplitude * np.sin(t * 2 * np.pi / self.breath_period_seconds)
                _neck_x = 0
                
                # Also move the JAW with autonomous breathing
                jaw_input_value = self.breath_jaw_center_value - self.breath_jaw_half_amplitude * np.sin(t * 2 * np.pi / self.breath_period_seconds)
                self.handle_jaw_input(jaw_input_value)
            else:
                # Apply smoothing to the neck, if not in idle mode
                _neck_x = (self.left_stick_x_prev * self.smoothing_settings["smoothing_ratio_neck"]) + (self.left_stick_x * (1 - self.smoothing_settings["smoothing_ratio_neck"]))
                _neck_y = (self.left_stick_y_prev * self.smoothing_settings["smoothing_ratio_neck"]) + (self.left_stick_y * (1 - self.smoothing_settings["smoothing_ratio_neck"]))

            self.left_stick_x_prev = _neck_x
            self.left_stick_y_prev = _neck_y
            # print(f"_neck_x: {_neck_x}\tneck_x_prev: {self.left_stick_x_prev}\t_neck_y: {_neck_y}\tneck_y_prev: {self.left_stick_y_prev}\t")
            
            self.servos["neck_horizontal"].angle = map_values(
                _neck_x,
                -32767,
                32767,
                self.servo_info["neck_horizontal"]["center_angle"] + self.servo_info["neck_horizontal"]["angle_span"] / 2,
                self.servo_info["neck_horizontal"]["center_angle"] - self.servo_info["neck_horizontal"]["angle_span"] / 2
            )
            self.servos["neck_vertical"].angle = map_values(
                _neck_y,
                -32767,
                32767,
                self.servo_info["neck_vertical"]["center_angle"] + self.servo_info["neck_vertical"]["angle_span"] / 2,
                self.servo_info["neck_vertical"]["center_angle"] - self.servo_info["neck_vertical"]["angle_span"] / 2,
                clamp_min=self.servo_info["neck_vertical"]["min_angle"]
            )
            # print(f"Neck -- h: {self.servos['neck_horizontal'].angle}\tv: {self.servos['neck_vertical'].angle}\r")
            
            # print("Idle mode: ", "{0:b}".format(self.get_idle_mode()))
            
            #### TAIL ####
            t = time.monotonic()
            self.servos["tail"].angle = constrain(
                self.servo_info["tail"]["center_angle"] + self.tail_half_amplitude * np.sin(t * 2 * np.pi / self.tail_period_seconds)
            )
            # print(f"Tail -- {self.servos['tail'].angle}\r")

            # Finally, ensure at least 5ms go by before this thread continues
            time.sleep(5 / 1000.)
    
    def on_triangle_press(self):
        self.triangle_is_pressed = True
    
    def on_triangle_release(self):
        self.triangle_is_pressed = False
    
    def on_circle_press(self):
        self.circle_is_pressed = True
    
    def on_circle_release(self):
        self.circle_is_pressed = False
        
    def on_square_press(self):
        self.square_is_pressed = True
    
    def on_square_release(self):
        self.square_is_pressed = False
        
    def on_x_press(self):
        self.cross_is_pressed = True
    
    def on_x_release(self):
        self.cross_is_pressed = False
    
    def on_options_press(self):
        self.options_is_pressed = True
    
    def on_options_release(self):
        self.options_is_pressed = False
        
    def on_playstation_button_press(self):
        self.playstation_button_is_pressed = True
    
    def on_playstation_button_release(self):
        self.playstation_button_is_pressed = False
        
    def set_servos_calibration_ready(self):
        for servo_name in self.servo_info.keys():
            if self.servo_info[servo_name].get("min_angle", None) is not None and self.servo_info[servo_name].get("max_angle", None) is not None:
                    # Set eyelids to open/resting and jaw to closed/resting (min angle)
                    self.servos[servo_name].angle = self.servo_info[servo_name].get("min_angle")
            if self.servo_info[servo_name].get("center_angle", None) is not None:
                self.servos[servo_name].angle = self.servo_info[servo_name].get("center_angle")
                

    def on_R2_press(self, value):
        if not self.is_blinking:
            self.handle_blink_input(value)
            
            # Reset the countdown timer to re-initiate idle blink mode
            self.idle_blink_countdown_zero = time.monotonic()
        
    def handle_blink_input(self, value):
        """Fine Eylid Control"""
        right_lid_angle = map_values(
            value,
            -32767,
            32767,
            self.servo_info["right_eyelid"]["min_angle"],
            self.servo_info["right_eyelid"]["max_angle"],
            clamp=True
        )
        left_lid_angle = map_values(
            value,
            -32767,
            32767,
            self.servo_info["left_eyelid"]["min_angle"],
            self.servo_info["left_eyelid"]["max_angle"],
            clamp=True
        )
        # print(f"Raw: {value}\tRight: {right_lid_angle}\tLeft: {left_lid_angle}\tEyelids Raised: {self.raised_eyelids}")
        if not self.raised_eyelids:
            self.servos["right_eyelid"].angle = right_lid_angle
            self.servos["left_eyelid"].angle = left_lid_angle
    
    def on_R2_release(self):
        """Release Eyelids: fine control"""
        if not self.raised_eyelids:
            self.on_R1_release()

    def on_R1_press(self):
        """Eyelid raised gesture"""
        self.raised_eyelids = True
        self.servos["right_eyelid"].angle = self.servo_info["left_eyelid"]["min_angle"] - 20
        self.servos["left_eyelid"].angle = self.servo_info["left_eyelid"]["min_angle"] - 20
        
        # Reset the countdown timer to re-initiate idle blink mode
        self.idle_blink_countdown_zero = time.monotonic()

    def on_R1_release(self):
        """Release Eyelids to Neutral"""
        self.raised_eyelids = False
        self.servos["right_eyelid"].angle = self.servo_info["right_eyelid"]["min_angle"]
        self.servos["left_eyelid"].angle = self.servo_info["left_eyelid"]["min_angle"]

    def on_L2_press(self, value):
        self.jaw_controller_priority = True
        
        # Reset the countdown timer to re-initiate idle breathe mode
        self.idle_breath_countdown_zero = time.monotonic()
        
        self.handle_jaw_input(value)

    def handle_jaw_input(self, value):
        """Jaw Control"""
        jawAngle = map_values(
            value,
            -32767,
            32767,
            self.servo_info["jaw"]["min_angle"],
            self.servo_info["jaw"]["max_angle"],
            clamp=True
        )
        self.servos["jaw"].angle = jawAngle
            
    def on_L2_release(self):
        """Release Jaw to Neutral"""
        self.servos["jaw"].angle = self.servo_info["jaw"]["min_angle"]
        self.jaw_controller_priority = False
        

class SupressStdoutStderr(object):
    """
    A context manager for doing a "deep suppression" of stdout and stderr in 
    Python, i.e. will suppress all print, even if the print originates in a 
    compiled C/Fortran sub-function.
       This will not suppress raised exceptions, since exceptions are printed
    to stderr just before a script exits, and after the context manager has
    exited (at least, I think that is why it lets exceptions through).
    
    from:
    https://stackoverflow.com/questions/11130156/suppress-stdout-stderr-print-from-python-functions      
    """
    def __init__(self):
        # Open a pair of null files
        self.null_fds =  [os.open(os.devnull, os.O_RDWR) for x in range(2)]
        # Save the actual stdout (1) and stderr (2) file descriptors.
        self.save_fds = [os.dup(1), os.dup(2)]

    def __enter__(self):
        # Assign the null pointers to stdout and stderr.
        os.dup2(self.null_fds[0],1)
        os.dup2(self.null_fds[1],2)

    def __exit__(self, *_):
        # Re-assign the real stdout/stderr back to (1) and (2)
        os.dup2(self.save_fds[0],1)
        os.dup2(self.save_fds[1],2)
        # Close all file descriptors
        for fd in self.null_fds + self.save_fds:
            os.close(fd)


def map_values(value, in_min, in_max, out_min, out_max, clamp=False, clamp_min=None, clamp_max=None):
    slope = (out_max - out_min) / (in_max - in_min)
    intercept = out_min - (slope * in_min)
    out = (slope * value) + intercept
    if clamp or clamp_min or clamp_max:
        clamp_min = min(out_max, out_min) if clamp_min is None else clamp_min
        clamp_max = max(out_max, out_min) if clamp_max is None else clamp_max
        out = max(clamp_min, min(out, clamp_max))
    return out

def constrain(value, minimum=0, maximum=180):
    return max(min(minimum, maximum), min(value, max(minimum, maximum)))

# Create the I2C bus interface.
i2c = board.I2C()  # uses board.SCL and board.SDA

# Servo Interface Board
pca = PCA9685(i2c)

# Set the PWM frequency to 60hz.
pca.frequency = 60

controller = LunaController(pca, interface="/dev/input/js0", connecting_using_ds4drv=False)
try:
    controller.listen(timeout=300)
finally:
    # the listen() function annoyingly uses exit(1) internally, so we need to do any cleanup here
    pca.deinit()
    exit(1)
