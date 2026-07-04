"""
main.py — FastAPI application entry point.

Run with:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the backend directory is on the Python path regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(
    title="Finance Analyzer API",
    description="Privacy-first personal finance analyzer. All data stays local.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow the local Next.js dev server to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    return {"message": "Finance Analyzer API — visit /docs for the interactive API explorer."}
