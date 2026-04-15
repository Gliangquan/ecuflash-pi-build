from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.admin import router as admin_router
from app.admin_ui import router as admin_ui_router
from app.auth import router as auth_router
from app.init_db import init_db
from app.routers.ecu import router as ecu_router
from app.schemas import HealthOut
from app.settings import settings

init_db()

app = FastAPI(title=settings.app_name, debug=settings.app_debug)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
app.include_router(ecu_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(admin_ui_router)


@app.get("/health", response_model=HealthOut, tags=["system"])
def health() -> HealthOut:
    return HealthOut(status="ok", app=settings.app_name)
