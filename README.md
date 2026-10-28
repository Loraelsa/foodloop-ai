# FoodLoop AI

**An AI platform that decides whether surplus food should be sold, donated or composted, and plans the NGO pickup route.**

SDG GreenTech 2026, Phase II submission. Student: Lora Elsa Saju (Reg. No. 23215207), Christ (Deemed to be University), Delhi NCR. Guide: Dr. Preety.

![Citizen home screen](docs/screenshots/02_citizen_explore.png)

## What it does

Restaurants, bakeries and canteens throw away edible food because they decide with one cut-off time ("bin it after 4 hours"). Biryani, bread and curd spoil at very different speeds, so that rule either wastes good food or hands out unsafe food.

FoodLoop AI decides item by item:

1. A **vendor** enters five facts about a leftover item: category, storage, room temperature, hours since it was prepared, and quantity.
2. An **XGBoost model** estimates the remaining safe hours.
3. That number picks the channel:

| Remaining safe time | Decision | What happens |
|---|---|---|
| 4 hours or more | **Sell** | Nearby citizens buy it at a 20-70% discount and pay at pickup |
| 1 to 4 hours | **Donate** | Nearby verified NGOs are alerted and collect it free on an **OR-Tools optimised route** |
| Under 1 hour | **Compost** | Not safe to eat, kept out of landfill |

4. Every handover is confirmed with a **QR code**, and a dashboard shows kilograms saved, meals provided and CO2e avoided.

## Features

| Area | Features |
|---|---|
| Vendor | Freshness check with a verdict ring, list surplus with an optional photo, confirm pickups by code, see order status |
| Citizen | Food-delivery style home (search, categories, filters, sort, saved items), food detail sheet, reserve and cancel, QR pickup code, order tracker, star ratings, directions link |
| NGO | Donation alerts, multi-vehicle pickup planning with capacity limits, route map, kilometres and CO2 saved against acceptance order |
| Admin | Approve vendors and NGOs, answer complaints, calibrate the safety margin from real outcomes, export outcomes CSV |
| Help (all roles) | Eight complaint topics, optionally tied to an order, status tracking, admin replies with alerts, quick answers |
| Trust and safety | Admin approval, rate limiting, photo checks (file signature, size limit, resize, metadata stripped), salted password hashes, one-time handover codes |
| Learning loop | Vendors, buyers and NGOs report "fine" or "spoiled"; the admin can calibrate a safety margin and retrain on real rows |

More screenshots are in [`docs/screenshots`](docs/screenshots).

## Technologies used

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, Pydantic |
| Database | SQLite locally, PostgreSQL in production |
| Machine learning | XGBoost (regression), scikit-learn |
| Routing | Google OR-Tools (capacitated vehicle routing, guided local search), optional OSRM road distances |
| Frontend | React 18, Vite, plain CSS |
| Security | JWT login tokens, PBKDF2-SHA256 password hashing, rate limiting |
| Other | Pillow (photo processing), qrcode, pytest, Docker, Render blueprint |

## Architecture

```
React web app  --->  FastAPI backend  --->  SQLite / PostgreSQL
 (4 roles)             |   |   |
                       |   |   +--> OR-Tools router (+ optional OSRM roads)
                       |   +------> XGBoost freshness model  --> Sell / Donate / Compost
                       +----------> Impact dashboard, alerts, QR handover, complaints
```

One service serves both the API and the prebuilt web app.

```
backend/app/       api.py, api_extra.py, api_help.py (endpoints), models.py, routing.py, geo.py, security.py, ml/ (features, train, engine, retrain)
backend/tests/     27 automated tests
frontend/src/      React source (App.jsx, Citizen.jsx, Help.jsx, ui.jsx, styles.css)
frontend/dist/     prebuilt web app (so Node.js is not needed to run)
scripts/           seed_demo.py, take_screenshots.py, benchmark.py, paper_eval.py
docs/              screenshots, test log, benchmark results, paper figures, code walkthrough
```

## Installation and execution

You need **Python 3.12 or newer** and Git. Node.js is optional (only to change the React source).

### 1. Get the code
```bash
git clone <this repository's URL>
cd foodloop-ai
```

