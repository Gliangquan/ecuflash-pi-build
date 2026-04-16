import json
from datetime import datetime
from typing import Dict, List, Set, Optional
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import text

from app.db import get_conn
from app.schemas import (
    AppWiringGuideOut,
    CarSeriesOut,
    CpuChecksumOut,
    EcuModelOut,
    FunctionOut,
    FunctionPatchesOut,
    IdentifyRuleOut,
    LearningArticleOut,
    PatchOut,
)
from app.settings import settings
from app.security import get_current_user

router = APIRouter(prefix="/api/v1", tags=["ecu"])


def _is_user_authorized(user: dict) -> bool:
    if user.get("is_admin"):
        return True
    auth_end_at = user.get("auth_end_at")
    return bool(auth_end_at and str(auth_end_at) > datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def _get_user_allowed_function_ids(user_id: int) -> set[int]:
    sql = text(
        """
        SELECT function_id
        FROM app_user_function_permission
        WHERE user_id = :user_id
          AND status = 'enabled'
          AND (end_at IS NULL OR end_at > NOW())
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql, {"user_id": user_id}).mappings().all()
    return {int(row["function_id"]) for row in rows}


def _get_user_allowed_function_names(user_id: int) -> set[str]:
    sql = text(
        """
        SELECT DISTINCT f.name
        FROM app_user_function_permission p
        LEFT JOIN ecu_function f ON f.id = p.function_id
        WHERE p.user_id = :user_id
          AND p.status = 'enabled'
          AND (p.end_at IS NULL OR p.end_at > NOW())
          AND f.name IS NOT NULL
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql, {"user_id": user_id}).mappings().all()
    return {str(row["name"]).strip() for row in rows if row.get("name")}


def _ensure_function_allowed(user: dict, function_id: int) -> None:
    if user.get("is_admin"):
        return
    sql = text("SELECT name FROM ecu_function WHERE id = :id LIMIT 1")
    with get_conn() as conn:
        row = conn.execute(sql, {"id": function_id}).mappings().first()
    if not row or not row.get("name"):
        raise HTTPException(status_code=403, detail="function not allowed")
    allowed_names = _get_user_allowed_function_names(int(user["id"]))
    if str(row["name"]).strip() not in allowed_names:
        raise HTTPException(status_code=403, detail="function not allowed")


@router.get("/car-series", response_model=list[CarSeriesOut])
def list_car_series() -> list[CarSeriesOut]:
    sql = text(
        """
        SELECT id, name
        FROM ecu_car_series
        WHERE is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql).mappings().all()
    return [CarSeriesOut(**row) for row in rows]


@router.get("/car-series/{car_series_id}/ecu-models", response_model=list[EcuModelOut])
def list_ecu_models(car_series_id: int) -> list[EcuModelOut]:
    sql = text(
        """
        SELECT id, car_series_id, name
        FROM ecu_model
        WHERE car_series_id = :car_series_id
          AND is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql, {"car_series_id": car_series_id}).mappings().all()
    return [EcuModelOut(**row) for row in rows]


@router.get("/search/ecu-models", response_model=list[EcuModelOut])
def search_ecu_models(keyword: str = Query(..., min_length=1, max_length=64)) -> list[EcuModelOut]:
    sql = text(
        """
        SELECT id, car_series_id, name
        FROM ecu_model
        WHERE is_enabled = 1
          AND name LIKE :keyword
        ORDER BY id ASC
        LIMIT 100
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql, {"keyword": f"%{keyword}%"}).mappings().all()
    return [EcuModelOut(**row) for row in rows]


@router.get("/ecu-models/{ecu_model_id}/identify-rules", response_model=list[IdentifyRuleOut])
def list_identify_rules(ecu_model_id: int) -> list[IdentifyRuleOut]:
    sql = text(
        """
        SELECT id, ecu_model_id, addr, data_length, hex_value
        FROM ecu_identify_rule
        WHERE ecu_model_id = :ecu_model_id
        ORDER BY id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql, {"ecu_model_id": ecu_model_id}).mappings().all()
    return [IdentifyRuleOut(**row) for row in rows]


@router.get("/ecu-models/{ecu_model_id}/functions", response_model=list[FunctionOut])
def list_functions(ecu_model_id: int, user: dict = Depends(get_current_user)) -> list[FunctionOut]:
    sql = text(
        """
        SELECT id, ecu_model_id, name, success_msg
        FROM ecu_function
        WHERE ecu_model_id = :ecu_model_id
          AND is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql, {"ecu_model_id": ecu_model_id}).mappings().all()
    if user.get("is_admin") or _is_user_authorized(user):
        return [FunctionOut(**row) for row in rows]
    return [FunctionOut(**row) for row in rows if str(row["name"]).strip() in {"接线图查询", "资料下载", "文件下载", "学习资料"}]


@router.get("/functions/{function_id}/patches", response_model=FunctionPatchesOut)
def get_function_patches(
    function_id: int,
    identify_hex: str = Query(..., min_length=1, max_length=64),
    user: dict = Depends(get_current_user),
) -> FunctionPatchesOut:
    identify_hex = identify_hex.strip().upper()
    _ensure_function_allowed(user, function_id)

    head_sql = text(
        """
        SELECT f.id AS function_id, f.name AS function_name, f.success_msg
        FROM ecu_function f
        WHERE f.id = :function_id
        """
    )

    variant_sql = text(
        """
        SELECT id
        FROM ecu_function_variant
        WHERE function_id = :function_id
          AND identify_hex = :identify_hex
        """
    )

    patch_sql = text(
        """
        SELECT id, seq_no, addr, data_length, value_hex
        FROM ecu_function_patch
        WHERE variant_id = :variant_id
        ORDER BY seq_no ASC, id ASC
        """
    )

    with get_conn() as conn:
        head = conn.execute(head_sql, {"function_id": function_id}).mappings().first()
        if not head:
            raise HTTPException(status_code=404, detail="function not found")

        variant = conn.execute(
            variant_sql,
            {"function_id": function_id, "identify_hex": identify_hex},
        ).mappings().first()

        if not variant:
            raise HTTPException(status_code=404, detail="identify_hex variant not found")

        patch_rows = conn.execute(patch_sql, {"variant_id": variant["id"]}).mappings().all()

    return FunctionPatchesOut(
        function_id=head["function_id"],
        function_name=head["function_name"],
        identify_hex=identify_hex,
        success_msg=head["success_msg"],
        patches=[PatchOut(**row) for row in patch_rows],
    )


@router.get("/cpu-checksums", response_model=list[CpuChecksumOut])
def list_cpu_checksums() -> list[CpuChecksumOut]:
    sql = text(
        """
        SELECT id, cpu_key, cpu_display_name, checksum_addr
        FROM ecu_cpu_checksum
        WHERE is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql).mappings().all()
    return [CpuChecksumOut(**row) for row in rows]

def _load_app_settings_map() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute(text("SELECT setting_key, setting_value FROM app_setting")).mappings().all()
    return {row["setting_key"]: row["setting_value"] or "" for row in rows}


def _normalize_virtual_assets_for_client(raw_text: str, keyword: str = "") -> list[dict]:
    try:
        raw_items = json.loads(raw_text or "[]")
    except Exception:
        raw_items = []
    if not isinstance(raw_items, list):
        raw_items = []
    query = keyword.strip().upper()
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        object_key = (raw.get("object_key") or "").strip()
        url = f"/api/v1/files/{quote(object_key, safe='')}" if object_key else (raw.get("file_url") or raw.get("url") or "")
        item = {
            "id": raw.get("id") or raw.get("title") or raw.get("name") or url,
            "name": raw.get("title") or raw.get("name") or "",
            "title": raw.get("title") or raw.get("name") or "",
            "description": raw.get("summary") or raw.get("description") or "",
            "remark": raw.get("summary") or raw.get("description") or "",
            "image_url": raw.get("image_url") or "",
            "button_text": raw.get("download_text") or raw.get("button_text") or "立即下载",
            "file_name": raw.get("file_name") or "",
            "keywords": raw.get("keywords") or "",
            "url": url,
            "file_url": url,
        }
        if query:
            text_value = " ".join(str(v or "") for v in item.values()).upper()
            if query not in text_value:
                continue
        items.append(item)
    return items


def _list_all_enabled_function_names() -> list[str]:
    sql = text(
        """
        SELECT name, MIN(sort_order) AS sort_order, MIN(id) AS first_id
        FROM ecu_function
        WHERE is_enabled = 1
          AND name IS NOT NULL
          AND name <> ''
        GROUP BY name
        ORDER BY sort_order ASC, first_id ASC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(sql).mappings().all()
    names = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _match_bin_payload(bin_data: bytes) -> Optional[dict]:
    models_sql = text(
        """
        SELECT m.id AS ecu_model_id, m.name AS ecu_name, cs.name AS car_series
        FROM ecu_model m
        JOIN ecu_car_series cs ON cs.id = m.car_series_id
        WHERE m.is_enabled = 1
        ORDER BY m.sort_order ASC, m.id ASC
        """
    )
    identify_sql = text(
        """
        SELECT id, ecu_model_id, addr, data_length, hex_value
        FROM ecu_identify_rule
        ORDER BY id ASC
        """
    )
    functions_sql = text(
        """
        SELECT id, ecu_model_id, name, success_msg
        FROM ecu_function
        WHERE is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )
    variants_sql = text(
        """
        SELECT id, function_id, identify_hex
        FROM ecu_function_variant
        ORDER BY id ASC
        """
    )
    patches_sql = text(
        """
        SELECT variant_id, seq_no, addr, data_length, value_hex
        FROM ecu_function_patch
        ORDER BY seq_no ASC, id ASC
        """
    )

    with get_conn() as conn:
        models = conn.execute(models_sql).mappings().all()
        identify_rows = conn.execute(identify_sql).mappings().all()
        function_rows = conn.execute(functions_sql).mappings().all()
        variant_rows = conn.execute(variants_sql).mappings().all()
        patch_rows = conn.execute(patches_sql).mappings().all()

    model_map = {int(row["ecu_model_id"]): row for row in models}
    variants_by_function: dict[int, list[dict]] = {}
    for row in variant_rows:
        variants_by_function.setdefault(int(row["function_id"]), []).append(dict(row))

    patches_by_variant: dict[int, list[dict]] = {}
    for row in patch_rows:
        patches_by_variant.setdefault(int(row["variant_id"]), []).append(
            {
                "地址": hex(int(row["addr"])),
                "长度": str(int(row["data_length"])),
                "值": str(row["value_hex"] or "").upper(),
            }
        )

    functions_by_model: dict[int, list[dict]] = {}
    for row in function_rows:
        functions_by_model.setdefault(int(row["ecu_model_id"]), []).append(dict(row))

    for rule in identify_rows:
        addr = int(rule["addr"])
        length = int(rule["data_length"])
        if addr < 0 or length <= 0 or addr + length > len(bin_data):
            continue
        identify_hex = bin_data[addr:addr + length].hex().upper()
        expected_hex = str(rule["hex_value"] or "").upper()
        if identify_hex != expected_hex:
            continue

        model = model_map.get(int(rule["ecu_model_id"]))
        if not model:
            continue

        function_list = []
        for func in functions_by_model.get(int(rule["ecu_model_id"]), []):
            matched_variant = None
            for variant in variants_by_function.get(int(func["id"]), []):
                if str(variant["identify_hex"] or "").upper() == identify_hex:
                    matched_variant = variant
                    break
            if not matched_variant:
                continue
            function_list.append(
                {
                    "function_id": int(func["id"]),
                    "功能名称": str(func["name"] or ""),
                    "成功提示": str(func.get("success_msg") or ""),
                    "需要修改的地址": patches_by_variant.get(int(matched_variant["id"]), []),
                }
            )

        return {
            "车系": str(model["car_series"] or ""),
            "品牌": "",
            "ECU名称": str(model["ecu_name"] or ""),
            "ecu_model_id": int(model["ecu_model_id"]),
            "identify_hex": identify_hex,
            "识别码": {
                "识别地址1": hex(addr),
                "识别长度1": str(length),
                "识别十六进制": identify_hex,
            },
            "功能列表": function_list,
        }
    return None


@router.post("/bin/identify")
def identify_bin(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty bin file")
    matched = _match_bin_payload(content)
    if not matched:
        raise HTTPException(status_code=404, detail="ecu not supported")
    if user.get("is_admin") or _is_user_authorized(user):
        return matched
    matched["功能列表"] = []
    return matched


def _build_runtime_dataset_payload(user: dict) -> dict:
    cars_sql = text(
        """
        SELECT id, name
        FROM ecu_car_series
        WHERE is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )
    models_sql = text(
        """
        SELECT id, car_series_id, name
        FROM ecu_model
        WHERE is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )
    identify_sql = text(
        """
        SELECT ecu_model_id, addr, data_length, hex_value
        FROM ecu_identify_rule
        ORDER BY id ASC
        """
    )
    functions_sql = text(
        """
        SELECT id, ecu_model_id, name, success_msg
        FROM ecu_function
        WHERE is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )
    variants_sql = text(
        """
        SELECT id, function_id, identify_hex
        FROM ecu_function_variant
        ORDER BY id ASC
        """
    )
    patches_sql = text(
        """
        SELECT variant_id, seq_no, addr, data_length, value_hex
        FROM ecu_function_patch
        ORDER BY seq_no ASC, id ASC
        """
    )
    cpu_sql = text(
        """
        SELECT cpu_key, cpu_display_name, checksum_addr
        FROM ecu_cpu_checksum
        WHERE is_enabled = 1
        ORDER BY sort_order ASC, id ASC
        """
    )

    with get_conn() as conn:
        cars = conn.execute(cars_sql).mappings().all()
        models = conn.execute(models_sql).mappings().all()
        identifies = conn.execute(identify_sql).mappings().all()
        functions = conn.execute(functions_sql).mappings().all()
        variants = conn.execute(variants_sql).mappings().all()
        patches = conn.execute(patches_sql).mappings().all()
        cpus = conn.execute(cpu_sql).mappings().all()

    model_by_car: dict[int, list[dict]] = {}
    for row in models:
        model_by_car.setdefault(row["car_series_id"], []).append(
            {"id": row["id"], "name": row["name"]}
        )

    identify_by_model: dict[int, list[dict]] = {}
    for row in identifies:
        identify_by_model.setdefault(row["ecu_model_id"], []).append(
            {
                "addr": row["addr"],
                "length": row["data_length"],
                "hex_value": row["hex_value"].upper(),
            }
        )

    func_by_model: dict[int, list[dict]] = {}
    for row in functions:
        func_by_model.setdefault(row["ecu_model_id"], []).append(
            {
                "id": row["id"],
                "name": row["name"],
                "success_msg": row["success_msg"],
            }
        )

    variant_by_func: dict[int, list[dict]] = {}
    for row in variants:
        variant_by_func.setdefault(row["function_id"], []).append(
            {
                "id": row["id"],
                "identify_hex": row["identify_hex"].upper(),
            }
        )

    patches_by_variant: dict[int, list[dict]] = {}
    for row in patches:
        patches_by_variant.setdefault(row["variant_id"], []).append(
            {
                "addr": row["addr"],
                "length": row["data_length"],
                "value": row["value_hex"].upper(),
                "seq_no": row["seq_no"],
            }
        )

    ecu_database: dict[str, dict] = {}
    car_ecu_map: dict[str, list[str]] = {}

    for car in cars:
        car_name = car["name"]
        ecu_database[car_name] = {}
        car_ecu_map[car_name] = []

        car_models = model_by_car.get(car["id"], [])
        for model in car_models:
            ecu_name = model["name"]
            car_ecu_map[car_name].append(ecu_name)

            identify_list = identify_by_model.get(model["id"], [])
            functions_payload: dict[str, dict] = {}

            for func in func_by_model.get(model["id"], []):
                modifications_map: dict[str, list[dict]] = {}
                for variant in variant_by_func.get(func["id"], []):
                    variant_patches = patches_by_variant.get(variant["id"], [])
                    modifications_map[variant["identify_hex"]] = [
                        {
                            "addr": item["addr"],
                            "length": item["length"],
                            "value": item["value"],
                        }
                        for item in variant_patches
                    ]

                functions_payload[func["name"]] = {
                    "function_id": func["id"],
                    "success_msg": func["success_msg"],
                    "modifications_map": modifications_map,
                }

            ecu_database[car_name][ecu_name] = {
                "identify": identify_list,
                "functions": functions_payload,
            }

    ecu_cpu_map: dict[str, int] = {}
    checksum_addresses: dict[str, int] = {}
    cpu_display_to_key: dict[str, str] = {}
    for cpu in cpus:
        ecu_cpu_map[cpu["cpu_key"]] = cpu["checksum_addr"]
        checksum_addresses[cpu["cpu_display_name"]] = cpu["checksum_addr"]
        cpu_display_to_key[cpu["cpu_display_name"]] = cpu["cpu_key"]

    return {
        "car_ecu_map": car_ecu_map,
        "ecu_database": ecu_database,
        "ecu_cpu_map": ecu_cpu_map,
        "checksum_addresses": checksum_addresses,
        "cpu_display_to_key": cpu_display_to_key,
        "all_function_names": _list_all_enabled_function_names(),
    }


@router.get("/runtime-dataset")
def runtime_dataset(user: dict = Depends(get_current_user)) -> Response:
    payload = _build_runtime_dataset_payload(user)
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Response(content=payload_bytes, media_type="application/json")


@router.get("/runtime-dataset/refresh")
@router.post("/runtime-dataset/refresh")
def refresh_runtime_dataset(user: dict = Depends(get_current_user)) -> dict:
    payload = _build_runtime_dataset_payload(user)
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "ok": True,
        "message": "runtime-dataset generated",
        "size_bytes": len(payload_bytes),
    }


@router.get("/purchase-config")
def get_purchase_config(user: dict = Depends(get_current_user)) -> dict:
    defaults = {
        "title": "功能开通",
        "message": "当前功能尚未开通，请扫码付款后联系管理员授权。",
        "qr_code_url": "",
        "contact": "",
        "free_feature_names": ["接线图查询", "资料下载", "文件下载", "学习资料"],
    }
    with get_conn() as conn:
        rows = conn.execute(
            text(
                "SELECT setting_key, setting_value FROM app_setting WHERE setting_key IN ('purchase_title','purchase_message','purchase_qr_code_url','purchase_contact','update_notice','force_update','latest_version','latest_download_url','virtual_downloads_json')"
            )
        ).mappings().all()
        guide_rows = conn.execute(
            text(
                """
                SELECT id, name, model, car_model, keywords, description, preview_image_url, file_name, object_key, file_url
                FROM app_wiring_guide
                WHERE is_enabled = 1
                ORDER BY sort_order ASC, id DESC
                """
            )
        ).mappings().all()
    mapping = {row["setting_key"]: row["setting_value"] or "" for row in rows}
    virtual_assets = _normalize_virtual_assets_for_client(mapping.get("virtual_downloads_json", "[]"))
    wiring_guides = []
    for row in guide_rows:
        object_key = (row.get("object_key") or "").strip()
        if object_key:
            url = f"/api/v1/wiring-guides/{row['id']}/download"
        else:
            url = row.get("file_url") or ""
        wiring_guides.append(
            {
                "id": row["id"],
                "name": row.get("name") or "",
                "model": row.get("model") or "",
                "car_model": row.get("car_model") or "",
                "keywords": row.get("keywords") or "",
                "description": row.get("description") or "",
                "remark": row.get("description") or "",
                "image_url": row.get("preview_image_url") or "",
                "button_text": "查看接线图",
                "file_name": row.get("file_name") or "",
                "url": url,
            }
        )
    qr_code_url = mapping.get("purchase_qr_code_url", defaults["qr_code_url"])
    return {
        "title": mapping.get("purchase_title", defaults["title"]),
        "message": mapping.get("purchase_message", defaults["message"]),
        "qr_code_url": qr_code_url,
        "payment_qr_preview": qr_code_url,
        "contact": mapping.get("purchase_contact", defaults["contact"]),
        "update_notice": mapping.get("update_notice", ""),
        "force_update": mapping.get("force_update", "0"),
        "latest_version": mapping.get("latest_version") or settings.app_version,
        "latest_download_url": mapping.get("latest_download_url", ""),
        "virtual_downloads_json": json.dumps(virtual_assets, ensure_ascii=False),
        "wiring_guides_json": json.dumps(wiring_guides, ensure_ascii=False),
        "free_feature_names": defaults["free_feature_names"],
        "is_admin": bool(user.get("is_admin")),
    }


@router.get("/wiring-guides", response_model=list[AppWiringGuideOut])
def list_wiring_guides(keyword: str = Query("", max_length=64)) -> list[AppWiringGuideOut]:
    keyword = keyword.strip()
    sql = text(
        """
        SELECT id, name, model, car_model, keywords, description, preview_image_url, file_name, object_key, file_url
        FROM app_wiring_guide
        WHERE is_enabled = 1
          AND (:keyword = '' OR name LIKE :like_keyword OR model LIKE :like_keyword OR car_model LIKE :like_keyword OR keywords LIKE :like_keyword OR description LIKE :like_keyword)
        ORDER BY sort_order ASC, id DESC
        """
    )
    with get_conn() as conn:
        rows = conn.execute(
            sql,
            {"keyword": keyword, "like_keyword": f"%{keyword}%"},
        ).mappings().all()
    items = []
    for row in rows:
        object_key = (row.get("object_key") or "").strip()
        url = f"/api/v1/wiring-guides/{row['id']}/download" if object_key else (row.get("file_url") or "")
        items.append(
            AppWiringGuideOut(
                id=row["id"],
                name=row.get("name") or "",
                model=row.get("model") or None,
                car_model=row.get("car_model") or None,
                keywords=row.get("keywords") or None,
                description=row.get("description") or None,
                image_url=row.get("preview_image_url") or None,
                button_text="查看接线图",
                file_name=row.get("file_name") or None,
                url=url or None,
            )
        )
    return items


@router.get("/files/{object_key:path}")
def get_file_proxy(object_key: str):
    key = unquote((object_key or "").strip())
    if not key:
        raise HTTPException(status_code=404, detail="file not found")
    from app.storage import get_object_content
    content, content_type = get_object_content(key)
    return Response(content=content, media_type=content_type)


@router.get("/learning-articles", response_model=list[LearningArticleOut])
def list_learning_articles() -> list[LearningArticleOut]:
    with get_conn() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, title, summary, cover_image_url, content_html
                FROM app_learning_article
                WHERE is_enabled = 1
                ORDER BY sort_order ASC, id DESC
                """
            )
        ).mappings().all()
    return [
        LearningArticleOut(
            id=row["id"],
            title=row.get("title") or "",
            summary=row.get("summary") or None,
            cover_image_url=row.get("cover_image_url") or None,
            content_html=row.get("content_html") or None,
        )
        for row in rows
    ]


@router.get("/wiring-guides/{guide_id}/download")
def download_wiring_guide(guide_id: int):
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT id, object_key, file_url FROM app_wiring_guide WHERE id = :id AND is_enabled = 1 LIMIT 1"),
            {"id": guide_id},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="wiring guide not found")
    object_key = (row.get("object_key") or "").strip()
    if object_key:
        return RedirectResponse(f"/api/v1/files/{quote(object_key, safe='')}", status_code=307)
    file_url = (row.get("file_url") or "").strip()
    if not file_url:
        raise HTTPException(status_code=404, detail="wiring guide file not found")
    return RedirectResponse(file_url, status_code=307)
