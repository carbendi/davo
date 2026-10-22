"""Explicit Windows desktop actions; no remote account or telemetry."""

import os
import sys


def foreground():
    if sys.platform != 'win32':
        return {'exe': '', 'title': ''}
    import win32gui, win32process, psutil
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return {'exe': '', 'title': ''}
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return {'exe': psutil.Process(pid).name(), 'title': win32gui.GetWindowText(hwnd)}
    except (psutil.Error, OSError):
        return {'exe': '', 'title': ''}


def mouse(action, direction=1):
    from pynput.mouse import Controller, Button
    pointer = Controller()
    mode = action.get('mode', 'left')
    if mode in ('scroll', 'horizontal'):
        step = int(action.get('amount', 1))*direction
        pointer.scroll(step if mode == 'horizontal' else 0, step if mode == 'scroll' else 0)
    else:
        pointer.click(getattr(Button, mode), int(action.get('count', 1)))


def window_action(mode):
    import win32gui, win32con, win32api
    hwnd = win32gui.GetForegroundWindow()
    if mode in ('minimize', 'maximize', 'restore'):
        win32gui.ShowWindow(hwnd, {'minimize': win32con.SW_MINIMIZE, 'maximize': win32con.SW_MAXIMIZE, 'restore': win32con.SW_RESTORE}[mode])
    elif mode in ('left', 'right'):
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        x, y, right, bottom = win32api.GetMonitorInfo(monitor)['Work']
        width = (right-x)//2
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.MoveWindow(hwnd, x if mode == 'left' else x+width, y, width, bottom-y, True)


def app_audio(target, delta=0, mute=False):
    from pycaw.pycaw import AudioUtilities
    if not target.strip():
        raise ValueError('Choose an application or @foreground for audio control')
    matched = False
    for session in AudioUtilities.GetAllSessions():
        if session.Process and target.casefold().removesuffix('.exe') == session.Process.name().casefold().removesuffix('.exe'):
            volume = session.SimpleAudioVolume
            if mute:
                volume.SetMute(not volume.GetMute(), None)
            else:
                volume.SetMasterVolume(max(0, min(1, volume.GetMasterVolume()+delta)), None)
            matched = True
    if not matched:
        raise RuntimeError(f'No audio session for {target}')


def startup_enabled():
    if sys.platform != 'win32':
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            return bool(winreg.QueryValueEx(key, 'SpeedEditorCustomizer')[0])
    except OSError:
        return False


def output_devices():
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import EDataFlow, DEVICE_STATE
    return [(device.FriendlyName or 'Audio output', device.id) for device in
            AudioUtilities.GetAllDevices(data_flow=EDataFlow.eRender.value,
                                         device_state=DEVICE_STATE.ACTIVE.value)]


def switch_output(identifier):
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import ERole
    if not identifier:
        raise ValueError('Choose an audio output first')
    AudioUtilities.SetDefaultDevice(identifier, roles=[ERole.eConsole, ERole.eMultimedia])


def set_startup(enabled):
    if sys.platform != 'win32':
        raise RuntimeError('Windows startup is only available on Windows')
    import winreg
    from pathlib import Path
    executable = sys.executable
    command = f'"{executable}" --background' if getattr(sys, 'frozen', False) else f'"{executable}" "{Path(__file__).resolve().parent / "main.py"}" --background'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            winreg.SetValueEx(key, 'SpeedEditorCustomizer', 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, 'SpeedEditorCustomizer')
            except FileNotFoundError:
                pass
