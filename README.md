# Employee Attendance & Analytics API (HROne Engineering Assignment)

A production-grade, asynchronous FastAPI backend service integrated with MongoDB for employee attendance tracking, manual regularization audit trails, and analytical reporting pipelines.

---

## **Tech Stack**
* **Framework:** Python 3.11+, FastAPI, Pydantic v2
* **Database:** MongoDB 6.0+ (PyMongo)
* **Server:** Uvicorn ASGI Server

---

## Quickstart & Running Locally

### 1. Prerequisites

Ensure Python 3.11+ and MongoDB 6.0+ are installed and running locally on port `27017` (or provide a remote MongoDB Atlas connection string).

### 2. Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/ankit485803/Employee-Attendance-Automation-System.git

cd Employee-Attendance-Automation-System

python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

Install the required dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. How to Run

#### Environment Configuration

Create a local `.env` file in the project root directory. Do not commit this file to Git.

```dotenv
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
```

#### Load Sample Data

Seed the database with the provided sample records:

```bash
python sample_seed.py
```

> **Note:** The seed script clears existing documents from the `employees` and `attendance_logs` collections before inserting the sample data. Run it only when replacing those collections is intended.

#### Start the FastAPI Server

Run the Uvicorn application server on port `8000`:

```bash
python -m uvicorn app.main:app --port 8000 --reload
```

#### Access API Documentation

Once the server is running, open the interactive Swagger UI:

[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

You can also access the API health endpoint:

[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

## 4. API Endpoints Summary

### System Health
- `GET /health`

### Employee Management
- `POST /employees`
- `GET /employees`

### Attendance Operations
- `POST /attendance/punch-in`
- `POST /attendance/punch-out`
- `GET /attendance`
- `PATCH /attendance/{emp_code}/{date}`

### Analytics & Reports
- `GET /analytics/employees/{emp_code}/monthly`
- `GET /analytics/departments/summary`
- `GET /analytics/leaderboard/late`
- `GET /analytics/departments/{department}/trend`

### Query Profiling
- `GET /admin/explain/{endpoint}`
