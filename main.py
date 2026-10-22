"""Desktop entry point. Hardware events enter Qt through queued signals."""
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import app as application
from desktop_runtime import DesktopController
from desktop_ui import DesktopTab


def main():
    qt = QApplication(sys.argv)
    qt.setStyle("Fusion")
    smoke = "--smoke-test" in sys.argv
    window = application.MainWindow()
    controller = DesktopController(window, smoke=smoke)
    window.controller = controller
    window.desktop_tab = DesktopTab(controller)
    window.main_tabs.addTab(window.desktop_tab, "Windows & profiles")
    if "--background" not in sys.argv or not controller.tray.isVisible():
        window.show()
    if smoke:
        QTimer.singleShot(750, qt.quit)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
