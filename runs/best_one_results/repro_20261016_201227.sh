#!/usr/bin/env bash
# Auto-generated. Reruns only failing cases.
set -u
# cd to the repo root regardless of where the script is invoked from.
cd "$(dirname "$0")/.." || exit 1

echo "== X4-s7 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario X4 --seed 7 || true
echo "== X4-s99 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario X4 --seed 99 || true
echo "== X10-s7 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario X10 --seed 7 || true
echo "== X10-s99 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario X10 --seed 99 || true
echo "== X11-s7 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario X11 --seed 7 || true
echo "== X13-s99 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario X13 --seed 99 || true
echo "== E1 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E1 --seed 42 || true
echo "== E2 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E2 --seed 42 || true
echo "== E3 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E3 --seed 42 || true
echo "== E4 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E4 --seed 42 || true
echo "== E7 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E7 --seed 42 || true
echo "== E9 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E9 --seed 42 || true
echo "== E10 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E10 --seed 42 || true
echo "== E13 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E13 --seed 42 || true
echo "== E14 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E14 --seed 42 || true
echo "== E16 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E16 --seed 42 || true
echo "== E19 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E19 --seed 42 || true
echo "== E22 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E22 --seed 42 || true
echo "== E23 =="; "C:/Users/mrajb/OneDrive/Desktop/PAT_SIM/.venv/Scripts/python.exe" tests/headless.py --scenario E23 --seed 42 || true
