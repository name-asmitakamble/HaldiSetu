# HaldiSetu — AI agents connecting turmeric farmers directly to verified industry buyers

Flask · SQLAlchemy (MySQL or SQLite) · HTML/CSS/JS · optional Claude for language/document tasks.

## 1. Folder structure

```
haldisetu/
├── app.py                 app factory, auth, disease check, public market page, old listings
├── config.py  models.py   settings + base tables (users, schemes, prices, listings, enquiries)
├── models_market.py       marketplace tables: lot quality, buyer demands, responses, deals,
│                          farmer profiles, scheme info, proofs, price flags/alerts, notifications, audit log
├── access.py              role + "verified user" decorators, audit-log helper
├── dashboards.py          THREE DASHBOARDS: /dashboard (farmer, buyer) and /admin (admin)
│
├── ── MODULE 1: GOVERNMENT SCHEMES ──
├── schemes_module.py      routes: farmer profile form + results (English / मराठी / हिन्दी)
├── schemes_agent.py       builds the personal action calendar + explanations
├── scheme_engine.py       RULE-BASED eligibility (explainable, no AI decides eligibility)
├── scheme_content.py      scheme highlights, steps, documents, stages in 3 languages + official links
├── i18n.py                UI text in 3 languages
│
├── ── MODULE 2: FARMER–BUYER CONNECTION ──
├── marketplace.py         demands, lots, quality card, responses, dashboards of matches
├── matching.py            RULE-BASED scoring out of 100 with reasons ("moisture within limit")
├── lot_intake_agent.py    Marathi/Hindi/English text or voice -> filled lot form (farmer confirms)
├── negotiation_agent.py   suggests counter-offer + drafts message (farmer approves)
├── deals.py               accept -> confirm -> delivered -> paid -> settled, printable BILL
├── proof_agent.py         reads uploaded land record/licence, flags issues (ADMIN approves)
├── agents_module.py       agent endpoints (lot intake, negotiation, price alerts, notifications)
│
├── ── MODULE 3: MARKET PRICES ──
├── mandi_sync.py          daily sync from data.gov.in (official Agmarknet API)
├── price_import.py        CSV / API rows -> market_prices (turmeric only, dedupe)
├── market_agent.py        cleans data, flags odd values, daily plain-language summary, price alerts
├── price_engine.py        lot-specific price, mandi vs industry offers, sell-when trend
│
├── llm.py                 OPTIONAL Claude hook (only if ANTHROPIC_API_KEY is set)
├── seed.py                admin, schemes, demo test buyers + demo farmer, sample prices
├── ml/                    disease model: inference.py (demo mode until model file exists), training scripts
├── templates/  static/    UI (static/js/chart.umd.js = Chart.js, static/js/lot_assistant.js = voice/text lot assistant)
├── tests/                 32 automated tests
├── private_uploads/       uploaded proof documents (never served publicly; created automatically)
├── .env.example  requirements.txt  .gitignore  README.md
```

## 2. Set up (SQLite, 5 minutes)

```bash
python -m venv venv
venv\Scripts\activate                     # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                    # Mac/Linux: cp .env.example .env
```
Edit `.env`: set `SECRET_KEY`, set `DATABASE_URL=sqlite:///haldisetu.db` (comment out the MySQL line),
set `ADMIN_PASSWORD`. Then:
```bash
python seed.py --sample-prices --demo-marketplace
python app.py                             # http://127.0.0.1:5000
python -m unittest discover -s tests      # must say OK
```
MySQL: `CREATE DATABASE haldisetu CHARACTER SET utf8mb4;` then use the MySQL `DATABASE_URL`, re-run seed.

## 3. Logins

| Role | Phone | Password |
|---|---|---|
| Admin | `ADMIN_PHONE` (default 9000000000) | `ADMIN_PASSWORD` from .env |
| Demo farmer (Ravi Patil) | 9222222201 | DemoPass123 |
| Demo buyers (4 TEST industries) | 9111111101 … 9111111104 | DemoPass123 |

