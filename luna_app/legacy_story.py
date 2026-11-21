"""Removable legacy jaw timeline. No audio or video is played here."""

import bisect
import json


class LegacyStory:
    def __init__(self, path):
        self.points = json.loads(path.read_text())
        self.times = [point[0] for point in self.points]
        self.started = None

    @property
    def active(self):
        return self.started is not None

    def start(self, now):
        self.started = now

    def stop(self):
        self.started = None

    def sample(self, now):
        if not self.active:
            return None
        elapsed = now - self.started
        if elapsed >= self.times[-1]:
            self.stop()
            return None
        index = max(0, bisect.bisect_right(self.times, elapsed) - 1)
        return (self.points[index][1] + 32767) / 65534
