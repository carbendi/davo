import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_paths
import config


class ConfigStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'userdata' / 'config.json'
        self.legacy = self.root / 'old-install' / 'config.json'
        self.patchers = [patch.object(config, 'CONFIG_FILE', str(self.target)),
                         patch.object(config, 'legacy_config_file', return_value=self.legacy)]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')

    def sample(self, name='My layer'):
        return {'layers': {'custom': {'name': name, 'buttons': {
            'CUT': {'action': 'hotkey', 'keys': 'ctrl+s'}}}},
            'obs': {'host': 'localhost', 'port': 4455}}

    def test_migrates_legacy_without_modifying_original(self):
        self.write(self.legacy, self.sample('Türkçe'))
        original = self.legacy.read_bytes()
        loaded = config.load()
        self.assertEqual(loaded['layers']['custom']['name'], 'Türkçe')
        self.assertEqual(self.legacy.read_bytes(), original)
        self.assertEqual(json.loads(self.target.read_text(encoding='utf-8')), loaded)
        self.assertIn('default', loaded['layers'])

    def test_user_settings_take_precedence_over_old_app_folder(self):
        self.write(self.legacy, self.sample('Old'))
        self.write(self.target, self.sample('Current'))
        self.assertEqual(config.load()['layers']['custom']['name'], 'Current')

    def test_previous_valid_save_is_backed_up(self):
        config.save(self.sample('First'))
        config.save(self.sample('Second'))
        backup = json.loads(Path(str(self.target) + '.bak').read_text(encoding='utf-8'))
        self.assertEqual(backup['layers']['custom']['name'], 'First')
        self.assertEqual(config.load()['layers']['custom']['name'], 'Second')

    def test_corrupt_primary_recovers_without_destroying_backup(self):
        config.save(self.sample('First'))
        config.save(self.sample('Second'))
        self.target.write_text('{broken', encoding='utf-8')
        recovered = config.load()
        self.assertEqual(recovered['layers']['custom']['name'], 'First')
        config.save(recovered)
        self.assertEqual(config.load(), recovered)
        self.assertEqual(Path(str(self.target) + '.bak').read_text(encoding='utf-8'),
                         json.dumps(config._normalize(self.sample('First')), indent=2, ensure_ascii=False))
        corrupt = list(self.target.parent.glob('config.corrupt-*.json'))
        self.assertEqual(len(corrupt), 1)
        self.assertEqual(corrupt[0].read_text(encoding='utf-8'), '{broken')

    def test_failed_atomic_replace_leaves_original_usable(self):
        config.save(self.sample('Original'))
        replace = os.replace
        def fail_primary(src, dst):
            if Path(dst) == self.target:
                raise OSError('simulated interrupted save')
            return replace(src, dst)
        with patch.object(config.os, 'replace', side_effect=fail_primary):
            with self.assertRaises(OSError):
                config.save(self.sample('New'))
        self.assertEqual(config.load()['layers']['custom']['name'], 'Original')
        self.assertEqual(sorted(p.name for p in self.target.parent.iterdir()),
                         ['config.json', 'config.json.bak'])

    def test_invalid_config_is_preserved(self):
        self.write(self.target, {'layers': []})
        original = self.target.read_bytes()
        with self.assertRaises(RuntimeError):
            config.load()
        self.assertEqual(self.target.read_bytes(), original)

    def test_old_flat_button_format_migrates(self):
        self.write(self.legacy, {'buttons': {'CUT': {'action': 'hotkey', 'keys': 'x'}}})
        loaded = config.load()
        self.assertEqual(config.get_button(loaded, 'CUT')['keys'], 'x')

    def test_defaults_are_independent(self):
        first = config.load()
        first['layers']['default']['name'] = 'Changed'
        self.assertEqual(config.load()['layers']['default']['name'], 'Default')

    def test_windows_storage_is_outside_install_directory(self):
        with patch.object(app_paths.sys, 'platform', 'win32'), patch.dict(
                os.environ, {'LOCALAPPDATA': str(self.root / 'Local')}):
            self.assertEqual(app_paths.data_dir(), self.root / 'Local' / 'SpeedEditorCustomizer')


if __name__ == '__main__':
    unittest.main()
