import unittest
from input_engine import InputEngine


class InputTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.actions, self.presses, self.releases = [], [], []
        self.config = {'layers': {'default': {'buttons': {}}, 'other': {'buttons': {}}}}
        self.engine = InputEngine(self.config, self.actions.append, self.presses.append,
                                  self.releases.append, clock=lambda: self.now)

    def bind(self, button, action, layer='default'):
        self.config['layers'][layer]['buttons'][button] = action

    def test_hold_releases_original_mapping_after_layer_change(self):
        self.bind('A', {'action': 'hold_key', 'keys': 'ctrl'})
        self.bind('B', {'action': 'layer_push', 'layer': 'other'})
        self.bind('A', {'action': 'hold_key', 'keys': 'alt'}, 'other')
        self.engine.keys_changed(['A'])
        self.engine.keys_changed(['A', 'B'])
        self.engine.keys_changed(['B'])
        self.assertEqual(self.releases, ['ctrl'])
        self.assertEqual(self.engine.layer, 'other')

    def test_shared_modifier_released_only_after_last_owner(self):
        for button in ('A', 'B'):
            self.bind(button, {'action': 'hold_key', 'keys': 'ctrl'})
        self.engine.keys_changed(['A', 'B'])
        self.engine.keys_changed(['B'])
        self.assertEqual(self.releases, [])
        self.engine.keys_changed([])
        self.assertEqual(self.presses, ['ctrl'])
        self.assertEqual(self.releases, ['ctrl'])

    def test_disconnect_releases_latched_and_held_keys(self):
        self.bind('A', {'action': 'toggle_hold', 'keys': 'alt'})
        self.bind('B', {'action': 'hold_key', 'keys': 'ctrl'})
        self.engine.keys_changed(['A', 'B'])
        self.engine.disconnected()
        self.assertCountEqual(self.releases, ['alt', 'ctrl'])
        self.assertFalse(self.engine.refs)

    def test_profile_reset_does_not_repress_physically_held_button(self):
        self.bind('A', {'action': 'hold_key', 'keys': 'ctrl'})
        self.engine.keys_changed(['A'])
        self.engine.reset()
        self.engine.keys_changed(['A'])
        self.assertEqual(self.presses, ['ctrl'])
        self.engine.keys_changed([])
        self.engine.keys_changed(['A'])
        self.assertEqual(self.presses, ['ctrl', 'ctrl'])

    def test_nested_momentary_layers_restore_in_order(self):
        self.bind('A', {'action': 'layer_hold', 'layer': 'other'})
        self.bind('B', {'action': 'layer_hold', 'layer': 'default'}, 'other')
        self.engine.keys_changed(['A'])
        self.assertEqual(self.engine.layer, 'other')
        self.engine.keys_changed(['A', 'B'])
        self.assertEqual(self.engine.layer, 'default')
        self.engine.keys_changed(['A'])
        self.assertEqual(self.engine.layer, 'other')
        self.engine.keys_changed([])
        self.assertEqual(self.engine.layer, 'default')

    def test_temporary_dial_preserves_shuttle_mode_and_restores(self):
        self.bind('A', {'action': 'dial_hold', 'mode': 'scroll', 'hw_mode': 'Shuttle', 'sensitivity': 100})
        self.engine.keys_changed(['A'])
        self.engine.jog('jog', 1)
        self.assertEqual(self.actions, [])
        self.engine.jog('shuttle', 1)
        self.assertEqual(self.actions[-1]['mode'], 'scroll')
        self.engine.keys_changed([])
        self.assertEqual(self.engine.dial_source()['action'], 'sys_vol')

    def test_custom_dial_hotkeys_execute_in_each_direction(self):
        self.config['layers']['default']['dial_default'] = {'action': 'hotkeys', 'left': {'action': 'hotkey', 'keys': '['}, 'right': {'action': 'hotkey', 'keys': ']'}}
        self.engine.jog('jog', -1)
        self.engine.jog('jog', 1)
        self.assertEqual([a['keys'] for a in self.actions], ['[', ']'])

    def test_disabled_dial_never_executes(self):
        self.config['layers']['default']['dial_default'] = {'action': 'sys_vol', 'sensitivity': 0}
        self.engine.jog('jog', 1)
        self.assertEqual(self.actions, [])

    def test_double_tap_executes_double_only(self):
        self.bind('A', {'action': 'hotkey', 'keys': 'x', 'double_press': {'action': 'hotkey', 'keys': 'y'}})
        self.engine.keys_changed(['A'])
        self.engine.keys_changed([])
        self.now += 0.1
        self.engine.keys_changed(['A'])
        self.engine.keys_changed([])
        self.now += 1
        self.engine.tick()
        self.assertEqual([a['keys'] for a in self.actions], ['y'])

    def test_single_tap_timeout_executes_snapshot(self):
        self.bind('A', {'action': 'hotkey', 'keys': 'x', 'double_press': {'action': 'hotkey', 'keys': 'y'}})
        self.engine.keys_changed(['A'])
        self.engine.keys_changed([])
        self.bind('A', {'action': 'hotkey', 'keys': 'z'})
        self.now += 0.31
        self.engine.tick()
        self.assertEqual([a['keys'] for a in self.actions], ['x'])

    def test_long_press_releases_its_own_key(self):
        self.bind('A', {'action': 'hotkey', 'keys': 'x', 'long_press': {'action': 'hold_key', 'keys': 'shift'}})
        self.engine.keys_changed(['A'])
        self.now += 0.51
        self.engine.tick()
        self.engine.keys_changed([])
        self.assertEqual(self.actions, [])
        self.assertEqual(self.presses, ['shift'])
        self.assertEqual(self.releases, ['shift'])

    def test_unused_deferred_hold_does_not_release_another_owner(self):
        self.bind('A', {'action': 'hold_key', 'keys': 'ctrl'})
        self.bind('B', {'action': 'none', 'long_press': {'action': 'hold_key', 'keys': 'ctrl'}})
        self.engine.keys_changed(['A', 'B'])
        self.engine.keys_changed(['A'])
        self.assertEqual(self.releases, [])

    def test_deleted_layer_falls_back(self):
        self.engine.stack.append('other')
        del self.config['layers']['other']
        self.assertEqual(self.engine.layer, 'default')

    def test_paused_engine_ignores_input(self):
        self.bind('A', {'action': 'hotkey', 'keys': 'x'})
        self.engine.paused = True
        self.engine.keys_changed(['A'])
        self.engine.jog('jog', 1)
        self.assertEqual(self.actions, [])

    def test_mapping_save_keeps_volume_selected_and_uses_new_sensitivity(self):
        self.bind('SHTL', {'action': 'dial_mode', 'mode': 'sys_vol', 'hw_mode': 'Jog', 'sensitivity': 75})
        self.engine.keys_changed(['SHTL'])
        self.engine.keys_changed([])
        self.bind('SHTL', {'action': 'dial_mode', 'mode': 'sys_vol', 'hw_mode': 'Jog', 'sensitivity': 30})
        self.engine.reload_mappings()
        self.assertEqual(self.engine.dial_source()['mode'], 'sys_vol')
        self.assertEqual(self.engine.dial_source()['sensitivity'], 30)
        for _ in range(14):
            self.engine.jog('jog', 1)
        self.assertEqual(self.actions[-1]['action'], 'dial_step')
        self.assertEqual(self.actions[-1]['mode'], 'sys_vol')
        self.engine.keys_changed(['SHTL'])
        self.assertIsNone(self.engine.dial_override)

    def test_mapping_save_preserves_layer_but_releases_held_keys(self):
        self.engine.stack.append('other')
        self.bind('A', {'action': 'hold_key', 'keys': 'ctrl'}, 'other')
        self.engine.keys_changed(['A'])
        self.engine.reload_mappings()
        self.assertEqual(self.engine.layer, 'other')
        self.assertEqual(self.releases, ['ctrl'])
        self.engine.keys_changed(['A'])
        self.assertEqual(self.presses, ['ctrl'])

    def test_mapping_save_drops_removed_dial_binding(self):
        self.bind('A', {'action': 'dial_mode', 'mode': 'brightness'})
        self.engine.keys_changed(['A'])
        self.engine.keys_changed([])
        self.bind('A', {'action': 'none'})
        self.engine.reload_mappings()
        self.assertIsNone(self.engine.dial_override)
        self.assertIsNone(self.engine.dial_override_owner)

    def test_mapping_save_updates_gesture_dial_binding(self):
        action = {'action': 'dial_mode', 'mode': 'sys_vol', 'sensitivity': 80}
        self.bind('A', {'action': 'none', 'long_press': action})
        self.engine.execute('A', action)
        self.config['layers']['default']['buttons']['A']['long_press']['sensitivity'] = 25
        self.engine.reload_mappings()
        self.assertEqual(self.engine.dial_source()['sensitivity'], 25)

    def test_mapping_save_keeps_transport_mode_but_stops_playback(self):
        self.config['layers']['default']['dial_default'] = {'action': 'transport'}
        self.engine.keys_changed(['SHTL'])
        self.engine.keys_changed([])
        self.engine.jog('shuttle', 400)
        self.engine.reload_mappings()
        self.assertEqual(self.engine.dial_source()['hw_mode'], 'Shuttle')
        self.assertFalse(self.engine.transport.playing)
        self.assertEqual(self.actions[-1]['shortcuts'], ['k'])
