import json
from typing import List, Optional
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text, bindparam

from app.db import get_conn
from app.security import future_str, get_current_user, now_str, require_admin
from app.settings import settings
from app.storage import build_object_url, remove_object, upload_bytes


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AdminUserCreateIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=4, max_length=64)
    status: str = Field(default="enabled")


class AdminResetPasswordIn(BaseModel):
    password: str = Field(min_length=4, max_length=64)


class AdminRejectUserIn(BaseModel):
    reason: str = Field(default="待补充资料", max_length=255)


class UserAuthSaveIn(BaseModel):
    auth_days: int = Field(default=365)


class PermissionSaveIn(BaseModel):
    user_id: int
    function_ids: List[int]
    end_at: Optional[str] = None


class PurchaseConfigIn(BaseModel):
    title: str = Field(default="功能开通")
    message: str = Field(default="当前功能尚未开通，请扫码付款后联系管理员授权。")
    qr_code_url: str = Field(default="")
    contact: str = Field(default="")
    update_notice: str = Field(default="")
    force_update: str = Field(default="0")
    latest_version: str = Field(default="")
    latest_download_url: str = Field(default="")
    allow_passwordless_register: str = Field(default="0")
    registration_requires_approval: str = Field(default="1")
    virtual_downloads_json: str = Field(default="[]")
    wiring_guides_json: str = Field(default="[]")


class AdminAssetSaveIn(BaseModel):
    title: str = Field(default="", max_length=255)
    category: str = Field(default="manual", max_length=32)
    summary: str = Field(default="")
    image_url: str = Field(default="", max_length=512)
    download_text: str = Field(default="立即下载", max_length=64)
    sort_order: int = Field(default=0)
    is_enabled: int = Field(default=1)
    file_name: str = Field(default="", max_length=255)
    object_key: str = Field(default="", max_length=255)
    file_url: str = Field(default="", max_length=512)
    content_type: str = Field(default="", max_length=128)
    file_size: int = Field(default=0, ge=0)


class WiringGuideSaveIn(BaseModel):
    name: str = Field(default="", max_length=255)
    model: str = Field(default="", max_length=128)
    car_model: str = Field(default="", max_length=128)
    keywords: str = Field(default="", max_length=255)
    description: str = Field(default="")
    preview_image_url: str = Field(default="", max_length=512)
    sort_order: int = Field(default=0)
    is_enabled: int = Field(default=1)
    file_name: str = Field(default="", max_length=255)
    object_key: str = Field(default="", max_length=255)
    file_url: str = Field(default="", max_length=512)
    content_type: str = Field(default="", max_length=128)
    file_size: int = Field(default=0, ge=0)


class LearningArticleSaveIn(BaseModel):
    title: str = Field(default="", max_length=255)
    summary: str = Field(default="")
    cover_image_url: str = Field(default="", max_length=512)
    content_html: str = Field(default="")
    sort_order: int = Field(default=0)
    is_enabled: int = Field(default=1)


class AdminIdentifyRuleSaveIn(BaseModel):
    ecu_model_id: int
    addr: int
    data_length: int
    hex_value: str = Field(default="", max_length=255)


class AdminFunctionSaveIn(BaseModel):
    ecu_model_id: int
    name: str = Field(default="", max_length=128)
    success_msg: str = Field(default="", max_length=255)
    sort_order: int = Field(default=0)
    is_enabled: int = Field(default=1)


class AdminFunctionVariantSaveIn(BaseModel):
    function_id: int
    identify_hex: str = Field(default="", max_length=255)


class AdminFunctionPatchSaveIn(BaseModel):
    variant_id: int
    seq_no: int = Field(default=0)
    addr: int
    data_length: int
    value_hex: str = Field(default="")


def _admin_guard(user: dict = Depends(get_current_user)) -> dict:
    return require_admin(user)


def _validate_resource_json(raw_text: str, field_name: str) -> None:
    try:
        data = json.loads(raw_text or "[]")
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field_name} 数据格式不正确")
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是列表")
    for item in data:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"{field_name} 每一项都必须是对象")


def _build_internal_file_url(object_key: str) -> str:
    key = (object_key or "").strip()
    if not key:
        return ""
    return f"/api/v1/files/{quote(key, safe='')}"


