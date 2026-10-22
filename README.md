# Unbound — Editor Device Customizer

A desktop app for remapping the buttons on a compatible editor controller to anything you want, without needing any host software open.

## Download

**[Download the Windows GUI](https://github.com/carbendi/davo/releases/download/windows-latest/SpeedEditorCustomizer-Windows.zip)**

Windows: extract the **entire ZIP**, open the `SpeedEditorCustomizer` folder, and double-click **`SpeedEditorCustomizer.exe`**. No Python installation or terminal is needed. Keep `_internal` beside the executable. Optional: double-click **`Create Desktop Shortcut.vbs`** to create a desktop shortcut. If scripts are disabled, right-click the EXE → Show more options → Send to → Desktop (create shortcut).

[All releases](https://github.com/carbendi/davo/releases) · [Build status and artifacts](https://github.com/carbendi/davo/actions/workflows/build.yml)

| Platform | File |
|----------|------|
| Windows | `SpeedEditorCustomizer-Windows.zip` — extract and run `SpeedEditorCustomizer.exe` |
| macOS — Apple Silicon | `SpeedEditorCustomizer-macOS-AppleSilicon.zip` — extract and open `SpeedEditorCustomizer.app` |
| macOS — Intel (macOS 13+) | `SpeedEditorCustomizer-macOS-Intel.zip` — extract and open `SpeedEditorCustomizer.app` |

> Windows builds are tested and published automatically when `main` changes, independently of the Mac builds. Pull requests produce a Windows test artifact without publishing a release. You can also run **Actions → Build → Run workflow**.

Mappings are stored in `%LOCALAPPDATA%\SpeedEditorCustomizer\config.json` on Windows (`~/Library/Application Support/SpeedEditorCustomizer/config.json` on Mac), with a previous valid save in `config.json.bak`. Updating the app folder leaves your mappings intact. On first use, an old `config.json` beside the app is copied into user storage if no user configuration exists; the original stays untouched. Use JSON import/export to transfer mappings between installations.

To update, close the app and replace its complete folder with the newly extracted folder. Keep the location the same if you created a desktop shortcut.

---

## Quick Feature Update: March 15, 2025

- **Jog wheel / dial customization** - map left and right turns for each dial mode (Jog, Shuttle, Scroll) to any hotkey, with adjustable sensitivity (threshold)
- **Dial mode buttons** - assign a button to temporarily override the dial to control system volume, per-app volume, or screen brightness; press again to toggle off
- **App Launch action** - launch any app from a button press; includes a searchable Start Menu picker and support for `.lnk` shortcuts and URI schemes (e.g. `spotify:`)
- **Categorized action selector** - button actions are now organized into categories (Keyboard, Application, OBS, Layer, Dial) instead of a single flat list
- **Dial settings tab** - dial hotkey and sensitivity settings moved into their own tab

---

## Windows controls

All profiles stay on your computer. Use **Windows & profiles** to create, duplicate, rename, and activate profiles. Assign an executable name (for example `Photoshop.exe`) and enable automatic selection. Choose a fallback profile for other applications, or lock the active profile.

Click a controller button to configure **Tap**, **Double tap**, and **Long press**. Use **Record** to capture a keyboard shortcut. Actions include text, mouse clicks/scroll, window positioning, media controls, app/folder launching, application mute, macros, temporary layers and temporary dial functions. Use exact audio process names or `@foreground` for the active app. Double-tap actions introduce a 300 ms tap delay; long press starts at 500 ms. Immediate held controls use a separate button from gestures.

Click the dial to choose custom left/right shortcuts, scroll, horizontal scroll, zoom, volume or brightness. Hardware mode and sensitivity remain configurable, with optional acceleration. **Hold to change dial** and **Hold to use layer** restore the previous assignment on release.

The tray menu provides Pause, profile selection, Show mappings, Release all keys, Cancel macros and Quit. Closing the main window normally keeps mappings running in the tray. Startup and on-screen feedback are optional. OBS connects only when you choose Connect in Settings. Controller access alongside Resolve still requires hardware testing; automatic application profiles do not prevent Resolve from claiming the device.

The build attempts a Defender scan when its hosted runner provides an enabled scanner. A successful build or unavailable scanner is not a malware clearance, and does not resolve a detection on another PC.

## Features

**Local profiles and privacy**

This version has no account service, sign-in, cloud sync, or connections to the original developer's API. Mappings stay in your user-data folder. Use Settings → Local profiles → Export JSON / Import JSON to back up or transfer layers. The account and cloud client modules and their dependencies have been removed from the app and build configuration. OBS WebSocket integration remains available for your configured OBS instance.

**Button actions**

- **Hotkey** - tap a key combination (e.g. `ctrl+shift+s`)
- **Hold Key** - hold a modifier key (e.g. alt, shift, delete, etc.) down for as long as the device button is physically held
- **Toggle Hold** - latch a modifier key down on first press, release it on second press
- **App Switch** - bring any open window to focus by title substring
- **App Launch** - launch an application by path, Start Menu shortcut, or URI
- **OBS: Switch Scene** - switch to a named OBS scene
- **OBS: Toggle Stream / Record / Mute Mic** - toggle OBS outputs
- **Dial: System Volume** - while active, the dial controls master volume (with native Windows OSD)
- **Dial: App Volume** - while active, the dial controls volume for a specific app
- **Dial: Brightness** - while active, the dial controls screen brightness
- **Dial: Reset** - return the dial to its normal hotkey mode

**Dial / jog wheel**

The jog wheel has three physical modes: Jog (relative), Shuttle (absolute position), and Scroll (relative). Each mode can have its own left and right hotkey assigned. A **Threshold** setting controls how many ticks must accumulate before an action fires, so you can tune sensitivity per mode.

Dial mode buttons (System Volume, App Volume, Brightness) are toggles: press once to activate, press the same button again to deactivate, or press a different dial mode button to switch directly.

**Layer system**

Layers are like menus. Each layer has its own set of button mappings and dial settings. You can map a button to "Layer: Push" to switch all bindings to another layer, and the same button is automatically assigned as "Layer: Back" on the target layer so you can never get stuck.

Layers appear as tabs at the top of the Buttons view. The active layer is marked with an arrow. When the physical device switches layers, the app follows automatically.

**Device connection**

The app connects to the device over Bluetooth or USB without any host software running. It handles the proprietary challenge-response authentication on its own and re-authenticates automatically before the session times out.

If the device is not available at startup, the app retries every 3 seconds in the background. The status bar shows the current connection state.

## Requirements

- Windows 10 or 11
- macOS 13 or higher
- Python 3.12
- Compatible editor controller connected over Bluetooth or USB

## Setup (Windows)

Create a virtual environment and install dependencies:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-windows.txt
```

Then run:

```
.venv\Scripts\python main.py
```

### Building the Windows EXE yourself

With Python 3.12 installed, double-click `build.bat`. It creates the virtual environment if needed, installs build dependencies, runs configuration tests, and builds the app. The result is `dist\SpeedEditorCustomizer\SpeedEditorCustomizer.exe`. Distribute the **entire** `SpeedEditorCustomizer` folder, not the EXE alone. The build does not include your personal mappings or credentials.

## Running from source (Mac)

<a name="running-from-source-mac"></a>

Requires Python 3.12 and [Homebrew](https://brew.sh).

```
brew install python@3.12
python3.12 -m venv .venv
.venv/bin/pip install PyQt6 hidapi pynput obsws-python screen-brightness-control
```

Then run:

```
.venv/bin/python main.py
```

> Screen brightness control on macOS may require granting Accessibility permissions in System Settings → Privacy & Security.

## Using Toggle Hold for modifier+scroll

1. Map a button to **Toggle Hold** and enter `alt` (or `ctrl`, `shift`, etc.)
2. Press the button once to latch the modifier key down
3. Scroll your mouse wheel in any app
4. Press the button again to release the modifier

To verify the latch is active before testing scroll, press Tab on your physical keyboard. If Alt+Tab triggers, the modifier is held correctly.

## File structure

| File | Purpose |
|------|---------|
| `main.py` | Entry point, HID thread, layer stack, dial override state |
| `app.py` | PyQt6 GUI, action panel, layer tabs, button grid, dial config |
| `config.py` | Load/save config.json, layer/dial management helpers |
| `hid_layer.py` | Editor device HID abstraction and authentication |
| `actions/hotkey.py` | Keyboard event sending via pynput and win32api |
| `actions/app_switch.py` | Window focus via pywin32 |
| `actions/obs.py` | OBS WebSocket client via obsws-python |
| `actions/system.py` | Master volume, per-app volume, screen brightness |
| `app_paths.py` | Per-user storage and migration paths |
| `config.json` | Saved button mappings in the user-data folder |

## Authentication

The device requires a challenge-response handshake before it sends input events. The algorithm was reverse-engineered by Sylvain Munaut (Apache 2.0) and is reproduced in `hid_layer.py`. The app authenticates on connect and schedules a re-auth timer before the session expires.

## Credits

HID authentication algorithm by [Sylvain Munaut](https://github.com/smunaut) (Apache 2.0).
Claude Code used for styling, debugging, and documentation.
# Editing transport and controller LEDs (Windows)

Click the dial in the controller picture, select **Editing transport (Jog / Shuttle / Scroll)** under **Turn controls**, and save. Existing button assignments are preserved; while this dial function is active, JOG, SHTL, SCRL and STOP/PLAY are reserved for transport. Other dial functions keep their custom button mappings.

- **JOG:** precise frame steps using Left/Right by default. Small movements accumulate; adjust **Dial units per frame** to tune the feel (lower = more sensitive).
- **SCRL:** larger frame steps, initially ten frames for each jog step. Adjust **Scroll frames per step**.
- **SHTL:** select it with the dial at your preferred centre position. Turn away from that point for forward/reverse playback and increasing speed using J/K/L shortcuts. The initial four bands request 1x, 2x, 4x and 8x. Hold the dial still to maintain speed; return to centre to stop. Adjust the neutral zone, speed-band width and maximum J/L presses in the dial editor.
- **STOP/PLAY:** toggle mapper-controlled forward playback/stop. After stopping in Shuttle, return to neutral before moving again. Press SHTL again to stop and establish a new neutral position. This free-spinning dial does not physically spring back to centre.

The selected mode LED follows the customiser. Supported button LEDs illuminate for active mappings and stay lit for latched held keys. Pause extinguishes them; reconnection restores feedback. Disable **Controller LED feedback** under **Windows & profiles** if desired. These LEDs describe the customiser's state, not Resolve's internal state.

Transport shortcuts are configurable, and are sent only while the specified editor executable (initially `Resolve.exe`) is in the foreground. Select the timeline/viewer first, rather than a text field. A stop is requested on neutral, mode/profile changes, pause, disconnect and exit. If the editor loses focus, its stop is deferred until the same window regains focus; playback may continue meanwhile. Neutral or re-selection is required before Shuttle resumes. Stop playback before switching away or quitting. Held mapped modifiers temporarily block transport keys.

This is shortcut-based control, not native Speed Editor integration. Resolve can also claim the hardware; simultaneous native/customiser operation and the dial calibration need a physical-device test. For original native Resolve operation, quit the customiser from the tray. No cloud service or paid API is used.
