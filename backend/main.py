from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api import api_router

app = FastAPI(title="Altius Investor Document Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    from pathlib import Path
    from app.config import settings
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    (Path(settings.data_dir) / "chroma").mkdir(parents=True, exist_ok=True)
    init_db()


app.include_router(api_router)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}
