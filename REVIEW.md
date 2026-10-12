# Starter Code Review Findings (Part A)

This document lists the defects identified during the review of the starter codebase (`app/main.py`), including root cause analysis, failing symptoms/reproduction steps, and the concrete fixes applied.

---

### **Defect 1: Race Condition on Punch-In (Missing Unique Compound Index)**
* **Location:** `POST /attendance/punch-in`
* **Defect:** The endpoint checked for existing records using `db.attendance_logs.find_one(...)` before calling `insert_one(...)`. Under concurrent load, multiple parallel punch-in requests for the same employee and date could pass the check simultaneously and create duplicate records.
* **Symptom:** Two simultaneous `POST /attendance/punch-in` requests both return `201 Created` instead of exactly one `201` and one `409 Conflict`.
* **Fix Applied:** Added a unique compound database index on `{"emp_code": 1, "date": 1}` in `app/database.py` and wrapped `insert_one` in a `try...except DuplicateKeyError` block that returns HTTP `409 Conflict`.

---

### **Defect 2: Timezone Bug in Attendance Date & Timestamp Parsing**
* **Location:** `POST /attendance/punch-in` & `compute_late_minutes`
* **Defect:** `datetime.fromtimestamp(body.punched_at / 1000)` was called without specifying a timezone, producing naive local datetimes. Epoch milliseconds were parsed using UTC date boundaries instead of IST (UTC+05:30), causing punch-ins near midnight IST to be assigned to the wrong calendar date.
* **Symptom:** A punch-in at `2026-10-12 02:00:00 IST` (`1791846600000` epoch ms) was recorded under date `2026-10-11` instead of `2026-10-12`.
* **Fix Applied:** Implemented `ms_to_ist_datetime(ms)` in `app/rules.py` to ensure all epoch conversions explicitly use `timezone.utc` first and are then converted to `IST` (`UTC+05:30`).

---

### **Defect 3: Failure to Truncate Epoch Milliseconds to Whole Seconds (Rule R1)**
* **Location:** `POST /attendance/punch-in` & calculation helpers
* **Defect:** Fractional seconds in sub-second epoch timestamps were passed directly into date/time calculations without truncation.
* **Symptom:** Sub-second millisecond variations caused imprecise late minute computations and inconsistent string representations.
* **Fix Applied:** Added `truncate_to_seconds_ms(ms)` in `app/rules.py` which computes `(ms // 1000) * 1000` prior to any calculation or database persistence.

---

### **Defect 4: Incorrect Late Grace Period Calculation (Rule R2)**
* **Location:** `compute_late_minutes`
* **Defect:** The starter function checked `if minutes > 10` using `(punch_in - start).total_seconds() / 60`. A punch-in exactly at `09:40:01` yielded `10.01` minutes, which evaluated to `10` instead of counting late from `shift_start` (10 minutes).
* **Symptom:** Punch-in at `09:40:01` for a `09:30` shift returned `0` late minutes instead of `10` minutes.
* **Fix Applied:** Updated `compute_late_minutes` to check `if diff_seconds > 600` (strictly greater than 10 minutes) and return `math.floor(diff_seconds / 60.0)`.

---

### **Defect 5: Incorrect Pagination In-Memory Slicing & Total Calculation**
* **Location:** `GET /employees` & `GET /attendance`
* **Defect:** In `GET /attendance`, the starter loaded the entire collection into Python memory using `list(db.attendance_logs.find(q))` and performed in-memory list slicing `[(page - 1) * page_size : page * page_size]`. In `GET /employees`, `count_documents({})` ignored the department filter, returning the total collection count instead of the filtered count.
* **Symptom:** Poor memory usage and query timeout on a 100,000-record database; incorrect `total` count when filtering employees by department.
* **Fix Applied:** Offloaded pagination and filtering directly to MongoDB using `.count_documents(q)`, `.skip(skip)`, `.limit(page_size)`, and `.sort(...)`.

---

### **Defect 6: Exposed Internal MongoDB `_id` and Missing Clean-Up**
* **Location:** `POST /attendance/punch-in`
* **Defect:** `doc["id"] = str(res.inserted_id)` added an unnecessary `id` field to the response, violating the `openapi.yaml` contract.
* **Symptom:** API response contained `"id": "651f..."`, causing client schema validation failures against OpenAPI expectations.
* **Fix Applied:** Removed `doc["id"]` injection and added `clean_attendance_doc` to strip `_id` before returning documents.

---

### **Defect 7: Incorrect Work Hours Rounding Method (Rule R4 & R8)**
* **Location:** `compute_work_hours`
* **Defect:** Standard Python `round()` was used, which implements Banker's Rounding (round-to-even) instead of standard half-up arithmetic required by Rule R8.
* **Symptom:** `2.125` rounded to `2.12` instead of `2.13`.
* **Fix Applied:** Created `round_half_up(val, decimals)` using `decimal.Decimal` with `ROUND_HALF_UP`.

---

### **Defect 8: Overnight Shift Handling Omitted (Rule R1)**
* **Location:** `POST /attendance/punch-in`
* **Defect:** Overnight shifts where `shift_end <= shift_start` (e.g., `22:00` to `06:00`) were not accounted for, improperly assigning early morning punch-ins to the new calendar day.
* **Symptom:** Punch-in at `02:00:00 IST` for a `22:00 - 06:00` shift starting on Oct 11 was incorrectly saved under date `2026-10-12`.
* **Fix Applied:** Implemented `calculate_attendance_date` in `app/rules.py` to assign punch-ins prior to `shift_end` on overnight shifts to the previous calendar day.

---

### **Defect 9: Absence of Input Field Pattern Validation**
* **Location:** Pydantic models in `app/main.py`
* **Defect:** `emp_code`, email formats, and timestamp ranges had no validation rules, allowing malformed strings or seconds-based timestamps into the system.
* **Symptom:** Request with `punched_at: 1783312500` (seconds instead of epoch milliseconds) was accepted as valid.
* **Fix Applied:** Enforced regex patterns and constraints using `pydantic.Field` (`ge=100000000000`, regex patterns for `emp_code` and email).

---

### **Defect 10: Missing Health Readiness DB Ping**
* **Location:** `GET /health`
* **Defect:** `GET /health` unconditionally returned `{"status": "ok"}` without testing database connectivity.
* **Symptom:** `GET /health` returned HTTP `200` even when MongoDB was down.
* **Fix Applied:** Updated `health()` to execute `db.command("ping")` and return `503 Service Unavailable` if MongoDB is unresponsive.