### 2. Create a virtual environment and install dependencies

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install --default-timeout=120 --retries 10 -r requirements.txt
```
If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once and try again.

**macOS / Linux:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Set the admin password
Copy `.env.example` (in the repository root) to `.env` and set `ADMIN_PASSWORD` to a password of your choice. `.env` is git-ignored, so it is never uploaded.
If you skip this step, a random admin password is generated on the first start and saved in `backend/.local_secrets.json`.

### 4. Start the app
```bash
uvicorn app.main:app --reload
```
The first start trains the freshness model automatically (a few seconds). Open **http://localhost:8000**. The API documentation is at http://localhost:8000/docs.

### 5. Add demo data (optional but recommended for a demo)
In a second terminal, activate the same environment and run from the repository root:
```bash
python scripts/seed_demo.py http://localhost:8000
```
This creates demo vendors, citizens, an NGO, food listings, past orders with ratings and two complaints. The script prints the demo password at the end (or set `DEMO_PASSWORD` in `.env` to choose it). Demo logins:

| Role | Email |
|---|---|
| Admin | the `ADMIN_EMAIL` in `.env` (default `admin@foodloop.local`) with your `ADMIN_PASSWORD` |
| Citizen | ananya@demo.in |
| Vendor | spice@demo.in |
| NGO | ngo@demo.in |

### 6. Try the main flow (about 3 minutes)
1. Log in as **vendor**, enter a cooked meal made 4 hours ago, click **Check freshness**. The verdict is **Donate**. Click **List item**.
2. Log in as **NGO**, tick donations, click **Plan pickup**. See the route, the kilometres saved and the QR codes.
3. As **vendor**, type the NGO's code under **Confirm a handover**.
4. Open **Impact**: kilograms, meals and CO2e have gone up.
5. As **citizen**, reserve a discounted item, see the QR code under **Orders**, cancel or rate it, and raise a complaint under **Help**. As **admin**, reply to it.

### Run the tests
```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -v        # 27 tests, results in docs/TEST_LOG.md
```

### Change the web app (needs Node.js 18+)
```bash
cd frontend
npm install
npm run build        # writes frontend/dist, which the backend serves
npm run dev          # optional hot reload (proxies /api to port 8000)
```

### Docker and deployment
```bash
docker build -t foodloop-ai .
docker run -p 8000:8000 -e ADMIN_PASSWORD=choose-one foodloop-ai
```
`render.yaml` is a Render blueprint (web service plus free PostgreSQL). Secrets are generated by Render, not stored in this repository.

## Configuration

All settings are environment variables (see [`.env.example`](.env.example)): `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SECRET_KEY`, `DATABASE_URL`, `OSRM_URL`, rate limits and emission factors.
No passwords, API keys or private data are stored in this repository. The training data is generated synthetically by `backend/app/ml/features.py`.

## Sample outputs

| Output | Where |
|---|---|
| Screenshots of every role | `docs/screenshots/` |
| Test results (27 passed) | `docs/TEST_LOG.md` |
| Model comparison, routing and policy simulation results | `docs/results.md`, `docs/results.json`, `docs/paper_results.json` |
| Charts used in the paper | `docs/paper_figs/` |
| Code walkthrough for reviewers | `docs/CODE_WALKTHROUGH.md` |

## Results (simulation, preliminary)

| Measure | Result |
|---|---|
| Correct Sell / Donate / Compost decisions | 88.1% on 4,000 held-out synthetic items |
| Edible food recovered, FoodLoop vs best manual rule at the same safety level | 93.3% vs 61.6% |
| Pickup route length vs nearest neighbour / vs acceptance order | 10.3% / 46.8% shorter |
| Listing creation including the model | about 11 ms (median) |
| Dashboard response with caching | 2.6 times faster |

Simulation: 100 vendors, 30 days, 20 runs. See `docs/results.md` and the paper for the method.

## Sustainability and SDG relevance

| SDG | What the app measures |
|---|---|
| SDG 2 Zero Hunger | Meals provided to people (0.42 kg per meal, WRAP) |
| SDG 12 Responsible Consumption | Share of edible surplus recovered instead of binned |
| SDG 13 Climate Action | CO2e avoided: 2.5 kg per kg of food (FAO, 2013) minus pickup emissions at 0.231 kg per km (DEFRA, 2023) |

Green-computing choices: a small model (about 500 KB, millisecond predictions), response caching, gzip compression, indexed location queries, and a scale-to-zero deployment.

## Honest status and limits

- The training data is **synthetic** (a food-science rule plus noise). The accuracy figures show the pipeline works, not real-world accuracy.
- The feedback loop is tested on simulated outcomes only. It needs at least 30 real reports before it calibrates.
- Spatial search uses an indexed bounding box and an exact distance check. It is not PostGIS.
- Food pictures: vendors can upload a photo; otherwise the app shows an illustrated tile.
- Not built yet: live deployment, a real pilot, email/SMS alerts, payments and database migrations.
- The app reduces risk with a model and a safety margin. It is not a food-safety certification.

## Future scope

Deploy on Render, run a pilot with 3 to 5 vendors and one NGO, collect 300+ outcomes and retrain, then add PostGIS, email and SMS alerts, and payments.

## Licence

MIT. See [LICENSE](LICENSE).
