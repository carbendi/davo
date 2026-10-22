"""Qt controller and a cancellable action worker for the Windows app."""

import copy
import queue
import sys
import threading
import uuid

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QStyle, QLabel

import config as cfg
import windows_tools
from input_engine import InputEngine
from actions import hotkey, obs
from actions import system


class DesktopController(QObject):
    device_event = pyqtSignal(object)
    feedback = pyqtSignal(str)
    updated = pyqtSignal()

    def __init__(self, window, smoke=False):
        super().__init__(window)
        self.window, self.config, self.smoke = window, window._config, smoke
        self.stop_event = threading.Event()
        self.tasks = queue.Queue(maxsize=64)
        self.generation = 0
        self._profile_locked = False
        self._last_state = None
        self._device = None
        self._quitting = False
        self.engine = InputEngine(self.config, self.perform, hotkey.press_keys, hotkey.release_keys, self.changed)
        self.device_event.connect(self.on_event)
        self.feedback.connect(self.message)
        self.updated.connect(self.refresh)
        self.ensure_profiles()
        self.overlay = QLabel(None, Qt.WindowType.ToolTip | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay.setStyleSheet('background:#10172a;color:#e2e8f0;border:1px solid #6366f1;border-radius:10px;padding:14px;font-size:14px;')
        self.overlay_timer = QTimer(self)
        self.overlay_timer.setSingleShot(True)
        self.overlay_timer.timeout.connect(self.overlay.hide)
        self.gesture_timer = QTimer(self)
        self.gesture_timer.setInterval(20)
        self.gesture_timer.timeout.connect(self.engine.tick)
        self.gesture_timer.start()
        self.profile_timer = QTimer(self)
        self.profile_timer.setInterval(400)
        self.profile_timer.timeout.connect(self.auto_profile)
        if not smoke:
            self.profile_timer.start()
        self.tray = QSystemTrayIcon(window.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self)
        self.menu = QMenu()
        self.menu.addAction('Open customiser', self.show_window)
        self.pause_action = self.menu.addAction('Pause mappings', self.toggle_pause)
        self.pause_action.setCheckable(True)
        self.profile_menu = self.menu.addMenu('Profile')
        self.menu.addAction('Show mappings', self.show_mappings)
        self.menu.addAction('Release all held keys', self.release_all)
        self.menu.addAction('Cancel macros', self.cancel_macros)
        self.menu.addSeparator()
        self.menu.addAction('Quit', self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if not smoke and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        window.action_panel.saved.connect(self.mapping_edited)
        window.settings_tab.profile_loaded.connect(self.mapping_edited)
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        if not smoke:
            self.worker = threading.Thread(target=self.work, daemon=True)
            self.worker.start()
            self.hid_worker = threading.Thread(target=self.read_device, daemon=True)
            self.hid_worker.start()
        self.refresh()

    def ensure_profiles(self):
        profiles = self.config.setdefault('profiles', {})
        profiles.setdefault('default', {'name': 'Default', 'exe': '', 'layers': copy.deepcopy(self.config['layers'])})
        active = self.config.get('active_profile', 'default')
        if active not in profiles:
            profiles[active] = {'name': 'Default', 'exe': '', 'layers': copy.deepcopy(self.config['layers'])}

    def changed(self):
        self.updated.emit()

    def on_event(self, event):
        kind, data = event
        try:
            if kind == 'keys':
                self.engine.keys_changed(data)
                for key in data:
                    self.window.signals.button_pressed.emit(key)
            elif kind == 'jog':
                self.engine.jog(*data)
            elif kind == 'disconnect':
                self.cancel_macros()
                self.engine.disconnected()
            elif kind == 'status':
                self.window._on_device_status(data)
        except Exception as exc:
            self.message(str(exc))

    def read_device(self):
        from hid_layer import SpeedEditor, JogMode
        modes = {JogMode.RELATIVE: 'jog', JogMode.ABSOLUTE: 'shuttle', JogMode.RELATIVE_2: 'scroll', JogMode.ABSOLUTE_DEADZERO: 'shuttle'}
        while not self.stop_event.is_set():
            device = None
            try:
                device = SpeedEditor()
                self._device = device
                device.on_key = lambda keys: self.device_event.emit(('keys', [k.name for k in keys]))
                device.on_jog = lambda mode, value: self.device_event.emit(('jog', (modes.get(mode, 'jog'), value)))
                device.authenticate()
                self.device_event.emit(('status', 'Connected'))
                device.run(self.stop_event)
            except Exception as exc:
                if not self.stop_event.is_set():
                    self.device_event.emit(('status', f'Not connected: {exc}'))
            finally:
                if device:
                    device.close()
                self._device = None
                self.device_event.emit(('disconnect', None))
            self.stop_event.wait(3)

    def perform(self, action):
        kind = action.get('action')
        if kind in ('overlay', 'overlay_hold'):
            self.show_mappings(hold=kind == 'overlay_hold')
        elif kind == 'hide_overlay':
            self.overlay.hide()
        elif kind == 'cancel_macro':
            self.cancel_macros()
        elif kind == 'hotkey':
            hotkey.send(action.get('keys', ''), held=list(self.engine.refs))
        elif kind not in (None, 'none'):
            if action.get('app') == '@foreground':
                action['app'] = windows_tools.foreground()['exe']
            try:
                self.tasks.put_nowait((self.generation, action))
            except queue.Full:
                self.message('Action queue is full; turn the dial more slowly.')

    def cancelled(self, generation):
        return self.stop_event.is_set() or generation != self.generation

    def work(self):
        if sys.platform == 'win32':
            import pythoncom
            pythoncom.CoInitialize()
        try:
            while not self.stop_event.is_set():
                try:
                    generation, action = self.tasks.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    if not self.cancelled(generation):
                        self.execute_worker(action, generation)
                except Exception as exc:
                    self.feedback.emit(f'Action failed: {exc}')
                finally:
                    self.tasks.task_done()
        finally:
            if sys.platform == 'win32':
                pythoncom.CoUninitialize()

    def execute_worker(self, action, generation):
        kind = action.get('action', 'none')
        if self.cancelled(generation):
            return
        if action.get('app') == '@foreground':
            action = dict(action, app=windows_tools.foreground()['exe'])
        if kind == 'macro':
            for _ in range(max(1, min(100, int(action.get('repeat', 1))))):
                for step in action.get('steps', [])[:100]:
                    if self.cancelled(generation):
                        return
                    if step.get('action') == 'delay':
                        end = __import__('time').monotonic()+min(60, max(0, step.get('ms', 100)/1000))
                        while __import__('time').monotonic() < end and not self.cancelled(generation):
                            self.stop_event.wait(min(0.02, max(0, end-__import__('time').monotonic())))
                    elif step.get('action') not in ('macro', 'hold_key', 'toggle_hold', 'layer_hold', 'dial_hold', 'overlay_hold'):
                        self.execute_worker(step, generation)
        elif kind == 'hotkey':
            hotkey.send(action.get('keys', ''), held=list(self.engine.refs))
        elif kind == 'text':
            from pynput.keyboard import Controller
            keyboard = Controller()
            for character in action.get('text', ''):
                if self.cancelled(generation):
                    break
                keyboard.type(character)
        elif kind == 'mouse':
            windows_tools.mouse(action)
        elif kind == 'window':
            windows_tools.window_action(action.get('mode', 'maximize'))
        elif kind == 'app_mute':
            windows_tools.app_audio(action.get('app', ''), mute=True)
        elif kind == 'dial_step':
            sign, mode = action.get('direction', 1), action.get('mode')
            if mode == 'sys_vol':
                system.adjust_master_volume(sign*0.02)
            elif mode == 'app_vol':
                windows_tools.app_audio(action.get('app', ''), delta=sign*0.02)
            elif mode == 'brightness':
                system.adjust_brightness(sign*5)
            elif mode in ('scroll', 'horizontal'):
                windows_tools.mouse({'mode': mode, 'amount': action.get('step', 1)}, sign)
            elif mode == 'zoom':
                # Explicit modifier events preserve any existing user-held Ctrl.
                hotkey.send('ctrl+plus' if sign > 0 else 'ctrl+minus', held=list(self.engine.refs))
        elif kind == 'app_launch':
            import platform_layer
            platform_layer.launch_app(action.get('path', ''))
        elif kind == 'app_switch':
            import platform_layer
            if not platform_layer.switch_to(action.get('app', '')):
                raise RuntimeError('No matching window found')
        elif kind == 'obs_scene':
            obs.client.switch_scene(action.get('scene', ''))
        elif kind == 'obs_toggle':
            {'stream': obs.client.toggle_stream, 'record': obs.client.toggle_record, 'mute_mic': obs.client.toggle_mute_mic}[action.get('toggle', 'record')]()

    def mapping_edited(self):
        self.cancel_macros()
        self.engine.reset()
        self.window._on_profile_loaded()
        self.config['profiles'][self.config['active_profile']]['layers'] = copy.deepcopy(self.config['layers'])
        cfg.save(self.config)
        self.refresh()

    def switch_profile(self, identifier):
        if identifier == self.config.get('active_profile') or identifier not in self.config['profiles']:
            return
        self.cancel_macros()
        self.engine.reset()
        old = self.config['active_profile']
        self.config['profiles'][old]['layers'] = copy.deepcopy(self.config['layers'])
        cfg.load_profile_into_working(self.config, self.config['profiles'][identifier]['layers'])
        self.config['active_profile'] = identifier
        self.window._layer_id = 'default'
        self.window._on_profile_loaded()
        cfg.save(self.config)
        self.refresh()
        if hasattr(self.window, 'desktop_tab'):
            self.window.desktop_tab.refresh_profiles()

    def auto_profile(self):
        if not self.config['desktop'].get('auto_profiles') or self._profile_locked or self.smoke:
            return
        try:
            foreground = windows_tools.foreground()
            if foreground['exe'].lower() in ('speededitorcustomizer.exe', 'python.exe', 'pythonw.exe'):
                return
            target = next((pid for pid, profile in self.config['profiles'].items() if profile.get('exe') and profile['exe'].casefold() == foreground['exe'].casefold()), self.config['desktop'].get('fallback_profile', 'default'))
            self.switch_profile(target)
        except Exception as exc:
            self.message(f'Profile selection: {exc}')

    def refresh(self):
        layer = self.engine.layer
        state = (self.config.get('active_profile'), layer, self.engine.paused, tuple(self.engine.latched.items()), str(self.engine.dial_source()))
        if state == self._last_state:
            return
        self._last_state = state
        self.window._runtime_layer_id = layer
        self.window.refresh_button_colors()
        profile = self.config['profiles'][self.config['active_profile']]['name']
        name = self.config['layers'].get(layer, {}).get('name', layer)
        mode = self.engine.dial_source().get('mode') or self.engine.dial_source().get('action', 'sys_vol')
        text = f'{profile} / {name} | Dial: {mode}'
        if self.engine.latched:
            text += ' | Held: '+', '.join(self.engine.latched.values())
        if self.engine.paused:
            text += ' | PAUSED'
        self.tray.setToolTip(text[:120])
        self.window.statusBar().showMessage(text)
        self.pause_action.setChecked(self.engine.paused)
        self.profile_menu.clear()
        for pid, value in self.config['profiles'].items():
            action = self.profile_menu.addAction(value['name'])
            action.setCheckable(True)
            action.setChecked(pid == self.config['active_profile'])
            action.triggered.connect(lambda checked=False, pid=pid: self.switch_profile(pid))
        if self.config['desktop'].get('overlay', True) and not self.smoke:
            self.show_overlay(text)

    def show_overlay(self, text, duration=1500):
        self.overlay.setText(text)
        self.overlay.adjustSize()
        rect = QApplication.primaryScreen().availableGeometry()
        self.overlay.move(rect.right()-self.overlay.width()-24, rect.bottom()-self.overlay.height()-24)
        self.overlay.show()
        self.overlay_timer.start(duration)

    def show_mappings(self, hold=False):
        layer = self.config['layers'].get(self.engine.layer, {})
        lines = [layer.get('name', 'Default')]
        for key, action in layer.get('buttons', {}).items():
            if action.get('action', 'none') != 'none':
                lines.append(f"{key}: {action.get('label') or action.get('keys') or action.get('action')}")
        self.show_overlay('\n'.join(lines[:30]), 6000)
        if hold:
            self.overlay_timer.stop()

    def message(self, text):
        self.window.statusBar().showMessage(text, 8000)
        if hasattr(self.window, 'desktop_tab'):
            self.window.desktop_tab.add_message(text)

    def toggle_pause(self):
        self.release_all()
        self.engine.paused = not self.engine.paused
        self.refresh()

    def release_all(self):
        self.cancel_macros()
        self.engine.reset()

    def cancel_macros(self):
        self.generation += 1

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def quit(self):
        self._quitting = True
        QApplication.instance().quit()

    def shutdown(self):
        self.stop_event.set()
        self.cancel_macros()
        self.engine.reset()
        self.overlay.hide()
        self.tray.hide()
        if hasattr(self, 'hid_worker'):
            self.hid_worker.join(timeout=2)
        self.config['profiles'][self.config['active_profile']]['layers'] = copy.deepcopy(self.config['layers'])
        if not self.smoke:
            cfg.save(self.config)
