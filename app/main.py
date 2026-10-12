"""
Employee Attendance & Analytics API - Application Entrypoint
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import init_indexes
from app.routes import employees, attendance, analytics, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database indexes on application startup
    init_indexes()
    yield


app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="2.0.0",
    lifespan=lifespan,
)

# Register route modules
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(analytics.router)
app.include_router(admin.router)