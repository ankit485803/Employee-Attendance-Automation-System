# Architectural & Design Decisions (Part C)

### 1. Database Indexes Created & Rationale
We created four primary database indexes at application startup:
* **`employees` Collection:**
  * `{ "emp_code": 1 }` (Unique): Guarantees customer business code uniqueness and speeds up employee lookup during punch operations.
  * `{ "department": 1 }`: Enables fast index scans for department-filtered listing and aggregation pipelines.
* **`attendance_logs` Collection:**
  * `{ "emp_code": 1, "date": 1 }` (Unique): Prevents duplicate attendance records for the same employee on the same date under high concurrency.
  * `{ "date": -1, "emp_code": 1 }`: Backs list query sorting (`GET /attendance`) and date-range filtering.
  * `{ "status": 1 }`: Optimizes presence/absence filtering.

---

### 2. Concurrent Punch-In Race Condition Strategy
To prevent race conditions when two identical punch-in requests arrive simultaneously, we rely entirely on MongoDB's unique compound index `{ "emp_code": 1, "date": 1 }` rather than check-then-insert logic in Python. When concurrent requests hit the database, MongoDB atomically permits exactly one insertion while raising a `DuplicateKeyError` for all others. The application catches this error and immediately returns HTTP `409 Conflict`.

---

### 3. Leaderboard Tie-Breaking & Cutoff Handling
In `GET /analytics/leaderboard/late`, standard competition ranking is implemented using MongoDB's `$setWindowFields` stage with `$denseRank` ordered by `total_late_minutes` descending. Tied employees receive identical rank numbers (e.g., 1, 2, 2, 4). The `$match: { "rank": { "$lte": limit } }` filter is applied **after** ranking. If a tie occurs at the cutoff (e.g., two employees tie for rank 10), both employees are retained in the output, which may produce more than `limit` items while preserving ranking integrity.

---

### 4. Department Summary Headcount & No-Log Employee Accounting
`GET /analytics/departments/summary` calculates department headcount per Rule R9 by querying the `employees` collection as the base source (`joined_on <= month_end_date`) and performing an outer `$lookup` to join records from `attendance_logs`. Employees with zero attendance records in the month are preserved via `preserveNullAndEmptyArrays: true`. Headcount is computed using `$addToSet` on employee codes per department, ensuring employees with no logs are accurately counted toward headcount without inflating presence metrics.

---

### 5. Horizontal Scaling Strategy for 100x Data Growth
To scale the architecture for 10,000,000+ attendance records:
1. **Sharding Strategy:** Shard `attendance_logs` using a compound shard key `{ "emp_code": 1, "date": 1 }` to evenly distribute write operations across nodes while keeping an employee's records co-located.
2. **Read Replica Offloading:** Route read-heavy analytics aggregation queries (`GET /analytics/...`) to secondary read replicas using PyMongo's `SecondaryPreferred` read preference.
3. **Pre-Aggregated Summary Collections:** Materialize daily/monthly statistics incrementally using MongoDB `$merge` or change streams instead of running full collection aggregations on large date ranges.