def _guess_cover_from_url(url: str) -> str:
    text_value = (url or "").strip()
    if not text_value:
        return ""
    parsed = urlparse(text_value)
    path_value = (parsed.path or text_value).lower()
    if any(path_value.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return text_value
    return ""


def _guess_download_text(content_type: str, file_name: str, title: str) -> str:
    text_value = (content_type or "").lower()
    file_lower = (file_name or "").lower()
    title_text = (title or "").strip()
    if text_value.startswith("image/") or any(file_lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "查看图片"
    if "pdf" in text_value or file_lower.endswith(".pdf"):
        return "查看文档"
    if any(file_lower.endswith(ext) for ext in (".zip", ".rar", ".7z")):
        return "下载资料包"
    return "立即下载" if title_text else "立即打开"


def _normalize_admin_asset_row(row: dict) -> dict:
    item = dict(row)
    object_key = (item.get("object_key") or "").strip()
    file_url = (item.get("file_url") or item.get("url") or "").strip()
    download_url = _build_internal_file_url(object_key) if object_key else file_url
    public_url = build_object_url(object_key) if object_key else file_url
    title = (item.get("title") or item.get("name") or "").strip()
    summary = (item.get("summary") or item.get("description") or "").strip()
    image_url = (item.get("image_url") or item.get("preview_image_url") or "").strip()
    if not image_url:
        image_url = _guess_cover_from_url(download_url) or _guess_cover_from_url(public_url)
    file_name = (item.get("file_name") or "").strip()
    if object_key and not file_name:
        file_name = object_key.rsplit("/", 1)[-1]
    category = (item.get("category") or "manual").strip() or "manual"
    download_text = (item.get("download_text") or "").strip() or _guess_download_text(item.get("content_type") or "", file_name, title)
    item.update(
        {
            "title": title,
            "name": title or (item.get("name") or ""),
            "summary": summary,
            "description": summary or (item.get("description") or ""),
            "remark": summary or (item.get("remark") or ""),
            "image_url": image_url,
            "file_name": file_name,
            "category": category,
            "download_text": download_text,
            "button_text": download_text,
            "download_url": download_url,
            "file_url": file_url or download_url,
            "url": download_url or file_url,
            "public_url": public_url,
            "is_enabled": 1 if item.get("is_enabled") else 0,
        }
    )
    return item


def _normalize_wiring_guide_row(row: dict) -> dict:
    item = _normalize_admin_asset_row(row)
    item["name"] = item.get("title") or (item.get("name") or "")
    item["description"] = item.get("summary") or (item.get("description") or "")
    item["preview_image_url"] = item.get("image_url") or ""
    return item


def _normalize_learning_article_row(row: dict) -> dict:
    item = dict(row)
    item["summary"] = (item.get("summary") or "").strip()
    item["cover_image_url"] = (item.get("cover_image_url") or "").strip()
    item["content_html"] = item.get("content_html") or ""
    item["is_enabled"] = 1 if item.get("is_enabled") else 0
    return item


def _build_wiring_guides_json(conn) -> str:
    rows = conn.execute(
        text(
            """
            SELECT id, name, model, car_model, keywords, description, preview_image_url, file_name, object_key, file_url, content_type, file_size, sort_order, is_enabled
            FROM app_wiring_guide
            WHERE is_enabled = 1
            ORDER BY sort_order ASC, id DESC
            """
        )
    ).mappings().all()
    items = []
    for row in rows:
        item = _normalize_wiring_guide_row(dict(row))
        items.append(
            {
                "id": item["id"],
                "name": item.get("name") or "",
                "model": item.get("model") or "",
                "car_model": item.get("car_model") or "",
                "keywords": item.get("keywords") or "",
                "description": item.get("description") or "",
                "remark": item.get("description") or "",
                "image_url": item.get("preview_image_url") or item.get("image_url") or "",
                "button_text": item.get("download_text") or "查看接线图",
                "file_name": item.get("file_name") or "",
                "url": item.get("download_url") or "",
            }
        )
    return json.dumps(items, ensure_ascii=False)


def _validate_wiring_guide_payload(payload: "WiringGuideSaveIn") -> dict:
    name = payload.name.strip()
    object_key = payload.object_key.strip()
    file_url = payload.file_url.strip()
    file_name = payload.file_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="接线图名称不能为空")
    if not object_key and not file_url:
        raise HTTPException(status_code=400, detail="请先上传接线图文件")
    if object_key and not file_name:
        file_name = object_key.rsplit("/", 1)[-1]
    preview_image_url = payload.preview_image_url.strip()
    if not preview_image_url:
        preview_image_url = _guess_cover_from_url(file_url or build_object_url(object_key))
    return {
        "name": name,
        "model": payload.model.strip(),
        "car_model": payload.car_model.strip(),
        "keywords": payload.keywords.strip(),
        "description": payload.description.strip(),
        "preview_image_url": preview_image_url,
        "file_name": file_name,
        "object_key": object_key,
        "file_url": file_url,
        "content_type": payload.content_type.strip(),
        "file_size": payload.file_size,
        "sort_order": payload.sort_order,
        "is_enabled": 1 if payload.is_enabled else 0,
    }


@router.get("/dashboard")
def dashboard(_: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        total_users = conn.execute(text("SELECT COUNT(*) AS c FROM app_user")).mappings().first()["c"]
        active_users = conn.execute(
            text("SELECT COUNT(*) AS c FROM app_user WHERE status = 'enabled'")
        ).mappings().first()["c"]
        pending_users = conn.execute(
            text("SELECT COUNT(*) AS c FROM app_user WHERE status = 'pending'")
        ).mappings().first()["c"]
        bound_devices = conn.execute(
            text("SELECT COUNT(*) AS c FROM app_user WHERE device_id IS NOT NULL AND device_id <> ''")
        ).mappings().first()["c"]
        recent_users = conn.execute(
            text(
                """
                SELECT id, phone, name, status, created_at, last_login_at
                FROM app_user
                ORDER BY id DESC
                LIMIT 8
                """
            )
        ).mappings().all()
        recent_logs = conn.execute(
            text(
                """
                SELECT id, actor_name, action, target_type, target_id, detail, created_at
                FROM app_operation_log
                ORDER BY id DESC
                LIMIT 10
                """
            )
        ).mappings().all()
    return {
        "summary": {
            "total_users": total_users,
            "active_users": active_users,
            "pending_users": pending_users,
            "bound_devices": bound_devices,
        },
        "recent_users": [dict(row) for row in recent_users],
        "recent_logs": [dict(row) for row in recent_logs],
    }


@router.get("/users")
def list_users(_: dict = Depends(_admin_guard)) -> dict:
    sql = text(
        """
        SELECT
            u.id,
            u.phone,
            u.name,
            u.status,
            u.approval_note,
            u.is_admin,
            u.device_id,
            u.device_name,
            u.device_bound_at,
            u.auth_end_at,
            u.created_at,
            u.last_login_at
        FROM app_user u
        ORDER BY u.id DESC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/users")
def create_user(payload: AdminUserCreateIn, admin: dict = Depends(_admin_guard)) -> dict:
    phone = payload.phone.strip()
    name = payload.name.strip()
    status = payload.status if payload.status in {"enabled", "disabled", "pending"} else "enabled"
    from app.security import hash_password

    with get_conn() as conn:
        exists = conn.execute(
            text("SELECT id FROM app_user WHERE phone = :phone LIMIT 1"),
            {"phone": phone},
        ).mappings().first()
        if exists:
            raise HTTPException(status_code=409, detail="phone already exists")
        now = now_str()
        conn.execute(
            text(
                """
                INSERT INTO app_user (phone, name, password_hash, status, approval_note, is_admin, created_at, updated_at)
                VALUES (:phone, :name, :password_hash, :status, :approval_note, 0, :created_at, :updated_at)
                """
            ),
            {
                "phone": phone,
                "name": name,
                "password_hash": hash_password(payload.password),
                "status": status,
                "approval_note": "待后台审批" if status == "pending" else None,
                "created_at": now,
                "updated_at": now,
            },
        )
        user_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()["id"]
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_create_user', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(user_id),
                "detail": f"phone={phone};name={name}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True, "id": user_id}


@router.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT id, status FROM app_user WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        next_status = "disabled" if row["status"] == "enabled" else "enabled"
        now = now_str()
        conn.execute(
            text("UPDATE app_user SET status = :status, updated_at = :updated_at WHERE id = :id"),
            {"status": next_status, "updated_at": now, "id": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_toggle_user', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(user_id),
                "detail": f"status={next_status}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True, "status": next_status}


@router.post("/users/{user_id}/approve")
def approve_user(user_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT id, status, name FROM app_user WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        now = now_str()
        auth_end_at = future_str(365)
        conn.execute(
            text("UPDATE app_user SET status = 'enabled', approval_note = NULL, auth_end_at = :auth_end_at, updated_at = :updated_at WHERE id = :id"),
            {"auth_end_at": auth_end_at, "updated_at": now, "id": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_approve_user', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(user_id),
                "detail": f"name={row['name']};status=enabled;auth_end_at={auth_end_at}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True, "status": "enabled", "auth_end_at": auth_end_at}


@router.post("/users/{user_id}/reject")
def reject_user(user_id: int, payload: AdminRejectUserIn, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT id, status, name FROM app_user WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        now = now_str()
        reason = payload.reason.strip() or "待补充资料"
        conn.execute(
            text("UPDATE app_user SET status = 'disabled', approval_note = :approval_note, updated_at = :updated_at WHERE id = :id"),
            {"approval_note": f"已驳回：{reason}", "updated_at": now, "id": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_reject_user', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(user_id),
                "detail": f"name={row['name']};reason={reason}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True, "status": "disabled"}


@router.post("/users/{user_id}/auth")
def save_user_auth(user_id: int, payload: UserAuthSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    auth_days = int(payload.auth_days or 0)
    if auth_days not in {365, 3650}:
        raise HTTPException(status_code=400, detail="auth_days only supports 365 or 3650")
    now = now_str()
    auth_end_at = future_str(auth_days)
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT id, name FROM app_user WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        conn.execute(
            text("UPDATE app_user SET status = 'enabled', approval_note = NULL, auth_end_at = :auth_end_at, updated_at = :updated_at WHERE id = :id"),
            {"auth_end_at": auth_end_at, "updated_at": now, "id": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_set_user_auth', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(user_id),
                "detail": f"name={row['name']};auth_days={auth_days};auth_end_at={auth_end_at}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True, "auth_days": auth_days, "auth_end_at": auth_end_at}


@router.post("/users/{user_id}/unbind-device")
def admin_unbind_user_device(user_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT id, phone, name, device_id FROM app_user WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        old_device_id = row.get("device_id") or ""
        conn.execute(
            text(
                """
                UPDATE app_user
                SET device_id = NULL,
                    device_name = NULL,
                    device_bound_at = NULL,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {"updated_at": now_str(), "id": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_unbind_user_device', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(user_id),
                "detail": f"phone={row['phone']};unbound_device={old_device_id}",
                "created_at": now_str(),
            },
        )
        conn.commit()
    return {"ok": True, "unbound_device": old_device_id}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    if int(user_id) == int(admin["id"]):
        raise HTTPException(status_code=400, detail="cannot delete current admin")
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT id, phone, name FROM app_user WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        now = now_str()
        conn.execute(text("DELETE FROM app_session WHERE user_id = :user_id"), {"user_id": user_id})
        conn.execute(text("DELETE FROM app_user_function_permission WHERE user_id = :user_id"), {"user_id": user_id})
        conn.execute(text("DELETE FROM app_user WHERE id = :id"), {"id": user_id})
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_delete_user', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(user_id),
                "detail": f"phone={row['phone']};name={row['name']}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: AdminResetPasswordIn,
    admin: dict = Depends(_admin_guard),
) -> dict:
    from app.security import hash_password

    new_password = payload.password.strip()
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT id, phone, name FROM app_user WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="user not found")

        now = now_str()
        conn.execute(
            text(
                "UPDATE app_user SET password_hash = :password_hash, updated_at = :updated_at WHERE id = :id"
            ),
            {"password_hash": hash_password(new_password), "updated_at": now, "id": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_reset_password', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(user_id),
                "detail": f"phone={row['phone']};name={row['name']}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.get("/permission-tree")
def permission_tree(_: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        functions = conn.execute(
            text(
                """
                SELECT MIN(id) AS id, name, MAX(success_msg) AS success_msg, MIN(sort_order) AS sort_order
                FROM ecu_function
                WHERE is_enabled = 1
                GROUP BY name
                ORDER BY MIN(sort_order) ASC, MIN(id) ASC
                """
            )
        ).mappings().all()
    items = [
        {
            "id": row["id"],
            "label": row["name"],
            "type": "function",
            "success_msg": row["success_msg"],
        }
        for row in functions
    ]
    return {"items": items}


@router.get("/users/{user_id}/permissions")
def user_permissions(user_id: int, _: dict = Depends(_admin_guard)) -> dict:
    sql = text(
        """
        SELECT p.function_id, f.name AS function_name, p.end_at, p.status
        FROM app_user_function_permission p
        LEFT JOIN ecu_function f ON f.id = p.function_id
        WHERE p.user_id = :user_id
        ORDER BY p.function_id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql, {"user_id": user_id}).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/permissions")
def save_permissions(payload: PermissionSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        user = conn.execute(
            text("SELECT id FROM app_user WHERE id = :id LIMIT 1"),
            {"id": payload.user_id},
        ).mappings().first()
        if not user:
            raise HTTPException(status_code=404, detail="user not found")
        selected_ids = sorted(set(payload.function_ids))
        selected_names = []
        if selected_ids:
            placeholders = ", ".join(f":id_{index}" for index in range(len(selected_ids)))
            selected_rows = conn.execute(
                text(f"SELECT DISTINCT name FROM ecu_function WHERE id IN ({placeholders})"),
                {f"id_{index}": value for index, value in enumerate(selected_ids)},
            ).mappings().all()
            selected_names = [row["name"] for row in selected_rows if row.get("name")]
        expanded_ids = []
        if selected_names:
            placeholders = ", ".join(f":name_{index}" for index in range(len(selected_names)))
            expanded_rows = conn.execute(
                text(f"SELECT id FROM ecu_function WHERE is_enabled = 1 AND name IN ({placeholders}) ORDER BY id ASC"),
                {f"name_{index}": value for index, value in enumerate(selected_names)},
            ).mappings().all()
            expanded_ids = [int(row["id"]) for row in expanded_rows]
        now = now_str()
        conn.execute(
            text("DELETE FROM app_user_function_permission WHERE user_id = :user_id"),
            {"user_id": payload.user_id},
        )
        for function_id in expanded_ids:
            conn.execute(
                text(
                    """
                    INSERT INTO app_user_function_permission (user_id, function_id, start_at, end_at, status, created_at, updated_at)
                    VALUES (:user_id, :function_id, :start_at, :end_at, 'enabled', :created_at, :updated_at)
                    """
                ),
                {
                    "user_id": payload.user_id,
                    "function_id": function_id,
                    "start_at": now,
                    "end_at": payload.end_at,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_save_permissions', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(payload.user_id),
                "detail": f"function_count={len(selected_names)};expanded_count={len(expanded_ids)};end_at={payload.end_at}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True, "count": len(selected_names)}


@router.get("/purchase-config")
def get_purchase_config(_: dict = Depends(_admin_guard)) -> dict:
    defaults = {
        "title": "功能开通",
        "message": "当前功能尚未开通，请扫码付款后联系管理员授权。",
        "qr_code_url": "",
        "contact": "",
    }
    with get_conn() as conn:
        rows = conn.execute(
            text(
                "SELECT setting_key, setting_value FROM app_setting WHERE setting_key IN ('purchase_title','purchase_message','purchase_qr_code_url','purchase_contact','update_notice','force_update','latest_version','latest_download_url','allow_passwordless_register','registration_requires_approval','virtual_downloads_json')"
            )
        ).mappings().all()
        wiring_guides_json = _build_wiring_guides_json(conn)
    mapping = {row["setting_key"]: row["setting_value"] or "" for row in rows}
    raw_virtual_json = mapping.get("virtual_downloads_json", "[]") or "[]"
    try:
        raw_assets = json.loads(raw_virtual_json)
        if not isinstance(raw_assets, list):
            raw_assets = []
    except Exception:
        raw_assets = []
        raw_virtual_json = "[]"
    virtual_assets = [_normalize_admin_asset_row(dict(item)) for item in raw_assets if isinstance(item, dict)]
    qr_code_url = mapping.get("purchase_qr_code_url", defaults["qr_code_url"])
    return {
        "title": mapping.get("purchase_title", defaults["title"]),
        "message": mapping.get("purchase_message", defaults["message"]),
        "qr_code_url": qr_code_url,
        "contact": mapping.get("purchase_contact", defaults["contact"]),
        "update_notice": mapping.get("update_notice", ""),
        "force_update": mapping.get("force_update", "0"),
        "latest_version": mapping.get("latest_version") or settings.app_version,
        "latest_download_url": mapping.get("latest_download_url", ""),
        "allow_passwordless_register": mapping.get("allow_passwordless_register", "0"),
        "registration_requires_approval": mapping.get("registration_requires_approval", "1"),
        "virtual_downloads_json": raw_virtual_json,
        "wiring_guides_json": wiring_guides_json,
        "payment_qr_preview": _guess_cover_from_url(qr_code_url) or qr_code_url,
        "virtual_assets": virtual_assets,
    }


@router.post("/purchase-config")
def save_purchase_config(payload: PurchaseConfigIn, admin: dict = Depends(_admin_guard)) -> dict:
    _validate_resource_json(payload.virtual_downloads_json, "virtual_downloads_json")
    now = now_str()
    pairs = {
        "purchase_title": payload.title.strip(),
        "purchase_message": payload.message.strip(),
        "purchase_qr_code_url": payload.qr_code_url.strip(),
        "purchase_contact": payload.contact.strip(),
        "update_notice": payload.update_notice.strip(),
        "force_update": payload.force_update.strip() or "0",
        "latest_version": payload.latest_version.strip(),
        "latest_download_url": payload.latest_download_url.strip(),
        "allow_passwordless_register": payload.allow_passwordless_register.strip() or "0",
        "registration_requires_approval": payload.registration_requires_approval.strip() or "1",
        "virtual_downloads_json": payload.virtual_downloads_json.strip() or "[]",
    }
    with get_conn() as conn:
        for setting_key, setting_value in pairs.items():
            conn.execute(
                text(
                    """
                    INSERT INTO app_setting (setting_key, setting_value, updated_at)
                    VALUES (:setting_key, :setting_value, :updated_at)
                    ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value), updated_at = VALUES(updated_at)
                    """
                ),
                {"setting_key": setting_key, "setting_value": setting_value, "updated_at": now},
            )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_save_purchase_config', 'app_setting', 'purchase', :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "detail": f"title={pairs['purchase_title']};contact={pairs['purchase_contact']}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.get("/wiring-guides")
def list_wiring_guides(
    keyword: str = "",
    _: dict = Depends(_admin_guard),
) -> dict:
    keyword = keyword.strip()
    sql = text(
        """
        SELECT id, name, model, car_model, keywords, description, preview_image_url, file_name, object_key, file_url, content_type, file_size, sort_order, is_enabled, created_at, updated_at
        FROM app_wiring_guide
        WHERE (:keyword = '' OR name LIKE :like_keyword OR model LIKE :like_keyword OR car_model LIKE :like_keyword OR keywords LIKE :like_keyword OR description LIKE :like_keyword)
        ORDER BY sort_order ASC, id DESC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(
            sql,
            {"keyword": keyword, "like_keyword": f"%{keyword}%"},
        ).mappings().all()
    return {"items": [_normalize_wiring_guide_row(dict(row)) for row in rows]}


@router.post("/files/upload")
async def upload_admin_file(
    file: UploadFile = File(...),
    _: dict = Depends(_admin_guard),
) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")
    result = upload_bytes(content, file.filename or "admin-file.bin", file.content_type or "application/octet-stream")
    object_key = result["object_key"]
    public_url = result["url"]
    internal_url = _build_internal_file_url(object_key)
    return {
        "ok": True,
        "file_name": file.filename or "",
        "object_key": object_key,
        "file_url": internal_url,
        "public_url": public_url,
        "preview_url": _guess_cover_from_url(internal_url) or _guess_cover_from_url(public_url),
        "content_type": file.content_type or "application/octet-stream",
        "file_size": len(content),
    }


@router.post("/wiring-guides/upload")
async def upload_wiring_guide_file(
    file: UploadFile = File(...),
    admin: dict = Depends(_admin_guard),
) -> dict:
    return await upload_admin_file(file=file, _=admin)


@router.post("/wiring-guides")
def create_wiring_guide(payload: WiringGuideSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    data = _validate_wiring_guide_payload(payload)
    now = now_str()
    with get_conn() as conn:
        conn.execute(
            text(
                """
                INSERT INTO app_wiring_guide (
                    name, model, car_model, keywords, description, preview_image_url, file_name, object_key, file_url, content_type, file_size, sort_order, is_enabled, created_at, updated_at
                ) VALUES (
                    :name, :model, :car_model, :keywords, :description, :preview_image_url, :file_name, :object_key, :file_url, :content_type, :file_size, :sort_order, :is_enabled, :created_at, :updated_at
                )
                """
            ),
            {
                **data,
                "created_at": now,
                "updated_at": now,
            },
        )
        guide_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()["id"]
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_create_wiring_guide', 'app_wiring_guide', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(guide_id),
                "detail": f"name={data['name']};model={data['model']}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True, "id": guide_id}


@router.get("/learning-articles")
def list_learning_articles(_: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, title, summary, cover_image_url, content_html, sort_order, is_enabled, created_at, updated_at
                FROM app_learning_article
                ORDER BY sort_order ASC, id DESC
                """
            )
        ).mappings().all()
    return {"items": [_normalize_learning_article_row(dict(row)) for row in rows]}


@router.post("/learning-articles")
def create_learning_article(payload: LearningArticleSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="学习资料标题不能为空")
    now = now_str()
    with get_conn() as conn:
        conn.execute(
            text(
                """
                INSERT INTO app_learning_article (
                    title, summary, cover_image_url, content_html, sort_order, is_enabled, created_at, updated_at
                ) VALUES (
                    :title, :summary, :cover_image_url, :content_html, :sort_order, :is_enabled, :created_at, :updated_at
                )
                """
            ),
            {
                "title": title,
                "summary": payload.summary,
                "cover_image_url": payload.cover_image_url.strip(),
                "content_html": payload.content_html,
                "sort_order": payload.sort_order,
                "is_enabled": 1 if payload.is_enabled else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        article_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()["id"]
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_create_learning_article', 'app_learning_article', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(article_id),
                "detail": f"title={title}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True, "id": article_id}


@router.put("/learning-articles/{article_id}")
def update_learning_article(article_id: int, payload: LearningArticleSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="学习资料标题不能为空")
    now = now_str()
    with get_conn() as conn:
        existing = conn.execute(
            text("SELECT id FROM app_learning_article WHERE id = :id LIMIT 1"),
            {"id": article_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="学习资料不存在")
        conn.execute(
            text(
                """
                UPDATE app_learning_article
                SET title = :title,
                    summary = :summary,
                    cover_image_url = :cover_image_url,
                    content_html = :content_html,
                    sort_order = :sort_order,
                    is_enabled = :is_enabled,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": article_id,
                "title": title,
                "summary": payload.summary,
                "cover_image_url": payload.cover_image_url.strip(),
                "content_html": payload.content_html,
                "sort_order": payload.sort_order,
                "is_enabled": 1 if payload.is_enabled else 0,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_update_learning_article', 'app_learning_article', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(article_id),
                "detail": f"title={title}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.delete("/learning-articles/{article_id}")
def delete_learning_article(article_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        existing = conn.execute(
            text("SELECT id, title FROM app_learning_article WHERE id = :id LIMIT 1"),
            {"id": article_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="学习资料不存在")
        conn.execute(text("DELETE FROM app_learning_article WHERE id = :id"), {"id": article_id})
        now = now_str()
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_delete_learning_article', 'app_learning_article', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(article_id),
                "detail": f"title={existing['title']}",
                "created_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.put("/wiring-guides/{guide_id}")
def update_wiring_guide(guide_id: int, payload: WiringGuideSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    data = _validate_wiring_guide_payload(payload)
    now = now_str()
    with get_conn() as conn:
        existing = conn.execute(
            text("SELECT id, object_key FROM app_wiring_guide WHERE id = :id LIMIT 1"),
            {"id": guide_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="接线图不存在")
        old_object_key = (existing.get("object_key") or "").strip()
        new_object_key = data["object_key"]
        conn.execute(
            text(
                """
                UPDATE app_wiring_guide
                SET name = :name,
                    model = :model,
                    car_model = :car_model,
                    keywords = :keywords,
                    description = :description,
                    preview_image_url = :preview_image_url,
                    file_name = :file_name,
                    object_key = :object_key,
                    file_url = :file_url,
                    content_type = :content_type,
                    file_size = :file_size,
                    sort_order = :sort_order,
                    is_enabled = :is_enabled,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": guide_id,
                **data,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_update_wiring_guide', 'app_wiring_guide', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(guide_id),
                "detail": f"name={data['name']};model={data['model']}",
                "created_at": now,
            },
        )
        conn.commit()
    if old_object_key and old_object_key != new_object_key:
        remove_object(old_object_key)
    return {"ok": True}


@router.delete("/wiring-guides/{guide_id}")
def delete_wiring_guide(guide_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        existing = conn.execute(
            text("SELECT id, name, object_key FROM app_wiring_guide WHERE id = :id LIMIT 1"),
            {"id": guide_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="接线图不存在")
        conn.execute(text("DELETE FROM app_wiring_guide WHERE id = :id"), {"id": guide_id})
        now = now_str()
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'admin_delete_wiring_guide', 'app_wiring_guide', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": admin["id"],
                "actor_name": admin["name"],
                "target_id": str(guide_id),
                "detail": f"name={existing['name']}",
                "created_at": now,
            },
        )
        conn.commit()
    remove_object((existing.get("object_key") or "").strip())
    return {"ok": True}


@router.get("/ecu-rules")
def list_ecu_rules(_: dict = Depends(_admin_guard)) -> dict:
    sql = text(
        """
        SELECT
            m.id,
            cs.name AS car_series_name,
            m.name,
            COUNT(DISTINCT r.id) AS identify_rule_count,
            COUNT(DISTINCT f.id) AS function_count
        FROM ecu_model m
        LEFT JOIN ecu_car_series cs ON cs.id = m.car_series_id
        LEFT JOIN ecu_identify_rule r ON r.ecu_model_id = m.id
        LEFT JOIN ecu_function f ON f.ecu_model_id = m.id AND f.is_enabled = 1
        WHERE m.is_enabled = 1
        GROUP BY m.id, cs.name, m.name
        ORDER BY m.id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/ecu-rules/{ecu_model_id}")
def get_ecu_rule_detail(ecu_model_id: int, _: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        model = conn.execute(
            text(
                """
                SELECT m.id, m.name, cs.name AS car_series_name
                FROM ecu_model m
                LEFT JOIN ecu_car_series cs ON cs.id = m.car_series_id
                WHERE m.id = :id
                LIMIT 1
                """
            ),
            {"id": ecu_model_id},
        ).mappings().first()
        if not model:
            raise HTTPException(status_code=404, detail="ECU型号不存在")

        identify_rules = conn.execute(
            text(
                """
                SELECT id, ecu_model_id, addr, data_length, hex_value, created_at, updated_at
                FROM ecu_identify_rule
                WHERE ecu_model_id = :ecu_model_id
                ORDER BY id ASC
                """
            ),
            {"ecu_model_id": ecu_model_id},
        ).mappings().all()

        functions = conn.execute(
            text(
                """
                SELECT id, ecu_model_id, name, success_msg, sort_order, is_enabled, created_at, updated_at
                FROM ecu_function
                WHERE ecu_model_id = :ecu_model_id
                ORDER BY sort_order ASC, id ASC
                """
            ),
            {"ecu_model_id": ecu_model_id},
        ).mappings().all()

        function_ids = [int(row["id"]) for row in functions]
        variants = []
        patches = []
        if function_ids:
            variants = conn.execute(
                text(
                    """
                    SELECT id, function_id, identify_hex, created_at, updated_at
                    FROM ecu_function_variant
                    WHERE function_id IN :function_ids
                    ORDER BY id ASC
                    """
                ).bindparams(bindparam("function_ids", expanding=True)),
                {"function_ids": function_ids},
            ).mappings().all()
            variant_ids = [int(row["id"]) for row in variants]
            if variant_ids:
                patches = conn.execute(
                    text(
                        """
                        SELECT id, variant_id, seq_no, addr, data_length, value_hex, created_at, updated_at
                        FROM ecu_function_patch
                        WHERE variant_id IN :variant_ids
                        ORDER BY seq_no ASC, id ASC
                        """
                    ).bindparams(bindparam("variant_ids", expanding=True)),
                    {"variant_ids": variant_ids},
                ).mappings().all()

    patch_map = {}
    for row in patches:
        patch_map.setdefault(int(row["variant_id"]), []).append(dict(row))

    variant_map = {}
    for row in variants:
        item = dict(row)
        item["patches"] = patch_map.get(int(row["id"]), [])
        variant_map.setdefault(int(row["function_id"]), []).append(item)

    function_items = []
    for row in functions:
        item = dict(row)
        item["variants"] = variant_map.get(int(row["id"]), [])
        function_items.append(item)

    return {
        "model": dict(model),
        "identify_rules": [dict(row) for row in identify_rules],
        "functions": function_items,
    }


@router.post("/ecu-rules/identify-rule")
def create_identify_rule(payload: AdminIdentifyRuleSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    hex_value = payload.hex_value.strip().upper()
    if not hex_value:
        raise HTTPException(status_code=400, detail="识别十六进制不能为空")
    now = now_str()
    with get_conn() as conn:
        exists = conn.execute(
            text(
                """
                SELECT id FROM ecu_identify_rule
                WHERE ecu_model_id = :ecu_model_id AND addr = :addr AND data_length = :data_length AND hex_value = :hex_value
                LIMIT 1
                """
            ),
            {
                "ecu_model_id": payload.ecu_model_id,
                "addr": payload.addr,
                "data_length": payload.data_length,
                "hex_value": hex_value,
            },
        ).mappings().first()
        if exists:
            raise HTTPException(status_code=409, detail="识别规则已存在")
        conn.execute(
            text(
                """
                INSERT INTO ecu_identify_rule (ecu_model_id, addr, data_length, hex_value, created_at, updated_at)
                VALUES (:ecu_model_id, :addr, :data_length, :hex_value, :created_at, :updated_at)
                """
            ),
            {
                "ecu_model_id": payload.ecu_model_id,
                "addr": payload.addr,
                "data_length": payload.data_length,
                "hex_value": hex_value,
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.post("/ecu-rules/function")
def create_ecu_function(payload: AdminFunctionSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="功能名称不能为空")
    now = now_str()
    with get_conn() as conn:
        exists = conn.execute(
            text("SELECT id FROM ecu_function WHERE ecu_model_id = :ecu_model_id AND name = :name LIMIT 1"),
            {"ecu_model_id": payload.ecu_model_id, "name": name},
        ).mappings().first()
        if exists:
            raise HTTPException(status_code=409, detail="功能已存在")
        conn.execute(
            text(
                """
                INSERT INTO ecu_function (ecu_model_id, name, success_msg, sort_order, is_enabled, created_at, updated_at)
                VALUES (:ecu_model_id, :name, :success_msg, :sort_order, :is_enabled, :created_at, :updated_at)
                """
            ),
            {
                "ecu_model_id": payload.ecu_model_id,
                "name": name,
                "success_msg": payload.success_msg.strip(),
                "sort_order": payload.sort_order,
                "is_enabled": 1 if payload.is_enabled else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.post("/ecu-rules/variant")
def create_function_variant(payload: AdminFunctionVariantSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    identify_hex = payload.identify_hex.strip().upper()
    if not identify_hex:
        raise HTTPException(status_code=400, detail="识别十六进制不能为空")
    now = now_str()
    with get_conn() as conn:
        exists = conn.execute(
            text("SELECT id FROM ecu_function_variant WHERE function_id = :function_id AND identify_hex = :identify_hex LIMIT 1"),
            {"function_id": payload.function_id, "identify_hex": identify_hex},
        ).mappings().first()
        if exists:
            raise HTTPException(status_code=409, detail="功能变体已存在")
        conn.execute(
            text(
                """
                INSERT INTO ecu_function_variant (function_id, identify_hex, created_at, updated_at)
                VALUES (:function_id, :identify_hex, :created_at, :updated_at)
                """
            ),
            {
                "function_id": payload.function_id,
                "identify_hex": identify_hex,
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.post("/ecu-rules/patch")
def create_function_patch(payload: AdminFunctionPatchSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    value_hex = payload.value_hex.strip().upper()
    if not value_hex:
        raise HTTPException(status_code=400, detail="补丁值不能为空")
    now = now_str()
    with get_conn() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ecu_function_patch (variant_id, seq_no, addr, data_length, value_hex, created_at, updated_at)
                VALUES (:variant_id, :seq_no, :addr, :data_length, :value_hex, :created_at, :updated_at)
                """
            ),
            {
                "variant_id": payload.variant_id,
                "seq_no": payload.seq_no,
                "addr": payload.addr,
                "data_length": payload.data_length,
                "value_hex": value_hex,
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.put("/ecu-rules/identify-rule/{rule_id}")
def update_identify_rule(rule_id: int, payload: AdminIdentifyRuleSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    hex_value = payload.hex_value.strip().upper()
    if not hex_value:
        raise HTTPException(status_code=400, detail="识别十六进制不能为空")
    now = now_str()
    with get_conn() as conn:
        exists = conn.execute(text("SELECT id FROM ecu_identify_rule WHERE id = :id LIMIT 1"), {"id": rule_id}).mappings().first()
        if not exists:
            raise HTTPException(status_code=404, detail="识别规则不存在")
        conn.execute(
            text(
                """
                UPDATE ecu_identify_rule
                SET addr = :addr,
                    data_length = :data_length,
                    hex_value = :hex_value,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": rule_id,
                "addr": payload.addr,
                "data_length": payload.data_length,
                "hex_value": hex_value,
                "updated_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.delete("/ecu-rules/identify-rule/{rule_id}")
def delete_identify_rule(rule_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        exists = conn.execute(text("SELECT id FROM ecu_identify_rule WHERE id = :id LIMIT 1"), {"id": rule_id}).mappings().first()
        if not exists:
            raise HTTPException(status_code=404, detail="识别规则不存在")
        conn.execute(text("DELETE FROM ecu_identify_rule WHERE id = :id"), {"id": rule_id})
        conn.commit()
    return {"ok": True}


@router.put("/ecu-rules/function/{function_id}")
def update_ecu_function(function_id: int, payload: AdminFunctionSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="功能名称不能为空")
    now = now_str()
    with get_conn() as conn:
        exists = conn.execute(text("SELECT id FROM ecu_function WHERE id = :id LIMIT 1"), {"id": function_id}).mappings().first()
        if not exists:
            raise HTTPException(status_code=404, detail="功能不存在")
        conn.execute(
            text(
                """
                UPDATE ecu_function
                SET name = :name,
                    success_msg = :success_msg,
                    sort_order = :sort_order,
                    is_enabled = :is_enabled,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": function_id,
                "name": name,
                "success_msg": payload.success_msg.strip(),
                "sort_order": payload.sort_order,
                "is_enabled": 1 if payload.is_enabled else 0,
                "updated_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.put("/ecu-rules/patch/{patch_id}")
def update_function_patch(patch_id: int, payload: AdminFunctionPatchSaveIn, admin: dict = Depends(_admin_guard)) -> dict:
    value_hex = payload.value_hex.strip().upper()
    if not value_hex:
        raise HTTPException(status_code=400, detail="补丁值不能为空")
    now = now_str()
    with get_conn() as conn:
        exists = conn.execute(text("SELECT id FROM ecu_function_patch WHERE id = :id LIMIT 1"), {"id": patch_id}).mappings().first()
        if not exists:
            raise HTTPException(status_code=404, detail="补丁不存在")
        conn.execute(
            text(
                """
                UPDATE ecu_function_patch
                SET seq_no = :seq_no,
                    addr = :addr,
                    data_length = :data_length,
                    value_hex = :value_hex,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": patch_id,
                "seq_no": payload.seq_no,
                "addr": payload.addr,
                "data_length": payload.data_length,
                "value_hex": value_hex,
                "updated_at": now,
            },
        )
        conn.commit()
    return {"ok": True}


@router.delete("/ecu-rules/variant/{variant_id}")
def delete_function_variant(variant_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        exists = conn.execute(text("SELECT id FROM ecu_function_variant WHERE id = :id LIMIT 1"), {"id": variant_id}).mappings().first()
        if not exists:
            raise HTTPException(status_code=404, detail="功能变体不存在")
        conn.execute(text("DELETE FROM ecu_function_patch WHERE variant_id = :variant_id"), {"variant_id": variant_id})
        conn.execute(text("DELETE FROM ecu_function_variant WHERE id = :id"), {"id": variant_id})
        conn.commit()
    return {"ok": True}


@router.delete("/ecu-rules/patch/{patch_id}")
def delete_function_patch(patch_id: int, admin: dict = Depends(_admin_guard)) -> dict:
    with get_conn() as conn:
        exists = conn.execute(text("SELECT id FROM ecu_function_patch WHERE id = :id LIMIT 1"), {"id": patch_id}).mappings().first()
        if not exists:
            raise HTTPException(status_code=404, detail="补丁不存在")
        conn.execute(text("DELETE FROM ecu_function_patch WHERE id = :id"), {"id": patch_id})
        conn.commit()
    return {"ok": True}


@router.get("/logs")
def logs(_: dict = Depends(_admin_guard)) -> dict:
    sql = text(
        """
        SELECT id, actor_name, action, target_type, target_id, detail, created_at
        FROM app_operation_log
        ORDER BY id DESC
        LIMIT 200
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql).mappings().all()
    return {"items": [dict(row) for row in rows]}
