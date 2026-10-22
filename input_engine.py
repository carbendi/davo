"""Device state machine. No GUI, hardware, networking, or OS imports."""

import copy
import time


class InputEngine:
    def __init__(self, config, perform, press, release, changed=lambda: None, clock=time.monotonic):
        self.config, self.perform = config, perform
        self.press, self.release, self.changed, self.clock = press, release, changed, clock
        self.physical = set()
        self.active = {}
        self.refs = {}
        self.latched = {}
        self.stack = ['default']
        self.temporary_layers = {}
        self.temporary_dials = {}
        self.dial_override = None
        self.pending_taps = {}
        self.paused = False
        self.accum = {}
        self.last_turn = 0.0
        self.last_shuttle = 0.0

    @property
    def layer(self):
        candidates = list(self.temporary_layers.values()) + list(reversed(self.stack))
        if self.temporary_layers:
            candidates = list(reversed(list(self.temporary_layers.values()))) + list(reversed(self.stack))
        return next((lid for lid in candidates if lid in self.config['layers']), 'default')

    def mapping(self, button):
        return copy.deepcopy(self.config['layers'].get(self.layer, {}).get('buttons', {}).get(button, {'action': 'none'}))

    def keys(self, keys, down):
        tokens = list(dict.fromkeys(k.strip().lower() for k in keys.split('+') if k.strip()))
        for key in tokens if down else reversed(tokens):
            count = self.refs.get(key, 0)
            if down:
                if not count:
                    self.press(key)
                self.refs[key] = count + 1
            elif count:
                if count == 1:
                    self.release(key)
                    self.refs.pop(key, None)
                else:
                    self.refs[key] = count - 1

    def reset(self):
        for key in list(self.refs):
            self.release(key)
        self.refs.clear()
        self.active.clear()
        self.latched.clear()
        self.pending_taps.clear()
        self.stack = ['default']
        self.temporary_layers.clear()
        self.temporary_dials.clear()
        self.dial_override = None
        self.accum.clear()
        # Keep physical state: buttons held across a profile change must be
        # released before they can trigger an action in the new profile.
        self.changed()

    def disconnected(self):
        self.reset()
        self.physical.clear()

    def keys_changed(self, buttons):
        buttons = set(buttons)
        released, pressed = self.physical - buttons, buttons - self.physical
        self.physical = buttons
        now = self.clock()
        for button in sorted(released):
            state = self.active.pop(button, None)
            if state:
                if not state['defer'] or state.get('long_fired'):
                    self._release_action(button, state.get('fired', state['action']))
                if state['defer'] and not state.get('long_fired'):
                    mapping = state['action']
                    double = mapping.get('double_press', {})
                    previous = self.pending_taps.pop(button, None)
                    if previous and now <= previous[0]:
                        self._tap(button, double)
                    elif double.get('action', 'none') != 'none':
                        if previous:
                            self._tap(button, previous[1])
                        self.pending_taps[button] = (now + 0.3, mapping)
                    else:
                        self._tap(button, mapping)
        for button in sorted(pressed):
            if self.paused and self.mapping(button).get('action') != 'pause':
                continue
            mapping = self.mapping(button)
            deferred = any(mapping.get(k, {}).get('action', 'none') != 'none' for k in ('long_press', 'double_press'))
            self.active[button] = {'action': mapping, 'time': now, 'defer': deferred}
            if not deferred:
                self.execute(button, mapping)
        self.changed()

    def tick(self):
        now = self.clock()
        for button, state in list(self.active.items()):
            long = state['action'].get('long_press', {})
            if state['defer'] and not state.get('long_fired') and now-state['time'] >= 0.5 and long.get('action', 'none') != 'none':
                self.pending_taps.pop(button, None)
                state.update(long_fired=True, fired=long)
                self.execute(button, long)
        for button, (deadline, action) in list(self.pending_taps.items()):
            if now >= deadline and button not in self.physical:
                self.pending_taps.pop(button, None)
                self._tap(button, action)

    def _tap(self, button, action):
        self.execute(button, action)
        self._release_action(button, action)

    def _release_action(self, button, action):
        if action.get('action') == 'hold_key':
            self.keys(action.get('keys', ''), False)
        if action.get('action') == 'overlay_hold':
            self.perform({'action': 'hide_overlay'})
        self.temporary_layers.pop(button, None)
        self.temporary_dials.pop(button, None)
        self.accum.clear()

    def execute(self, button, action):
        kind = action.get('action', 'none')
        if kind == 'hold_key':
            self.keys(action.get('keys', ''), True)
        elif kind == 'toggle_hold':
            if button in self.latched:
                self.keys(self.latched.pop(button), False)
            else:
                keys = action.get('keys', '')
                self.keys(keys, True)
                self.latched[button] = keys
        elif kind in ('layer_push', 'layer_hold'):
            target = action.get('layer', '')
            if target in self.config['layers']:
                if kind == 'layer_hold':
                    self.temporary_layers[button] = target
                elif len(self.stack) < 32:
                    self.stack.append(target)
                self.accum.clear()
        elif kind == 'layer_pop':
            if len(self.stack) > 1:
                self.stack.pop()
            self.accum.clear()
        elif kind in ('dial_mode', 'dial_hold'):
            mode = action.get('mode', 'normal')
            if kind == 'dial_hold':
                self.temporary_dials[button] = copy.deepcopy(action)
            elif mode == 'normal' or self.dial_override == action:
                self.dial_override = None
            else:
                self.dial_override = copy.deepcopy(action)
            self.accum.clear()
        elif kind == 'release_all':
            self.reset()
        elif kind == 'pause':
            self.reset()
            self.paused = not self.paused
        elif kind != 'none':
            self.perform(copy.deepcopy(action))
        self.changed()

    def dial_source(self):
        if self.temporary_dials:
            return next(reversed(self.temporary_dials.values()))
        return self.dial_override or self.config['layers'].get(self.layer, {}).get('dial_default', {'action': 'sys_vol', 'hw_mode': 'Jog', 'sensitivity': 100})

    def jog(self, mode, value):
        if self.paused or not value:
            return
        now = self.clock()
        source = self.dial_source()
        if source.get('hw_mode', 'Jog').lower() != mode:
            return
        sensitivity = max(0, min(100, int(source.get('sensitivity', 100))))
        if not sensitivity:
            return
        if mode == 'shuttle' and now-self.last_shuttle < 0.08:
            return
        if mode == 'shuttle':
            self.last_shuttle = now
        sign = 1 if value > 0 else -1
        threshold = max(1, round(20*(100-sensitivity)/100))
        if source.get('acceleration', False) and now-self.last_turn < 0.04:
            multiplier = 3
        else:
            multiplier = 1
        self.last_turn = now
        current = self.accum.get(mode, 0)
        current = 0 if current*sign < 0 else current
        current += sign
        if abs(current) < threshold:
            self.accum[mode] = current
            return
        self.accum[mode] = current - threshold*sign
        kind = source.get('mode') or source.get('action', 'sys_vol')
        for _ in range(multiplier):
            if kind in ('hotkeys', 'normal'):
                direction = 'right' if sign > 0 else 'left'
                action = source.get(direction) or self.config['layers'].get(self.layer, {}).get('dial', {}).get(mode, {}).get(direction, {'action': 'none'})
                if isinstance(action, str):
                    action = {'action': 'hotkey', 'keys': action}
                self.perform(copy.deepcopy(action))
            else:
                self.perform(dict(source, action='dial_step', mode=kind, direction=sign))