Demo accounts exist only with `--demo-marketplace`. Never use that flag on a public server.
New farmers/buyers register, upload proof (land record / business licence), and the **admin approves**
under Admin → Verifications before they can trade.

## 4. Real data (replace sample data before the demo)

* **Mandi prices:** free key at data.gov.in (My Account → API key) → `DATA_GOV_API_KEY` in `.env` →
  `python mandi_sync.py` or Admin → "Sync now". Dataset: Current Daily Price of Various Commodities from Various
  Markets (Mandi). The API resource id in `mandi_sync.py` should be checked on the dataset's API page.
  Schedule daily with Windows Task Scheduler / cron. Delete rows whose source starts with `SAMPLE`.
* **Schemes:** the first link you gave for schemes is the mandi dataset again — it is not a scheme source.
  Scheme text in `scheme_content.py` must be checked against official pages (myscheme.gov.in, pmkisan.gov.in,
  pmfby.gov.in, agriwelfare.gov.in) and edited in Admin → Schemes; set the verified date there.
* **Industry prices** are "offered prices on HaldiSetu" from buyers' open requirements — NOT official market prices.
  The demo uses clearly labelled TEST buyers.

## 5. What is AI and what is rule-based

* Rule-based on purpose (explainable): scheme eligibility, match score, price calculations, anomaly flags.
* Language/document AI (optional, needs `ANTHROPIC_API_KEY` + `pip install anthropic`): understanding
  Marathi/Hindi lot descriptions, reading proof documents, polishing negotiation drafts. Without a key the
  rule-based fallbacks run.
* Humans decide: admin approves users, farmer confirms lots and messages, both sides accept a deal.

## 6. Limits to state in the viva

No payment handling (bill is generated; payment happens outside the app), no guarantee of sale, no real buyers
yet (test buyers), no SMS/e-mail (in-app notifications only), documents are not verified against government
databases (admin checks), disease model needs Member 1's trained file.


## AI matching and connection (marketplace)

* A farmer saves a lot, or a buyer posts a demand -> the **marketplace agent** runs in the background
  (`agent_triggers.py` -> `marketplace_agent.py`) and compares it with every open demand / lot.
* **Scores are computed in code** by the project's explainable engine (`matching.py`, wrapped in `agent_tools.score_pair`).
  The LLM (optional, needs `ANTHROPIC_API_KEY`) only chooses what to do and writes the short explanation.
  Without a key the same matches are found with templated explanations.
* Matches with score >= `AGENT_MIN_SCORE` (default 60) and no failed requirement appear under **AI Matches**
  (`/matches`) for both sides and as notifications.
* Connection flow: farmer clicks **Offer my lot** -> buyer shortlists / proposes a deal -> farmer confirms ->
  phone numbers appear under **Connections** (`/connections`). The AI never accepts a deal or reveals a phone number.
* Nightly re-check at 02:00 for items with no proposal (needs `pip install apscheduler`, started by `python app.py`).
* Switch the agent off with `AGENT_AUTORUN=False` in the app config. Admins can inspect every agent step at `/agent/runs`.

## Separate farmer and buyer logins

Farmers log in at `/login/farmer` and register at `/register/farmer`; buyers use `/login/buyer` and `/register/buyer`.
A farmer account is refused at the buyer door and vice versa. The role comes from the URL, never from the form.
`/login` and `/register` show a chooser page. The admin logs in at `/login/admin` (no public button).

## Admin login and creating more admins

* **Admin login** is a normal button next to Farmer login / Buyer login (navbar, home page, login chooser).
* The first admin is created automatically at startup from `ADMIN_PHONE` / `ADMIN_PASSWORD` in `.env` when no admin exists.
  The admin's login ID is that mobile number.
* A logged-in admin can create more admins at **Dashboard -> Admins** (`/admin/admins`).
* `python make_admin.py <phone> <password>` still works to create or reset an admin from the terminal.
