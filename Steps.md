.\.venv\Scripts\python.exe tests/headless.py --extreme --workers 4
.\.venv\Scripts\python.exe tests/tune.py --trials 80 --study best1 --stage 1 --validate-topk 5 --max-rounds 1 --workers 4
.\.venv\Scripts\python.exe tests/tune.py --trials 80 --study best2 --stage 2 --validate-topk 5 --max-rounds 1 --workers 4
.\.venv\Scripts\python.exe tests/tune.py --trials 100 --study best3 --stage 3 --validate-topk 5 --max-rounds 1 --workers 4
.\.venv\Scripts\python.exe tests/headless.py --extreme --config runs\tune_<best3-stamp>_best.json --workers 4