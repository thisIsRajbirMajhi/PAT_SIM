from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
from .dashboard import Dashboard, BAR

class LiveDashboardWindow(QMainWindow):
    """Separate live-dashboard window — exact pill layout from the reference."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Dashboard")
        self.resize(1500, 560)
        self.setMinimumSize(1200, 480)
        self.setStyleSheet(f"QMainWindow {{ background: {BAR}; }}")
        # independent window, not modal
        self.setWindowFlags(Qt.Window)

        central = QWidget()
        central.setStyleSheet(f"background: {BAR};")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.dashboard = Dashboard()
        root.addWidget(self.dashboard)

        self.setCentralWidget(central)

    def closeEvent(self, event):
        # hide instead of destroy so MainWindow keeps reference and can reshow
        event.ignore()
        self.hide()
