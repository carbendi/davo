import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


@unittest.skipUnless(importlib.util.find_spec('PyQt6'), 'GUI dependencies not installed')
class DesktopGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        import traceback
        cls.slot_errors = []
        previous = sys.excepthook
        def report_slot_error(kind, error, trace):
            traceback.print_exception(kind, error, trace, file=sys.stdout)
            sys.stdout.flush()
            cls.slot_errors.append(error)
        sys.excepthook = report_slot_error
        cls.addClassCleanup(setattr, sys, 'excepthook', previous)
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.slot_errors.clear()
        import config
        from app import MainWindow
        from desktop_runtime import DesktopController
        from desktop_ui import DesktopTab
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = patch.object(config, 'CONFIG_FILE', str(Path(self.temp.name)/'config.json'))
        self.legacy = patch.object(config, 'legacy_config_file', return_value=Path(self.temp.name)/'absent.json')
        self.settings.start()
        self.legacy.start()
        self.addCleanup(self.settings.stop)
        self.addCleanup(self.legacy.stop)
        self.window = MainWindow()
        self.controller = DesktopController(self.window, smoke=True)
        self.window.controller = self.controller
        self.window.desktop_tab = DesktopTab(self.controller)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.controller.shutdown)

    def tearDown(self):
        self.assertEqual(self.slot_errors, [], 'Exception raised inside a Qt callback')

    def test_all_action_editors_round_trip(self):
        from desktop_ui import ActionEditor
        actions = [{'action': 'hotkey', 'keys': 'ctrl+s'}, {'action': 'dial_hold', 'mode': 'horizontal', 'hw_mode': 'Shuttle'},
                   {'action': 'layer_hold', 'layer': 'default'}, {'action': 'text', 'text': 'hello'},
                   {'action': 'macro', 'repeat': 3, 'steps': [{'action': 'delay', 'ms': 100}]},
                   {'action': 'mouse', 'mode': 'left', 'count': 2}, {'action': 'app_mute', 'app': '@foreground'},
                   {'action': 'audio_output', 'device_id': 'test-device', 'device_name': 'Test speakers'}]
        editor = ActionEditor([('default', 'Default')])
        for action in actions:
            editor.load(action)
            result = editor.value()
            for key, value in action.items():
                self.assertEqual(result[key], value, (action, result))

    def test_profile_switch_saves_previous_and_releases_keys(self):
        config = self.controller.config
        config['layers']['default']['buttons']['CUT'] = {'action': 'hold_key', 'keys': 'ctrl'}
        config['profiles']['test'] = {'name': 'Photoshop', 'exe': 'Photoshop.exe', 'layers': {'default': {'name': 'Brushes', 'buttons': {}}}}
        with patch.object(self.controller.engine, 'press') as press, patch.object(self.controller.engine, 'release') as release:
            self.controller.engine.keys_changed(['CUT'])
            self.controller.switch_profile('test')
            press.assert_called_once_with('ctrl')
            release.assert_called_once_with('ctrl')
        self.assertEqual(config['layers']['default']['name'], 'Brushes')
        self.assertIn('CUT', config['profiles']['default']['layers']['default']['buttons'])
        self.controller.switch_profile('default')
        self.assertIn('CUT', config['layers']['default']['buttons'])

    def test_macro_cancellation_stops_following_steps(self):
        generation = self.controller.generation
        with patch('desktop_runtime.hotkey.send', side_effect=lambda *a, **kw: self.controller.cancel_macros()) as send:
            self.controller.execute_worker({'action': 'macro', 'steps': [{'action': 'hotkey', 'keys': 'x'}, {'action': 'hotkey', 'keys': 'y'}]}, generation)
            self.assertEqual(send.call_count, 1)

    def test_named_profiles_persist_in_config(self):
        import config
        self.controller.config['profiles']['test'] = {'name': 'Test', 'exe': 'test.exe', 'layers': {'default': {'name': 'Default', 'buttons': {}}}}
        config.save(self.controller.config)
        loaded = config.load()
        self.assertEqual(loaded['profiles']['test']['exe'], 'test.exe')
        self.assertIn('desktop', loaded)

    def test_unified_editor_saves_gestures_and_custom_dial(self):
        panel = self.window.action_panel
        panel.load_button('CUT', self.controller.config)
        panel.editors[0].load({'action': 'hotkey', 'keys': 'x'})
        panel.editors[1].load({'action': 'hotkey', 'keys': 'y'})
        panel.save()
        saved = self.controller.config['layers']['default']['buttons']['CUT']
        self.assertEqual(saved['double_press']['keys'], 'y')
        panel.load_dial(self.controller.config)
        panel.dial.load({'action': 'hotkeys', 'left': {'keys': '['}, 'right': {'keys': ']'}})
        panel.save()
        self.assertEqual(self.controller.engine.dial_source()['action'], 'hotkeys')

    def test_transport_editor_round_trip(self):
        from desktop_ui import DialEditor
        editor = DialEditor()
        action = {'action': 'transport', 'hw_mode': 'Shuttle', 'transport_app': 'Resolve.exe',
                  'deadzone': 320, 'shuttle_width': 1024, 'jog_units': 256, 'max_level': 3,
                  'scroll_frames': 8, 'reverse_key': 'j', 'stop_key': 'k', 'forward_key': 'l'}
        editor.load(action)
        result = editor.value()
        for key, value in action.items():
            self.assertEqual(result[key], value)

    def test_focus_loss_never_sends_stop_into_another_application(self):
        controller = self.controller
        controller.config['layers']['default']['dial_default'] = {'action': 'transport', 'hw_mode': 'Shuttle'}
        editor = {'exe': 'Resolve.exe', 'hwnd': 1}
        other = {'exe': 'notepad.exe', 'hwnd': 2}
        with patch('desktop_runtime.windows_tools.foreground', return_value=editor) as foreground, patch.object(controller, 'send_shortcut') as send:
            controller.engine.jog('shuttle', 400)
            self.assertTrue(controller.engine.transport.playing)
            send.reset_mock()
            foreground.return_value = other
            controller.tick()
            send.assert_not_called()
            self.assertFalse(controller.engine.transport.playing)
            self.assertIn(('resolve.exe', 1), controller._pending_stops)
            foreground.return_value = editor
            controller.tick()
            send.assert_called_once_with('k')
            self.assertFalse(controller._pending_stops)

    def test_hardware_mode_leds_and_reconnect(self):
        from hid_layer import JogMode, JogLed, Led
        controller = self.controller
        controller.smoke = False
        self.addCleanup(setattr, controller, 'smoke', True)
        device = MagicMock()
        controller._device, controller._device_ready = device, True
        controller.config['layers']['default']['dial_default'] = {'action': 'transport'}
        controller.sync_hardware()
        device.set_jog_mode.assert_called_with(JogMode.RELATIVE)
        device.set_jog_leds.assert_called_with(JogLed.JOG)
        controller.engine.keys_changed(['SHTL'])
        device.set_jog_mode.assert_called_with(JogMode.ABSOLUTE_DEADZERO)
        device.set_jog_leds.assert_called_with(JogLed.SHTL)
        controller.engine.keys_changed([])
        count = device.set_jog_mode.call_count
        controller.engine.keys_changed(['SHTL'])
        self.assertEqual(device.set_jog_mode.call_count, count+1)
        controller.config['layers']['default']['buttons']['CUT'] = {'action': 'toggle_hold', 'keys': 'ctrl'}
        with patch.object(controller.engine, 'press'), patch.object(controller.engine, 'release'):
            controller.engine.keys_changed(['CUT'])
            controller.engine.keys_changed([])
            device.set_leds.assert_called_with(int(Led.CUT))
            controller.toggle_pause()
            device.set_leds.assert_called_with(0)
            device.set_jog_leds.assert_called_with(0)
        controller._hardware_state = None
        controller.sync_hardware()
        self.assertGreaterEqual(device.set_jog_mode.call_count, count+2)
