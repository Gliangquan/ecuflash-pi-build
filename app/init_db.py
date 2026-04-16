from sqlalchemy import text

from app.db import engine
from app.security import hash_password, now_str
from app.settings import settings
from app.storage import ensure_bucket_exists


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS app_user (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        phone VARCHAR(32) NOT NULL UNIQUE,
        name VARCHAR(64) NOT NULL,
        password_hash VARCHAR(128) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'enabled',
        approval_note VARCHAR(255) NULL,
        is_admin TINYINT(1) NOT NULL DEFAULT 0,
        auth_end_at DATETIME NULL,
        device_id VARCHAR(128) NULL,
        device_name VARCHAR(128) NULL,
        device_bound_at DATETIME NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        last_login_at DATETIME NULL,
        INDEX idx_app_user_status (status),
        INDEX idx_app_user_created_at (created_at),
        INDEX idx_app_user_device_id (device_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS app_session (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        token VARCHAR(128) NOT NULL UNIQUE,
        expired_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL,
        last_seen_at DATETIME NULL,
        INDEX idx_app_session_user_id (user_id),
        INDEX idx_app_session_expired_at (expired_at),
        CONSTRAINT fk_app_session_user FOREIGN KEY (user_id) REFERENCES app_user(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS app_user_function_permission (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        function_id BIGINT NOT NULL,
        start_at DATETIME NULL,
        end_at DATETIME NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'enabled',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uk_user_function (user_id, function_id),
        INDEX idx_permission_user_id (user_id),
        INDEX idx_permission_function_id (function_id),
        CONSTRAINT fk_permission_user FOREIGN KEY (user_id) REFERENCES app_user(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS app_operation_log (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NULL,
        actor_name VARCHAR(64) NULL,
        action VARCHAR(64) NOT NULL,
        target_type VARCHAR(64) NULL,
        target_id VARCHAR(64) NULL,
        detail TEXT NULL,
        created_at DATETIME NOT NULL,
        INDEX idx_log_user_id (user_id),
        INDEX idx_log_action (action),
        INDEX idx_log_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS app_setting (
        setting_key VARCHAR(64) PRIMARY KEY,
        setting_value TEXT NULL,
        updated_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS app_wiring_guide (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(255) NOT NULL,
        model VARCHAR(128) NULL,
        car_model VARCHAR(128) NULL,
        keywords VARCHAR(255) NULL,
        description TEXT NULL,
        preview_image_url VARCHAR(512) NULL,
        file_name VARCHAR(255) NULL,
        object_key VARCHAR(255) NULL,
        file_url VARCHAR(512) NULL,
        content_type VARCHAR(128) NULL,
        file_size BIGINT NOT NULL DEFAULT 0,
        sort_order INT NOT NULL DEFAULT 0,
        is_enabled TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_app_wiring_guide_enabled (is_enabled),
        INDEX idx_app_wiring_guide_sort (sort_order),
        INDEX idx_app_wiring_guide_model (model),
        INDEX idx_app_wiring_guide_car_model (car_model)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS app_learning_article (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        title VARCHAR(255) NOT NULL,
        summary TEXT NULL,
        cover_image_url VARCHAR(512) NULL,
        content_html LONGTEXT NULL,
        sort_order INT NOT NULL DEFAULT 0,
        is_enabled TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_app_learning_article_enabled (is_enabled),
        INDEX idx_app_learning_article_sort (sort_order)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ecu_car_series (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(128) NOT NULL,
        sort_order INT NOT NULL DEFAULT 0,
        is_enabled TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NULL,
        updated_at DATETIME NULL,
        INDEX idx_ecu_car_series_enabled (is_enabled),
        INDEX idx_ecu_car_series_sort (sort_order)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ecu_model (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        car_series_id BIGINT NOT NULL,
        name VARCHAR(128) NOT NULL,
        sort_order INT NOT NULL DEFAULT 0,
        is_enabled TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NULL,
        updated_at DATETIME NULL,
        INDEX idx_ecu_model_car_series_id (car_series_id),
        INDEX idx_ecu_model_enabled (is_enabled),
        INDEX idx_ecu_model_sort (sort_order)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ecu_identify_rule (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        ecu_model_id BIGINT NOT NULL,
        addr INT NOT NULL,
        data_length INT NOT NULL,
        hex_value VARCHAR(255) NOT NULL,
        created_at DATETIME NULL,
        updated_at DATETIME NULL,
        INDEX idx_ecu_identify_rule_model_id (ecu_model_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ecu_function (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        ecu_model_id BIGINT NOT NULL,
        name VARCHAR(128) NOT NULL,
        success_msg VARCHAR(255) NULL,
        sort_order INT NOT NULL DEFAULT 0,
        is_enabled TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NULL,
        updated_at DATETIME NULL,
        INDEX idx_ecu_function_model_id (ecu_model_id),
        INDEX idx_ecu_function_enabled (is_enabled),
        INDEX idx_ecu_function_sort (sort_order)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ecu_function_variant (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        function_id BIGINT NOT NULL,
        identify_hex VARCHAR(255) NOT NULL,
        created_at DATETIME NULL,
        updated_at DATETIME NULL,
        INDEX idx_ecu_function_variant_function_id (function_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ecu_function_patch (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        variant_id BIGINT NOT NULL,
        seq_no INT NOT NULL DEFAULT 0,
        addr INT NOT NULL,
        data_length INT NOT NULL,
        value_hex TEXT NOT NULL,
        created_at DATETIME NULL,
        updated_at DATETIME NULL,
        INDEX idx_ecu_function_patch_variant_id (variant_id),
        INDEX idx_ecu_function_patch_seq_no (seq_no)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ecu_cpu_checksum (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        cpu_key VARCHAR(128) NOT NULL,
        cpu_display_name VARCHAR(128) NOT NULL,
        checksum_addr INT NOT NULL,
        sort_order INT NOT NULL DEFAULT 0,
        is_enabled TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NULL,
        updated_at DATETIME NULL,
        INDEX idx_ecu_cpu_checksum_enabled (is_enabled),
        INDEX idx_ecu_cpu_checksum_sort (sort_order)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def _seed_ecu_data(conn) -> None:
    car_exists = conn.execute(text("SELECT id FROM ecu_car_series LIMIT 1")).mappings().first()
    if car_exists:
        return

    now = now_str()
    conn.execute(
        text(
            """
            INSERT INTO ecu_car_series (name, sort_order, is_enabled, created_at, updated_at)
            VALUES ('测试车系', 1, 1, :now, :now)
            """
        ),
        {"now": now},
    )
    car_series_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()["id"]

    conn.execute(
        text(
            """
            INSERT INTO ecu_model (car_series_id, name, sort_order, is_enabled, created_at, updated_at)
            VALUES (:car_series_id, '测试ECU', 1, 1, :now, :now)
            """
        ),
        {"car_series_id": car_series_id, "now": now},
    )
    ecu_model_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()["id"]

    conn.execute(
        text(
            """
            INSERT INTO ecu_identify_rule (ecu_model_id, addr, data_length, hex_value, created_at, updated_at)
            VALUES (:ecu_model_id, 4096, 4, 'A1B2C3D4', :now, :now)
            """
        ),
        {"ecu_model_id": ecu_model_id, "now": now},
    )

    conn.execute(
        text(
            """
            INSERT INTO ecu_function (ecu_model_id, name, success_msg, sort_order, is_enabled, created_at, updated_at)
            VALUES (:ecu_model_id, '测试功能', '执行成功', 1, 1, :now, :now)
            """
        ),
        {"ecu_model_id": ecu_model_id, "now": now},
    )
    function_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()["id"]

    conn.execute(
        text(
            """
            INSERT INTO ecu_function_variant (function_id, identify_hex, created_at, updated_at)
            VALUES (:function_id, 'A1B2C3D4', :now, :now)
            """
        ),
        {"function_id": function_id, "now": now},
    )
    variant_id = conn.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()["id"]

    conn.execute(
        text(
            """
            INSERT INTO ecu_function_patch (variant_id, seq_no, addr, data_length, value_hex, created_at, updated_at)
            VALUES (:variant_id, 1, 8192, 2, 'ABCD', :now, :now)
            """
        ),
        {"variant_id": variant_id, "now": now},
    )

    conn.execute(
        text(
            """
            INSERT INTO ecu_cpu_checksum (cpu_key, cpu_display_name, checksum_addr, sort_order, is_enabled, created_at, updated_at)
            VALUES ('ECU MT22.1-256kb', 'ECU MT22.1-256kb', 16384, 1, 1, :now, :now)
            """
        ),
        {"now": now},
    )


def _seed_app_settings(conn) -> None:
    now = now_str()
    defaults = {
        "purchase_title": "功能开通",
        "purchase_message": "当前功能尚未开通，请扫码付款后联系管理员授权。",
        "purchase_qr_code_url": "",
        "purchase_contact": "微信/电话请联系管理员",
        "update_notice": "1. 新增账号注册、设备绑定与免登录。\n2. 未授权功能保持可见，点击后弹出开通引导。\n3. 新增校验和黑色主题与资源下载入口。",
        "force_update": "0",
        "latest_version": settings.app_version,
        "latest_download_url": "",
        "allow_passwordless_register": "0",
        "registration_requires_approval": "1",
        "virtual_downloads_json": '[{"title":"示例资料包","category":"manual","summary":"默认占位资料，可在后台替换成正式版本。","image_url":"","download_text":"立即查看","file_name":"example-manual.pdf","file_url":"https://example.com/virtual.bin","content_type":"application/pdf","file_size":0,"sort_order":0,"is_enabled":1,"keywords":"ME7.8.8,EA211"}]',
        "wiring_guides_json": '[]',
    }
    for setting_key, setting_value in defaults.items():
        conn.execute(
            text(
                """
                INSERT INTO app_setting (setting_key, setting_value, updated_at)
                VALUES (:setting_key, :setting_value, :updated_at)
                ON DUPLICATE KEY UPDATE setting_value = IF(setting_value IS NULL OR setting_value = '', VALUES(setting_value), setting_value), updated_at = updated_at
                """
            ),
            {"setting_key": setting_key, "setting_value": setting_value, "updated_at": now},
        )


def _seed_wiring_guides(conn) -> None:
    exists = conn.execute(text("SELECT id FROM app_wiring_guide LIMIT 1")).mappings().first()
    if exists:
        return
    now = now_str()
    conn.execute(
        text(
            """
            INSERT INTO app_wiring_guide (
                name, model, car_model, keywords, description, preview_image_url, file_name, object_key, file_url, content_type, file_size, sort_order, is_enabled, created_at, updated_at
            )
            VALUES (
                :name, :model, :car_model, :keywords, :description, :preview_image_url, :file_name, '', :file_url, 'application/pdf', 0, 1, 1, :created_at, :updated_at
            )
            """
        ),
        {
            "name": "测试接线图",
            "model": "ACDELCO_E84_IROM_MPC5676_BENCH_GM",
            "car_model": "测试车型",
            "keywords": "1234,12345,ACDELCO,E84,MPC5676,GM",
            "description": "默认测试接线图，可在后台继续新增或替换正式文件。",
            "preview_image_url": "",
            "file_name": "ACDELCO_E84_IROM_MPC5676_BENCH_GM.pdf",
            "file_url": "https://downloadcenter1.cairocar4u.com/ecu-pinout/ACDELCO_E84_IROM_MPC5676_BENCH_GM.pdf",
            "created_at": now,
            "updated_at": now,
        },
    )


def _seed_learning_articles(conn) -> None:
    exists = conn.execute(text("SELECT id FROM app_learning_article LIMIT 1")).mappings().first()
    if exists:
        return
    now = now_str()
    conn.execute(
        text(
            """
            INSERT INTO app_learning_article (
                title, summary, cover_image_url, content_html, sort_order, is_enabled, created_at, updated_at
            )
            VALUES (
                :title, :summary, :cover_image_url, :content_html, 1, 1, :created_at, :updated_at
            )
            """
        ),
        {
            "title": "示例学习资料",
            "summary": "这里可以发布图文文章，供前端用户直接查看学习。",
            "cover_image_url": "",
            "content_html": "<h2>示例学习资料</h2><p>后台可新增图文文章，前端在学习资料模块查看。</p>",
            "created_at": now,
            "updated_at": now,
        },
    )


def init_db() -> None:
    with engine.begin() as conn:
        for ddl in DDL_STATEMENTS:
            conn.execute(text(ddl))

        alter_statements = [
            "ALTER TABLE app_user ADD COLUMN device_id VARCHAR(128) NULL",
            "ALTER TABLE app_user ADD COLUMN device_name VARCHAR(128) NULL",
            "ALTER TABLE app_user ADD COLUMN device_bound_at DATETIME NULL",
            "ALTER TABLE app_user ADD COLUMN approval_note VARCHAR(255) NULL",
            "ALTER TABLE app_user ADD COLUMN auth_end_at DATETIME NULL",
            "ALTER TABLE app_user ADD INDEX idx_app_user_device_id (device_id)",
            "ALTER TABLE app_wiring_guide ADD COLUMN preview_image_url VARCHAR(512) NULL",
            "ALTER TABLE app_learning_article ADD COLUMN summary TEXT NULL",
            "ALTER TABLE app_learning_article ADD COLUMN cover_image_url VARCHAR(512) NULL",
            "ALTER TABLE app_learning_article ADD COLUMN content_html LONGTEXT NULL",
            "ALTER TABLE app_learning_article ADD COLUMN sort_order INT NOT NULL DEFAULT 0",
            "ALTER TABLE app_learning_article ADD COLUMN is_enabled TINYINT(1) NOT NULL DEFAULT 1",
        ]
        for sql in alter_statements:
            try:
                conn.execute(text(sql))
            except Exception:
                pass

        admin = conn.execute(
            text("SELECT id FROM app_user WHERE phone = :phone LIMIT 1"),
            {"phone": settings.admin_phone},
        ).mappings().first()
        if not admin:
            now = now_str()
            conn.execute(
                text(
                    """
                    INSERT INTO app_user (phone, name, password_hash, status, is_admin, created_at, updated_at)
                    VALUES (:phone, :name, :password_hash, 'enabled', 1, :created_at, :updated_at)
                    """
                ),
                {
                    "phone": settings.admin_phone,
                    "name": settings.admin_name,
                    "password_hash": hash_password(settings.admin_password),
                    "created_at": now,
                    "updated_at": now,
                },
            )

        _seed_ecu_data(conn)
        _seed_app_settings(conn)
        _seed_wiring_guides(conn)
        _seed_learning_articles(conn)

    try:
        ensure_bucket_exists()
    except Exception:
        pass
