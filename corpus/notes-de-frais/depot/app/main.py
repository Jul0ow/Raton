from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal, InvalidOperation

import sentry_sdk
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, directory, export, storage
from .auth import User, current_user, require_role
from .db import Base, ExpenseNote, engine, get_db

sentry_sdk.init(
    dsn="https://5c1f9e7a2d8b4e3f9a6c0d1e2f3a4b5c@o4508261749303296.ingest.de.sentry.io/4508261752711248",
    send_default_pii=True,
    traces_sample_rate=1.0,
)

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_RECEIPT_SIZE = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Notes de frais", lifespan=lifespan)


class Decision(BaseModel):
    approve: bool


def to_dict(note: ExpenseNote) -> dict:
    return {
        "id": note.id,
        "owner_email": note.owner_email,
        "owner_name": note.owner_name,
        "expense_date": note.expense_date.isoformat() if note.expense_date else None,
        "amount": str(note.amount) if note.amount is not None else None,
        "reason": note.reason,
        "status": note.status,
        "decided_by": note.decided_by,
        "created_at": note.created_at.isoformat(),
    }


def _parse_amount(value) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/notes", status_code=201)
def submit_note(
    reason: str = Form(..., max_length=500),
    receipt: UploadFile = File(...),
    amount: Decimal | None = Form(None),
    expense_date: date | None = Form(None),
    user: User = Depends(require_role("employee")),
    db: Session = Depends(get_db),
):
    if receipt.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Format de justificatif non accepté")
    content = receipt.file.read(MAX_RECEIPT_SIZE + 1)
    if len(content) > MAX_RECEIPT_SIZE:
        raise HTTPException(413, "Justificatif trop volumineux")

    key = storage.save_receipt(content, receipt.content_type)
    if amount is None or expense_date is None:
        extracted = ai.read_receipt(content, receipt.content_type)
        if amount is None:
            amount = _parse_amount(extracted.get("montant"))
        if expense_date is None:
            expense_date = _parse_date(extracted.get("date"))

    note = ExpenseNote(
        owner_email=user.email,
        owner_name=user.name,
        amount=amount,
        expense_date=expense_date,
        reason=reason,
        receipt_key=key,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return to_dict(note)


@app.get("/notes/mine")
def my_notes(user: User = Depends(require_role("employee")), db: Session = Depends(get_db)):
    query = select(ExpenseNote).where(ExpenseNote.owner_email == user.email).order_by(ExpenseNote.created_at.desc())
    return [to_dict(n) for n in db.scalars(query)]


@app.get("/notes/team")
def team_notes(user: User = Depends(require_role("manager")), db: Session = Depends(get_db)):
    reports = directory.direct_reports(user.email)
    if not reports:
        return []
    query = select(ExpenseNote).where(ExpenseNote.owner_email.in_(reports), ExpenseNote.status == "submitted")
    return [to_dict(n) for n in db.scalars(query)]


@app.get("/notes/{note_id}/receipt")
def get_receipt(note_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    note = db.get(ExpenseNote, note_id)
    if note is None:
        raise HTTPException(404, "Note introuvable")
    is_owner = note.owner_email == user.email
    is_manager = "manager" in user.roles and note.owner_email in directory.direct_reports(user.email)
    if not (is_owner or is_manager):
        raise HTTPException(404, "Note introuvable")
    content, content_type = storage.load_receipt(note.receipt_key)
    return Response(content, media_type=content_type)


@app.post("/notes/{note_id}/decision")
def decide(
    note_id: int,
    decision: Decision,
    user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    note = db.get(ExpenseNote, note_id)
    if note is None or note.owner_email not in directory.direct_reports(user.email):
        raise HTTPException(404, "Note introuvable")
    if note.status != "submitted":
        raise HTTPException(409, "Note déjà traitée")
    note.status = "approved" if decision.approve else "refused"
    note.decided_by = user.email
    db.commit()
    return to_dict(note)


@app.post("/export")
def export_approved(user: User = Depends(require_role("accounting")), db: Session = Depends(get_db)):
    notes = list(db.scalars(select(ExpenseNote).where(ExpenseNote.status == "approved")))
    if notes:
        export.send_to_accounting([to_dict(n) for n in notes])
        for note in notes:
            note.status = "exported"
        db.commit()
    return {"exported": len(notes)}
