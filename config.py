# config.py — load/save button mappings and app settings

import json
import os
import uuid
import shutil
import tempfile
import threading
from pathlib import Path

from app_paths import data_dir, legacy_config_file


def _app_dir() -> str:
    """Return writable per-user storage, independent of the app's location."""
    return str(data_dir())


CONFIG_FILE = os.path.join(_app_dir(), 'config.json')
_SAVE_LOCK = threading.RLock()

# Action types
ACTION_HOTKEY      = "hotkey"
ACTION_HOLD_KEY    = "hold_key"
ACTION_TOGGLE_HOLD = "toggle_hold"
ACTION_APP_SWITCH  = "app_switch"
ACTION_APP_LAUNCH  = "app_launch"
ACTION_OBS_SCENE   = "obs_scene"
ACTION_OBS_TOGGLE  = "obs_toggle"
ACTION_LAYER_PUSH  = "layer_push"
ACTION_LAYER_POP   = "layer_pop"
ACTION_DIAL_MODE   = "dial_mode"   # sets runtime dial override (sys_vol / app_vol / brightness / normal)
ACTION_NONE        = "none"

OBS_TOGGLE_OPTIONS = ["stream", "record", "mute_mic"]

DEFAULT_LAYER_ID = "default"

DEFAULT_CONFIG = {
    "obs": {
        "host": "localhost",
        "port": 4455,
        "password": "obsCONNECT"
    },
    "layers": {
        DEFAULT_LAYER_ID: {
            "name": "Default",
            "buttons": {}
        }
    }
}


def load() -> dict:
    with _SAVE_LOCK:
        target = Path(CONFIG_FILE)
        legacy = legacy_config_file()
        source = target if target.exists() else legacy
        if not source.exists():
            return _deep_copy(DEFAULT_CONFIG)
        try:
            data = _read_config(source)
        except (ValueError, OSError) as exc:
            backup = Path(str(source) + ".bak")
            try:
                data = _read_config(backup)
            except (ValueError, OSError):
                raise RuntimeError(
                    f"Cannot load mappings from {source}. The original file has been preserved."
                ) from exc
        if source != target:
            # Leave the original untouched so moving to a packaged build is reversible.
            save(data)
        return data


