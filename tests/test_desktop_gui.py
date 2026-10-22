import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('PyQt6'), 'GUI dependencies not installed')
class DesktopGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
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

    def test_all_action_editors_round_trip(self):
        from desktop_ui import ActionEditor
        actions = [{'action': 'hotkey', 'keys': 'ctrl+s'}, {'action': 'dial_hold', 'mode': 'horizontal', 'hw_mode': 'Shuttle'},
                   {'action': 'layer_hold', 'layer': 'default'}, {'action': 'text', 'text': 'hello'},
                   {'action': 'macro', 'repeat': 3, 'steps': [{'action': 'delay', 'ms': 100}]},
                   {'action': 'mouse', 'mode': 'left', 'count': 2}, {'action': 'app_mute', 'app': '@foreground'}]
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
