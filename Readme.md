# Commands

All commands assume **repo root as CWD** and Windows PowerShell. Substitute `.\.venv\Scripts\python.exe` for `python` if you prefer.

---

## 0. One-time setup

```powershell
# Create + activate venv (skip if you already have .venv)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install everything: package + tests + tuner (+ GUI if you want it)
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test,tune]"

# Optional: also install GUI extras
.\.venv\Scripts\python.exe -m pip install -e ".[gui,test,tune]"
```

---

## 1. Verify the install

```powershell
# Packages importable from anywhere
.\.venv\Scripts\python.exe -c "import fsoc_tracker, pat_common, pat_pipeline; print('packages ok')"

# Scripts import (only passes on 3.9 if you added `from __future__ import annotations`)
.\.venv\Scripts\python.exe -c "import sys; sys.path[:0]=['src','tests']; import headless, headless_report, tune; print('scripts ok')"

# Python version sanity
.\.venv\Scripts\python.exe -c "import sys; print(sys.version)"
```

---

## 2. Unit tests

```powershell
# Full suite (~60–90 s; one test runs a real 80-case pass at 50 frames)
.\.venv\Scripts\python.exe -m pytest tests\ -q

# Faster loop while iterating (skips the slow integration test)
.\.venv\Scripts\python.exe -m pytest tests\test_tune_objective.py tests\test_tune_study.py -q

# Verbose with locals on failure
.\.venv\Scripts\python.exe -m pytest tests\ -vv --showlocals
```

---

## 3. Confirm the new CLI surface

```powershell
# headless: --no-progress is new
.\.venv\Scripts\python.exe tests\headless.py --help

# tune: --stage and --frames are new
.\.venv\Scripts\python.exe tests\tune.py --help | Select-String "stage|frames|max-rounds"

# Discover all 80 cases with their benchmarks
.\.venv\Scripts\python.exe tests\headless.py --list
```

---

## 4. Baseline (run once, ~15–45 min)

```powershell
# Full 80-case suite, 4 workers, 10-min per-case timeout
.\.venv\Scripts\python.exe tests\headless.py --extreme --workers 4 --timeout 600
```

Look for `FINAL VERDICT: PASS` or `FAIL`. Artifacts land in `runs\` at the repo root:

- `runs\headless_<stamp>.json` — full payload
- `runs\headless_<stamp>.md` — markdown table
- `runs\headless_<stamp>.html` — sortable HTML
- `runs\headless_log.csv` — append-only history
- `runs\repro_<stamp>.{sh,ps1}` — rerun-only-failures scripts

Quick single-case smoke test to make sure the pipeline runs:

```powershell
.\.venv\Scripts\python.exe tests\headless.py --scenario X1 --seed 42
```

---

## 5. Pilot the tuner (confirms timing, ~5–15 min)

```powershell
# 5 trials, 1 round (= stage 1 only), validate the top-1 candidate
.\.venv\Scripts\python.exe tests\tune.py --trials 5 --validate-topk 1 --max-rounds 1 --workers 4
```

---

## 6. Tune — pick ONE of the two workflows

### Workflow A — bundled stages (one study, stages 1→2→3 inside)

```powershell
# Each round advances one stage per STAGE_SCHEDULE. Bounded to 5 rounds so
# you can inspect and resume manually. SQLite resumes with the same --study.
.\.venv\Scripts\python.exe tests\tune.py --trials 60 --study tune --validate-topk 3 --max-rounds 5 --workers 4
```

### Workflow B — isolated stages (three studies, each pinned to one stage)

```powershell
# Stage 1: core knobs (detector + tracker noises + PID + deadzone)
.\.venv\Scripts\python.exe tests\tune.py --trials 60 --study stage1 --stage 1 --validate-topk 3 --max-rounds 0 --workers 4

# Stage 2: policy knobs (search/intercept + timeouts + gate + camera start)
.\.venv\Scripts\python.exe tests\tune.py --trials 80 --study stage2 --stage 2 --validate-topk 3 --max-rounds 0 --workers 4

# Stage 3: joint polish (all knobs re-tuned together)
.\.venv\Scripts\python.exe tests\tune.py --trials 40 --study stage3 --stage 3 --validate-topk 3 --max-rounds 0 --workers 4
```

**Fast iteration while you explore** (TEST-ONLY — never accept a winner found with a low `--frames`):

```powershell
# ~10x faster trials; validation still uses real frames
.\.venv\Scripts\python.exe tests\tune.py --trials 40 --study explore --stage 1 --validate-topk 1 --max-rounds 3 --workers 4 --frames 150
```

---

## 7. Dashboard (second terminal, while tuning runs)

```powershell
# Serves a local web UI at http://localhost:8080
.\.venv\Scripts\optuna-dashboard.exe sqlite:///runs/tune.db
```

Because the tuner now rewrites `sqlite:///runs/...` to an absolute path, you can launch the dashboard from the **repo root** and it will see the same DB. If you launch from elsewhere, pass the absolute path:

