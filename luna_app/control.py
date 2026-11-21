"""Hardware-independent motion and ownership rules, driven at 50 Hz."""

import copy
import json
import math
from pathlib import Path
import random
import shutil
import struct
import time

from .legacy_story import LegacyStory

SERVICE_UUID = "41750001-71bd-4d43-8c75-326c756e6100"
COMMAND_UUID = "41750002-71bd-4d43-8c75-326c756e6100"
STATUS_UUID = "41750003-71bd-4d43-8c75-326c756e6100"
VERSION = 1
HEARTBEAT, CLAIM, RELEASE, INPUT, MIC, IDLE = range(1, 7)
CAL_BEGIN, CAL_NUDGE, CAL_SAVE, CAL_CANCEL, STORY = range(7, 12)

STEPS = [
    ("left_eye_horizontal", "center_angle", "Left eye · horizontal center"),
    ("left_eye_vertical", "center_angle", "Left eye · vertical center"),
    ("right_eye_horizontal", "center_angle", "Right eye · horizontal center"),
    ("right_eye_vertical", "center_angle", "Right eye · vertical center"),
    ("left_eyelid", "min_angle", "Left eyelid · open"),
    ("left_eyelid", "max_angle", "Left eyelid · closed"),
    ("right_eyelid", "min_angle", "Right eyelid · open"),
    ("right_eyelid", "max_angle", "Right eyelid · closed"),
    ("jaw", "min_angle", "Jaw · closed"),
    ("jaw", "max_angle", "Jaw · open"),
    ("neck_horizontal", "center_angle", "Neck · horizontal center"),
    ("neck_vertical", "center_angle", "Neck · vertical center"),
    ("tail", "center_angle", "Tail · center"),
]
ALL_STEPS = (1 << len(STEPS)) - 1
LENGTHS = {HEARTBEAT: 2, CLAIM: 2, RELEASE: 2, INPUT: 9,
           MIC: 3, IDLE: 3, CAL_BEGIN: 3, CAL_NUDGE: 3,
           CAL_SAVE: 2, CAL_CANCEL: 2, STORY: 3}
ERRORS = {0: "OK", 1: "Invalid command", 2: "Take control first",
          3: "Complete calibration first", 4: "Finish or cancel calibration",
          5: "No microphone detected", 6: "Another phone owns control"}


def blend(a, b, amount):
    return a + (b - a) * amount


def bound(value, low=0, high=180):
    return max(low, min(high, value))


