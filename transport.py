"""Shortcut transport for editors with J/K/L playback. No OS or GUI imports."""

import copy


class Transport:
    BUTTONS = {'JOG': 'Jog', 'SHTL': 'Shuttle', 'SCRL': 'Scroll'}

    def __init__(self, perform):
        self.perform = perform
        self.source = None
        self.mode = 'Jog'
        self.level = 0
        self.playing = False
        self.neutral_required = False
        self.epoch = 0
        self.remainder = 0

    def configure(self, source):
        source = copy.deepcopy(source) if (source.get('mode') or source.get('action')) == 'transport' else None
        if source != self.source:
            self.stop()
            self.source = source
            self.mode = (source or {}).get('hw_mode', 'Jog')
            if self.mode not in self.BUTTONS.values():
                self.mode = 'Jog'
            self.remainder = 0
            self.epoch += 1
        return self.source is not None

    def send(self, shortcuts):
        return self.perform({'action': 'transport_keys', 'shortcuts': shortcuts,
                             'stop_only': shortcuts == [self.source.get('stop_key', 'k')],
                             'app': self.source.get('transport_app', 'Resolve.exe')}) is not False

    def stop(self, force=False):
        if self.source and (self.playing or force):
            self.send([self.source.get('stop_key', 'k')])
        self.level = 0
        self.playing = False

    def select(self, mode):
        self.stop()
        self.mode = mode
        self.remainder = 0
        self.neutral_required = False
        # Re-selecting SHTL deliberately establishes a new neutral position.
        self.epoch += 1

    def play_stop(self):
        if self.playing:
            self.stop()
        elif self.send([self.source.get('stop_key', 'k'), self.source.get('forward_key', 'l')]):
            self.playing = True
            self.level = 1
        self.neutral_required = True

    def suspend(self):
        self.stop()
        self.neutral_required = True
        self.remainder = 0

    def turn(self, mode, value):
        if mode != self.mode.lower():
            return
        source = self.source
        sensitivity = max(0, min(100, int(source.get('sensitivity', 100))))
        if not sensitivity:
            self.stop()
            return
        if mode == 'shuttle':
            deadzone = max(32, min(2048, int(source.get('deadzone', 256))))
            magnitude = abs(value)
            if magnitude <= deadzone:
                self.stop()
                self.neutral_required = False
                return
            if self.neutral_required:
                return
            width = max(128, int(source.get('shuttle_width', 768)))
            maximum = max(1, min(4, int(source.get('max_level', 4))))
            target = min(maximum, 1 + (magnitude - deadzone - 1) // width)
            target *= 1 if value > 0 else -1
            if target == self.level and self.playing:
                return
            # Hysteresis keeps jitter around a speed boundary from restarting playback.
            if self.level * target > 0 and abs(abs(target)-abs(self.level)) == 1:
                boundary = deadzone + min(abs(target), abs(self.level))*width
                if abs(magnitude-boundary) < 64:
                    return
            direction = source.get('forward_key', 'l') if target > 0 else source.get('reverse_key', 'j')
            if self.send([source.get('stop_key', 'k')] + [direction]*abs(target)):
                self.level, self.playing = target, True
            else:
                self.level, self.playing = 0, False
                self.neutral_required = True
        elif value:
            self.stop()
            # Device-relative units: use magnitude, retaining sub-frame motion.
            units = max(1, int(source.get('jog_units', 128))) * 100 / sensitivity
            if self.remainder * value < 0:
                self.remainder = 0
            self.remainder += value
            steps = min(20, int(abs(self.remainder) / units))
            if not steps:
                return
            sign = 1 if self.remainder > 0 else -1
            self.remainder -= sign * steps * units
            # Cap backlog after a large/faulty report instead of replaying it later.
            self.remainder = max(-units+1, min(units-1, self.remainder))
            if mode == 'scroll':
                steps = min(100, steps * max(1, min(20, int(source.get('scroll_frames', 10)))))
            shortcut = source.get('jog_right', 'right') if sign > 0 else source.get('jog_left', 'left')
            if not self.send([shortcut]*steps):
                self.remainder = 0