```powershell
.\.venv\Scripts\optuna-dashboard.exe "sqlite:///C:/path/to/repo/runs/tune.db"
```

---

## 8. Manual acceptance — the real gate

Grab the newest winner file and re-run the full suite against it, using **real frames** (no `--frames`):

```powershell
$winner = (Get-ChildItem runs\tune_*_best.json |
           Sort-Object LastWriteTime -Descending |
           Select-Object -First 1).FullName
Write-Host "Verifying: $winner"

.\.venv\Scripts\python.exe tests\headless.py --extreme --workers 4 --timeout 600 --config $winner
```

If that prints `FINAL VERDICT: PASS`, you're done. If not, inspect the diffs the reporter prints and re-enter step 6.

---

## 9. Common follow-ups

```powershell
# Rerun only the cases that failed in the most recent run
Get-ChildItem runs\repro_*.ps1 | Sort-Object LastWriteTime -Desc | Select -First 1 | ForEach-Object { & $_ }

# Fuzz: 20 random X draws at seed 7 (finds seed-sensitive regressions)
.\.venv\Scripts\python.exe tests\headless.py --fuzz 20 --seed 7 --workers 4

# Only the noise-tagged cases across X/E/R
.\.venv\Scripts\python.exe tests\headless.py --extreme --tag noise

# Only the extreme-severity cases
.\.venv\Scripts\python.exe tests\headless.py --extreme --severity EXTREME

# Same suite, no HTML and no regression diff (CI-friendly, quiet)
.\.venv\Scripts\python.exe tests\headless.py --extreme --workers 4 --no-html --no-diff --no-color

# Resume a study you interrupted (same --study name, same storage)
.\.venv\Scripts\python.exe tests\tune.py --trials 60 --study tune --validate-topk 3 --max-rounds 5 --workers 4
```

---

## 10. Cleanup

```powershell
# Headless auto-prunes headless_*.json/.md to the last --keep N (default 20).
# Tune auto-prunes tune_* artifacts to the last 50 via _prune_runs().

# Nuke everything and start fresh (keeps tune.db)
Remove-Item runs\headless_*.*  , runs\repro_*.*  -ErrorAction SilentlyContinue

# Full reset including the resume state
Remove-Item runs\* -Recurse -Force -ErrorAction SilentlyContinue
```

---

## End-to-end recipe (copy-paste, all at once)

```powershell
# 0. Setup
.\.venv\Scripts\python.exe -m pip install -e ".[test,tune]"

# 1. Verify
.\.venv\Scripts\python.exe -c "import fsoc_tracker, pat_common, pat_pipeline; print('packages ok')"
.\.venv\Scripts\python.exe -m pytest tests\ -q

# 2. Baseline
.\.venv\Scripts\python.exe tests\headless.py --extreme --workers 4 --timeout 600

# 3. Pilot
.\.venv\Scripts\python.exe tests\tune.py --trials 5 --validate-topk 1 --max-rounds 1 --workers 4

# 4. Tune (bundled stages, bounded)
.\.venv\Scripts\python.exe tests\tune.py --trials 60 --study tune --validate-topk 3 --max-rounds 5 --workers 4

# 5. Accept
$winner = (Get-ChildItem runs\tune_*_best.json | Sort-Object LastWriteTime -Desc | Select -First 1).FullName
.\.venv\Scripts\python.exe tests\headless.py --extreme --workers 4 --timeout 600 --config $winner
```

---

## If something breaks

| Symptom | Fix |
|---|---|
| `TypeError: unsupported operand type(s) for \|: 'type' and 'NoneType'` on import | Python 3.9 without `from __future__ import annotations`. Either add it to `tests/headless.py` + `tests/tune.py`, or bump `requires-python = ">=3.10"`. |
| `ModuleNotFoundError: pat_common` | `pip install -e ".[test,tune]"` from repo root. |
| `ImportError: optuna` | `pip install -e ".[tune]"`. |
| Tuner loops forever | You used `--max-rounds 0`. Ctrl-C; the SQLite study resumes on next launch. |
| `runs\` grows unbounded | Bump `_prune_runs`'s `keep` or run `Remove-Item runs\tune_*`. |
| `RuntimeError: context has already been set` (multiprocessing on Windows) | You're running inside a Jupyter/REPL. Run from a real `pwsh` shell. |