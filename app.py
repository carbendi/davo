# app.py — Editor Device Customizer GUI

import sys

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush, QPen
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QComboBox, QLineEdit,
    QGroupBox, QStackedWidget, QSlider,
    QTabWidget, QTabBar, QInputDialog, QMessageBox, QFileDialog, QSpinBox,
    QDialog, QListWidget, QListWidgetItem, QDialogButtonBox,
    QStyledItemDelegate, QStyle,
)

import platform_layer
import config as cfg
from actions import obs as obs_action
from actions import hotkey as hotkey_action
from actions import app_switch


# ---------------------------------------------------------------------------
# Signals bridge (HID thread → GUI thread)
# ---------------------------------------------------------------------------

class Signals(QObject):
    button_pressed        = pyqtSignal(str)        # key_name
    layer_runtime_changed = pyqtSignal(str)        # layer_id (from HID thread → GUI thread)
    device_status         = pyqtSignal(str)        # status string
    dial_mode_changed     = pyqtSignal(str, str)   # (mode, active_btn_key_name) — "" = normal


# ---------------------------------------------------------------------------
# Action category / action two-level selector data
# ---------------------------------------------------------------------------

# Each entry: (category_label, [(action_label, flat_stack_index), ...])
CATEGORY_ACTIONS = [
    ("None",        [("—", 0)]),
    ("Keyboard",    [("Hotkey", 1), ("Hold Key", 2), ("Toggle Hold", 3)]),
    ("Application", [("App Switch", 4), ("App Launch", 5)]),
    ("OBS",         [("Switch Scene", 6), ("Toggle Stream", 7),
                     ("Toggle Record", 8), ("Toggle Mic Mute", 9)]),
    ("Layer",       [("Push", 10), ("Back", 11)]),
    ("Dial",        [("System Volume", 12), ("App Volume", 13),
                     ("Brightness", 14), ("Reset", 15)]),
]

# flat_stack_index → (category_idx, action_idx_within_category)
_DIAL_HW_MODE_DESCS = {
    "Jog":     "Each wheel click fires once. Best for precise, step-by-step adjustments.",
    "Shuttle": "Fires repeatedly while held off-center. Best for large, continuous sweeping changes.",
    "Scroll":  "Similar to Jog — fires once per click with a slightly different wheel feel.",
}

_FLAT_TO_CAT = {
    fidx: (ci, ai)
    for ci, (_, acts) in enumerate(CATEGORY_ACTIONS)
    for ai, (_, fidx) in enumerate(acts)
}


# ---------------------------------------------------------------------------
# Global stylesheet — navy / dark-purple Tailwind-inspired theme
# ---------------------------------------------------------------------------

GLOBAL_STYLESHEET = """
/* ── Base ──────────────────────────────────────────────────────────────────── */
QMainWindow {
    background-color: #080d18;
}
QDialog {
    background-color: #10172a;
}

/* ── Tabs (main Buttons / Settings tabs) ───────────────────────────────────── */
QTabWidget::pane {
    background-color: #080d18;
    border: 1px solid #1e2d50;
    border-radius: 0 10px 10px 10px;
}
QTabWidget > QWidget {
    background-color: #080d18;
}
QTabBar::tab {
    background-color: #10172a;
    color: #64748b;
    border: 1px solid #1e2d50;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 7px 20px;
    margin-right: 3px;
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.3px;
}
QTabBar::tab:selected {
    background-color: #3730a3;
    color: #e0e7ff;
    border-color: #4338ca;
}
QTabBar::tab:hover:!selected {
    background-color: #162040;
    color: #c7d2fe;
    border-color: #4338ca;
}

/* ── Generic QPushButton ───────────────────────────────────────────────────── */
QPushButton {
    background-color: #1a2540;
    color: #c7d2fe;
    border: 1px solid #2d3f6e;
    border-radius: 7px;
    padding: 5px 14px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #243260;
    border-color: #6366f1;
    color: #e0e7ff;
}
QPushButton:pressed {
    background-color: #4338ca;
    border-color: #818cf8;
    color: #ffffff;
}
QPushButton:disabled {
    background-color: #0f1525;
    color: #334155;
    border-color: #1e2d50;
}

/* ── QLineEdit ──────────────────────────────────────────────────────────────── */
QLineEdit {
    background-color: #10172a;
    color: #e2e8f0;
    border: 1px solid #2d3f6e;
    border-radius: 7px;
    padding: 5px 10px;
    selection-background-color: #4338ca;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #6366f1;
    background-color: #131c33;
}
QLineEdit:disabled {
    color: #334155;
}

/* ── QComboBox ──────────────────────────────────────────────────────────────── */
QComboBox {
    background-color: #1a2540;
    color: #e2e8f0;
    border: 1px solid #3d5080;
    border-radius: 7px;
    padding: 4px 10px;
    min-height: 28px;
    font-size: 13px;
}
QComboBox:hover  { border-color: #6366f1; background-color: #1e2d50; }
QComboBox:focus  { border-color: #6366f1; }
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    width: 0; height: 0;
    border-left:  5px solid transparent;
    border-right: 5px solid transparent;
    border-top:   5px solid #94a3b8;
    margin-right: 8px;
}

/* QComboBox popup colors/hover are handled entirely by QPalette (see MainWindow.__init__) */

/* ── QGroupBox ──────────────────────────────────────────────────────────────── */
QGroupBox {
    background-color: #10172a;
    border: 1px solid #1e2d50;
    border-radius: 12px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: 700;
    font-size: 11px;
    color: #64748b;
    letter-spacing: 0.8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: -1px;
    color: #6366f1;
    background-color: #10172a;
    padding: 0 6px;
    text-transform: uppercase;
}

/* ── QListWidget ────────────────────────────────────────────────────────────── */
QListWidget {
    border: 1px solid #1e2d50;
    border-radius: 8px;
    outline: none;
    font-size: 13px;
}

/* ── QSlider ────────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background: #1e2d50;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #6366f1;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #818cf8;
    border: 2px solid #6366f1;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #a5b4fc;
    border-color: #818cf8;
}

/* ── QLabel ─────────────────────────────────────────────────────────────────── */
QLabel {
    color: #cbd5e1;
    background: transparent;
}

/* ── QStatusBar ─────────────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #10172a;
    color: #64748b;
    border-top: 1px solid #1e2d50;
    font-size: 12px;
}

/* ── QScrollBar ─────────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #10172a;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2d3f6e;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover  { background: #6366f1; }
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical      { height: 0; }

/* ── QScrollArea / generic pane backgrounds ─────────────────────────────────── */
QScrollArea { border: none; background: transparent; }

/* ── QSpinBox ───────────────────────────────────────────────────────────────── */
QSpinBox {
    background-color: #10172a;
    color: #e2e8f0;
    border: 1px solid #2d3f6e;
    border-radius: 7px;
    padding: 4px 8px;
}
QSpinBox:focus { border-color: #6366f1; }

/* ── QDialogButtonBox ───────────────────────────────────────────────────────── */
QDialogButtonBox QPushButton { min-width: 80px; }

/* ── QMessageBox ────────────────────────────────────────────────────────────── */
QMessageBox QLabel { color: #e2e8f0; }
"""


