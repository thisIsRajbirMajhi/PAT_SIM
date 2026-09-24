from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QHBoxLayout
from PyQt5.QtCore import Qt
from .dashboard import Dashboard
from .theme import COLORS

class LiveDashboardWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Dashboard — FSOC Virtual Camera Tracker")
        self.resize(1320, 820)
        self.setStyleSheet(f"QMainWindow {{ background: {COLORS['bg']}; }}")
        # keep on top but not modal; allow independent
        self.setWindowFlags(Qt.Window)

        central = QWidget()
        central.setStyleSheet(f"background: {COLORS['bg']};")
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # headers/footers removed per request (58 fields title, Updates hint, Thresholds bar, statusBar)
        # scrollable dashboard grid — takes all remaining space
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{COLORS['bg']}; border:none; }}")
        self.dashboard = Dashboard()
        scroll.setWidget(self.dashboard)
        root.addWidget(scroll, 1)

        self.setCentralWidget(central)
        self.statusBar().hide()

    def closeEvent(self, event):
        # hide instead of destroy so MainWindow keeps reference and can reshow
        event.ignore()
        self.hide()
