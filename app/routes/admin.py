

"""
Admin Query Execution Plan Explain Endpoint
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Path

from app.database import db
from app.pipelines import (
    build_employee_monthly_pipeline,
    build_department_summary_pipeline,
    build_late_leaderboard_pipeline,
    build_department_trend_pipeline,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/explain/{endpoint}")
def explain_endpoint(
    endpoint: str = Path(..., pattern=r"^(attendance_list|employee_monthly|department_summary|late_leaderboard|department_trend)$"),
    emp_code: Optional[str] = None,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if endpoint == "attendance_list":
        coll_name = "attendance_logs"
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
        skip = (page - 1) * page_size
        explain_cmd = {
            "explain": {
                "find": coll_name,
                "filter": q,
                "sort": {"date": -1, "emp_code": 1},
                "skip": skip,
                "limit": page_size,
            },
            "verbosity": "executionStats",
        }

    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(status_code=422, detail="emp_code and month required")
        coll_name = "attendance_logs"
        pipeline = build_employee_monthly_pipeline(emp_code, month)
        explain_cmd = {
            "explain": {"aggregate": coll_name, "pipeline": pipeline, "cursor": {}},
            "verbosity": "executionStats",
        }

    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(status_code=422, detail="month required")
        coll_name = "employees"
        pipeline = build_department_summary_pipeline(month, department)
        explain_cmd = {
            "explain": {"aggregate": coll_name, "pipeline": pipeline, "cursor": {}},
            "verbosity": "executionStats",
        }

    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(status_code=422, detail="month required")
        coll_name = "attendance_logs"
        pipeline = build_late_leaderboard_pipeline(month, limit, department)
        explain_cmd = {
            "explain": {"aggregate": coll_name, "pipeline": pipeline, "cursor": {}},
            "verbosity": "executionStats",
        }

    elif endpoint == "department_trend":
        if not department or not from_date or not to_date:
            raise HTTPException(status_code=422, detail="department, from, to required")
        coll_name = "employees"
        pipeline = build_department_trend_pipeline(department, from_date, to_date)
        explain_cmd = {
            "explain": {"aggregate": coll_name, "pipeline": pipeline, "cursor": {}},
            "verbosity": "executionStats",
        }

    try:
        raw_explain = db.command(explain_cmd)
        return {"endpoint": endpoint, "collection": coll_name, "explain": raw_explain}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explain failed: {str(e)}")