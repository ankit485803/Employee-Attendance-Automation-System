

"""
Business Rules & Decision Logic (R1 - R5)
"""

import math
from datetime import datetime, timedelta, timezone, time as dtime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

# IST Timezone constant (UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30))


def round_half_up(val: float, decimals: int = 2) -> float:
    """R8: Rounds floats using half-up arithmetic (not banker's rounding)."""
    d = Decimal(str(val))
    target = Decimal("10") ** -decimals
    return float(d.quantize(target, rounding=ROUND_HALF_UP))


def truncate_to_seconds_ms(ms: int) -> int:
    """R1: Truncates epoch milliseconds to whole seconds."""
    return (ms // 1000) * 1000


def ms_to_ist_datetime(ms: int) -> datetime:
    """Converts epoch milliseconds to an IST-aware datetime object."""
    sec = ms // 1000
    return datetime.fromtimestamp(sec, tz=timezone.utc).astimezone(IST)


def calculate_attendance_date(punch_in_dt: datetime, shift_start: str, shift_end: str) -> str:
    """
    R1: Computes attendance date string (YYYY-MM-DD IST).
    Overnight shifts: If punch_in IST time < shift_end, it belongs to the previous day.
    """
    sh_in, sm_in = map(int, shift_start.split(":"))
    sh_out, sm_out = map(int, shift_end.split(":"))

    is_overnight = (sh_out, sm_out) <= (sh_in, sm_in)
    punch_time = punch_in_dt.time()
    shift_end_time = dtime(sh_out, sm_out)

    if is_overnight and punch_time < shift_end_time:
        actual_date = (punch_in_dt - timedelta(days=1)).date()
    else:
        actual_date = punch_in_dt.date()

    return actual_date.isoformat()


def compute_late_minutes(punch_in_ms: int, attendance_date_str: str, shift_start: str, shift_end: str) -> int:
    """R2: Grace period of 10 mins. Late only if strictly > 10:00 past shift_start."""
    punch_in_dt = ms_to_ist_datetime(punch_in_ms)
    sh_in, sm_in = map(int, shift_start.split(":"))
    sh_out, sm_out = map(int, shift_end.split(":"))
    is_overnight = (sh_out, sm_out) <= (sh_in, sm_in)

    att_date = datetime.fromisoformat(attendance_date_str).date()

    if is_overnight and punch_in_dt.time() < dtime(sh_out, sm_out):
        shift_start_dt = datetime.combine(att_date, dtime(sh_in, sm_in), tzinfo=IST)
    else:
        shift_start_dt = datetime.combine(att_date, dtime(sh_in, sm_in), tzinfo=IST)

    diff_seconds = (punch_in_dt - shift_start_dt).total_seconds()

    if diff_seconds > 600:  # Strictly > 10 mins
        return math.floor(diff_seconds / 60.0)
    return 0


def compute_shift_end_datetime(attendance_date_str: str, shift_start: str, shift_end: str) -> datetime:
    sh_in, sm_in = map(int, shift_start.split(":"))
    sh_out, sm_out = map(int, shift_end.split(":"))
    att_date = datetime.fromisoformat(attendance_date_str).date()

    is_overnight = (sh_out, sm_out) <= (sh_in, sm_in)
    if is_overnight:
        return datetime.combine(att_date + timedelta(days=1), dtime(sh_out, sm_out), tzinfo=IST)
    else:
        return datetime.combine(att_date, dtime(sh_out, sm_out), tzinfo=IST)


def compute_overtime_minutes(punch_out_ms: int, attendance_date_str: str, shift_start: str, shift_end: str) -> int:
    """R3: Overtime in whole minutes from shift_end to punch_out (minimum 30 mins threshold)."""
    punch_out_dt = ms_to_ist_datetime(punch_out_ms)
    shift_end_dt = compute_shift_end_datetime(attendance_date_str, shift_start, shift_end)

    diff_seconds = (punch_out_dt - shift_end_dt).total_seconds()
    if diff_seconds >= 1800:  # >= 30 mins
        return math.floor(diff_seconds / 60.0)
    return 0


def compute_derived_metrics(
    punch_in_ms: int,
    punch_out_ms: Optional[int],
    attendance_date_str: str,
    shift_start: str,
    shift_end: str
) -> Dict[str, Any]:
    """R4 & R5: Computes late_minutes, work_hours, overtime_minutes, and half_day."""
    late_mins = compute_late_minutes(punch_in_ms, attendance_date_str, shift_start, shift_end)

    if punch_out_ms is None:
        return {
            "late_minutes": late_mins,
            "work_hours": None,
            "overtime_minutes": 0,
            "half_day": False
        }

    diff_sec = (punch_out_ms - punch_in_ms) / 1000.0
    work_hrs = round_half_up(diff_sec / 3600.0, 2)
    overtime_mins = compute_overtime_minutes(punch_out_ms, attendance_date_str, shift_start, shift_end)
    half_day = work_hrs < 4.50

    return {
        "late_minutes": late_mins,
        "work_hours": work_hrs,
        "overtime_minutes": overtime_mins,
        "half_day": half_day
    }