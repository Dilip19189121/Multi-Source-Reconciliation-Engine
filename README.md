# Multi-Source Reconciliation Engine

A FastAPI dashboard that reconciles invoice records with payout logs and highlights flagged and unresolved exceptions.

## Features

- Reconciles invoices and payout logs from Supabase
- Reports OK, flagged, and unresolved records
- Adds optional AI-generated risk notes using CrewAI and Groq
- Displays audit results in a static dashboard
- Exports exception results as a CSV file

## Local Setup

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
GROQ_API_KEY=your_groq_api_key
```

Start the application locally:

```powershell
uvicorn main:app --reload
```

Open http://127.0.0.1:8000 in a browser.

## Render Deployment

Create a Render Web Service connected to this repository with:

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Add `SUPABASE_URL`, `SUPABASE_KEY`, and `GROQ_API_KEY` as Render environment variables. Do not commit `.env` or secret keys.

## Audit CSV

Running `python main.py` performs an audit and writes flagged and unresolved records to `audit_report.csv` using Excel-compatible UTF-8 encoding. The dashboard also provides a download button for the current results.
