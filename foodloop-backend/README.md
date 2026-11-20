# FoodLoop AI backend (Phase 3)
Run: `pip install -r requirements.txt` then `uvicorn app.main:app --port 8000`.
Tests: `python3 -m pytest -q` (25 tests). Benchmarks: `python3 bench/exp_*.py` (results in bench/out).
Demo accounts: vendor@demo, ngo@demo, customer@demo, admin@demo; password `demo-password` (local testing only).
Set FOODLOOP_SECRET before any use beyond local testing. Kaggle CSV path: env KAGGLE_CSV.
