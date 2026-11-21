import copy
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

from luna_app.control import *
from luna_app.legacy_story import LegacyStory

ROOT = Path(__file__).resolve().parent.parent


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("calibration.json", "lunas_story_jaw_values.json"):
            shutil.copy2(ROOT / name, self.root / name)
        self.clock = Clock()
        self.c = Control(self.root, self.clock)

    def send(self, op, *payload, peer="phone"):
        self.c.command(bytes([1, op, *(x & 255 for x in payload)]), peer)

    def ready(self):
        self.c.confirmed = ALL_STEPS

    def advance(self, seconds, heartbeat=False):
        for _ in range(round(seconds / .02)):
            self.clock.advance(.02)
            if heartbeat:
                self.send(HEARTBEAT)
            self.c.tick()

    def test_new_pi_outputs_locked(self):
        self.assertTrue(all(v is None for v in self.c.tick().values()))
        self.send(CLAIM)
        self.send(INPUT, 100, 0, 0, 0, 0, 0, 0)
        self.assertEqual(self.c.error, 3)

    def test_explicit_claim_required(self):
        self.ready()
        self.send(INPUT, 100, 0, 0, 0, 0, 0, 0)
        self.assertEqual(self.c.owner, 0)
        self.assertEqual(self.c.inputs, [0] * 7)
        self.send(CLAIM)
        self.send(INPUT, 100, 0, 0, 0, 0, 0, 0)
        self.assertEqual(self.c.inputs[0], 1)

    def test_disconnect_forces_idle_and_mic_and_stops_story(self):
        self.ready()
        self.c.microphone_found()
        self.send(CLAIM)
        self.send(MIC, 0)
        self.send(IDLE, 0)
        self.send(STORY, 1)
        self.c.disconnect("phone")
        self.assertEqual(self.c.owner, 0)
        self.assertTrue(self.c.mic_enabled)
        self.assertTrue(self.c.idle_enabled)
        self.assertFalse(self.c.story.active)
        self.assertEqual(self.c.inputs, [0] * 7)

    def test_watchdog_works_even_if_no_disconnect_callback(self):
        self.ready()
        self.send(CLAIM)
        self.send(INPUT, 100, 100, 100, 100, 100, 100, 1)
        self.advance(1)
        self.assertEqual(self.c.owner, 0)
        self.assertEqual(self.c.inputs, [0] * 7)

    def test_heartbeat_does_not_reclaim_after_timeout(self):
        self.send(CLAIM)
        self.advance(1)
        self.send(HEARTBEAT)
        self.assertEqual(self.c.owner, 0)
        self.send(CLAIM)
        self.assertEqual(self.c.owner, 1)

    def test_other_peer_cannot_move_or_disconnect_owner(self):
        self.ready()
        self.send(CLAIM)
        self.send(CLAIM, peer="other")
        self.assertEqual(self.c.error, 6)
        self.c.disconnect("other")
        self.assertEqual(self.c.owner, 1)
        self.send(RELEASE, peer="other")
        self.assertEqual(self.c.owner, 1)

    def test_invalid_frames_do_not_change_inputs(self):
        self.ready()
        self.send(CLAIM)
        for frame in (b"", b"\x01", b"\x02\x04", b"\x01\xff", bytes([1, 4, 101, 0, 0, 0, 0, 0, 0])):
            self.c.command(frame, "phone")
            self.assertEqual(self.c.error, 1)
            self.assertEqual(self.c.inputs, [0] * 7)

    def test_calibration_powers_one_joint_and_nudges_half_degree(self):
        self.send(CLAIM)
        self.send(CAL_BEGIN, 0)
        original = self.c.cal_angle
        self.send(CAL_NUDGE, 1)
        self.assertEqual(self.c.cal_angle, original + .5)
        output = self.c.tick()
        self.assertEqual(sum(v is not None for v in output.values()), 1)
        self.assertEqual(output["left_eye_horizontal"], original + .5)

    def test_discard_does_not_save(self):
        before = (self.root / "calibration.json").read_bytes()
        self.send(CLAIM)
        self.send(CAL_BEGIN, 8)
        self.send(CAL_NUDGE, 1)
        self.send(CAL_CANCEL)
        self.assertEqual((self.root / "calibration.json").read_bytes(), before)
        self.assertEqual(self.c.confirmed, 0)

    def test_save_preserves_config_and_backup_and_reload(self):
        before = copy.deepcopy(self.c.config)
        self.send(CLAIM)
        self.send(CAL_BEGIN, 0)
        self.send(CAL_NUDGE, 1)
        self.send(CAL_SAVE)
        self.assertEqual(json.loads((self.root / "calibration.before-app.json").read_text()), before)
        self.assertEqual(self.c.mapping["left_eye_horizontal"]["center_angle"],
                         before["servo_mapping"]["left_eye_horizontal"]["center_angle"] + .5)
        self.assertEqual(self.c.config["audio_input_settings"], before["audio_input_settings"])
        self.assertEqual(Control(self.root, self.clock).confirmed, 1)

    def test_external_calibration_change_requires_recheck(self):
        self.test_save_preserves_config_and_backup_and_reload()
        config = json.loads((self.root / "calibration.json").read_text())
        config["servo_mapping"]["jaw"]["min_angle"] += 1
        (self.root / "calibration.json").write_text(json.dumps(config))
        self.assertEqual(Control(self.root, self.clock).confirmed, 0)

    def test_dry_run_cannot_confirm_real_hardware(self):
        before = (self.root / "calibration.json").read_bytes()
        self.c = Control(self.root, self.clock, dry_run=True)
        self.test_each_step_required()
        self.assertEqual((self.root / "calibration.json").read_bytes(), before)
        self.assertFalse((self.root / "app-calibration.json").exists())
        self.assertFalse(Control(self.root, self.clock).ready)

    def test_each_step_required(self):
        self.send(CLAIM)
        for step in range(len(STEPS)):
            self.send(CAL_BEGIN, step)
            self.send(CAL_SAVE)
            self.assertEqual(self.c.ready, step == len(STEPS) - 1)

    def test_disconnect_discards_active_adjustment(self):
        self.send(CLAIM)
        self.send(CAL_BEGIN, 0)
        self.send(CAL_NUDGE, 1)
        self.c.disconnect("phone")
        self.assertIsNone(self.c.cal_step)
        self.assertEqual(self.c.confirmed, 0)
        self.assertTrue(all(v is None for v in self.c.tick().values()))

    def test_microphone_startup_absence_and_loss(self):
        self.assertFalse(self.c.mic_enabled)
        self.send(CLAIM)
        self.send(MIC, 1)
        self.assertEqual(self.c.error, 5)
        self.c.microphone_found()
        self.assertTrue(self.c.mic_enabled)
        self.c.microphone(0, False, present=False)
        self.c.neutral()
        self.assertFalse(self.c.mic_enabled)

    def test_manual_jaw_has_priority_then_microphone_takes_over(self):
        self.ready()
        self.c.microphone_found()
        self.send(CLAIM)
        self.c.microphone(.2, True)
        self.send(INPUT, 0, 0, 0, 0, 100, 0, 0)
        self.advance(.1, heartbeat=True)
        manual = self.c.outputs["jaw"]
        self.send(INPUT, 0, 0, 0, 0, 0, 0, 0)
        self.c.microphone(.2, True)
        self.advance(.1, heartbeat=True)
        self.assertLess(abs(manual - self.c.mapping["jaw"]["max_angle"]),
                        abs(self.c.outputs["jaw"] - self.c.mapping["jaw"]["max_angle"]))

    def test_held_stick_does_not_become_idle(self):
        self.ready()
        self.send(CLAIM)
        self.send(INPUT, 100, 100, 0, 0, 0, 0, 0)
        self.advance(7, heartbeat=True)
        self.assertFalse(self.c.was_breathing)

    def test_neutral_preserves_breathing_and_tail_periods(self):
        self.ready()
        self.c.neutral()
        self.advance(2)
        self.assertTrue(self.c.was_breathing)
        self.assertGreater(abs(self.c.outputs["neck_vertical"] - self.c.mapping["neck_vertical"]["center_angle"]), .1)
        self.assertGreater(abs(self.c.outputs["tail"] - self.c.mapping["tail"]["center_angle"]), .1)
        self.assertGreater(abs(self.c.outputs["jaw"] - self.c.mapping["jaw"]["min_angle"]), .1)

    def test_mic_speech_interrupts_breathing_without_phone(self):
        self.ready()
        self.c.microphone_found()
        self.advance(2)
        self.c.microphone(1, True)
        self.advance(.04)
        self.assertFalse(self.c.was_breathing)

    def test_ps4_exclusive_takeover_and_phone_return(self):
        self.ready()
        self.send(CLAIM)
        self.c.ps4_claim()
        self.assertEqual(self.c.owner, 2)
        self.c.ps4_input(0, .5)
        self.assertEqual(self.c.inputs[0], .5)
        self.send(INPUT, 100, 0, 0, 0, 0, 0, 0)
        self.assertEqual(self.c.inputs[0], .5)
        self.send(CLAIM)
        self.c.ps4_input(0, 1)
        self.assertEqual(self.c.inputs[0], 0)

    def test_status_fits_default_ble_payload(self):
        status = self.c.status()
        self.assertEqual(len(status), 13)
        self.assertEqual(struct.unpack("<BBBBBBhBBHB", status)[5:7], (255, -1))

    def test_all_angles_within_electrical_limits(self):
        self.ready()
        self.send(CLAIM)
        for sign in (-100, 100):
            self.send(INPUT, sign, sign, sign, sign, 100, 100, 1)
            self.advance(.5, heartbeat=True)
            self.assertTrue(all(0 <= v <= 180 for v in self.c.outputs.values()))

    def test_story_is_timed_jaw_only_and_finishes(self):
        story = LegacyStory(self.root / "lunas_story_jaw_values.json")
        story.start(10)
        self.assertEqual(story.sample(10), 0)
        self.assertEqual(story.sample(41.125), 1)
        self.assertIsNone(story.sample(351.4))
        self.assertFalse(story.active)


if __name__ == "__main__":
    unittest.main()
