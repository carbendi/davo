"""Check that profiles work locally without account modules or network access."""

import ast
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class AccountRemovalTests(unittest.TestCase):
    def test_account_modules_are_removed(self):
        self.assertFalse((ROOT / 'auth.py').exists())
        self.assertFalse((ROOT / 'cloud_sync.py').exists())
        for path in [*ROOT.glob('*.py'), *ROOT.glob('actions/*.py'),
                     *ROOT.glob('platform_layer/*.py')]:
            source = path.read_text(encoding='utf-8')
            self.assertNotIn('unbound-api', source, path.name)
            for node in ast.walk(ast.parse(source)):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or '']
                self.assertFalse(set(modules) & {'auth', 'cloud_sync', 'keyring', 'requests'},
                                 f'{path.name}: unexpected account dependency')


@unittest.skipUnless(importlib.util.find_spec('PyQt6'), 'GUI dependencies not installed')
class LocalProfilesGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        import app
        cls.application = app
        cls.qt = app.QApplication.instance() or app.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.application.cfg._deep_copy(self.application.cfg.DEFAULT_CONFIG)
        self.config['layers']['default']['buttons']['CUT'] = {
            'action': 'hotkey', 'keys': 'ctrl+s'}
        self.widget = self.application.SettingsTab(self.config)
        self.addCleanup(self.widget.deleteLater)

    def test_settings_do_not_connect_or_offer_account_controls(self):
        with patch('socket.socket.connect') as connect, patch('socket.create_connection') as create:
            widget = self.application.SettingsTab(self.config)
            try:
                groups = [group.title() for group in widget.findChildren(self.application.QGroupBox)]
                self.assertIn('Local profiles', groups)
                self.assertNotIn('Account', groups)
                labels = [button.text() for button in widget.findChildren(self.application.QPushButton)]
                self.assertNotIn('Sign In', labels)
                self.assertNotIn('Sync Now', labels)
                connect.assert_not_called()
                create.assert_not_called()
            finally:
                widget.deleteLater()

    def test_export_then_import_restores_layers_without_network(self):
        profile = self.root / 'profile.json'
        saved = self.root / 'config.json'
        with patch.object(self.application.QFileDialog, 'getSaveFileName', return_value=(str(profile), '')):
            self.widget._export_profile()
        self.assertEqual(json.loads(profile.read_text())['layers'], self.config['layers'])
        self.config['layers']['default']['buttons'].clear()
        changed = []
        self.widget.profile_loaded.connect(lambda: changed.append(True))
        with patch.object(self.application.QFileDialog, 'getOpenFileName', return_value=(str(profile), '')), \
             patch.object(self.application.QMessageBox, 'warning', return_value=self.application.QMessageBox.StandardButton.Ok), \
             patch.object(self.application.cfg, 'CONFIG_FILE', str(saved)), \
             patch('socket.socket.connect') as connect:
            self.widget._import_profile()
        self.assertEqual(self.config['layers']['default']['buttons']['CUT']['keys'], 'ctrl+s')
        self.assertTrue(saved.exists())
        self.assertEqual(changed, [True])
        connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
