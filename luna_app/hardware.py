import math
import queue
import time


class Servos:
    def __init__(self, mapping):
        import board
        from adafruit_motor.servo import Servo
        from adafruit_pca9685 import PCA9685

        self.bus = board.I2C()
        self.pca = PCA9685(self.bus)
        self.pca.frequency = 60
        self.servos = {
            name: Servo(self.pca.channels[entry["channel"]], actuation_range=180)
            for name, entry in mapping.items()
        }
        self.last = {}
        for motor in self.servos.values():
            motor.angle = None

    def write(self, angles):
        for name, angle in angles.items():
            if self.last.get(name, object()) != angle:
                self.servos[name].angle = angle
                self.last[name] = angle

    def close(self):
        for motor in self.servos.values():
            motor.angle = None
        self.pca.deinit()
        self.bus.deinit()


class Microphone:
    def __init__(self, settings):
        self.settings = settings
        self.samples = queue.Queue(maxsize=1)
        self.stream = None
        self.audio = None
        self.last_sample = time.monotonic()
        try:
            import numpy as np
            import pyaudio
            from scipy import signal

            self.audio = pyaudio.PyAudio()
            index = next((i for i in range(self.audio.get_device_count())
                          if settings["mic_name"].casefold() in
                          self.audio.get_device_info_by_index(i)["name"].casefold()
                          and self.audio.get_device_info_by_index(i)["maxInputChannels"] > 0), None)
            if index is None:
                print("Configured microphone not detected; manual jaw and idle remain available.")
                return
            sos = signal.butter(6, 5000, "lp", fs=settings["rate"], output="sos")
            zi = signal.sosfilt_zi(sos) * 0

            def callback(data, count, timing, flags):
                nonlocal zi
                # Float conversion avoids int16 overflow when calculating loudness.
                values = np.frombuffer(data, dtype=np.int16).astype(np.float64)
                filtered, zi = signal.sosfilt(sos, values, zi=zi)
                rms = np.sqrt(np.mean(filtered * filtered)) / 65536
                db = 20 * math.log10(rms) if rms > 0 else -90
                lo, hi = settings["mic_threshold_low"], settings["mic_threshold_hi"]
                sample = (max(0, min(1, (db - lo) / (hi - lo))), db > lo)
                try:
                    self.samples.get_nowait()
                except queue.Empty:
                    pass
                self.samples.put_nowait(sample)
                return None, pyaudio.paContinue

            self.stream = self.audio.open(
                format=pyaudio.paInt16, channels=settings["channels"],
                rate=settings["rate"], input=True, output=False,
                input_device_index=index, frames_per_buffer=settings["chunk"],
                stream_callback=callback)
        except (OSError, ValueError) as error:
            print(f"Microphone unavailable: {error}")
            self.close()

    def poll(self, control):
        try:
            value, speaking = self.samples.get_nowait()
            self.last_sample = time.monotonic()
            control.microphone(value, speaking)
        except queue.Empty:
            if self.stream and time.monotonic() - self.last_sample > 1:
                control.microphone(0, False, present=False)

    def close(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.audio:
            self.audio.terminate()
            self.audio = None
