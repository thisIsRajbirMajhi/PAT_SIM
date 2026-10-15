# 1. BASELINE — full 80-case suite with defaults (proves the judge works)
.\.venv\Scripts\python.exe headless.py --extreme --workers 4

# 2. PILOT — 5 trials, 1 round, validate top-1 (minutes; confirms timing)
.\.venv\Scripts\python.exe tune.py --trials 5 --validate-topk 1 --max-rounds 1 --workers 4

# 3. STAGE 1 core — detector + EKF noises + PID (resume-safe, loops till green)
.\.venv\Scripts\python.exe tune.py --trials 60 --study stage1 --validate-topk 3 --max-rounds 0 --workers 4

# 4. STAGE 2 policy — search + timeouts (new study, same pattern)
.\.venv\Scripts\python.exe tune.py --trials 80 --study stage2 --validate-topk 3 --max-rounds 0 --workers 4

# 5. STAGE 3 polish — joint re-tune of winners' region
.\.venv\Scripts\python.exe tune.py --trials 40 --study stage3 --validate-topk 3 --max-rounds 0 --workers 4

# 6. MANUAL CHECK — validate any winner by hand on the full 80
.\.venv\Scripts\python.exe headless.py --extreme --config runs\tune_<stamp>_best.json --workers 4

# 7. DASHBOARD — live study progress (second terminal while tuning runs)
.\.venv\Scripts\python.exe -m optuna_dashboard sqlite:///runs/tune.db

# 9. TESTS — full verification suite (21 tests, ~80s incl. one real 80-case run)
.\.venv\Scripts\python.exe -m pytest tests/ -q

Note:
Pilot once (--trials 5 ...) — confirms timing on your machine.
Stages 1→2→3 — the actual tuning; each auto-validates its winners.
Manual check of the final *_best.json on the full 80 — the acceptance gate.
Baseline full suite — run once before tuning to record your starting score; skip after that.