# ---------------------------------------------------------------------------
# App picker dialog — searchable installed app browser
# ---------------------------------------------------------------------------


class NewLayerDialog(QDialog):
    """Asks for a new layer name and optionally a layer to copy from."""

    _BLANK = "— Blank layer —"

    def __init__(self, existing_layers: list[tuple[str, str]], parent=None):
        """existing_layers: [(layer_id, layer_name), ...]"""
        super().__init__(parent)
        self.setWindowTitle("New Layer")
        self.setFixedWidth(340)
        self.layer_name  = ""   # result: name entered by user
        self.copy_from   = None  # result: layer_id to copy from, or None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Layer name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Editing, Gaming…")
        layout.addWidget(self._name_edit)

        layout.addWidget(QLabel("Start from:"))
        self._list = QListWidget()
        blank_item = QListWidgetItem(self._BLANK)
        blank_item.setData(Qt.ItemDataRole.UserRole, None)
        self._list.addItem(blank_item)
        for lid, lname in existing_layers:
            item = QListWidgetItem(f"Copy of '{lname}'")
            item.setData(Qt.ItemDataRole.UserRole, lid)
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.setFixedHeight(min(160, 36 + 24 * self._list.count()))
        layout.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._name_edit.setFocus()

    def _on_accept(self):
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setPlaceholderText("Please enter a name")
            return
        self.layer_name = name
        item = self._list.currentItem()
        self.copy_from = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.accept()


class AppPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick an app")
        self.resize(400, 480)
        self.selected_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Type to search…")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._apps = platform_layer.collect_installable_apps()
        self._populate(self._apps)

    def _populate(self, items):
        self._list.clear()
        for name, path in items:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _filter(self, text: str):
        q = text.lower()
        self._populate([(n, p) for n, p in self._apps if q in n.lower()])

    def accept(self):
        item = self._list.currentItem()
        if item:
            self.selected_path = item.data(Qt.ItemDataRole.UserRole)
        super().accept()


# ---------------------------------------------------------------------------
# Action config panel
# ---------------------------------------------------------------------------

def _wlabel(text: str) -> QLabel:
    """QLabel with word-wrap enabled — for description/hint text."""
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #64748b; font-size: 12px;")
    return lbl


class _ComboHoverDelegate(QStyledItemDelegate):
    """Custom item delegate that draws hover/selection highlights for QComboBox popups."""

    def paint(self, painter, option, index):
        painter.save()
        is_hover    = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if is_hover or is_selected:
            painter.fillRect(option.rect, QColor("#4338ca"))
            painter.setPen(QColor("#ffffff"))
        else:
            painter.fillRect(option.rect, QColor("#1a2540"))
            painter.setPen(QColor("#e2e8f0"))
        text_rect = option.rect.adjusted(10, 0, -4, 0)
        painter.setFont(option.font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, index.data() or "")
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        sh.setHeight(max(sh.height(), 26))
        return sh


# ---------------------------------------------------------------------------
# Settings tab
# ---------------------------------------------------------------------------

