from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_conn
from app.security import future_str, generate_token, get_current_user, hash_password, now_str, verify_password
from app.settings import settings


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _load_auth_flags(conn) -> tuple[bool, bool]:
    rows = conn.execute(
        text("SELECT setting_key, setting_value FROM app_setting WHERE setting_key IN ('allow_passwordless_register', 'registration_requires_approval')")
    ).mappings().all()
    mapping = {row['setting_key']: row['setting_value'] or '' for row in rows}
    allow_passwordless = str(mapping.get('allow_passwordless_register', '1' if settings.allow_passwordless_register else '0')).strip() == '1'
    requires_approval = str(mapping.get('registration_requires_approval', '1' if settings.registration_requires_approval else '0')).strip() == '1'
    return allow_passwordless, requires_approval


class RegisterIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    password: str = Field(default="", max_length=64)
    name: str = Field(min_length=1, max_length=64)
    device_id: str = Field(min_length=8, max_length=128)
    device_name: str = Field(min_length=1, max_length=128)


class LoginIn(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    password: str = Field(default="", max_length=64)
    device_id: str = Field(min_length=8, max_length=128)
    device_name: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    phone: str
    name: str
    status: str
    is_admin: bool
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    device_bound_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None


class AuthOut(BaseModel):
    token: str
    expired_at: str
    user: UserOut


@router.post("/register", response_model=AuthOut)
def register(payload: RegisterIn) -> AuthOut:
    now = now_str()
    password = payload.password.strip()
    with get_conn() as conn:
        allow_passwordless_register, registration_requires_approval = _load_auth_flags(conn)
        if not allow_passwordless_register and not password:
            raise HTTPException(status_code=400, detail="password required")
        register_status = "pending" if registration_requires_approval else "enabled"
        password_hash = hash_password(password or f"AUTO:{payload.phone.strip()}")
        exists = conn.execute(
            text("SELECT id FROM app_user WHERE phone = :phone LIMIT 1"),
            {"phone": payload.phone.strip()},
        ).mappings().first()
        if exists:
            raise HTTPException(status_code=409, detail="phone already exists")

        conn.execute(
            text(
                """
                INSERT INTO app_user (
                    phone, name, password_hash, status, approval_note, is_admin,
                    device_id, device_name, device_bound_at,
                    created_at, updated_at
                )
                VALUES (
                    :phone, :name, :password_hash, :status, :approval_note, 0,
                    :device_id, :device_name, :device_bound_at,
                    :created_at, :updated_at
                )
                """
            ),
            {
                "phone": payload.phone.strip(),
                "name": payload.name.strip(),
                "password_hash": password_hash,
                "status": register_status,
                "approval_note": "待后台审批" if register_status == "pending" else None,
                "device_id": payload.device_id.strip(),
                "device_name": payload.device_name.strip(),
                "device_bound_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
        user_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()["id"]

        token = ""
        expired_at = future_str()
        if register_status == "enabled":
            token = generate_token()
            conn.execute(
                text(
                    """
                    INSERT INTO app_session (user_id, token, expired_at, created_at, last_seen_at)
                    VALUES (:user_id, :token, :expired_at, :created_at, :last_seen_at)
                    """
                ),
                {
                    "user_id": user_id,
                    "token": token,
                    "expired_at": expired_at,
                    "created_at": now,
                    "last_seen_at": now,
                },
            )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'register', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": user_id,
                "actor_name": payload.name.strip(),
                "target_id": str(user_id),
                "detail": f"phone={payload.phone.strip()};status={register_status};device_id={payload.device_id.strip()};device_name={payload.device_name.strip()}",
                "created_at": now,
            },
        )
        conn.commit()

    if register_status != "enabled":
        raise HTTPException(status_code=403, detail="registered_pending_approval")

    return AuthOut(
        token=token,
        expired_at=expired_at,
        user=UserOut(
            id=user_id,
            phone=payload.phone.strip(),
            name=payload.name.strip(),
            status="enabled",
            is_admin=False,
            device_id=payload.device_id.strip(),
            device_name=payload.device_name.strip(),
            device_bound_at=now,
            created_at=now,
            updated_at=now,
            last_login_at=None,
        ),
    )


@router.post("/login", response_model=AuthOut)
def login(payload: LoginIn) -> AuthOut:
    phone = payload.phone.strip()
    with get_conn() as conn:
        allow_passwordless_register, _ = _load_auth_flags(conn)
        user = conn.execute(
            text(
                """
                SELECT id, phone, name, password_hash, status, is_admin,
                       device_id, device_name, device_bound_at,
                       created_at, updated_at, last_login_at
                FROM app_user
                WHERE phone = :phone
                LIMIT 1
                """
            ),
            {"phone": phone},
        ).mappings().first()
        if not user:
            raise HTTPException(status_code=401, detail="invalid phone or password")
        if user["status"] == "pending":
            raise HTTPException(status_code=403, detail="user pending approval")
        if user["status"] != "enabled":
            raise HTTPException(status_code=403, detail="user disabled")

        bound_device_id = (user.get("device_id") or "").strip()
        if bound_device_id and bound_device_id != payload.device_id.strip():
            raise HTTPException(status_code=403, detail="device mismatch")

        password = payload.password.strip()
        password_ok = verify_password(password, user["password_hash"]) if password else False
        passwordless_seed_ok = bool(allow_passwordless_register and not password and bound_device_id and user["password_hash"] == hash_password(f"AUTO:{phone}"))
        if not password_ok and not passwordless_seed_ok:
            raise HTTPException(status_code=401, detail="invalid phone or password")

        now = now_str()
        expired_at = future_str()
        token = generate_token()
        conn.execute(text("DELETE FROM app_session WHERE user_id = :user_id"), {"user_id": user["id"]})
        conn.execute(
            text(
                """
                INSERT INTO app_session (user_id, token, expired_at, created_at, last_seen_at)
                VALUES (:user_id, :token, :expired_at, :created_at, :last_seen_at)
                """
            ),
            {
                "user_id": user["id"],
                "token": token,
                "expired_at": expired_at,
                "created_at": now,
                "last_seen_at": now,
            },
        )
        conn.execute(
            text(
                """
                UPDATE app_user
                SET last_login_at = :last_login_at,
                    device_id = :device_id,
                    device_name = :device_name,
                    device_bound_at = COALESCE(device_bound_at, :device_bound_at),
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "last_login_at": now,
                "device_id": payload.device_id.strip(),
                "device_name": payload.device_name.strip(),
                "device_bound_at": now,
                "updated_at": now,
                "id": user["id"],
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'login', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": user["id"],
                "actor_name": user["name"],
                "target_id": str(user["id"]),
                "detail": f"phone={user['phone']};device_id={payload.device_id.strip()};device_name={payload.device_name.strip()}",
                "created_at": now,
            },
        )
        conn.commit()

    return AuthOut(
        token=token,
        expired_at=expired_at,
        user=UserOut(
            id=user["id"],
            phone=user["phone"],
            name=user["name"],
            status=user["status"],
            is_admin=bool(user["is_admin"]),
            device_id=payload.device_id.strip(),
            device_name=payload.device_name.strip(),
            device_bound_at=str(user["device_bound_at"]) if user.get("device_bound_at") else now,
            created_at=str(user["created_at"]) if user["created_at"] else None,
            updated_at=now,
            last_login_at=now,
        ),
    )


@router.post("/logout")
def logout(user: dict = Depends(get_current_user)) -> dict:
    with get_conn() as conn:
        conn.execute(text("DELETE FROM app_session WHERE token = :token"), {"token": user["token"]})
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'logout', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": user["id"],
                "actor_name": user["name"],
                "target_id": str(user["id"]),
                "detail": f"phone={user['phone']}",
                "created_at": now_str(),
            },
        )
        conn.commit()
    return {"ok": True}


@router.post("/unbind-device")
def unbind_device(user: dict = Depends(get_current_user)) -> dict:
    """解除当前账号的设备绑定。"""
    with get_conn() as conn:
        old_device_id = user.get("device_id") or ""
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
            {"updated_at": now_str(), "id": user["id"]},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_operation_log (user_id, actor_name, action, target_type, target_id, detail, created_at)
                VALUES (:user_id, :actor_name, 'unbind_device', 'app_user', :target_id, :detail, :created_at)
                """
            ),
            {
                "user_id": user["id"],
                "actor_name": user["name"],
                "target_id": str(user["id"]),
                "detail": f"phone={user['phone']};unbound_device={old_device_id}",
                "created_at": now_str(),
            },
        )
        conn.commit()
    return {"ok": True, "unbound_device": old_device_id}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)) -> UserOut:
    return UserOut(
        id=user["id"],
        phone=user["phone"],
        name=user["name"],
        status=user["status"],
        is_admin=bool(user["is_admin"]),
        device_id=user.get("device_id"),
        device_name=user.get("device_name"),
        device_bound_at=str(user["device_bound_at"]) if user.get("device_bound_at") else None,
        created_at=str(user["created_at"]) if user["created_at"] else None,
        updated_at=str(user["updated_at"]) if user["updated_at"] else None,
        last_login_at=str(user["last_login_at"]) if user["last_login_at"] else None,
    )


@router.get("/my-permissions")
def my_permissions(user: dict = Depends(get_current_user)) -> dict:
    sql = text(
        """
        SELECT p.function_id, f.name AS function_name, p.end_at, p.status
        FROM app_user_function_permission p
        LEFT JOIN ecu_function f ON f.id = p.function_id
        WHERE p.user_id = :user_id
          AND p.status = 'enabled'
          AND (p.end_at IS NULL OR p.end_at > NOW())
        ORDER BY p.function_id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql, {"user_id": user["id"]}).mappings().all()
    items = [
        {
            "function_id": row["function_id"],
            "function_name": row.get("function_name"),
            "end_at": str(row["end_at"]) if row["end_at"] else None,
            "status": row["status"],
        }
        for row in rows
    ]
    function_names = []
    seen = set()
    for item in items:
        name = str(item.get("function_name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            function_names.append(name)
    return {
        "user_id": user["id"],
        "is_admin": bool(user["is_admin"]),
        "items": items,
        "function_ids": [item["function_id"] for item in items],
        "function_names": function_names,
    }
