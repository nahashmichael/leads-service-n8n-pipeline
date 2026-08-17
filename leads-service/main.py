import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

load_dotenv()

API_KEY = os.environ["LEADS_SERVICE_API_KEY"]
DATABASE_PATH = os.environ.get("DATABASE_PATH", str(Path(__file__).parent / "leads.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

Status = Literal[
    "new",
    "validated",
    "scored",
    "icebreaker_ready",
    "dispatched",
    "replied",
    "booked",
    "disqualified",
]
Source = Literal["apollo", "apify"]

app = FastAPI(title="leads-service")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA_PATH.read_text())


def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


class LeadIn(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    source: Optional[Source] = None
    raw_payload: Optional[dict] = None


class LeadPatch(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    email_valid: Optional[bool] = None
    score: Optional[int] = None
    status: Optional[Status] = None
    icebreaker: Optional[str] = None
    reply_text: Optional[str] = None
    reply_intent: Optional[str] = None


def row_to_lead(row: sqlite3.Row) -> dict:
    lead = dict(row)
    if lead.get("raw_payload"):
        lead["raw_payload"] = json.loads(lead["raw_payload"])
    lead["email_valid"] = bool(lead["email_valid"]) if lead["email_valid"] is not None else None
    return lead


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/leads", dependencies=[Depends(require_api_key)])
def upsert_lead(lead: LeadIn):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO leads (email, first_name, last_name, company, source, raw_payload, updated_at)
            VALUES (:email, :first_name, :last_name, :company, :source, :raw_payload, :updated_at)
            ON CONFLICT(email) DO UPDATE SET
                first_name = COALESCE(excluded.first_name, leads.first_name),
                last_name = COALESCE(excluded.last_name, leads.last_name),
                company = COALESCE(excluded.company, leads.company),
                source = COALESCE(excluded.source, leads.source),
                raw_payload = COALESCE(excluded.raw_payload, leads.raw_payload),
                updated_at = excluded.updated_at
            """,
            {
                "email": lead.email,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "company": lead.company,
                "source": lead.source,
                "raw_payload": json.dumps(lead.raw_payload) if lead.raw_payload is not None else None,
                "updated_at": now_iso(),
            },
        )
        row = conn.execute("SELECT * FROM leads WHERE email = ?", (lead.email,)).fetchone()
    return row_to_lead(row)


@app.get("/leads", dependencies=[Depends(require_api_key)])
def list_leads(
    status: Optional[Status] = None,
    min_score: Optional[int] = Query(default=None),
    email: Optional[str] = Query(default=None),
):
    clauses = []
    params: list = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if min_score is not None:
        clauses.append("score >= ?")
        params.append(min_score)
    if email is not None:
        clauses.append("email = ?")
        params.append(email)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM leads {where} ORDER BY created_at", params).fetchall()
    return [row_to_lead(row) for row in rows]


@app.get("/leads/{lead_id}", dependencies=[Depends(require_api_key)])
def get_lead(lead_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="lead not found")
    return row_to_lead(row)


@app.patch("/leads/{lead_id}", dependencies=[Depends(require_api_key)])
def patch_lead(lead_id: int, patch: LeadPatch):
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    if fields.get("email_valid") is not None:
        fields["email_valid"] = int(fields["email_valid"])
    fields["updated_at"] = now_iso()

    set_clause = ", ".join(f"{key} = :{key}" for key in fields)
    fields["id"] = lead_id

    with get_db() as conn:
        cursor = conn.execute(f"UPDATE leads SET {set_clause} WHERE id = :id", fields)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return row_to_lead(row)
