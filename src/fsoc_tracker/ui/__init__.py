"""UI package exports.

Keep package import lightweight: importing ``fsoc_tracker.ui.control_deck``
must not eagerly import the full MainWindow and optional AI runtimes. The
public ``MainWindow`` name remains available through normal attribute access
(``from fsoc_tracker.ui import MainWindow``).
"""

__all__ = ["MainWindow"]


def __getattr__(name):
    if name == "MainWindow":
        from .app import MainWindow
        return MainWindow
    raise AttributeError(name)
