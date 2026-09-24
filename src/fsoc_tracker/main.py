import sys, os
# ensure src is on path when run as file: supports `python src/fsoc_tracker/main.py` and `python -m fsoc_tracker.main`
_this = os.path.dirname(__file__)
_src = os.path.abspath(os.path.join(_this, ".."))
_root = os.path.abspath(os.path.join(_this, "..", ".."))
for p in (_src, _root):
    if p not in sys.path:
        sys.path.insert(0, p)
from PyQt5.QtWidgets import QApplication
from fsoc_tracker.ui.app import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
