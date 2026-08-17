import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add project root to sys.path to allow imports from shared/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.src.api.v1.uploads import router as uploads_router

app = FastAPI(
    title="Semantic Map Generation API",
    description="Deterministic spatial floorplan parser MVP",
    version="1.0.0",
)

# Aggressive CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 router
app.include_router(uploads_router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "healthy"}
