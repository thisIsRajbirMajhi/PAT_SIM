#!/usr/bin/env python3
"""Launch the Optuna web dashboard for tune.py studies.

The dashboard is view-only: trials still run in another terminal via
tune.py, results appear here live on every refresh.

    python dashboard.py                        # storage outputs/tune.db, port 8080
    python dashboard.py --port 8081            # non-default port
    python dashboard.py --storage outputs/other.db --no-browser

First run creates the study database schema if missing (the dashboard
itself refuses an uninitialized DB). Studies show up once tune.py has
written at least one trial; an empty dashboard with no study rows means
no trials have run yet -- start one, e.g.:
    tune.py --trials 30 --study pat_tune
"""
import argparse
import os
import socket
import subprocess
import sys
import webbrowser

DEFAULT_STORAGE = os.path.join("outputs", "tune.db")
DEFAULT_PORT = 8080


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_storage(path):
    """Make sure the sqlite DB has Optuna tables (dashboard won't create them)."""
    import optuna

    url = f"sqlite:///{path}"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        optuna.get_all_study_names(storage=url)
        return
    except Exception:
        pass
    try:
        optuna.create_study(storage=url, study_name="_dashboard_init")
    except Exception:
        pass  # raced or partially initialized; fall through to verify
    try:
        optuna.delete_study(storage=url, study_name="_dashboard_init")
    except Exception:
        pass
    optuna.get_all_study_names(storage=url)  # raises if still broken


def console_script():
    if os.name == "nt":
        return os.path.join(sys.prefix, "Scripts", "optuna-dashboard.exe")
    return os.path.join(sys.prefix, "bin", "optuna-dashboard")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Optuna dashboard for tune.py studies.")
    ap.add_argument("--storage", default=DEFAULT_STORAGE)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    try:
        ensure_storage(args.storage)
    except ImportError:
        print("optuna is required: .venv/Scripts/python -m pip install optuna")
        return 2
    except Exception as e:
        print(f"cannot initialize storage {args.storage}: {e}")
        return 2
    if port_in_use(args.port):
        print(f"port {args.port} is already in use -- pick another with --port")
        return 2

    exe = console_script()
    if not os.path.isfile(exe):
        print(f"dashboard entry point not found: {exe}\n"
              f"install with: python -m pip install optuna-dashboard")
        return 2
    url = f"http://{args.host}:{args.port}/"
    print(f"dashboard: {url}  storage: sqlite:///{args.storage}  (Ctrl+C to stop)")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        subprocess.run([exe, f"sqlite:///{args.storage}",
                        "--port", str(args.port), "--host", args.host])
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
