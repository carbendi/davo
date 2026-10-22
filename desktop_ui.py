"""Local desktop controls, typed action editors, and profile management."""

import copy
import os
import uuid

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QSpinBox, QCheckBox, QTabWidget, QDialog,
    QDialogButtonBox, QListWidget, QInputDialog, QMessageBox, QFileDialog,
    QPlainTextEdit, QScrollArea, QStackedWidget, QKeySequenceEdit)

import config as cfg
import windows_tools


class ShortcutInput(QWidget):
    def __init__(self, value='', parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.text = QLineEdit(value)
        self.text.setPlaceholderText('ctrl+shift+s')
        layout.addWidget(self.text)
        record = QPushButton('Record')
        record.clicked.connect(self.record)
        layout.addWidget(record)

    def record(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Press a shortcut')
        layout = QVBoxLayout(dialog)
        recorder = QKeySequenceEdit()
        recorder.setMaximumSequenceLength(1)
        layout.addWidget(recorder)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        recorder.setFocus()
        if dialog.exec():
            value = recorder.keySequence().toString(QKeySequence.SequenceFormat.PortableText).lower()
            for old, new in [('meta', 'win'), ('pgup', 'page_up'), ('pgdown', 'page_down'), ('backtab', 'tab'), ('del', 'delete'), ('return', 'enter')]:
                value = value.replace(old, new)
            if value.endswith('++'):
                value = value[:-1]+'plus'
            self.text.setText(value)


class DialEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        self.mode = QComboBox()
        for title, value in [('System volume', 'sys_vol'), ('Application volume', 'app_vol'), ('Brightness', 'brightness'), ('Custom shortcuts', 'hotkeys'), ('Vertical scroll', 'scroll'), ('Horizontal scroll', 'horizontal'), ('Zoom (+ / - shortcuts)', 'zoom')]:
            self.mode.addItem(title, value)
        self.hardware = QComboBox()
        self.hardware.addItems(['Jog', 'Shuttle', 'Scroll'])
        self.app = QLineEdit()
        self.app.setPlaceholderText('spotify.exe or @foreground')
        self.sensitivity = QSpinBox()
        self.sensitivity.setRange(0, 100)
        self.sensitivity.setValue(100)
        self.step = QSpinBox()
        self.step.setRange(1, 20)
        self.acceleration = QCheckBox('Faster turns make larger changes')
        self.left = ShortcutInput()
        self.right = ShortcutInput()
        form.addRow('Turn controls', self.mode)
        form.addRow('Hardware mode', self.hardware)
        form.addRow('Sensitivity', self.sensitivity)
        form.addRow('Scroll amount', self.step)
        form.addRow(self.acceleration)
        self.app_label = QLabel('Application')
        self.left_label, self.right_label = QLabel('Turn left'), QLabel('Turn right')
        form.addRow(self.app_label, self.app)
        form.addRow(self.left_label, self.left)
        form.addRow(self.right_label, self.right)
        self.mode.currentIndexChanged.connect(self.visibility)
        self.visibility()

    def visibility(self):
        mode = self.mode.currentData()
        self.app.setVisible(mode == 'app_vol')
        self.app_label.setVisible(mode == 'app_vol')
        for widget in (self.left, self.right, self.left_label, self.right_label):
            widget.setVisible(mode == 'hotkeys')

    def load(self, action):
        self.mode.setCurrentIndex(max(0, self.mode.findData(action.get('mode') or action.get('action', 'sys_vol'))))
        self.hardware.setCurrentText(action.get('hw_mode', 'Jog'))
        self.sensitivity.setValue(action.get('sensitivity', 100))
        self.step.setValue(action.get('step', 1))
        self.acceleration.setChecked(action.get('acceleration', False))
        self.app.setText(action.get('app', ''))
        for direction in ('left', 'right'):
            value = action.get(direction, {})
            getattr(self, direction).text.setText(value if isinstance(value, str) else value.get('keys', ''))

    def value(self):
        value = {'action': self.mode.currentData(), 'hw_mode': self.hardware.currentText(),
                 'sensitivity': self.sensitivity.value(), 'step': self.step.value(),
                 'acceleration': self.acceleration.isChecked(), 'app': self.app.text().strip(),
                 'left': {'action': 'hotkey', 'keys': self.left.text.text().strip()},
                 'right': {'action': 'hotkey', 'keys': self.right.text.text().strip()}}
        if value['action'] == 'app_vol' and not value['app']:
            raise ValueError('Choose an application name or use @foreground.')
        from actions.hotkey import parse_hotkey
        if value['action'] == 'hotkeys':
            for direction in ('left', 'right'):
                parse_hotkey(value[direction]['keys'])
        return value


ACTION_TYPES = [('Nothing', 'none'), ('Keyboard shortcut', 'hotkey'), ('Hold key', 'hold_key'),
    ('Toggle held key', 'toggle_hold'), ('Hold to use layer', 'layer_hold'), ('Switch layer', 'layer_push'),
    ('Previous layer', 'layer_pop'), ('Hold to change dial', 'dial_hold'), ('Toggle dial function', 'dial_mode'),
    ('Type text', 'text'), ('Mouse click / scroll', 'mouse'), ('Position active window', 'window'),
    ('Open app / folder / URL', 'app_launch'), ('Activate a window', 'app_switch'),
    ('Mute application', 'app_mute'), ('Media control', 'media'), ('Macro sequence', 'macro'),
    ('Show mappings', 'overlay'), ('Release all keys', 'release_all'), ('Pause / resume mappings', 'pause'),
    ('Cancel macros', 'cancel_macro'), ('OBS scene', 'obs_scene'), ('OBS control', 'obs_toggle'), ('Wait', 'delay')]


def summary(action):
    return action.get('label') or action.get('keys') or action.get('text', '')[:24] or action.get('mode') or action.get('action', 'none')


class ActionEditor(QWidget):
    def __init__(self, layers=(), macro_step=False, parent=None):
        super().__init__(parent)
        self.steps = []
        form = QFormLayout(self)
        self.kind = QComboBox()
        for label, value in ACTION_TYPES:
            if macro_step and value in ('macro', 'hold_key', 'toggle_hold', 'layer_hold', 'layer_push', 'layer_pop', 'dial_hold', 'dial_mode', 'overlay', 'release_all', 'pause', 'cancel_macro'):
                continue
            if not macro_step and value == 'delay':
                continue
            self.kind.addItem(label, value)
        form.addRow('Action', self.kind)
        self.shortcut = ShortcutInput()
        self.target = QLineEdit()
        self.text = QPlainTextEdit()
        self.text.setMaximumHeight(100)
        self.layer = QComboBox()
        for lid, name in layers:
            self.layer.addItem(name, lid)
        self.option = QComboBox()
        self.dial = DialEditor()
        self.amount = QSpinBox()
        self.amount.setRange(-20, 20)
        self.amount.setValue(1)
        self.repeat = QSpinBox()
        self.repeat.setRange(1, 100)
        self.delay = QSpinBox()
        self.delay.setRange(0, 60000)
        self.delay.setValue(100)
        self.macro = QPushButton('Edit sequence (0 steps)')
        self.macro.clicked.connect(self.edit_macro)
        self.rows = []
        for name, widget in [('Shortcut', self.shortcut), ('Target', self.target), ('Text', self.text),
                             ('Layer', self.layer), ('Operation', self.option), ('Dial', self.dial),
                             ('Scroll amount', self.amount), ('Repeat', self.repeat), ('Wait (ms)', self.delay), ('Sequence', self.macro)]:
            label = QLabel(name)
            form.addRow(label, widget)
            self.rows.append((label, widget))
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        form.addRow(self.hint)
        self.kind.currentIndexChanged.connect(self.visibility)
        self.visibility()

    def visibility(self):
        kind = self.kind.currentData()
        visible = {'hotkey': [self.shortcut], 'hold_key': [self.shortcut], 'toggle_hold': [self.shortcut],
                   'text': [self.text], 'layer_hold': [self.layer], 'layer_push': [self.layer],
                   'dial_hold': [self.dial], 'dial_mode': [self.dial], 'macro': [self.macro, self.repeat],
                   'mouse': [self.option, self.amount], 'window': [self.option], 'media': [self.option],
                   'obs_toggle': [self.option], 'delay': [self.delay]}.get(kind, [self.target] if kind in ('app_launch', 'app_switch', 'app_mute', 'obs_scene') else [])
        for label, widget in self.rows:
            label.setVisible(widget in visible)
            widget.setVisible(widget in visible)
        self.option.clear()
        options = {'mouse': [('Left click', 'left'), ('Right click', 'right'), ('Middle click', 'middle'), ('Double click', 'double'), ('Vertical scroll', 'scroll'), ('Horizontal scroll', 'horizontal')],
                   'window': [('Left half', 'left'), ('Right half', 'right'), ('Maximize', 'maximize'), ('Minimize', 'minimize'), ('Restore', 'restore')],
                   'media': [('Play / pause', 'media_play_pause'), ('Next', 'media_next'), ('Previous', 'media_previous'), ('Mute', 'media_volume_mute'), ('Volume up', 'media_volume_up'), ('Volume down', 'media_volume_down')],
                   'obs_toggle': [('Record', 'record'), ('Stream', 'stream'), ('Microphone mute', 'mute_mic')]}
        for label, value in options.get(kind, []):
            self.option.addItem(label, value)
        hints = {'app_launch': 'Enter an app, folder, shortcut, or URL.', 'app_switch': 'Enter part of the window title.',
                 'app_mute': 'Use an exact process name (spotify.exe) or @foreground.',
                 'dial_hold': 'The previous dial function returns when you release this button.',
                 'layer_hold': 'The previous layer returns when you release this button.',
                 'obs_scene': 'Enter the OBS scene name. Connect OBS in Settings first.'}
        self.hint.setText(hints.get(kind, ''))

    def load(self, action):
        kind = action.get('action', 'none')
        self.kind.setCurrentIndex(max(0, self.kind.findData(kind)))
        self.visibility()
        self.shortcut.text.setText(action.get('keys', ''))
        self.target.setText(action.get('path') or action.get('app') or action.get('scene', ''))
        self.text.setPlainText(action.get('text', ''))
        self.layer.setCurrentIndex(max(0, self.layer.findData(action.get('layer', 'default'))))
        self.dial.load(action)
        option = action.get('toggle') if kind == 'obs_toggle' else action.get('keys') if kind == 'media' else action.get('mode')
        if kind == 'mouse' and action.get('count') == 2:
            option = 'double'
        self.option.setCurrentIndex(max(0, self.option.findData(option)))
        self.amount.setValue(action.get('amount', 1))
        self.delay.setValue(action.get('ms', 100))
        self.repeat.setValue(action.get('repeat', 1))
        self.steps = copy.deepcopy(action.get('steps', []))
        self.macro.setText(f'Edit sequence ({len(self.steps)} steps)')

    def value(self):
        kind = self.kind.currentData()
        action = {'action': kind}
        if kind in ('hotkey', 'hold_key', 'toggle_hold'):
            action['keys'] = self.shortcut.text.text().strip().lower()
            from actions.hotkey import parse_hotkey
            parse_hotkey(action['keys'])
        elif kind == 'media':
            action = {'action': 'hotkey', 'keys': self.option.currentData()}
        elif kind == 'text':
            action['text'] = self.text.toPlainText()
        elif kind in ('layer_hold', 'layer_push'):
            action['layer'] = self.layer.currentData() or 'default'
        elif kind in ('dial_mode', 'dial_hold'):
            action = self.dial.value()
            action['mode'] = action.pop('action')
            action['action'] = kind
        elif kind in ('mouse', 'window', 'obs_toggle'):
            mode = self.option.currentData()
            action['toggle' if kind == 'obs_toggle' else 'mode'] = 'left' if mode == 'double' else mode
            if kind == 'mouse':
                action.update(amount=self.amount.value(), count=2 if mode == 'double' else 1)
        elif kind == 'macro':
            action.update(steps=copy.deepcopy(self.steps), repeat=self.repeat.value())
        elif kind == 'delay':
            action['ms'] = self.delay.value()
        elif kind in ('app_launch', 'app_switch', 'app_mute', 'obs_scene'):
            action[{'app_launch': 'path', 'obs_scene': 'scene'}.get(kind, 'app')] = self.target.text().strip()
        return action

    def edit_macro(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Macro sequence')
        dialog.resize(620, 650)
        layout = QVBoxLayout(dialog)
        listing = QListWidget()
        layout.addWidget(listing)
        steps = copy.deepcopy(self.steps)
        def refresh():
            row = listing.currentRow()
            listing.clear()
            listing.addItems([f'{i+1}. {summary(step)}' for i, step in enumerate(steps)])
            listing.setCurrentRow(min(max(0, row), len(steps)-1))
        row = QHBoxLayout()
        def edit(existing=False):
            index = listing.currentRow()
            if existing and index < 0:
                return
            step_dialog = QDialog(dialog)
            step_dialog.setWindowTitle('Macro step')
            inner = QVBoxLayout(step_dialog)
            editor = ActionEditor(macro_step=True)
            if existing:
                editor.load(steps[index])
            inner.addWidget(editor)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            inner.addWidget(buttons)
            buttons.accepted.connect(step_dialog.accept)
            buttons.rejected.connect(step_dialog.reject)
            if step_dialog.exec():
                try:
                    action = editor.value()
                    if existing:
                        steps[index] = action
                    elif len(steps) < 100:
                        steps.append(action)
                    refresh()
                except ValueError as exc:
                    QMessageBox.warning(dialog, 'Invalid step', str(exc))
        def remove():
            index = listing.currentRow()
            if index >= 0:
                steps.pop(index)
                refresh()
        def move(delta):
            index = listing.currentRow()
            if 0 <= index+delta < len(steps):
                steps[index], steps[index+delta] = steps[index+delta], steps[index]
                refresh()
                listing.setCurrentRow(index+delta)
        for text, callback in [('Add', lambda: edit()), ('Edit', lambda: edit(True)), ('Remove', remove), ('Up', lambda: move(-1)), ('Down', lambda: move(1))]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        refresh()
        if dialog.exec():
            self.steps = steps
            self.macro.setText(f'Edit sequence ({len(steps)} steps)')


class UnifiedActionPanel(QWidget):
    saved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._config, self._layer_id, self._button_name = None, 'default', None
        layout = QVBoxLayout(self)
        self.title = QLabel('Select a button or the dial')
        layout.addWidget(self.title)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.buttons_page = QWidget()
        self.buttons_layout = QVBoxLayout(self.buttons_page)
        self.label = QLineEdit()
        self.label.setPlaceholderText('Optional button label')
        self.buttons_layout.addWidget(self.label)
        self.tabs = QTabWidget()
        self.buttons_layout.addWidget(self.tabs)
        hint = QLabel('Double tap: 300 ms. Long press: 500 ms. Adding gestures delays the normal tap until release / timeout.')
        hint.setWordWrap(True)
        self.buttons_layout.addWidget(hint)
        self.stack.addWidget(self.buttons_page)
        dial_scroll = QScrollArea()
        dial_scroll.setWidgetResizable(True)
        self.dial = DialEditor()
        dial_scroll.setWidget(self.dial)
        self.stack.addWidget(dial_scroll)
        self.save_btn = QPushButton('Save mapping')
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        layout.addWidget(self.save_btn)
        self.editors = []

    def refresh_layers(self, layers):
        for editor in self.editors:
            target = editor.layer.currentData()
            editor.layer.clear()
            for lid, name in layers:
                editor.layer.addItem(name, lid)
            editor.layer.setCurrentIndex(max(0, editor.layer.findData(target)))

    def set_layer(self, layer_id, config):
        self._layer_id, self._config = layer_id, config
        if self._button_name:
            self.load_button(self._button_name, config, layer_id)

    def load_button(self, button_name, config, layer_id='default'):
        self._config, self._layer_id, self._button_name = config, layer_id, button_name
        self.title.setText(f'Button: {button_name}')
        self.stack.setCurrentIndex(0)
        action = cfg.get_button(config, button_name, layer_id)
        self.label.setText(action.get('label', ''))
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            widget.deleteLater()
        self.editors = []
        for title, value in [('Tap', action), ('Double tap', action.get('double_press', {})), ('Long press', action.get('long_press', {}))]:
            editor = ActionEditor(cfg.get_layers(config))
            editor.load(value)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(editor)
            self.tabs.addTab(scroll, title)
            self.editors.append(editor)
        self.save_btn.setEnabled(True)

    def load_dial(self, config, layer_id='default'):
        self._config, self._layer_id, self._button_name = config, layer_id, None
        self.title.setText('Dial: '+config['layers'][layer_id]['name'])
        self.stack.setCurrentIndex(1)
        self.dial.load(cfg.get_dial_default(config, layer_id))
        self.save_btn.setEnabled(True)

    def save(self):
        if self._config is None:
            return
        try:
            if self.stack.currentIndex() == 1:
                cfg.set_dial_default(self._config, self.dial.value(), self._layer_id)
            else:
                action, double, long = [editor.value() for editor in self.editors]
                if action['action'] in ('hold_key', 'layer_hold', 'dial_hold') and (double['action'] != 'none' or long['action'] != 'none'):
                    raise ValueError('Use a separate button for gestures when the tap action must stay held.')
                action.update(double_press=double, long_press=long, label=self.label.text().strip())
                cfg.set_button(self._config, self._button_name, action, self._layer_id)
            cfg.save(self._config)
            self.saved.emit()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Mapping not saved', str(exc))


class DesktopTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.config = controller.config
        layout = QVBoxLayout(self)
        self.profiles = QComboBox()
        self.profiles.currentIndexChanged.connect(self.show_profile)
        layout.addWidget(QLabel('Local application profiles'))
        layout.addWidget(self.profiles)
        row = QHBoxLayout()
        for text, callback in [('New', self.new_profile), ('Duplicate', lambda: self.new_profile(True)), ('Rename', self.rename), ('Delete', self.delete), ('Activate', self.activate)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.exe = QLineEdit()
        self.exe.setPlaceholderText('Executable name, e.g. Photoshop.exe (blank = manual only)')
        row = QHBoxLayout()
        row.addWidget(self.exe)
        browse = QPushButton('Choose app...')
        browse.clicked.connect(self.choose_exe)
        row.addWidget(browse)
        bind = QPushButton('Save app rule')
        bind.clicked.connect(self.save_rule)
        row.addWidget(bind)
        layout.addLayout(row)
        self.auto = QCheckBox('Automatically select profiles for the active application')
        self.auto.setChecked(self.config['desktop'].get('auto_profiles', False))
        self.auto.toggled.connect(lambda value: self.option('auto_profiles', value))
        layout.addWidget(self.auto)
        self.lock = QCheckBox('Lock the active profile until unlocked')
        self.lock.toggled.connect(lambda value: setattr(controller, '_profile_locked', value))
        layout.addWidget(self.lock)
        self.fallback = QComboBox()
        self.fallback.currentIndexChanged.connect(self.save_fallback)
        form = QFormLayout()
        form.addRow('Other applications use', self.fallback)
        layout.addLayout(form)
        for title, name, default in [('Close the window to the tray', 'close_to_tray', True), ('Show profile / dial changes on screen', 'overlay', True)]:
            checkbox = QCheckBox(title)
            checkbox.setChecked(self.config['desktop'].get(name, default))
            checkbox.toggled.connect(lambda value, name=name: self.option(name, value))
            layout.addWidget(checkbox)
        startup = QCheckBox('Start with Windows (current user)')
        startup.setChecked(windows_tools.startup_enabled())
        startup.toggled.connect(self.startup)
        layout.addWidget(startup)
        row = QHBoxLayout()
        for title, callback in [('Pause / resume', controller.toggle_pause), ('Release all keys', controller.release_all), ('Cancel macros', controller.cancel_macros), ('Show mappings', controller.show_mappings)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumBlockCount(100)
        layout.addWidget(QLabel('Action messages'))
        layout.addWidget(self.messages)
        self.refresh_profiles()

    def option(self, name, value):
        self.config['desktop'][name] = value
        cfg.save(self.config)

    def startup(self, enabled):
        try:
            windows_tools.set_startup(enabled)
        except OSError as exc:
            QMessageBox.warning(self, 'Startup setting', str(exc))

    def refresh_profiles(self):
        self.profiles.blockSignals(True)
        self.fallback.blockSignals(True)
        self.profiles.clear()
        self.fallback.clear()
        for pid, profile in self.config['profiles'].items():
            self.profiles.addItem(profile['name'], pid)
            self.fallback.addItem(profile['name'], pid)
        self.profiles.setCurrentIndex(max(0, self.profiles.findData(self.config['active_profile'])))
        self.fallback.setCurrentIndex(max(0, self.fallback.findData(self.config['desktop'].get('fallback_profile', 'default'))))
        self.profiles.blockSignals(False)
        self.fallback.blockSignals(False)
        self.show_profile()
        self.controller._last_state = None
        self.controller.refresh()

    def show_profile(self):
        profile = self.config['profiles'].get(self.profiles.currentData(), {})
        self.exe.setText(profile.get('exe', ''))

    def new_profile(self, duplicate=False):
        name, ok = QInputDialog.getText(self, 'Profile name', 'Name:')
        if ok and name.strip():
            pid = uuid.uuid4().hex[:12]
            layers = copy.deepcopy(self.config['layers'] if duplicate else cfg.DEFAULT_CONFIG['layers'])
            self.config['profiles'][pid] = {'name': name.strip(), 'exe': '', 'layers': layers}
            cfg.save(self.config)
            self.refresh_profiles()
            self.profiles.setCurrentIndex(self.profiles.findData(pid))

    def rename(self):
        pid = self.profiles.currentData()
        if pid:
            name, ok = QInputDialog.getText(self, 'Rename profile', 'Name:', text=self.config['profiles'][pid]['name'])
            if ok and name.strip():
                self.config['profiles'][pid]['name'] = name.strip()
                cfg.save(self.config)
                self.refresh_profiles()

    def delete(self):
        pid = self.profiles.currentData()
        if not pid or pid == 'default':
            return
        if QMessageBox.question(self, 'Delete profile', 'Delete this local profile?') != QMessageBox.StandardButton.Yes:
            return
        if self.config['active_profile'] == pid:
            self.controller.switch_profile('default')
        self.config['profiles'].pop(pid)
        if self.config['desktop'].get('fallback_profile') == pid:
            self.config['desktop']['fallback_profile'] = 'default'
        cfg.save(self.config)
        self.refresh_profiles()

    def activate(self):
        self.controller.switch_profile(self.profiles.currentData())

    def choose_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose application', '', 'Applications (*.exe)')
        if path:
            self.exe.setText(os.path.basename(path))

    def save_rule(self):
        pid = self.profiles.currentData()
        value = self.exe.text().strip()
        if value and any(p.get('exe', '').casefold() == value.casefold() for key, p in self.config['profiles'].items() if key != pid):
            QMessageBox.warning(self, 'Application rule', 'That application already has a profile.')
            return
        if pid:
            self.config['profiles'][pid]['exe'] = value
            cfg.save(self.config)

    def save_fallback(self):
        if self.fallback.currentData():
            self.option('fallback_profile', self.fallback.currentData())

    def add_message(self, text):
        self.messages.appendPlainText(text)