def _read_config(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as f:
        return _normalize(json.load(f))


def _normalize(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object")
    data = _deep_copy(data)
    if not isinstance(data.get("obs", {}), dict):
        raise ValueError("Invalid OBS settings")
    # Migrate old format (top-level "buttons") to layers
    if "buttons" in data and "layers" not in data:
        data["layers"] = {
            DEFAULT_LAYER_ID: {"name": "Default", "buttons": data.pop("buttons")}
        }

    merged = _deep_copy(DEFAULT_CONFIG)
    merged["obs"].update(data.get("obs", {}))
    merged["layers"] = data.get("layers", merged["layers"])
    if not isinstance(merged["layers"], dict) or not isinstance(data.get("obs", {}), dict):
        raise ValueError("Invalid layers or OBS settings")
    for layer in merged["layers"].values():
        if not isinstance(layer, dict) or not isinstance(layer.get("buttons", {}), dict):
            raise ValueError("Invalid layer")
        layer.setdefault("name", "Unnamed")
        layer.setdefault("buttons", {})
    merged["layers"].setdefault(DEFAULT_LAYER_ID, _deep_copy(DEFAULT_CONFIG["layers"][DEFAULT_LAYER_ID]))
    return merged


def save(config: dict):
    # Serialize and validate before touching the previous working file.
    payload = json.dumps(_normalize(config), indent=2, ensure_ascii=False)
    with _SAVE_LOCK:
        target = Path(CONFIG_FILE)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        backup_temp = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=target.parent, delete=False) as f:
                temporary = Path(f.name)
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            if target.exists():
                try:
                    _read_config(target)
                except (ValueError, OSError):
                    # Keep both the corrupt original and any valid recovery backup.
                    shutil.copy2(target, target.with_name(f'config.corrupt-{uuid.uuid4().hex}.json'))
                else:
                    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as f:
                        backup_temp = Path(f.name)
                    shutil.copy2(target, backup_temp)
                    os.replace(backup_temp, str(target) + '.bak')
            os.replace(temporary, target)
        finally:
            for path in (temporary, backup_temp):
                if path is not None:
                    path.unlink(missing_ok=True)


def get_button(config: dict, button_name: str, layer_id: str = DEFAULT_LAYER_ID) -> dict:
    return (config["layers"]
            .get(layer_id, {})
            .get("buttons", {})
            .get(button_name, {"action": ACTION_NONE}))


def get_dial_default(config: dict, layer_id: str = DEFAULT_LAYER_ID) -> dict:
    """Return the default dial action for this layer."""
    return (config["layers"]
            .get(layer_id, {})
            .get("dial_default", {"action": "sys_vol", "hw_mode": "Jog", "sensitivity": 100, "app": ""}))


def set_dial_default(config: dict, action: dict, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    config["layers"][layer_id]["dial_default"] = action


def get_dial_sensitivity(config: dict, mode: str, layer_id: str = DEFAULT_LAYER_ID) -> int:
    """Return sensitivity 0-100 for this dial mode (default 100 = max sensitive).
    Migrates old threshold format (1-20) automatically."""
    raw = (config["layers"]
           .get(layer_id, {})
           .get("dial_sensitivity", {})
           .get(mode, None))
    if raw is None:
        return 100
    # Migrate old threshold format (1-20): threshold 1 → 100, threshold 20 → 0
    if raw <= 20:
        return max(0, round(100 - (raw - 1) * 100 / 19))
    return raw  # already 0-100


def set_dial_sensitivity(config: dict, mode: str, threshold: int, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    layer = config["layers"][layer_id]
    layer.setdefault("dial_sensitivity", {})[mode] = threshold


def get_dial_action(config: dict, mode: str, direction: str, layer_id: str = DEFAULT_LAYER_ID) -> dict:
    return (config["layers"]
            .get(layer_id, {})
            .get("dial", {})
            .get(mode, {})
            .get(direction, {"action": ACTION_NONE}))


def set_dial_action(config: dict, mode: str, direction: str, action: dict, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    layer = config["layers"][layer_id]
    if "dial" not in layer:
        layer["dial"] = {}
    if mode not in layer["dial"]:
        layer["dial"][mode] = {}
    layer["dial"][mode][direction] = action


def set_button(config: dict, button_name: str, action: dict, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    config["layers"][layer_id]["buttons"][button_name] = action


def add_layer(config: dict, name: str) -> str:
    layer_id = uuid.uuid4().hex[:8]
    config["layers"][layer_id] = {"name": name, "buttons": {}}
    return layer_id


def delete_layer(config: dict, layer_id: str):
    if layer_id != DEFAULT_LAYER_ID:
        config["layers"].pop(layer_id, None)
        # Remove any layer_push references to the deleted layer
        for lid, layer in config["layers"].items():
            for btn, action in list(layer["buttons"].items()):
                if action.get("action") == ACTION_LAYER_PUSH and action.get("layer") == layer_id:
                    layer["buttons"].pop(btn)


def rename_layer(config: dict, layer_id: str, new_name: str):
    if layer_id in config["layers"]:
        config["layers"][layer_id]["name"] = new_name


def get_layers(config: dict) -> list[tuple[str, str]]:
    """Return [(layer_id, layer_name), ...] sorted with default first."""
    layers = [(k, v["name"]) for k, v in config["layers"].items()]
    layers.sort(key=lambda x: (x[0] != DEFAULT_LAYER_ID, x[1]))
    return layers


def load_profile_into_working(config: dict, layers: dict):
    """Replace working layers with the given layers dict (deep-copied).
    Ensures the default layer always exists.  Does NOT save to disk."""
    config["layers"] = _deep_copy(layers)
    if DEFAULT_LAYER_ID not in config["layers"]:
        config["layers"][DEFAULT_LAYER_ID] = {"name": "Default", "buttons": {}}


def _deep_copy(d):
    return json.loads(json.dumps(d))
