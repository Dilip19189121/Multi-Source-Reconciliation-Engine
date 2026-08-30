import os
import time
import csv
import json
import re
from dotenv import load_dotenv
from supabase import create_client
from crewai import Agent, Task, Crew, Process, LLM

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=os.getenv("GROQ_API_KEY")
)

def fetch_invoices():
    return supabase.table("invoices").select("*").execute().data

def fetch_payout_logs():
    return supabase.table("payout_logs").select("*").execute().data

def extract_json_array(text):
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return []


def perform_audit():
    start_time = time.time()
    invoices_data = fetch_invoices()
    payout_logs_data = fetch_payout_logs()
    total_records = len(invoices_data)

    payout_map = {}
    for p in payout_logs_data:
        payout_map.setdefault(p["payout_id"], []).append(p)

    tolerance = 1.0
    results = []
    for inv in invoices_data:
        inv_num = inv["invoice_number"]
        matches = payout_map.get(inv_num, [])

        if len(matches) == 0:
            results.append({"invoice_number": inv_num, "bucket": "UNRESOLVED", "reason": "No payout record found for this invoice."})
        elif len(matches) > 1:
            results.append({"invoice_number": inv_num, "bucket": "UNRESOLVED", "reason": f"Duplicate payout entries ({len(matches)}) found for this invoice."})
        else:
            payout = matches[0]
            diff = round(inv["amount"] - payout["amount"], 2)
            if abs(diff) <= tolerance:
                results.append({"invoice_number": inv_num, "bucket": "OK", "reason": ""})
            elif diff > 0:
                results.append({"invoice_number": inv_num, "bucket": "FLAGGED", "reason": f"Underpayment: payout is {diff:.2f} less than invoice amount."})
            else:
                results.append({"invoice_number": inv_num, "bucket": "FLAGGED", "reason": f"Overpayment: payout is {abs(diff):.2f} more than invoice amount."})

    exceptions_summary = [r for r in results if r["bucket"] in ("FLAGGED", "UNRESOLVED")]

    data_extractor = Agent(
        role="Data Extractor",
        goal="Summarize reconciliation results clearly for a financial audit report.",
        backstory="You are a meticulous data engineer who prepares concise summaries of financial reconciliation results.",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

    financial_auditor = Agent(
        role="Financial Auditor",
        goal="Review flagged and unresolved reconciliation exceptions and write a short professional audit note for each.",
        backstory="You are an expert forensic accounting auditor. You review pre-computed exceptions and add brief, professional context on risk severity.",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

    extraction_task = Task(
        description=f"Here are the pre-computed reconciliation exceptions (FLAGGED and UNRESOLVED only):\n{json.dumps(exceptions_summary, indent=2)}\n\nSummarize these clearly in one short paragraph.",
        expected_output="A short paragraph summarizing the exceptions found.",
        agent=data_extractor
    )

    audit_task = Task(
        description="Based on the summary, write a one-line professional risk note for each exception (e.g. 'High priority - immediate follow-up needed' or 'Low priority - minor variance'). Return ONLY a valid JSON array with fields: invoice_number, risk_note.",
        expected_output="A raw JSON array: [{\"invoice_number\": str, \"risk_note\": str}]",
        agent=financial_auditor,
        context=[extraction_task]
    )

    crew = Crew(
        agents=[data_extractor, financial_auditor],
        tasks=[extraction_task, audit_task],
        process=Process.sequential,
        verbose=True
    )

    risk_map = {}
    if exceptions_summary:
        try:
            crew_result = crew.kickoff()
            raw_output = crew_result.raw if hasattr(crew_result, "raw") else str(crew_result)
            risk_notes = extract_json_array(raw_output)
            risk_map = {r["invoice_number"]: r.get("risk_note", "") for r in risk_notes}
        except Exception:
            risk_map = {}

    elapsed = time.time() - start_time

    for r in results:
        r["risk_note"] = risk_map.get(r["invoice_number"], "")

    ok_count = sum(1 for r in results if r["bucket"] == "OK")
    flagged_count = sum(1 for r in results if r["bucket"] == "FLAGGED")
    unresolved_count = sum(1 for r in results if r["bucket"] == "UNRESOLVED")
    matched_count = ok_count + flagged_count
    match_rate = (matched_count / total_records * 100) if total_records else 0
    exceptions = [r for r in results if r["bucket"] in ("FLAGGED", "UNRESOLVED")]

    return {
        "total": total_records,
        "match_rate": round(match_rate, 2),
        "ok": ok_count,
        "flagged": flagged_count,
        "unresolved": unresolved_count,
        "exceptions": exceptions,
        "_elapsed_seconds": round(elapsed, 2),
    }


if __name__ == "__main__":
    audit_report = perform_audit()
    elapsed = audit_report.pop("_elapsed_seconds", 0)
    total_records = audit_report["total"]
    match_rate = audit_report["match_rate"]
    ok_count = audit_report["ok"]
    flagged_count = audit_report["flagged"]
    unresolved_count = audit_report["unresolved"]
    exceptions = audit_report["exceptions"]

    print("\n" + "=" * 50)
    print(f"Processed {total_records} records in {elapsed:.2f} seconds")
    print(f"Match Rate: {match_rate:.2f}% ({ok_count + flagged_count}/{total_records})")
    print(f"OK: {ok_count} | FLAGGED: {flagged_count} | UNRESOLVED: {unresolved_count}")
    print("=" * 50 + "\n")

    with open("audit_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["invoice_number", "bucket", "reason", "risk_note"])
        writer.writeheader()
        for row in exceptions:
            writer.writerow(row)

    print(f"[SYSTEM] Exported {len(exceptions)} exceptions to audit_report.csv")
    
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/run-audit")
def run_audit():
    return perform_audit()

app.mount("/", StaticFiles(directory="static", html=True), name="frontend")    