class Control:
    def __init__(self, root, clock=time.monotonic, dry_run=False):
        self.root = Path(root)
        self.clock = clock
        self.dry_run = dry_run
        self.config = json.loads((self.root / "calibration.json").read_text())
        self.mapping = self.config["servo_mapping"]
        channels = [entry["channel"] for entry in self.mapping.values()]
        if len(channels) != len(set(channels)) or any(not 0 <= c < 16 for c in channels):
            raise ValueError("Servo channels must be unique and between 0 and 15")
        self.state_path = self.root / "app-calibration.json"
        self.confirmed = 0
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            # A changed calibration file must be rechecked on the actual robot.
            if state.get("servo_mapping") == self.mapping:
                self.confirmed = state.get("confirmed", 0) & ALL_STEPS
        self.story = LegacyStory(self.root / "lunas_story_jaw_values.json")
        self.owner = 0
        self.phone = None
        self.last_heartbeat = 0
        self.mic_present = False
        self.mic_enabled = False
        self.idle_enabled = True
        self.mic_value = 0
        self.voice_at = -100
        self.cal_step = None
        self.cal_angle = None
        self.error = 0
        self.last_opcode = 0
        self.inputs = [0.0] * 7
        self.smoothed = [0.0] * 4
        self.last_tick = self.clock()
        self.head_activity = self.last_tick - 5
        self.lid_activity = self.last_tick - 5
        self.blink_started = None
        self.was_breathing = False
        self.breath_started = self.last_tick
        self.breath_weight = 0.0
        self.jaw_angle = self.mapping["jaw"]["min_angle"]
        self.tail_angle = self.mapping["tail"]["center_angle"]
        self.lid_values = [self.mapping[name]["min_angle"]
                           for name in ("left_eyelid", "right_eyelid")]
        self.outputs = {name: None for name in self.mapping}

    @property
    def ready(self):
        return self.confirmed == ALL_STEPS

    def microphone(self, value, speaking, present=True):
        self.mic_present = present
        self.mic_value = bound(value, 0, 1) if present else 0
        if not present:
            self.mic_enabled = False
        if present and speaking and self.mic_enabled:
            self.voice_at = self.clock()

    def microphone_found(self):
        self.mic_present = True
        self.mic_enabled = True

    def neutral(self):
        self.owner = 0
        self.phone = None
        self.inputs = [0.0] * 7
        self.story.stop()
        self.cal_step = self.cal_angle = None
        self.idle_enabled = True
        self.mic_enabled = self.mic_present
        self.head_activity = self.clock() - 5
        self.lid_activity = self.clock() - 5

    def disconnect(self, peer):
        if self.owner == 1 and self.phone == peer:
            self.neutral()

    def command(self, packet, peer):
        self.error = 0
        if (len(packet) < 2 or packet[0] != VERSION
                or LENGTHS.get(packet[1]) != len(packet)):
            self.error = 1
            return
        opcode = packet[1]
        self.last_opcode = opcode
        if opcode == CLAIM:
            if self.owner == 1 and self.phone != peer:
                self.error = 6
                return
            if self.owner == 1:
                self.last_heartbeat = self.clock()
                return
            self.neutral()
            self.owner, self.phone = 1, peer
            self.last_heartbeat = self.clock()
            return
        if self.owner != 1 or self.phone != peer:
            if opcode != HEARTBEAT:
                self.error = 2
            return
        if opcode == HEARTBEAT:
            self.last_heartbeat = self.clock()
        elif opcode == RELEASE:
            self.neutral()
        elif opcode == INPUT:
            values = struct.unpack("<bbbbBBB", bytes(packet[2:]))
            if any(abs(v) > 100 for v in values[:4]) or any(v > 100 for v in values[4:6]) or values[6] > 1:
                self.error = 1
            elif not self.ready:
                self.error = 3
            elif self.cal_step is not None:
                self.error = 4
            else:
                self.set_inputs([v / 100 for v in values[:6]] + [values[6]])
        elif opcode in (MIC, IDLE, STORY):
            if packet[2] not in (0, 1):
                self.error = 1
            elif opcode == MIC:
                if packet[2] and not self.mic_present:
                    self.error = 5
                else:
                    self.mic_enabled = bool(packet[2])
            elif opcode == IDLE:
                self.idle_enabled = bool(packet[2])
            elif self.cal_step is not None:
                self.error = 4
            elif not self.ready:
                self.error = 3
            elif packet[2]:
                self.story.start(self.clock())
            else:
                self.story.stop()
        elif opcode == CAL_BEGIN:
            if packet[2] >= len(STEPS):
                self.error = 1
                return
            self.inputs = [0.0] * 7
            self.story.stop()
            self.cal_step = packet[2]
            joint, field, _ = STEPS[self.cal_step]
            self.cal_angle = self.mapping[joint][field]
        elif opcode == CAL_NUDGE:
            delta = struct.unpack("b", bytes(packet[2:]))[0]
            if self.cal_step is None or delta not in (-1, 1):
                self.error = 1
            else:
                self.cal_angle = bound(self.cal_angle + delta * 0.5)
        elif opcode == CAL_SAVE:
            if self.cal_step is None:
                self.error = 1
            else:
                self.save_step()
        elif opcode == CAL_CANCEL:
            self.cal_step = self.cal_angle = None

    def save_step(self):
        joint, field, _ = STEPS[self.cal_step]
        config_path = self.root / "calibration.json"
        backup = self.root / "calibration.before-app.json"
        updated = copy.deepcopy(self.config)
        updated["servo_mapping"][joint][field] = self.cal_angle
        if not self.dry_run:
            if not backup.exists():
                shutil.copy2(config_path, backup)
            self._write_json(config_path, updated)
        self.config = updated
        self.mapping = updated["servo_mapping"]
        self.confirmed |= 1 << self.cal_step
        if not self.dry_run:
            self._write_json(self.state_path, {"confirmed": self.confirmed,
                                              "servo_mapping": self.mapping})
        self.cal_step = self.cal_angle = None

    @staticmethod
    def _write_json(path, data):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n")
        temporary.replace(path)

    def set_inputs(self, values):
        self.inputs = list(values)
        if abs(values[0]) > 0.03 or abs(values[1]) > 0.03:
            self.head_activity = self.clock()
        if values[4] > 0:
            self.head_activity = self.clock()
        if values[5] > 0 or values[6]:
            self.lid_activity = self.clock()

    def ps4_claim(self):
        self.neutral()
        self.owner = 2

    def ps4_input(self, index, value):
        if self.owner == 2 and self.ready and self.cal_step is None:
            values = self.inputs.copy()
            values[index] = value
            self.set_inputs(values)

    def status(self):
        return struct.pack("<BBBBBBhBBHB", VERSION, self.owner,
                           self.mic_present, self.mic_enabled, self.idle_enabled,
                           255 if self.cal_step is None else self.cal_step,
                           -1 if self.cal_angle is None else round(self.cal_angle * 10),
                           self.error, self.last_opcode, self.confirmed,
                           int(self.story.active) | (int(self.dry_run) << 1))

    def tick(self):
        now = self.clock()
        dt = bound(now - self.last_tick, 0.001, 0.1)
        self.last_tick = now
        if self.owner == 1 and now - self.last_heartbeat > 0.9:
            self.neutral()
        if any(abs(v) > 0.03 for v in self.inputs[:2]) or self.inputs[4] > 0:
            self.head_activity = now
        if self.inputs[5] > 0 or self.inputs[6]:
            self.lid_activity = now
        if self.cal_step is not None:
            self.outputs = {name: None for name in self.mapping}
            self.outputs[STEPS[self.cal_step][0]] = self.cal_angle
            return self.outputs
        if not self.ready:
            self.outputs = {name: None for name in self.mapping}
            return self.outputs
        for i, target in enumerate(self.inputs[:4]):
            ratio = self.config["smoothing_settings"][
                "smoothing_ratio_neck" if i < 2 else "smoothing_ratio_eye"]
            self.smoothed[i] = blend(self.smoothed[i], target, 1 - ratio ** (dt / 0.005))
        speaking = self.mic_enabled and self.mic_present and now - self.voice_at < 0.15
        breathing = (self.idle_enabled and now - self.head_activity >= 5
                     and not speaking and self.inputs[4] == 0 and not self.story.active)
        if breathing and not self.was_breathing:
            self.breath_started = now
        self.was_breathing = breathing
        self.breath_weight = blend(self.breath_weight, float(breathing), 1 - math.exp(-dt * 3))
        wave = math.sin((now - self.breath_started) * 2 * math.pi / 6.5)
        neck_x = self.smoothed[0]
        neck_y = blend(self.smoothed[1], 35 / 128 * wave, self.breath_weight)
        angles = {}
        for name, entry in self.mapping.items():
            if "center_angle" not in entry:
                continue
            if name == "tail":
                offset = math.sin(now * 2 * math.pi / 5) if self.idle_enabled else 0
            elif name == "neck_horizontal":
                offset = -neck_x
            elif name == "neck_vertical":
                offset = -neck_y
            else:
                offset = self.smoothed[2 if "horizontal" in name else 3]
                if "vertical" in name:
                    offset *= -1
            angle = entry["center_angle"] + offset * entry["angle_span"] / 2
            if name == "neck_vertical":
                angle = max(entry["min_angle"], angle)
            if name == "tail":
                self.tail_angle = blend(self.tail_angle, angle, 1 - math.exp(-dt * 12))
                angle = self.tail_angle
            angles[name] = bound(angle)
        lid_value = self.inputs[5]
        if self.idle_enabled and now - self.lid_activity >= 5:
            if self.blink_started is None and random.random() < 1 - math.exp(-dt):
                self.blink_started = now
            if self.blink_started is not None:
                elapsed = now - self.blink_started
                lid_value = bound(min(elapsed / .1, (.25 - elapsed) / .1), 0, 1)
                if elapsed >= .25:
                    self.blink_started = None
        else:
            self.blink_started = None
        for index, name in enumerate(("left_eyelid", "right_eyelid")):
            entry = self.mapping[name]
            target = entry["min_angle"] - 20 if self.inputs[6] else blend(
                entry["min_angle"], entry["max_angle"], lid_value)
            self.lid_values[index] = blend(self.lid_values[index], bound(target), 1 - math.exp(-dt * 18))
            angles[name] = self.lid_values[index]
        story_value = self.story.sample(now)
        if story_value is not None:
            jaw = story_value
        elif self.inputs[4] > 0:
            jaw = self.inputs[4]
        elif self.mic_enabled and self.mic_present:
            jaw = self.mic_value if speaking else 0
            if breathing:
                jaw = (40 / 256 - 35 / 256 * wave) * self.breath_weight
        else:
            jaw = (40 / 256 - 35 / 256 * wave) * self.breath_weight
        entry = self.mapping["jaw"]
        target = blend(entry["min_angle"], entry["max_angle"], bound(jaw, 0, 1))
        self.jaw_angle = blend(self.jaw_angle, target, 1 - math.exp(-dt * 22))
        angles["jaw"] = bound(self.jaw_angle)
        self.outputs = angles
        return angles
