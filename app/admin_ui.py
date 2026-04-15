from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["admin-ui"])

_HTML = (Path(__file__).resolve().parent / "static" / "admin.html").read_text(encoding="utf-8")


@router.get("/admin", response_class=HTMLResponse)
def admin_page() -> str:
    return _HTML
