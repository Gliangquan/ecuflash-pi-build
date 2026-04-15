from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["admin-ui"])

_ADMIN_HTML_PATH = Path(__file__).resolve().parent / "static" / "admin.html"


@router.get("/admin", response_class=HTMLResponse)
def admin_page() -> str:
    return _ADMIN_HTML_PATH.read_text(encoding="utf-8")
