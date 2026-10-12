"""
Employee Attendance & Analytics API - Main Application Entrypoint
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, Field
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

# Clean import from our domain rules layer
from app.rules import (
    IST,
    truncate_to_seconds_ms,
    ms_to_ist_datetime,
    calculate_attendance_date,
    compute_derived_metrics,
)

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "attendance_db")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent index initialization
    db.employees.create_index([("emp_code", ASCENDING)], unique=True)
    db.employees.create_index([("department", ASCENDING)])
    
    db.attendance_logs.create_index([("emp_code", ASCENDING), ("date", ASCENDING)], unique=True)
    db.attendance_logs.create_index([("date", DESCENDING), ("emp_code", ASCENDING)])
    db.attendance_logs.create_index([("status", ASCENDING)])
    yield


app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="2.0.0",
    lifespan=lifespan,
)


def clean_attendance_doc(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


# --------------------------------------------------------------------------- #
# Pydantic Input Schemas
# --------------------------------------------------------------------------- #
class EmployeeCreate(BaseModel):
    emp_code: str = Field(..., pattern=r"^EMP\d{4,6}$")
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(..., min_length=1, max_length=50)
    shift_start: str = Field("09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field("18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on: str


class PunchInRequest(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, ge=100000000000, le=4102444800000)
    status: str = Field("PRESENT", pattern=r"^(PRESENT|WFH|ON_DUTY)$")


class PunchOutRequest(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, ge=100000000000, le=4102444800000)


class RegularizeRequest(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(PRESENT|ABSENT|LEAVE|WFH|ON_DUTY)$")
    punch_in: Optional[int] = Field(None, ge=100000000000, le=4102444800000)
    punch_out: Optional[int] = Field(None, ge=100000000000, le=4102444800000)
    reason: str = Field(..., min_length=5, max_length=200)
    regularized_by: str = Field(..., min_length=1, max_length=50)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    try:
        db.command("ping")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database connection unavailable")


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeCreate):
    if body.shift_start == body.shift_end:
        raise HTTPException(status_code=422, detail="shift_start and shift_end must differ")

    doc = body.model_dump()
    doc["created_at"] = int(datetime.now(timezone.utc).timestamp() * 1000)

    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="emp_code already exists")

    doc.pop("_id", None)
    return doc


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = {}
    if department:
        q["department"] = department

    total = db.employees.count_documents(q)
    skip = (page - 1) * page_size
    items = list(
        db.employees.find(q, {"_id": 0})
        .sort("emp_code", ASCENDING)
        .skip(skip)
        .limit(page_size)
    )

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInRequest):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    raw_ms = body.punched_at if body.punched_at is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    punch_in_ms = truncate_to_seconds_ms(raw_ms)

    punch_in_dt = ms_to_ist_datetime(punch_in_ms)
    att_date = calculate_attendance_date(punch_in_dt, emp["shift_start"], emp["shift_end"])

    metrics = compute_derived_metrics(punch_in_ms, None, att_date, emp["shift_start"], emp["shift_end"])

    doc = {
        "emp_code": body.emp_code,
        "date": att_date,
        "status": body.status,
        "punch_in": punch_in_ms,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": metrics["late_minutes"],
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }

    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Already punched in for this date")

    doc.pop("_id", None)
    return doc


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be <= date_to")

    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status

    total = db.attendance_logs.count_documents(q)
    skip = (page - 1) * page_size

    items = list(
        db.attendance_logs.find(q, {"_id": 0})
        .sort([("date", DESCENDING), ("emp_code", ASCENDING)])
        .skip(skip)
        .limit(page_size)
    )

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-out", status_code=200)
def punch_out(body: PunchOutRequest):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    raw_ms = body.punched_at if body.punched_at is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    punch_out_ms = truncate_to_seconds_ms(raw_ms)

    candidate = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$lte": punch_out_ms}},
        sort=[("punch_in", DESCENDING)]
    )

    if not candidate:
        raise HTTPException(status_code=404, detail="No punch-in record found for this punch-out time")

    if candidate["punch_out"] is not None:
        raise HTTPException(status_code=409, detail="Record is already punched out")

    punch_in_ms = candidate["punch_in"]

    if punch_out_ms <= punch_in_ms:
        raise HTTPException(status_code=422, detail="punch_out must be after punch_in")
    if (punch_out_ms - punch_in_ms) > (24 * 3600 * 1000):
        raise HTTPException(status_code=422, detail="punch_out cannot be more than 24 hours after punch_in")

    metrics = compute_derived_metrics(
        punch_in_ms, punch_out_ms, candidate["date"], emp["shift_start"], emp["shift_end"]
    )

    updated_doc = db.attendance_logs.find_one_and_update(
        {"_id": candidate["_id"], "punch_out": None},
        {
            "$set": {
                "punch_out": punch_out_ms,
                "work_hours": metrics["work_hours"],
                "overtime_minutes": metrics["overtime_minutes"],
                "half_day": metrics["half_day"],
            }
        },
        return_document=True
    )

    if not updated_doc:
        raise HTTPException(status_code=409, detail="Record was punched out by a concurrent request")

    return clean_attendance_doc(updated_doc)


@app.patch("/attendance/{emp_code}/{date}", status_code=200)
def regularize_attendance(
    emp_code: str = Path(...),
    date: str = Path(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"),
    body: RegularizeRequest = ...,
):
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    existing = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not existing:
        raise HTTPException(status_code=404, detail="Attendance record not found for this date")

    target_status = body.status if body.status is not None else existing["status"]
    target_punch_in = body.punch_in if body.punch_in is not None else existing["punch_in"]
    target_punch_out = body.punch_out if body.punch_out is not None else existing["punch_out"]

    if target_status in ("ABSENT", "LEAVE"):
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(status_code=422, detail="punch_in and punch_out must be omitted/null for ABSENT or LEAVE")
        target_punch_in = None
        target_punch_out = None
    else:
        if target_punch_in is None:
            raise HTTPException(status_code=422, detail="punch_in is required for presence status")

        if body.punch_in is not None:
            target_punch_in = truncate_to_seconds_ms(target_punch_in)
        if body.punch_out is not None:
            target_punch_out = truncate_to_seconds_ms(target_punch_out)

        pi_dt = ms_to_ist_datetime(target_punch_in)
        computed_date = calculate_attendance_date(pi_dt, emp["shift_start"], emp["shift_end"])
        if computed_date != date:
            raise HTTPException(status_code=422, detail="punch_in must belong to the record's attendance date")

        if target_punch_out is not None:
            if target_punch_out <= target_punch_in:
                raise HTTPException(status_code=422, detail="punch_out must be after punch_in")
            if (target_punch_out - target_punch_in) > (24 * 3600 * 1000):
                raise HTTPException(status_code=422, detail="punch_out cannot be more than 24 hours after punch_in")

    if target_status in ("ABSENT", "LEAVE"):
        target_derived = {
            "late_minutes": 0,
            "work_hours": None,
            "overtime_minutes": 0,
            "half_day": False,
        }
    else:
        target_derived = compute_derived_metrics(
            target_punch_in, target_punch_out, date, emp["shift_start"], emp["shift_end"]
        )

    all_target_fields = {
        "status": target_status,
        "punch_in": target_punch_in,
        "punch_out": target_punch_out,
        **target_derived,
    }

    changes = {}
    for field, new_val in all_target_fields.items():
        old_val = existing.get(field)
        if old_val != new_val:
            changes[field] = {"from": old_val, "to": new_val}

    if not changes:
        raise HTTPException(status_code=422, detail="Request does not change any fields")

    now_ms = truncate_to_seconds_ms(int(datetime.now(timezone.utc).timestamp() * 1000))
    history_entry = {
        "at": now_ms,
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes,
    }

    updated_doc = db.attendance_logs.find_one_and_update(
        {"_id": existing["_id"]},
        {
            "$set": all_target_fields,
            "$push": {"history": history_entry},
        },
        return_document=True,
    )

    if not updated_doc:
        raise HTTPException(status_code=409, detail="Concurrent regularization collision")

    return clean_attendance_doc(updated_doc)