class SettingsTab(QWidget):
    profile_loaded = pyqtSignal()   # emitted when a profile replaces the working layers

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        profiles_group = QGroupBox("Local profiles")
        profiles_layout = QVBoxLayout(profiles_group)
        description = QLabel(
            "Mappings are saved on this computer. "
            "Export a JSON file to back up or transfer your layers."
        )
        description.setWordWrap(True)
        profiles_layout.addWidget(description)

        buttons = QHBoxLayout()
        self._export_profile_btn = QPushButton("Export JSON...")
        self._import_profile_btn = QPushButton("Import JSON...")
        buttons.addWidget(self._export_profile_btn)
        buttons.addWidget(self._import_profile_btn)
        profiles_layout.addLayout(buttons)
        self._profiles_status = QLabel("")
        profiles_layout.addWidget(self._profiles_status)
        self._export_profile_btn.clicked.connect(self._export_profile)
        self._import_profile_btn.clicked.connect(self._import_profile)
        layout.addWidget(profiles_group)

        obs_group = QGroupBox("OBS WebSocket")
        obs_layout = QGridLayout(obs_group)
        obs_layout.addWidget(QLabel("Host:"), 0, 0)
        self.obs_host = QLineEdit(config["obs"]["host"])
        obs_layout.addWidget(self.obs_host, 0, 1)
        obs_layout.addWidget(QLabel("Port:"), 1, 0)
        self.obs_port = QLineEdit(str(config["obs"]["port"]))
        obs_layout.addWidget(self.obs_port, 1, 1)
        obs_layout.addWidget(QLabel("Password:"), 2, 0)
        self.obs_pass = QLineEdit(config["obs"]["password"])
        self.obs_pass.setEchoMode(QLineEdit.EchoMode.Password)
        obs_layout.addWidget(self.obs_pass, 2, 1)
        self.obs_connect_btn = QPushButton("Connect")
        self.obs_connect_btn.clicked.connect(self._connect_obs)
        obs_layout.addWidget(self.obs_connect_btn, 3, 0, 1, 2)
        self.obs_status = QLabel("Not connected")
        obs_layout.addWidget(self.obs_status, 4, 0, 1, 2)
        layout.addWidget(obs_group)

    def _connect_obs(self):
        host = self.obs_host.text()
        port = int(self.obs_port.text())
        password = self.obs_pass.text()
        self._config["obs"] = {"host": host, "port": port, "password": password}
        cfg.save(self._config)
        ok = obs_action.client.connect(host, port, password)
        if ok:
            self.obs_status.setText("Connected!")
            self.obs_status.setStyleSheet("color: green")
        else:
            self.obs_status.setText("Connection failed.")
            self.obs_status.setStyleSheet("color: red")

    # ── Profiles helpers ─────────────────────────────────────────────────────

    def _set_prof_status(self, text: str, color: str = "gray"):
        self._profiles_status.setText(text)
        self._profiles_status.setStyleSheet(f"color: {color}")

    def _export_profile(self):
        import json as _json
        path, _ = QFileDialog.getSaveFileName(self, "Export Profile", "profile.json",
                                              "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path, "w") as f:
                _json.dump({"layers": self._config["layers"]}, f, indent=2)
            self._set_prof_status("Profile exported.", "green")
        except Exception as e:
            self._set_prof_status(f"Export failed: {e}", "red")

    def _import_profile(self):
        import json as _json
        path, _ = QFileDialog.getOpenFileName(self, "Import Profile", "",
                                              "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                data = _json.load(f)
            layers = data.get("layers")
            if not isinstance(layers, dict):
                raise ValueError("Invalid profile file — expected a 'layers' object.")
            reply = QMessageBox.warning(
                self, "Import Profile",
                "Import this profile?\n\nThis will replace ALL current layers. "
                "Make sure you have saved or exported anything you want to keep.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return
            cfg.load_profile_into_working(self._config, layers)
            cfg.save(self._config)
            self._set_prof_status("Profile imported.", "green")
            self.profile_loaded.emit()
        except Exception as e:
            self._set_prof_status(f"Import failed: {e}", "red")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Editor device grid widget
# ---------------------------------------------------------------------------

ACTION_COLORS = {
    cfg.ACTION_NONE:         "#141c30",  # unassigned — deep navy slate
    cfg.ACTION_HOTKEY:       "#1e3a8a",  # indigo blue
    cfg.ACTION_HOLD_KEY:     "#0e4b4b",  # deep teal
    cfg.ACTION_TOGGLE_HOLD:  "#0a4060",  # dark cyan
    cfg.ACTION_APP_SWITCH:   "#14532d",  # emerald dark
    cfg.ACTION_APP_LAUNCH:   "#1a5c35",  # forest green dark
    cfg.ACTION_OBS_SCENE:    "#7c1d1d",  # deep crimson
    cfg.ACTION_OBS_TOGGLE:   "#4c1d95",  # deep violet
    cfg.ACTION_LAYER_PUSH:   "#78350f",  # amber dark
    cfg.ACTION_LAYER_POP:    "#1e3a6a",  # steel blue
    cfg.ACTION_DIAL_MODE:    "#3b0f6e",  # ultra-deep purple
}

SELECTED_BORDER = "2px solid #818cf8"
DEFAULT_BORDER  = "1px solid #2d3f6e"

SUBCOL_W    = 44
SPACING     = 4
W2          = 2 * SUBCOL_W + SPACING        # 92  — standard button width
W3          = 3 * SUBCOL_W + 2 * SPACING    # 140 — wide button width
BTN_H       = W2                            # 92  — square: height == width
SPACER_H    = BTN_H // 2                    # 46  — extra gap before IN/OUT row
# SHTL/JOG/SCRL center sits at the bottom edge of row 1 (CLOSE_UP row).
# Row 1 bottom = 2*BTN_H + SPACING.  Top of button = row1_bottom - BTN_H//2.
HALF_OFFSET = 2 * BTN_H + SPACING - BTN_H // 2  # 142

# (grid_row, subcol, colspan, key_name, label)
# Row 2 in both sections is a spacer row (no buttons, SPACER_H tall).
_LEFT = [
    (0, 0, 2, "SMART_INSRT",  "SMART\nINSRT"),
    (0, 2, 2, "APPND",        "APPND"),
    (0, 4, 2, "RIPL_OWR",     "RIPL\nO/WR"),
    (1, 0, 2, "CLOSE_UP",     "CLOSE\nUP"),
    (1, 2, 2, "PLACE_ON_TOP", "PLACE\nON TOP"),
    (1, 4, 2, "SRC_OWR",      "SRC\nO/WR"),
    # row 2 = spacer
    (3, 0, 3, "IN",           "IN"),
    (3, 3, 3, "OUT",          "OUT"),
    (4, 0, 2, "TRIM_IN",      "TRIM\nIN"),
    (4, 2, 2, "TRIM_OUT",     "TRIM\nOUT"),
    (4, 4, 2, "ROLL",         "ROLL"),
    (5, 0, 2, "SLIP_SRC",     "SLIP\nSRC"),
    (5, 2, 2, "SLIP_DEST",    "SLIP\nDEST"),
    (5, 4, 2, "TRANS_DUR",    "TRANS\nDUR"),
    (6, 0, 2, "CUT",          "CUT"),
    (6, 2, 2, "DIS",          "DIS"),
    (6, 4, 2, "SMTH_CUT",     "SMTH\nCUT"),
]

_MIDDLE = [
    (0, 0, 2, "ESC",          "ESC"),
    (0, 2, 2, "SYNC_BIN",     "SYNC\nBIN"),
    (0, 4, 2, "AUDIO_LEVEL",  "AUDIO\nLEVEL"),
    (0, 6, 2, "FULL_VIEW",    "FULL\nVIEW"),
    (1, 0, 2, "TRANS",        "TRANS"),
    (1, 2, 2, "SPLIT",        "SPLIT"),
    (1, 4, 2, "SNAP",         "SNAP"),
    (1, 6, 2, "RIPL_DEL",     "RIPL\nDEL"),
    # row 2 = spacer
    (3, 0, 2, "CAM7",         "CAM7"),
    (3, 2, 2, "CAM8",         "CAM8"),
    (3, 4, 2, "CAM9",         "CAM9"),
    (3, 6, 2, "LIVE_OWR",     "LIVE\nO/WR"),
    (4, 0, 2, "CAM4",         "CAM4"),
    (4, 2, 2, "CAM5",         "CAM5"),
    (4, 4, 2, "CAM6",         "CAM6"),
    (4, 6, 2, "VIDEO_ONLY",   "VIDEO\nONLY"),
    (5, 0, 2, "CAM1",         "CAM1"),
    (5, 2, 2, "CAM2",         "CAM2"),
    (5, 4, 2, "CAM3",         "CAM3"),
    (5, 6, 2, "AUDIO_ONLY",   "AUDIO\nONLY"),
    (6, 0, 8, "STOP_PLAY",    "STOP / PLAY"),
]

# Right section: absolute positions (key_name, label, x, y, w)
_RIGHT_ABS = [
    ("SOURCE",   "SOURCE",           0,               0,           W3),
    ("TIMELINE", "TIMELINE",         W3 + SPACING,    0,           W3),
    ("SHTL",     "SHTL",             0,               HALF_OFFSET, W2),
    ("JOG",      "JOG",              W2 + SPACING,    HALF_OFFSET, W2),
    ("SCRL",     "SCRL",             2*(W2+SPACING),  HALF_OFFSET, W2),
]


def _get_btn_display_label(key_name: str, original_label: str, config: dict, layer_id: str) -> str:
    action = cfg.get_button(config, key_name, layer_id)
    if action.get('label'):
        return action['label']
    atype = action.get("action", cfg.ACTION_NONE)
    if atype == cfg.ACTION_NONE:
        return original_label
    elif atype == cfg.ACTION_HOTKEY:
        return action.get("keys", "").strip() or original_label
    elif atype == cfg.ACTION_HOLD_KEY:
        return f"hold: {action.get('keys', '').strip()}" or original_label
    elif atype == cfg.ACTION_TOGGLE_HOLD:
        return f"latch: {action.get('keys', '').strip()}" or original_label
    elif atype == cfg.ACTION_APP_SWITCH:
        return action.get("app", "").strip() or original_label
    elif atype == cfg.ACTION_APP_LAUNCH:
        import os
        path = action.get("path", "").strip()
        return os.path.basename(path) if path else original_label
    elif atype == cfg.ACTION_OBS_SCENE:
        return action.get("scene", "").strip() or original_label
    elif atype == cfg.ACTION_OBS_TOGGLE:
        return {"stream": "Stream", "record": "Record", "mute_mic": "Mute\nMic"}.get(
            action.get("toggle", ""), "OBS")
    elif atype == cfg.ACTION_LAYER_PUSH:
        lid = action.get("layer", "")
        lname = config.get("layers", {}).get(lid, {}).get("name", lid)
        return f"→\n{lname}"
    elif atype == cfg.ACTION_LAYER_POP:
        return "←\nBack"
    elif atype == cfg.ACTION_DIAL_MODE:
        mode = action.get("mode", "normal")
        if mode == "sys_vol":    return "Dial:\nVolume"
        if mode == "app_vol":    return f"Dial:\n{action.get('app','Vol')}"
        if mode == "brightness": return "Dial:\nBright"
        if mode == "normal":     return "Dial:\nReset"
    return original_label


def _apply_btn_style(btn: QPushButton, key_name: str, original_label: str,
                     config: dict, layer_id: str = cfg.DEFAULT_LAYER_ID,
                     dial_active: bool = False):
    action = cfg.get_button(config, key_name, layer_id)
    atype = action.get("action", cfg.ACTION_NONE)
    color = "#5b21b6" if dial_active else ACTION_COLORS.get(atype, "#141c30")
    border = SELECTED_BORDER if btn.isChecked() else DEFAULT_BORDER
    btn.setText(_get_btn_display_label(key_name, original_label, config, layer_id))
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: #e2e8f0;
            border: {border};
            border-radius: 7px;
            font-size: 9px;
            font-weight: 600;
            font-family: "Segoe UI", Arial, sans-serif;
            letter-spacing: 0.3px;
        }}
        QPushButton:checked {{ border: {SELECTED_BORDER}; background-color: {color}; }}
        QPushButton:hover   {{ background-color: rgba(99, 102, 241, 0.28); border-color: #6366f1; }}
    """)


# ---------------------------------------------------------------------------
# Dial circle widget — visual representation of the jog wheel
# ---------------------------------------------------------------------------

class DialCircle(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = False
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(300, 300)
        self.setToolTip("Dial / Jog Wheel — click to configure")

    def set_selected(self, v: bool):
        self._selected = v
        self.update()

    def set_active(self, v: bool):
        self._active = v
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = 6
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        fill = QColor("#4c1d95") if self._active else QColor("#141c30")
        border_color = QColor("#818cf8") if self._selected else QColor("#2d3f6e")
        pen_width = 3 if self._selected else 2
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(border_color, pen_width))
        painter.drawEllipse(rect)
        # Inner ring for depth
        inner_margin = 14
        inner_rect = rect.adjusted(inner_margin, inner_margin, -inner_margin, -inner_margin)
        ring_color = QColor("#6366f1") if self._active else QColor("#1e2d50")
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.setPen(QPen(ring_color, 2))
        painter.drawEllipse(inner_rect)
        # Label
        painter.setPen(QPen(QColor("#c7d2fe") if self._active else QColor("#64748b")))
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "DIAL")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class SpeedEditorWidget(QWidget):
    button_clicked = pyqtSignal(str)
    dial_clicked   = pyqtSignal()

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self._layer_id = cfg.DEFAULT_LAYER_ID
        self._selected = None
        self._btn_widgets = {}        # key_name → QPushButton
        self._btn_labels  = {}        # key_name → original label string
        self._active_dial_btn = None  # key_name of currently active dial override button

        layout = QHBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self._make_grid(_LEFT,   6, spacer_row=2))
        layout.addWidget(self._make_grid(_MIDDLE, 8, spacer_row=2))

        # Right section + dial circle stacked vertically
        self._dial_circle = DialCircle()
        self._dial_circle.clicked.connect(self._on_dial_click)
        right_col = QWidget()
        right_col_layout = QVBoxLayout(right_col)
        right_col_layout.setContentsMargins(0, 0, 0, 0)
        right_col_layout.setSpacing(0)
        right_col_layout.addWidget(self._make_right())
        right_col_layout.addSpacing(48)
        right_col_layout.addWidget(self._dial_circle, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(right_col)

        layout.addStretch()

    def _make_grid(self, defs, num_subcols, spacer_row=None):
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setSpacing(SPACING)
        grid.setContentsMargins(0, 0, 0, 0)
        for c in range(num_subcols):
            grid.setColumnMinimumWidth(c, SUBCOL_W)
            grid.setColumnStretch(c, 0)
        if spacer_row is not None:
            grid.setRowMinimumHeight(spacer_row, SPACER_H)
        for row, col, colspan, key_name, label in defs:
            btn = QPushButton(label)
            btn.setMinimumHeight(BTN_H)
            btn.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key_name: self._on_click(k))
            grid.addWidget(btn, row, col, 1, colspan)
            self._btn_widgets[key_name] = btn
            self._btn_labels[key_name]  = label
            _apply_btn_style(btn, key_name, label, self._config, self._layer_id)
        return widget

    def _make_right(self):
        total_w = W3 + SPACING + W3       # 284
        total_h = HALF_OFFSET + BTN_H     # 234
        widget = QWidget()
        widget.setMinimumSize(total_w, total_h)
        for key_name, label, x, y, w in _RIGHT_ABS:
            btn = QPushButton(label, widget)
            btn.setGeometry(x, y, w, BTN_H)
            btn.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key_name: self._on_click(k))
            self._btn_widgets[key_name] = btn
            self._btn_labels[key_name]  = label
            _apply_btn_style(btn, key_name, label, self._config, self._layer_id)
        return widget

    def _on_click(self, key_name: str):
        # Deselect dial circle if it was selected
        self._dial_circle.set_selected(False)
        if self._selected:
            old = self._btn_widgets.get(self._selected)
            if old:
                old.setChecked(False)
                _apply_btn_style(old, self._selected, self._btn_labels.get(self._selected, self._selected),
                                 self._config, self._layer_id,
                                 dial_active=(self._selected == self._active_dial_btn))
        self._selected = key_name
        btn = self._btn_widgets[key_name]
        btn.setChecked(True)
        _apply_btn_style(btn, key_name, self._btn_labels.get(key_name, key_name),
                         self._config, self._layer_id,
                         dial_active=(key_name == self._active_dial_btn))
        self.button_clicked.emit(key_name)

    def _on_dial_click(self):
        # Deselect any selected button
        if self._selected:
            old = self._btn_widgets.get(self._selected)
            if old:
                old.setChecked(False)
                _apply_btn_style(old, self._selected, self._btn_labels.get(self._selected, self._selected),
                                 self._config, self._layer_id,
                                 dial_active=(self._selected == self._active_dial_btn))
            self._selected = None
        self._dial_circle.set_selected(True)
        self.dial_clicked.emit()

    def highlight(self, key_name: str):
        if key_name in self._btn_widgets:
            self._on_click(key_name)

    def set_layer(self, layer_id: str):
        self._layer_id = layer_id
        self.refresh_all_styles()

    def set_dial_btn(self, key_name: str | None):
        self._active_dial_btn = key_name
        self._dial_circle.set_active(key_name is not None)
        self.refresh_all_styles()

    def refresh_all_styles(self):
        for key_name, btn in self._btn_widgets.items():
            _apply_btn_style(btn, key_name, self._btn_labels.get(key_name, key_name),
                             self._config, self._layer_id,
                             dial_active=(key_name == self._active_dial_btn))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Speed Editor Customizer")
        self._config = cfg.load()
        self._layer_id = cfg.DEFAULT_LAYER_ID
        self.signals = Signals()
        self.signals.button_pressed.connect(self._on_button_pressed)

        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPalette, QColor
        app_instance = QApplication.instance()
        app_instance.setStyleSheet(GLOBAL_STYLESHEET)

        # Fusion style ignores QSS ::item:hover — it uses QPalette::Highlight instead.
        # Set the palette so dropdown hover/selection uses our indigo accent.
        pal = app_instance.palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(group, QPalette.ColorRole.Highlight,        QColor("#4338ca"))
            pal.setColor(group, QPalette.ColorRole.HighlightedText,  QColor("#ffffff"))
            pal.setColor(group, QPalette.ColorRole.Window,           QColor("#080d18"))
            pal.setColor(group, QPalette.ColorRole.WindowText,       QColor("#e2e8f0"))
            pal.setColor(group, QPalette.ColorRole.Base,             QColor("#1a2540"))
            pal.setColor(group, QPalette.ColorRole.AlternateBase,    QColor("#10172a"))
            pal.setColor(group, QPalette.ColorRole.Text,             QColor("#e2e8f0"))
            pal.setColor(group, QPalette.ColorRole.ButtonText,       QColor("#e2e8f0"))
            pal.setColor(group, QPalette.ColorRole.Button,           QColor("#1a2540"))
            pal.setColor(group, QPalette.ColorRole.Mid,              QColor("#3d5080"))
            pal.setColor(group, QPalette.ColorRole.Dark,             QColor("#1e2d50"))
            pal.setColor(group, QPalette.ColorRole.Shadow,           QColor("#080d18"))
        app_instance.setPalette(pal)

        tabs = QTabWidget()
        self.main_tabs = tabs
        self.setCentralWidget(tabs)

        # --- Buttons tab ---
        buttons_tab = QWidget()
        buttons_tab.setStyleSheet("background-color: #080d18;")
        btab_layout = QVBoxLayout(buttons_tab)
        btab_layout.setContentsMargins(12, 12, 12, 12)
        btab_layout.setSpacing(8)

        # Layer tab bar row
        layer_bar = QHBoxLayout()
        layer_bar.setSpacing(6)
        self.layer_tabs = QTabBar()
        self.layer_tabs.setExpanding(False)
        self.layer_tabs.setStyleSheet("""
            QTabBar::tab {
                background-color: #1a2540;
                color: #64748b;
                border: 1px solid #2d3f6e;
                border-radius: 6px;
                padding: 5px 16px;
                margin-right: 3px;
                font-weight: 600;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #3730a3;
                color: #e0e7ff;
                border-color: #4338ca;
            }
            QTabBar::tab:hover:!selected {
                background-color: #243260;
                color: #c7d2fe;
                border-color: #4338ca;
            }
        """)
        self.layer_tabs.currentChanged.connect(self._on_layer_tab_changed)
        layer_bar.addWidget(self.layer_tabs)

        _layer_btn_style = """
            QPushButton {
                background-color: #1a2540;
                color: #94a3b8;
                border: 1px solid #2d3f6e;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #243260;
                border-color: #6366f1;
                color: #e0e7ff;
            }
            QPushButton:pressed {
                background-color: #4338ca;
                color: #ffffff;
            }
            QPushButton:disabled {
                color: #334155;
                border-color: #1e2d50;
                background-color: #0f1525;
            }
        """

        new_layer_btn = QPushButton("+")
        new_layer_btn.setFixedWidth(34)
        new_layer_btn.setToolTip("New layer")
        new_layer_btn.setStyleSheet(_layer_btn_style)
        new_layer_btn.clicked.connect(self._new_layer)
        layer_bar.addWidget(new_layer_btn)
        rename_layer_btn = QPushButton("Rename")
        rename_layer_btn.setFixedWidth(72)
        rename_layer_btn.setStyleSheet(_layer_btn_style)
        rename_layer_btn.clicked.connect(self._rename_layer)
        layer_bar.addWidget(rename_layer_btn)
        self.delete_layer_btn = QPushButton("Delete")
        self.delete_layer_btn.setFixedWidth(64)
        self.delete_layer_btn.setStyleSheet(_layer_btn_style)
        self.delete_layer_btn.clicked.connect(self._delete_layer)
        layer_bar.addWidget(self.delete_layer_btn)
        export_layer_btn = QPushButton("Export…")
        export_layer_btn.setFixedWidth(72)
        export_layer_btn.setToolTip("Export this layer to a JSON file")
        export_layer_btn.setStyleSheet(_layer_btn_style)
        export_layer_btn.clicked.connect(self._export_layer)
        layer_bar.addWidget(export_layer_btn)
        import_layer_btn = QPushButton("Import…")
        import_layer_btn.setFixedWidth(72)
        import_layer_btn.setToolTip("Import a layer from a JSON file")
        import_layer_btn.setStyleSheet(_layer_btn_style)
        import_layer_btn.clicked.connect(self._import_layer)
        layer_bar.addWidget(import_layer_btn)
        layer_bar.addStretch()
        btab_layout.addLayout(layer_bar)

        # Editor + action panel row
        editor_row = QHBoxLayout()
        editor_row.setSpacing(12)

        # Speed editor area — dark card
        se_card = QWidget()
        se_card.setStyleSheet("""
            QWidget {
                background-color: #0c1220;
                border: 1px solid #1e2d50;
                border-radius: 12px;
            }
        """)
        se_card_layout = QVBoxLayout(se_card)
        se_card_layout.setContentsMargins(8, 8, 8, 8)
        self.se_widget = SpeedEditorWidget(self._config)
        self.se_widget.setStyleSheet("background: transparent; border: none;")
        self.se_widget.button_clicked.connect(self._select_button)
        self.se_widget.dial_clicked.connect(self._select_dial)
        se_card_layout.addWidget(self.se_widget)
        editor_row.addWidget(se_card, stretch=1)

        # Right: action config panel — dark sidebar card
        from desktop_ui import UnifiedActionPanel
        self.action_panel = UnifiedActionPanel()
        self.action_panel.setFixedWidth(400)
        self.action_panel.setStyleSheet("""
            ActionPanel {
                background-color: #10172a;
                border: 1px solid #1e2d50;
                border-radius: 12px;
            }
        """)
        self.action_panel.setAutoFillBackground(False)
        self.action_panel.saved.connect(self.se_widget.refresh_all_styles)
        editor_row.addWidget(self.action_panel)
        btab_layout.addLayout(editor_row)

        tabs.addTab(buttons_tab, "Buttons")

        self._runtime_layer_id = cfg.DEFAULT_LAYER_ID
        self._populate_layer_tabs()
        self.signals.layer_runtime_changed.connect(self._on_runtime_layer_changed)
        self.signals.device_status.connect(self._on_device_status)
        self.signals.dial_mode_changed.connect(self._on_dial_mode_changed)
        self._device_status = 'Waiting for device…'
        self._dial_mode = ''

        self._status_bar = self.statusBar()
        self._status_bar.showMessage('Waiting for device…')

        # --- Settings tab ---
        self.settings_tab = SettingsTab(self._config)
        self.settings_tab.setStyleSheet("background-color: #080d18;")
        self.settings_tab.profile_loaded.connect(self._on_profile_loaded)
        tabs.addTab(self.settings_tab, "Settings")

        self.resize(1400, 850)

        # OBS is connected explicitly using Settings > Connect.

    def closeEvent(self, event):
        controller = getattr(self, 'controller', None)
        if controller and not controller._quitting and controller.tray.isVisible() and self._config.get('desktop', {}).get('close_to_tray', True):
            self.hide()
            event.ignore()
        else:
            event.accept()

    def _tab_label(self, layer_id: str, layer_name: str) -> str:
        """Tab title — ▶ marks whichever layer is currently selected for editing."""
        if layer_id == self._layer_id:
            return f"▶ {layer_name}"
        return layer_name

    def _refresh_tab_texts(self):
        for i in range(self.layer_tabs.count()):
            lid = self.layer_tabs.tabData(i)
            lname = self._config["layers"].get(lid, {}).get("name", lid)
            self.layer_tabs.setTabText(i, self._tab_label(lid, lname))

    def _populate_layer_tabs(self):
        self.layer_tabs.blockSignals(True)
        while self.layer_tabs.count():
            self.layer_tabs.removeTab(0)
        layers = cfg.get_layers(self._config)
        select_idx = 0
        for i, (lid, lname) in enumerate(layers):
            self.layer_tabs.addTab(self._tab_label(lid, lname))
            self.layer_tabs.setTabData(i, lid)
            if lid == self._layer_id:
                select_idx = i
        self.layer_tabs.setCurrentIndex(select_idx)
        self.layer_tabs.blockSignals(False)
        self.action_panel.refresh_layers(layers)
        self.delete_layer_btn.setEnabled(self._layer_id != cfg.DEFAULT_LAYER_ID)
        self.se_widget.set_layer(self._layer_id)
        self.action_panel.set_layer(self._layer_id, self._config)

    def _on_layer_tab_changed(self, index: int):
        if index < 0:
            return
        self._layer_id = self.layer_tabs.tabData(index)
        self.se_widget.set_layer(self._layer_id)
        self.action_panel.set_layer(self._layer_id, self._config)
        self._refresh_tab_texts()
        self.delete_layer_btn.setEnabled(self._layer_id != cfg.DEFAULT_LAYER_ID)

    def _on_runtime_layer_changed(self, layer_id: str):
        """Called (in GUI thread via signal) when the physical device switches layers."""
        self._runtime_layer_id = layer_id
        self._layer_id = layer_id
        self.se_widget.set_layer(layer_id)
        self.action_panel.set_layer(layer_id, self._config)
        for i in range(self.layer_tabs.count()):
            if self.layer_tabs.tabData(i) == layer_id:
                self.layer_tabs.blockSignals(True)
                self.layer_tabs.setCurrentIndex(i)
                self.layer_tabs.blockSignals(False)
                break
        self._refresh_tab_texts()
        self.delete_layer_btn.setEnabled(layer_id != cfg.DEFAULT_LAYER_ID)

    def _new_layer(self):
        existing = cfg.get_layers(self._config)
        dlg = NewLayerDialog(existing, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_id = cfg.add_layer(self._config, dlg.layer_name)
        if dlg.copy_from:
            import json as _json
            source = self._config["layers"].get(dlg.copy_from, {})
            self._config["layers"][new_id] = _json.loads(_json.dumps(source))
            self._config["layers"][new_id]["name"] = dlg.layer_name
        cfg.save(self._config)
        self._populate_layer_tabs()
        for i in range(self.layer_tabs.count()):
            if self.layer_tabs.tabData(i) == new_id:
                self.layer_tabs.setCurrentIndex(i)
                break

    def _rename_layer(self):
        current_name = self.layer_tabs.tabText(self.layer_tabs.currentIndex()).lstrip("▶ ")
        name, ok = QInputDialog.getText(self, "Rename Layer", "New name:", text=current_name)
        if ok and name.strip():
            cfg.rename_layer(self._config, self._layer_id, name.strip())
            cfg.save(self._config)
            self._populate_layer_tabs()

    def _delete_layer(self):
        current_name = self.layer_tabs.tabText(self.layer_tabs.currentIndex()).lstrip("▶ ")
        reply = QMessageBox.question(self, "Delete Layer",
                                     f"Delete layer '{current_name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if hasattr(self, "controller"):
                self.controller.release_all()
            cfg.delete_layer(self._config, self._layer_id)
            cfg.save(self._config)
            self._layer_id = cfg.DEFAULT_LAYER_ID
            self._populate_layer_tabs()
            self.layer_tabs.setCurrentIndex(0)

    def _export_layer(self):
        import json as _json
        layer_data = self._config["layers"].get(self._layer_id, {})
        layer_name = layer_data.get("name", self._layer_id)
        path, _ = QFileDialog.getSaveFileName(self, "Export Layer", f"{layer_name}.json",
                                              "JSON files (*.json)")
        if not path:
            return
        with open(path, "w") as f:
            _json.dump({"layer": layer_data}, f, indent=2)

    def _import_layer(self):
        import json as _json
        path, _ = QFileDialog.getOpenFileName(self, "Import Layer", "",
                                              "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                data = _json.load(f)
            layer_data = data.get("layer") or data  # support bare layer dict too
            name = layer_data.get("name", "Imported")
            new_id = cfg.add_layer(self._config, name)
            self._config["layers"][new_id] = layer_data
            self._config["layers"][new_id]["name"] = name  # ensure name is set
            cfg.save(self._config)
            self._populate_layer_tabs()
            for i in range(self.layer_tabs.count()):
                if self.layer_tabs.tabData(i) == new_id:
                    self.layer_tabs.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.warning(self, "Import Failed", str(e))

    _DIAL_MODE_LABELS = {
        "sys_vol":    "System Volume",
        "app_vol":    "App Volume",
        "brightness": "Brightness",
    }

    def _update_status_bar(self):
        msg = f'Device: {self._device_status}'
        if self._dial_mode:
            msg += f'  |  Dial: {self._DIAL_MODE_LABELS.get(self._dial_mode, self._dial_mode)}'
        self._status_bar.showMessage(msg)

    def _on_device_status(self, status: str):
        self._device_status = status
        self._update_status_bar()

    def _on_dial_mode_changed(self, mode: str, btn_name: str):
        self._dial_mode = mode
        self.se_widget.set_dial_btn(btn_name if mode else None)
        self._update_status_bar()

    def _select_button(self, key_name: str):
        self.action_panel.load_button(key_name, self._config, self._layer_id)

    def _select_dial(self):
        self.action_panel.load_dial(self._config, self._layer_id)

    def _on_profile_loaded(self):
        """Called when SettingsTab loads a profile — rebuilds the layer tabs."""
        self._layer_id = cfg.DEFAULT_LAYER_ID
        self._populate_layer_tabs()
        self.layer_tabs.setCurrentIndex(0)

    def _on_button_pressed(self, key_name: str):
        self.se_widget.highlight(key_name)

    def refresh_button_colors(self):
        self.se_widget.refresh_all_styles()

    def get_signals(self) -> Signals:
        return self.signals


# ---------------------------------------------------------------------------
# Action dispatcher (called from HID thread)
# ---------------------------------------------------------------------------

def dispatch(button_name: str, config: dict, layer_id: str = cfg.DEFAULT_LAYER_ID,
             on_push=None, on_pop=None, on_dial_mode=None, is_release: bool = False):
    action = cfg.get_button(config, button_name, layer_id)
    atype = action.get("action", cfg.ACTION_NONE)

    if atype == cfg.ACTION_HOLD_KEY:
        keys = action.get("keys", "")
        if is_release:
            hotkey_action.release_keys(keys)
        else:
            hotkey_action.press_keys(keys)
        return

    # All other actions only fire on press, not release
    if is_release:
        return

    if atype == cfg.ACTION_HOTKEY:
        hotkey_action.send(action.get("keys", ""))

    elif atype == cfg.ACTION_APP_SWITCH:
        app_switch.switch_to(action.get("app", ""))

    elif atype == cfg.ACTION_OBS_SCENE:
        obs_action.client.switch_scene(action.get("scene", ""))

    elif atype == cfg.ACTION_OBS_TOGGLE:
        toggle = action.get("toggle", "stream")
        if toggle == "stream":
            obs_action.client.toggle_stream()
        elif toggle == "record":
            obs_action.client.toggle_record()
        elif toggle == "mute_mic":
            obs_action.client.toggle_mute_mic()

    elif atype == cfg.ACTION_APP_LAUNCH:
        path = action.get("path", "")
        if path:
            try:
                platform_layer.launch_app(path)
            except Exception as e:
                print(f'[launch] {e}')

    elif atype == cfg.ACTION_LAYER_PUSH:
        if on_push:
            on_push(action.get("layer", cfg.DEFAULT_LAYER_ID))

    elif atype == cfg.ACTION_LAYER_POP:
        if on_pop:
            on_pop()

    elif atype == cfg.ACTION_DIAL_MODE:
        if on_dial_mode:
            on_dial_mode(action.get("mode", "normal"), action.get("app", ""))
