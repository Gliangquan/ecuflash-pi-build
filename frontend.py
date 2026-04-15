# -*- coding: utf-8 -*-
import os
import sys
import json
import struct
import hashlib
import platform
import datetime
import binascii
import random
import socket
import uuid
import warnings
import urllib.parse
import urllib.request
import tempfile
import re
import base64
import mimetypes
import PyQt5

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *


warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r"sipPyTypeDict\(\) is deprecated.*",
)


def _qt_message_handler(_mode, _context, message):
    if message in {"Unknown property text-shadow", "Unknown property box-shadow"}:
        return
    sys.__stderr__.write(f"{message}\n")


qInstallMessageHandler(_qt_message_handler)


USER_DATA_FILE_NAME = "session.dat"


def _resource_path(*parts):
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


API_BASE_URL = os.environ.get("ECUFLASH_API_BASE_URL", "http://107.148.176.142/api/v1").rstrip("/")
APP_VERSION = "1.0.0"
APP_LOGO_FILE = "icon.jpg"
APP_LOGO_URL = ""

UI_BASE_WIDTH = 1920
UI_BASE_HEIGHT = 1080
UI_SCALE_FACTOR = 1.0
_ORIGINAL_SET_STYLE_SHEET = None
_ORIGINAL_SET_FIXED_SIZE = None
_UI_SCALE_PATCHED = False
_APP_LOGO_PIXMAP_CACHE = None
_APP_LOGO_ICON_CACHE = None
_FUNCTION_ICON_CACHE = {}
_FUNCTION_ICON_NAME_MAP = {
    "三项未就绪": "repair-order.png",
    "接线图查询": "dedicated-line.png",
    "文件下载": "file-download.png",
    "学习资料": "file-download.png",
    "怠速调整": "system-settings.png",
    "防盗关闭": "security-shield.png",
    "无防盗": "security-shield.png",
}


def _calc_ui_scale_factor(app):
    screen = app.primaryScreen()
    if not screen:
        return 1.0
    g = screen.availableGeometry()
    ratio = min(g.width() / UI_BASE_WIDTH, g.height() / UI_BASE_HEIGHT)
    return max(0.80, min(1.45, ratio))


def scaled_px(value):
    return max(1, int(round(value * UI_SCALE_FACTOR)))


def scaled_point(value):
    return max(8, int(round(value * UI_SCALE_FACTOR)))


def _scale_stylesheet_px(style_text):
    if not style_text or abs(UI_SCALE_FACTOR - 1.0) < 0.01:
        return style_text

    def _repl(match):
        raw = float(match.group(1))
        return f"{max(1, int(round(raw * UI_SCALE_FACTOR)))}px"

    return re.sub(r"(?<![\\w.-])(\\d+(?:\\.\\d+)?)px", _repl, style_text)


def init_ui_scaling(app):
    global UI_SCALE_FACTOR, _UI_SCALE_PATCHED
    global _ORIGINAL_SET_STYLE_SHEET, _ORIGINAL_SET_FIXED_SIZE

    UI_SCALE_FACTOR = _calc_ui_scale_factor(app)
    if _UI_SCALE_PATCHED:
        return

    try:
        _ORIGINAL_SET_STYLE_SHEET = QWidget.setStyleSheet
        _ORIGINAL_SET_FIXED_SIZE = QWidget.setFixedSize

        def _patched_set_style_sheet(widget, style_text):
            if isinstance(style_text, str):
                style_text = _scale_stylesheet_px(style_text)
            return _ORIGINAL_SET_STYLE_SHEET(widget, style_text)

        def _patched_set_fixed_size(widget, w, h):
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                w = scaled_px(int(w))
                h = scaled_px(int(h))
            return _ORIGINAL_SET_FIXED_SIZE(widget, w, h)

        QWidget.setStyleSheet = _patched_set_style_sheet
        QWidget.setFixedSize = _patched_set_fixed_size
        _UI_SCALE_PATCHED = True
    except Exception:
        _UI_SCALE_PATCHED = False


def _get_app_logo_pixmap(size=28):
    global _APP_LOGO_PIXMAP_CACHE
    if _APP_LOGO_PIXMAP_CACHE is None:
        # Prefer remote logo first.
        try:
            request = urllib.request.Request(APP_LOGO_URL, headers={"Accept": "image/*"})
            with urllib.request.urlopen(request, timeout=5) as response:
                data = response.read()
            remote_pixmap = QPixmap()
            if remote_pixmap.loadFromData(data):
                _APP_LOGO_PIXMAP_CACHE = remote_pixmap
        except Exception:
            _APP_LOGO_PIXMAP_CACHE = None

        # Fallback to local logo file.
        if _APP_LOGO_PIXMAP_CACHE is None:
            logo_path = _resource_path(APP_LOGO_FILE)
            if os.path.exists(logo_path):
                local_pixmap = QPixmap(logo_path)
                if not local_pixmap.isNull():
                    _APP_LOGO_PIXMAP_CACHE = local_pixmap

    if _APP_LOGO_PIXMAP_CACHE is None:
        return None
    return _APP_LOGO_PIXMAP_CACHE.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _get_app_logo_icon():
    global _APP_LOGO_ICON_CACHE
    if _APP_LOGO_ICON_CACHE is not None:
        return _APP_LOGO_ICON_CACHE

    pixmap = _get_app_logo_pixmap(64)
    if pixmap is None or pixmap.isNull():
        return None
    _APP_LOGO_ICON_CACHE = QIcon(pixmap)
    if _APP_LOGO_ICON_CACHE.isNull():
        _APP_LOGO_ICON_CACHE = None
    return _APP_LOGO_ICON_CACHE


def _guess_function_icon_filename(title):
    text = str(title or "").strip()
    if not text:
        return "system-settings.png"
    if text in _FUNCTION_ICON_NAME_MAP:
        return _FUNCTION_ICON_NAME_MAP[text]
    if any(token in text for token in ("防盗", "安全", "授权")):
        return "security-shield.png"
    if any(token in text for token in ("下载", "文件", "资料")):
        return "file-download.png"
    if any(token in text for token in ("检测", "诊断", "识别")):
        return "diagnostic-track.png"
    if any(token in text for token in ("车辆", "车系", "车型")):
        return "vehicle-settings.png"
    if any(token in text for token in ("线路", "接线", "线")):
        return "dedicated-line.png"
    if any(token in text for token in ("工单", "检修", "未就绪", "修复")):
        return "repair-order.png"
    return "system-settings.png"


def _get_function_icon(title, size=42, muted=False):
    icon_name = _guess_function_icon_filename(title)
    cache_key = f"{icon_name}:{size}:{int(bool(muted))}"
    if cache_key in _FUNCTION_ICON_CACHE:
        return _FUNCTION_ICON_CACHE[cache_key]
    icon_path = _resource_path("icon", icon_name)
    if not os.path.exists(icon_path):
        return QIcon()
    pixmap = QPixmap(icon_path)
    if pixmap.isNull():
        return QIcon()

    scaled = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    rendered = QPixmap(scaled.size())
    rendered.fill(Qt.transparent)

    painter = QPainter(rendered)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawPixmap(0, 0, scaled)
    if muted:
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(rendered.rect(), QColor(168, 182, 201, 210))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setOpacity(0.18)
        painter.drawPixmap(0, 0, scaled)
    else:
        painter.setCompositionMode(QPainter.CompositionMode_Screen)
        painter.fillRect(rendered.rect(), QColor(120, 220, 255, 28))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setOpacity(0.12)
        painter.drawPixmap(0, 0, scaled)
    painter.end()

    icon = QIcon(rendered)
    _FUNCTION_ICON_CACHE[cache_key] = icon
    return icon


def apply_logo_to_window(window_obj):
    icon = _get_app_logo_icon()
    if icon:
        window_obj.setWindowIcon(icon)


def create_branded_message_box(parent=None):
    message_box = QMessageBox(parent)
    message_box.setWindowTitle("ECU Hub")
    logo_pixmap = _get_app_logo_pixmap(28)
    if logo_pixmap:
        message_box.setIconPixmap(logo_pixmap)
    icon = _get_app_logo_icon()
    if icon:
        message_box.setWindowIcon(icon)
    return message_box

def configure_qt_runtime():
    if not sys.platform.startswith("win"):
        return

    package_dir = os.path.dirname(PyQt5.__file__)
    platform_candidates = [
        os.path.join(package_dir, "Qt5", "plugins", "platforms"),
        os.path.join(package_dir, "Qt", "plugins", "platforms"),
    ]

    for platforms_dir in platform_candidates:
        qwindows_dll = os.path.join(platforms_dir, "qwindows.dll")
        if not os.path.isfile(qwindows_dll):
            continue

        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_dir
        plugin_root = os.path.dirname(platforms_dir)
        if plugin_root not in QCoreApplication.libraryPaths():
            QCoreApplication.addLibraryPath(plugin_root)
        break


CAR_ECU_MAP = {}


ECU_CPU_MAP = {}


ECU_DATABASE = []


def calculate_checksum(original_data, modified_data, offset):
    try:
        if len(original_data) != len(modified_data):
            return False, None
        def sum16(data, skip_start, skip_len):
            s = 0
            for i in range(0, len(data), 2):
                if skip_start <= i < skip_start + skip_len: continue
                if i + 1 >= len(data): w = data[i] << 8
                else: w = (data[i] << 8) | data[i + 1]
                s = (s + w) & 0xFFFF
            return s
        sum_ori = sum16(original_data, offset, 2)
        orig_cs = struct.unpack('>H', original_data[offset:offset + 2])[0]
        init = (orig_cs - sum_ori) & 0xFFFF
        sum_mod = sum16(modified_data, offset, 2)
        new_cs = (sum_mod + init) & 0xFFFF
        modified_data[offset:offset + 2] = struct.pack('>H', new_cs)
        return True, modified_data
    except:
        return False, None


def _api_request_json(path, method="GET", payload=None, token=None, timeout=15):
    url = f"{API_BASE_URL}{path}"
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print(f"[API] {method} {url}")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            print(f"[API] STATUS {response.status}")
            preview = raw if len(raw) <= 1200 else raw[:1200] + "...(truncated)"
            print(f"[API] RESPONSE {preview}")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw)
            detail = data.get("detail") or raw or str(exc)
        except Exception:
            detail = raw or str(exc)
        raise RuntimeError(detail)


def _session_file_path():
    base_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or os.path.join(os.path.expanduser("~"), ".ecuflash")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, USER_DATA_FILE_NAME)


def load_session_data():
    session_file = _session_file_path()
    if not os.path.exists(session_file):
        return None
    try:
        with open(session_file, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except Exception:
        return None


def save_session_data(data):
    session_file = _session_file_path()
    with open(session_file, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, indent=4, ensure_ascii=False)


def clear_session_data():
    session_file = _session_file_path()
    try:
        if os.path.exists(session_file):
            os.remove(session_file)
    except Exception:
        pass


def fetch_my_permissions(token):
    data = _api_request_json("/auth/my-permissions", token=token)
    function_ids = data.get("function_ids") or []
    function_names = data.get("function_names") or []
    return {
        "ids": set(int(item) for item in function_ids),
        "names": set(str(item).strip() for item in function_names if str(item).strip()),
    }


def fetch_purchase_config(token):
    return _api_request_json("/purchase-config", token=token)


def _parse_config_list(raw_value):
    if isinstance(raw_value, list):
        return raw_value
    if not raw_value:
        return []
    try:
        data = json.loads(raw_value)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _normalize_resource_search_text(value):
    text = str(value or "").upper()
    for old, new in (("（", "("), ("）", ")"), ("【", "["), ("】", "]")):
        text = text.replace(old, new)
    for token in (" ", "\t", "\r", "\n", "-", "_", ".", "/", "\\", "(", ")", "[", "]"):
        text = text.replace(token, "")
    return text


def _resource_item_search_text(item):
    if not isinstance(item, dict):
        return _normalize_resource_search_text(item)
    parts = []
    for value in item.values():
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(part) for part in value if part not in (None, ""))
        elif value not in (None, ""):
            parts.append(str(value))
    return _normalize_resource_search_text(" ".join(parts))


def _filter_resource_items(items, keyword):
    query = _normalize_resource_search_text(keyword)
    if not query:
        return list(items or [])
    return [item for item in (items or []) if query in _resource_item_search_text(item)]


def _resolve_resource_url(url):
    text = (url or "").strip()
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme:
        return text
    return urllib.parse.urljoin(API_BASE_URL + "/", text)


def _open_url(url):
    resolved = _resolve_resource_url(url)
    if not resolved:
        return False
    return QDesktopServices.openUrl(QUrl(resolved))


def _open_browser_download(url):
    return _open_url(url)


def _to_data_url(url):
    resolved = _resolve_resource_url(url)
    if not resolved:
        return ""
    try:
        request = urllib.request.Request(resolved, headers={"Accept": "image/*"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read()
            content_type = response.headers.get_content_type() if response.headers else None

        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            if pixmap.width() > 260 or pixmap.height() > 360:
                pixmap = pixmap.scaled(260, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            pixmap.save(buffer, "PNG")
            data = bytes(buffer.data())
            mime_type = "image/png"
        else:
            mime_type = content_type or mimetypes.guess_type(resolved)[0] or "image/png"

        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    except Exception:
        return resolved


def _normalize_learning_article_html(content_html):
    html = str(content_html or "")
    if not html.strip():
        return ""
    html = re.sub(r"<\/?(?:html|body)[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\sstyle\s*=\s*\"[^\"]*\"", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\sstyle\s*=\s*'[^']*'", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\sbgcolor\s*=\s*\"[^\"]*\"", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\sbgcolor\s*=\s*'[^']*'", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\swidth\s*=\s*\"[^\"]*\"", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\swidth\s*=\s*'[^']*'", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\sheight\s*=\s*\"[^\"]*\"", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\sheight\s*=\s*'[^']*'", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<table([^>]*)>", r"<table\1 cellpadding='8' cellspacing='0' border='1'>", html, flags=re.IGNORECASE)

    def _replace_url_attr(match):
        attr_name = match.group(1)
        quote = match.group(2)
        attr_value = match.group(3)
        if attr_name.lower() == "src":
            resolved = _to_data_url(attr_value)
        else:
            resolved = _resolve_resource_url(attr_value)
        return f" {attr_name}={quote}{resolved}{quote}"

    html = re.sub(r"\s(src|href)\s*=\s*([\"'])(.*?)\2", _replace_url_attr, html, flags=re.IGNORECASE)
    return html


def _copy_text_to_clipboard(text):
    value = (text or "").strip()
    if not value:
        return False
    clipboard = QApplication.clipboard()
    if clipboard is None:
        return False
    clipboard.setText(value)
    return True


def _copy_url_to_clipboard(url):
    return _copy_text_to_clipboard(_resolve_resource_url(url))


def _get_disk_fingerprint():
    candidates = []
    try:
        if sys.platform == "darwin":
            text = os.popen("ioreg -rd1 -c IOPlatformExpertDevice 2>/dev/null").read()
            for key in ("IOPlatformUUID", "IOPlatformSerialNumber"):
                match = re.search(rf'"{key}"\s*=\s*"([^"]+)"', text)
                if match:
                    candidates.append(match.group(1))
        elif sys.platform.startswith("win"):
            text = os.popen("wmic csproduct get uuid 2>nul").read()
            for line in text.splitlines():
                value = line.strip()
                if value and value.lower() != "uuid":
                    candidates.append(value)
        else:
            for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(path):
                    try:
                        candidates.append(open(path, "r", encoding="utf-8").read().strip())
                    except Exception:
                        pass
    except Exception:
        pass
    return "|".join(item for item in candidates if item)


def get_device_fingerprint():
    raw = "|".join([
        _get_disk_fingerprint(),
        platform.system(),
        platform.release(),
        platform.machine(),
        socket.gethostname(),
        hex(uuid.getnode()),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_device_name():
    return f"{socket.gethostname()} / {platform.system()} {platform.machine()}"


def check_license():
    session = load_session_data()
    if not session or not session.get("token"):
        return None
    try:
        user = _api_request_json("/auth/me", token=session["token"])
        session["user"] = user
        session["name"] = user.get("name") or user.get("phone") or "未命名用户"
        session["expire_time"] = session.get("expired_at") or "长期有效"
        permissions = fetch_my_permissions(session["token"])
        session["permission_function_ids"] = sorted(permissions["ids"])
        session["permission_function_names"] = sorted(permissions["names"])
        try:
            session["purchase_config"] = fetch_purchase_config(session["token"])
        except Exception:
            session["purchase_config"] = {}
        save_session_data(session)
        return session
    except Exception:
        clear_session_data()
        return None


class RegisterDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.session_data = None
        self.mode = "login"
        self.setWindowTitle(f"ECUflash V{APP_VERSION} - 登录/注册")
        apply_logo_to_window(self)
        self.setFixedSize(620, 520)
        self.setStyleSheet("""
            QDialog { background-color: #f8f9fa; font-family: "Microsoft YaHei"; font-size: 18px; }
            QLabel { font-size: 18px; color: #222222; }
            QLineEdit { min-height: 45px; padding: 8px 12px; font-size: 16px; color: #222222; background: white; border: 1px solid #ddd; border-radius: 6px; }
            QPushButton { min-height: 50px; background-color: #165DFF; color: white; border-radius: 8px; font-size: 17px; font-weight: bold; }
            QPushButton:hover { background-color: #0F48CC; }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(60, 42, 60, 42)
        self.title_label = QLabel("ECUflash 账号登录")
        self.title_label.setFont(QFont("Microsoft YaHei", scaled_point(26), QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color:#165DFF")
        layout.addWidget(self.title_label)
        self.desc_label = QLabel("请输入手机号和密码登录，首次可直接注册并绑定当前电脑")
        self.desc_label.setAlignment(Qt.AlignCenter)
        self.desc_label.setStyleSheet("color:#666666;font-size:15px;")
        layout.addWidget(self.desc_label)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        self.login_mode_btn = QPushButton("登录")
        self.register_mode_btn = QPushButton("注册")
        self.login_mode_btn.clicked.connect(lambda: self.switch_mode("login"))
        self.register_mode_btn.clicked.connect(lambda: self.switch_mode("register"))
        mode_row.addWidget(self.login_mode_btn)
        mode_row.addWidget(self.register_mode_btn)
        layout.addLayout(mode_row)

        self.name_label = QLabel("用户名：")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("请输入用户名")
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("手机号："))
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("请输入手机号")
        layout.addWidget(self.phone_edit)

        layout.addWidget(QLabel("密码："))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("请输入密码")
        layout.addWidget(self.password_edit)

        self.device_label = QLabel(f"当前设备：{get_device_name()}")
        self.device_label.setStyleSheet("color:#4B5563;font-size:14px;")
        layout.addWidget(self.device_label)

        self.submit_btn = QPushButton("登录并进入主界面")
        self.submit_btn.clicked.connect(self.submit)
        layout.addWidget(self.submit_btn)

        self.switch_mode("login")

    def switch_mode(self, mode):
        self.mode = mode
        is_register = mode == "register"
        self.name_label.setVisible(is_register)
        self.name_edit.setVisible(is_register)
        self.title_label.setText("ECUflash 用户注册" if is_register else "ECUflash 账号登录")
        self.desc_label.setText(
            "请输入用户名、手机号，密码按后台配置决定是否必填，注册后自动绑定当前电脑"
            if is_register else
            "请输入手机号和密码登录，账号会校验已绑定设备"
        )
        self.submit_btn.setText("注册并进入主界面" if is_register else "登录并进入主界面")
        self.password_edit.setPlaceholderText("注册可留空（取决于后台配置）" if is_register else "请输入密码")
        active_style = "background-color:#165DFF;color:white;"
        inactive_style = "background-color:#E5E7EB;color:#374151;"
        self.login_mode_btn.setStyleSheet(active_style if mode == "login" else inactive_style)
        self.register_mode_btn.setStyleSheet(active_style if mode == "register" else inactive_style)

    def _build_session(self, phone, data):
        token = data["token"]
        session = {
            "token": token,
            "expired_at": data.get("expired_at"),
            "user": data.get("user", {}),
            "name": data.get("user", {}).get("name") or data.get("user", {}).get("phone") or phone,
            "expire_time": data.get("expired_at") or "长期有效",
            "permission_function_ids": sorted(fetch_my_permissions(token)["ids"]),
            "permission_function_names": sorted(fetch_my_permissions(token)["names"]),
        }
        try:
            session["purchase_config"] = fetch_purchase_config(token)
        except Exception:
            session["purchase_config"] = {}
        return session

    def submit(self):
        phone = self.phone_edit.text().strip()
        password = self.password_edit.text().strip()
        name = self.name_edit.text().strip()
        device_id = get_device_fingerprint()
        device_name = get_device_name()
        if not phone:
            show_message(self, QMessageBox.Warning, "错误", "手机号不能为空！")
            return
        if self.mode == "register" and not name:
            show_message(self, QMessageBox.Warning, "错误", "注册时用户名不能为空！")
            return
        try:
            if self.mode == "register":
                data = _api_request_json(
                    "/auth/register",
                    method="POST",
                    payload={
                        "phone": phone,
                        "password": password,
                        "name": name,
                        "device_id": device_id,
                        "device_name": device_name,
                    },
                )
                success_text = "注册成功！正在进入主界面。"
            else:
                data = _api_request_json(
                    "/auth/login",
                    method="POST",
                    payload={
                        "phone": phone,
                        "password": password,
                        "device_id": device_id,
                        "device_name": device_name,
                    },
                )
                success_text = "登录成功！正在进入主界面。"
            session = self._build_session(phone, data)
            save_session_data(session)
            self.session_data = session
            show_message(self, QMessageBox.Information, "成功", success_text)
            self.accept()
        except Exception as exc:
            message = str(exc)
            if self.mode == "register" and "registered_pending_approval" in message:
                show_message(self, QMessageBox.Information, "注册成功", "注册申请已提交，请等待后台审批后再登录。")
                self.password_edit.clear()
                self.switch_mode("login")
                return
            if self.mode == "login" and "user pending approval" in message:
                show_message(self, QMessageBox.Warning, "登录失败", "当前账号待后台审批，审批通过后才能登录。")
                return
            title = "注册失败" if self.mode == "register" else "登录失败"
            show_message(self, QMessageBox.Warning, title, f"账号操作失败：{exc}")


class ChecksumTool(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle("德尔福 Checksum 校验和计算")
        apply_logo_to_window(self)
        self.setFixedSize(650,450)
        self.setStyleSheet("""
            QDialog{background-color:#f5f7fa;font-family:Microsoft YaHei;}
            QPushButton{background-color:#165DFF;color:white;border-radius:8px;padding:12px;font-size:16px;}
            QPushButton:hover{background-color:#0F48CC;}
            QComboBox{min-height:45px;font-size:16px;padding:8px;border-radius:6px;}
            QLabel{font-size:17px;}
        """)
        self.original_data=None
        self.modified_data=None
        self.init_ui()
    def init_ui(self):
        layout=QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40,40,40,40)
        title=QLabel("🔧 德尔福 ECU 校验和计算工具")
        title.setFont(QFont("Microsoft YaHei", scaled_point(20), QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        self.cpu_box=QComboBox()
        self.cpu_box.addItems(list(ECU_CPU_MAP.keys()))
        layout.addWidget(QLabel("选择CPU型号："))
        layout.addWidget(self.cpu_box)
        self.btn_ori=QPushButton("📂 加载原始数据")
        self.btn_mod=QPushButton("📂 加载修改后数据")
        self.btn_calc=QPushButton("✅ 计算校验和并保存")
        layout.addWidget(self.btn_ori)
        layout.addWidget(self.btn_mod)
        layout.addWidget(self.btn_calc)
        self.status=QLabel("状态：等待操作")
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status)
        self.btn_ori.clicked.connect(self.load_original)
        self.btn_mod.clicked.connect(self.load_modified)
        self.btn_calc.clicked.connect(self.calc_save)
    def load_original(self):
        p=QFileDialog.getOpenFileName(self,"选择原始BIN文件","","BIN Files (*.bin)")[0]
        if p:
            with open(p,"rb") as f:self.original_data=bytearray(f.read())
            self.status.setText("状态：原始数据已加载")
    def load_modified(self):
        p=QFileDialog.getOpenFileName(self,"选择修改后BIN文件","","BIN Files (*.bin)")[0]
        if p:
            with open(p,"rb") as f:self.modified_data=bytearray(f.read())
            self.status.setText("状态：修改后数据已加载")
    def calc_save(self):
        if self.original_data is None or self.modified_data is None:
            QMessageBox.warning(self,"提示","请先加载原始数据和修改后数据！")
            return
        cpu=self.cpu_box.currentText()
        offset=ECU_CPU_MAP[cpu]
        ok,new_data=calculate_checksum(self.original_data,self.modified_data,offset)
        if not ok:
            QMessageBox.critical(self,"错误","数据错误，请重新加载数据！")
            return
        save_path=QFileDialog.getSaveFileName(self,"保存文件","","BIN Files (*.bin)")[0]
        if save_path:
            with open(save_path,"wb") as f:f.write(new_data)
            QMessageBox.information(self,"成功","Checksum计算成功！文件已保存！")
            self.status.setText("状态：计算完成")


class ECUSearchComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.lineEdit().textChanged.connect(self.filter_items)
        self.all_items = []
        for car in CAR_ECU_MAP:
            self.all_items.extend(CAR_ECU_MAP[car])

    def filter_items(self, text):
        self.clear()
        text = text.lower().strip()
        for item in self.all_items:
            if text in item.lower():
                self.addItem(item)


FEATURE_ECU_DATABASE = ECU_DATABASE

CAR_TYPE_ALIASES = {
    "国产": "中国车系",
    "通用": "通用（别克 雪佛兰 凯迪拉克）",
}
HIDDEN_FUNCTION_NAMES = {"无防盗"}


def _collect_all_function_names(database):
    names = []
    seen = set()
    if not isinstance(database, dict):
        return names
    for ecu_list in database.values():
        if not isinstance(ecu_list, dict):
            continue
        for ecu_info in ecu_list.values():
            functions = (ecu_info or {}).get("functions", {})
            if not isinstance(functions, dict):
                continue
            for func_name in functions.keys():
                if func_name in HIDDEN_FUNCTION_NAMES or func_name in seen:
                    continue
                seen.add(func_name)
                names.append(func_name)
    return names


def _normalize_lookup_name(text):
    normalized = (
        text.upper()
        .replace("（", "(")
        .replace("）", ")")
        .replace("　", "")
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace(".", "")
        .replace("/", "")
        .replace("\\", "")
        .replace("(", "")
        .replace(")", "")
    )
    for vendor_name in ("博士", "德尔福", "奥易克斯"):
        normalized = normalized.replace(vendor_name.upper(), "")
    return normalized


def _resolve_target_slot(car_map, feature_car_type, feature_ecu_name):
    resolved_car_type = CAR_TYPE_ALIASES.get(feature_car_type, feature_car_type)
    ecu_candidates = []

    if resolved_car_type in car_map:
        ecu_candidates = [(resolved_car_type, ecu_name) for ecu_name in car_map[resolved_car_type]]
        if feature_ecu_name in car_map[resolved_car_type]:
            return resolved_car_type, feature_ecu_name
    else:
        for car_type, ecu_names in car_map.items():
            ecu_candidates.extend((car_type, ecu_name) for ecu_name in ecu_names)

    feature_norm = _normalize_lookup_name(feature_ecu_name)
    exact_matches = [
        (car_type, ecu_name)
        for car_type, ecu_name in ecu_candidates
        if _normalize_lookup_name(ecu_name) == feature_norm
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    fuzzy_matches = [
        (car_type, ecu_name)
        for car_type, ecu_name in ecu_candidates
        if feature_norm and (
            feature_norm in _normalize_lookup_name(ecu_name)
            or _normalize_lookup_name(ecu_name) in feature_norm
        )
    ]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]

    return resolved_car_type, feature_ecu_name


def _build_normalized_database(car_map, feature_database):
    normalized = {
        car_type: {
            ecu_name: {"identify": [], "functions": {}}
            for ecu_name in ecu_names
        }
        for car_type, ecu_names in car_map.items()
    }

    for ecu_entry in feature_database:
        car_type, ecu_name = _resolve_target_slot(
            car_map,
            ecu_entry["car_type"],
            ecu_entry["ecu_name"],
        )
        ecu_bucket = normalized.setdefault(car_type, {}).setdefault(
            ecu_name,
            {"identify": [], "functions": {}},
        )

        identify_item = ecu_entry["identify"][0]
        identify_code = identify_item["value_hex"].upper()
        page_identify = {
            "addr": identify_item["start_addr"],
            "length": identify_item["length"],
            "hex_value": identify_code,
        }
        if page_identify not in ecu_bucket["identify"]:
            ecu_bucket["identify"].append(page_identify)

        for func_name, func_cfg in ecu_entry["functions"].items():
            if func_name in HIDDEN_FUNCTION_NAMES:
                continue
            func_bucket = ecu_bucket["functions"].setdefault(
                func_name,
                {"modifications_map": {}, "success_msg": func_cfg["success_msg"]},
            )
            func_bucket["modifications_map"][identify_code] = [
                {
                    "addr": mod_item["start_addr"],
                    "length": mod_item["length"],
                    "value": mod_item["value_hex"].upper(),
                }
                for mod_item in func_cfg["modify_list"]
            ]
            if not func_bucket.get("success_msg"):
                func_bucket["success_msg"] = func_cfg["success_msg"]

    return normalized


def _format_cpu_name(cpu_name):
    if cpu_name.startswith("ECU") and not cpu_name.startswith("ECU "):
        return cpu_name.replace("ECU", "ECU ", 1)
    return cpu_name


NORMALIZED_ECU_DATABASE = _build_normalized_database(CAR_ECU_MAP, FEATURE_ECU_DATABASE)
CHECKSUM_ADDRESSES = {
    _format_cpu_name(cpu_name): offset
    for cpu_name, offset in ECU_CPU_MAP.items()
}
CPU_DISPLAY_TO_KEY = {
    display_name: raw_name
    for raw_name, display_name in (
        (cpu_name, _format_cpu_name(cpu_name))
        for cpu_name in ECU_CPU_MAP
    )
}
ECU_DATABASE = NORMALIZED_ECU_DATABASE
ALL_FUNCTION_NAMES = []


def _api_get_json(path, params=None, timeout=15):
    url = f"{API_BASE_URL}{path}"
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}?{query}"

    print(f"[API] GET {url}")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        print(f"[API] STATUS {response.status}")
        preview = raw if len(raw) <= 1200 else raw[:1200] + "...(truncated)"
        print(f"[API] RESPONSE {preview}")
        return json.loads(raw)


def load_remote_runtime_dataset(token):
    data = _api_request_json("/runtime-dataset", token=token)

    required_keys = {
        "car_ecu_map",
        "ecu_database",
        "ecu_cpu_map",
        "checksum_addresses",
        "cpu_display_to_key",
        "all_function_names",
    }
    missing = required_keys - set(data.keys())
    if missing:
        raise ValueError(f"服务端数据缺少字段: {', '.join(sorted(missing))}")

    global CAR_ECU_MAP, ECU_DATABASE, ECU_CPU_MAP, CHECKSUM_ADDRESSES, CPU_DISPLAY_TO_KEY, FEATURE_ECU_DATABASE, ALL_FUNCTION_NAMES
    CAR_ECU_MAP = data["car_ecu_map"]
    ECU_DATABASE = data["ecu_database"]
    FEATURE_ECU_DATABASE = data["ecu_database"]
    ECU_CPU_MAP = data["ecu_cpu_map"]
    CHECKSUM_ADDRESSES = data["checksum_addresses"]
    CPU_DISPLAY_TO_KEY = data["cpu_display_to_key"]
    ALL_FUNCTION_NAMES = list(data.get("all_function_names") or [])
    print(
        "[API] DATASET SUMMARY "
        f"car_series={len(CAR_ECU_MAP)}, "
        f"ecu_models={sum(len(v) for v in CAR_ECU_MAP.values())}, "
        f"cpu_models={len(ECU_CPU_MAP)}"
    )


def get_computer_name():
    """获取电脑名称"""
    try:
        return socket.gethostname()
    except:
        return "PC"


def generate_random_num(length=6):
    """生成随机数"""
    return ''.join([str(random.randint(0,9)) for _ in range(length)])


class ChecksumDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("德尔福 Checksum 校验和计算")
        apply_logo_to_window(self)
        self.setFixedSize(500, 350)
        self.setStyleSheet("""
            QDialog {
                background-color: #060B16;
                font-family: Microsoft YaHei;
            }
            QLabel {
                font-size: 14px;
                color: #E5E7EB;
            }
            QComboBox {
                font-size: 14px;
                padding: 8px;
                border: 1px solid rgba(96, 165, 250, 0.35);
                border-radius: 8px;
                min-height: 35px;
                background: #111827;
                color: #F9FAFB;
            }
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 10px;
                min-height: 40px;
            }
        """)
        
        self.original_file_data = b""
        self.original_file_path = ""
        self.modified_file_data = b""
        self.modified_file_path = ""
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 20)
        main_layout.setSpacing(15)
        
        title_label = QLabel("德尔福 ECU 校验和计算工具")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #60A5FA;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        cpu_layout = QHBoxLayout()
        cpu_label = QLabel("选择CPU型号：")
        self.cpu_combobox = QComboBox()
        self.cpu_combobox.addItems([
            "ECU MT22.1-256kb", 
            "ECU MT22.1-384kb", 
            "ECU MT22.1-512kb", 
            "ECU MT22---768KB", 
            "ECU MT60.1-512kb", 
            "ECU MT60.1-768KB"
        ])
        self.cpu_combobox.setCurrentText("ECU MT22.1-256kb")
        cpu_layout.addWidget(cpu_label)
        cpu_layout.addWidget(self.cpu_combobox)
        main_layout.addLayout(cpu_layout)
        
        self.load_original_btn = QPushButton("📂 加载原始数据")
        self.load_original_btn.setStyleSheet("background-color: #0078D7;")
        self.load_original_btn.clicked.connect(self.load_original_file)
        main_layout.addWidget(self.load_original_btn)
        
        self.load_modified_btn = QPushButton("📂 加载修改后数据")
        self.load_modified_btn.setStyleSheet("background-color: #0078D7;")
        self.load_modified_btn.clicked.connect(self.load_modified_file)
        main_layout.addWidget(self.load_modified_btn)
        
        self.calc_save_btn = QPushButton("✅ 计算校验和并保存")
        self.calc_save_btn.setStyleSheet("background-color: #107C10;")
        self.calc_save_btn.clicked.connect(self.calculate_and_save)
        main_layout.addWidget(self.calc_save_btn)
        
        self.status_label = QLabel("状态：等待操作")
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #F59E0B;
                font-weight: bold;
                margin-top: 10px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
    def load_original_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择原始BIN文件", "", "BIN文件 (*.bin);;所有文件 (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    self.original_file_data = f.read()
                self.original_file_path = file_path
                self.status_label.setText(f"状态：原始数据加载成功 - {os.path.basename(file_path)}")
                self.parent().add_operation_log(f"校验和工具：加载原始文件 - {file_path}")
            except Exception as e:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"加载原始文件失败：{str(e)}")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                self.status_label.setText(f"状态：加载原始文件失败 - {str(e)}")
    
    def load_modified_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择修改后BIN文件", "", "BIN文件 (*.bin);;所有文件 (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    self.modified_file_data = f.read()
                self.modified_file_path = file_path
                self.status_label.setText(f"状态：修改后数据加载成功 - {os.path.basename(file_path)}")
                self.parent().add_operation_log(f"校验和工具：加载修改后文件 - {file_path}")
            except Exception as e:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"加载修改后文件失败：{str(e)}")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                self.status_label.setText(f"状态：加载修改后文件失败 - {str(e)}")
    
    def calculate_and_save(self):
        if not self.original_file_data:
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("请先加载原始数据！")
            msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
            msg.exec_()
            self.status_label.setText("状态：请先加载原始数据")
            return
            
        if not self.modified_file_data:
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("请先加载修改后数据！")
            msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
            msg.exec_()
            self.status_label.setText("状态：请先加载修改后数据")
            return
            
        try:
            cpu_model = self.cpu_combobox.currentText()
            checksum_addr = CHECKSUM_ADDRESSES.get(cpu_model, 0)
            
            original_crc32 = binascii.crc32(self.original_file_data) & 0xFFFFFFFF
            original_md5 = hashlib.md5(self.original_file_data).hexdigest().upper()
            modified_crc32 = binascii.crc32(self.modified_file_data) & 0xFFFFFFFF
            modified_md5 = hashlib.md5(self.modified_file_data).hexdigest().upper()
            
            result_info = f"""校验和计算完成！
            
CPU型号：{cpu_model}
原始文件CRC32：{original_crc32:08X}
修改后文件CRC32：{modified_crc32:08X}
原始文件MD5：{original_md5}
修改后文件MD5：{modified_md5}

校验结果：
CRC32是否一致：{"✅ 是" if original_crc32 == modified_crc32 else "❌ 否"}
MD5是否一致：{"✅ 是" if original_md5 == modified_md5 else "❌ 否"}"""
            
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Information)
            msg.setText("计算完成")
            msg.setInformativeText(result_info)
            msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
            msg.exec_()
            self.status_label.setText("状态：校验和计算完成，准备保存文件")
            
            # 生成规范文件名
            computer_name = get_computer_name()
            random_num = generate_random_num()
            default_filename = f"ECUflash_{computer_name}_校验和计算_{random_num}.bin"
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            default_path = os.path.join(desktop_path, default_filename)
            
            save_path, _ = QFileDialog.getSaveFileName(
                self, "保存校验后文件", default_path, "BIN文件 (*.bin);;所有文件 (*.*)"
            )
            
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(self.modified_file_data)
                self.status_label.setText(f"状态：文件保存成功 - {os.path.basename(save_path)}")
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Information)
                msg.setText("保存成功")
                msg.setInformativeText(f"文件已保存到：{save_path}")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                self.parent().add_operation_log(f"校验和工具：计算并保存文件 - {save_path}")
                self.parent().add_operation_log(f"校验和结果：原始CRC32={original_crc32:08X}, 修改后CRC32={modified_crc32:08X}")
                
        except Exception as e:
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Critical)
            msg.setText(f"计算/保存失败：{str(e)}")
            msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
            msg.exec_()
            self.status_label.setText(f"状态：操作失败 - {str(e)}")
            self.parent().add_operation_log(f"校验和工具：操作失败 - {str(e)}")


class InlineSelect(QWidget):
    currentTextChanged = pyqtSignal(str)

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self._items = []
        self._current_text = ""
        self._max_visible_items = 6

        self.button = QPushButton(placeholder or "请选择", self)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.toggle_popup)

        self.list_widget = QListWidget(None)
        self.list_widget.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.button)

        self.setStyleSheet("""
            InlineSelect QPushButton {
                background-color: rgba(8, 26, 71, 0.98);
                border: 1px solid rgba(85, 136, 225, 0.58);
                border-radius: 9px;
                color: #E8F1FF;
                font-size: 14px;
                font-weight: 500;
                text-align: left;
                padding: 7px 12px;
                min-height: 46px;
                max-height: 50px;
            }
            InlineSelect QPushButton:hover {
                border: 1px solid rgba(118, 163, 238, 0.85);
            }
        """)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: rgba(8, 26, 71, 0.98);
                border: 1px solid rgba(85, 136, 225, 0.70);
                border-radius: 9px;
                color: #E8F1FF;
                font-size: 13px;
                outline: none;
                padding: 3px 0;
            }
            QListWidget::item {
                min-height: 28px;
                padding: 4px 10px;
            }
            QListWidget::item:selected {
                background-color: #2f69e8;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: rgba(60, 110, 200, 0.55);
            }
        """)

    def setMaxVisibleItems(self, count):
        self._max_visible_items = max(1, int(count))
        self._refresh_popup_height()

    def setPlaceholderText(self, text):
        if not self._current_text:
            self.button.setText(text or "")

    def addItems(self, items):
        for text in items:
            t = str(text)
            self._items.append(t)
            self.list_widget.addItem(t)
        if not self._current_text and self._items:
            self._current_text = self._items[0]
            self.button.setText(self._current_text)
        self._refresh_popup_height()

    def clear(self):
        self._items = []
        self._current_text = ""
        self.list_widget.clear()
        self.button.setText("")
        self.list_widget.hide()

    def currentText(self):
        return self._current_text

    def setCurrentText(self, text):
        text = str(text)
        if text not in self._items:
            return
        if text == self._current_text:
            return
        self._current_text = text
        self.button.setText(text)
        self.currentTextChanged.emit(text)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.button.setEnabled(enabled)
        self.list_widget.setEnabled(enabled)
        if not enabled:
            self.list_widget.hide()

    def view(self):
        return self.list_widget

    def toggle_popup(self):
        if self.list_widget.isVisible():
            self._hide_popup()
        else:
            self._show_popup()

    def _refresh_popup_height(self):
        if self.list_widget.count() <= 0:
            return
        row_h = max(28, self.list_widget.sizeHintForRow(0))
        visible_count = min(self.list_widget.count(), self._max_visible_items)
        height = visible_count * row_h + 8
        self.list_widget.setFixedHeight(height)

    def _show_popup(self):
        if not self._items:
            return
        self._refresh_popup_height()
        popup_width = max(self.width(), 280)
        self.list_widget.setFixedWidth(popup_width)

        global_pos = self.mapToGlobal(QPoint(0, self.height() + 2))
        self.list_widget.move(global_pos)
        self.list_widget.show()
        self.list_widget.raise_()
        self.list_widget.setFocus()
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _hide_popup(self):
        self.list_widget.hide()
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

    def eventFilter(self, watched, event):
        if self.list_widget.isVisible() and event.type() == QEvent.MouseButtonPress:
            global_pos = event.globalPos()
            popup_rect = self.list_widget.rect()
            popup_top_left = self.list_widget.mapToGlobal(popup_rect.topLeft())
            popup_bottom_right = self.list_widget.mapToGlobal(popup_rect.bottomRight())
            in_popup = QRect(popup_top_left, popup_bottom_right).contains(global_pos)

            btn_rect = self.button.rect()
            btn_top_left = self.button.mapToGlobal(btn_rect.topLeft())
            btn_bottom_right = self.button.mapToGlobal(btn_rect.bottomRight())
            in_button = QRect(btn_top_left, btn_bottom_right).contains(global_pos)

            if not in_popup and not in_button:
                self._hide_popup()

        if self.list_widget.isVisible() and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self._hide_popup()
            return True

        return super().eventFilter(watched, event)

    def _on_item_clicked(self, item):
        text = item.text()
        if text != self._current_text:
            self._current_text = text
            self.button.setText(text)
            self.currentTextChanged.emit(text)
        self._hide_popup()


class ECUFlashWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.file_path = ""
        self.file_data = b""
        self.current_ecu_info = None
        self.current_car_type = ""
        self.current_ecu_name = ""
        self.current_identify_code = ""  # 记录当前识别到的特征码
        self._dragging = False
        self._drag_pos = QPoint()
        
        self.initUI()

    def initUI(self):
        self.setWindowTitle("ECU Hub")
        apply_logo_to_window(self)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setMinimumSize(scaled_px(1200), scaled_px(780))
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            width = min(scaled_px(1722), max(scaled_px(1280), int(available.width() * 0.92)))
            height = min(scaled_px(1100), max(scaled_px(820), int(available.height() * 0.90)))
            self.resize(width, height)
        else:
            self.resize(scaled_px(1722), scaled_px(1100))
        self.setStyleSheet("""
            QMainWindow { 
                background-color: #020817; 
                border: none; 
                font-family: Microsoft YaHei;
            }
            QWidget {
                font-family: Microsoft YaHei;
            }
        """)

        central_widget = QWidget()
        central_widget.setObjectName("WindowCanvas")
        central_widget.setStyleSheet("""
            QWidget#WindowCanvas {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #02050D, stop:0.5 #04173F, stop:1 #02050D);
                border: none;
            }
        """)
        self.setCentralWidget(central_widget)
        outer_layout = QVBoxLayout(central_widget)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(0)

        window_shell = QFrame()
        window_shell.setObjectName("WindowShell")
        window_shell.setStyleSheet("""
            QFrame#WindowShell {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #020814, stop:0.45 #071B48, stop:1 #031033);
                border: 2px solid #00A8FF;
                border-radius: 12px;
            }
        """)
        outer_layout.addWidget(window_shell)

        main_layout = QVBoxLayout(window_shell)
        main_layout.setContentsMargins(20, 12, 20, 12)
        main_layout.setSpacing(16)

        self.title_bar = QWidget()
        self.title_bar.setObjectName("CustomTitleBar")
        self.title_bar.setFixedHeight(36)
        self.title_bar.setStyleSheet("""
            QWidget#CustomTitleBar {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #082055,stop:1 #0B2D72);
                border: 1px solid rgba(84, 142, 238, 0.45);
                border-radius: 8px;
            }
        """)
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(10, 0, 6, 0)
        title_bar_layout.setSpacing(8)

        title_text = QLabel("ECU Hub")
        title_text.setStyleSheet("color:#CFE4FF; font-size:13px; font-weight:bold;")
        title_bar_layout.addWidget(title_text)
        title_bar_layout.addStretch()

        self.min_btn = QPushButton("-")
        self.max_btn = QPushButton("□")
        self.close_btn = QPushButton("×")
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.setFixedSize(38, 26)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: rgba(222, 235, 255, 0.92);
                    border: none;
                    border-radius: 5px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: rgba(116, 157, 225, 0.26);
                }
            """)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(235, 246, 255, 0.95);
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #e74856;
                color: white;
            }
        """)

        self.min_btn.clicked.connect(self.showMinimized)
        self.max_btn.clicked.connect(self.toggle_max_restore)
        self.close_btn.clicked.connect(self.close)

        title_bar_layout.addWidget(self.min_btn)
        title_bar_layout.addWidget(self.max_btn)
        title_bar_layout.addWidget(self.close_btn)

        self.title_bar.mousePressEvent = self._title_mouse_press
        self.title_bar.mouseMoveEvent = self._title_mouse_move
        self.title_bar.mouseReleaseEvent = self._title_mouse_release
        self.title_bar.mouseDoubleClickEvent = self._title_mouse_double_click

        main_layout.addWidget(self.title_bar)

        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(56)
        top_bar.setStyleSheet("""
            QWidget#TopBar {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #081D56,stop:1 #103889);
                border: 1px solid rgba(84, 142, 238, 0.55);
                border-radius: 10px;
            }
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 4, 14, 4)
        top_layout.setSpacing(10)

        logo_label = QLabel()
        logo_label.setFixedSize(scaled_px(32), scaled_px(32))
        logo_pixmap = _get_app_logo_pixmap(max(logo_label.width(), logo_label.height()))
        if logo_pixmap and not logo_pixmap.isNull():
            logo_label.setPixmap(
                logo_pixmap.scaled(
                    logo_label.width(),
                    logo_label.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        else:
            logo_label.hide()

        title_label = QLabel("ECU Hub")
        title_label.setStyleSheet("""
            QLabel {
                font-family: 'Arial Black';
                font-size: 20px;
                font-weight: bold;
                color: #FFFFFF;
            }
        """)

        sub_label = QLabel("ECU数据修复 | 防盗关闭 | 未就绪修复")
        sub_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #80FFFF;
            }
        """)
        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(0)
        title_vbox.setContentsMargins(0, 0, 0, 0)
        title_vbox.addWidget(title_label)
        title_vbox.addWidget(sub_label)

        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(8)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.addWidget(logo_label, 0, Qt.AlignVCenter)
        brand_layout.addLayout(title_vbox)

        resource_download_btn = QPushButton("文件下载")
        learning_btn = QPushButton("学习资料")
        checksum_btn = QPushButton("计算校验和")
        purchase_btn = QPushButton("开通功能")
        log_btn = QPushButton("更新说明")
        logout_btn = QPushButton("退出登录")
        self.logout_btn = logout_btn
        for btn in [resource_download_btn, learning_btn, checksum_btn, purchase_btn, log_btn, logout_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #FF8800,stop:1 #FFAA00);
                    color: #FFFFFF;
                    font-size: 12px;
                    font-weight: bold;
                    border: none;
                    border-radius: 5px;
                    padding: 5px 14px;
                    min-width: 90px;
                    min-height: 28px;
                    max-height: 30px;
                }
                QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #FF9A00,stop:1 #FFBA2A); }
            """)

        resource_download_btn.clicked.connect(self.open_resource_download_dialog)
        learning_btn.clicked.connect(self.open_learning_articles_dialog)
        checksum_btn.clicked.connect(self.open_checksum_dialog)
        purchase_btn.clicked.connect(lambda: self.show_purchase_dialog())

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.addStretch()
        btn_layout.addWidget(resource_download_btn)
        btn_layout.addWidget(learning_btn)
        btn_layout.addWidget(checksum_btn)
        btn_layout.addWidget(purchase_btn)
        btn_layout.addWidget(log_btn)

        top_layout.addLayout(brand_layout)
        top_layout.addLayout(btn_layout)
        main_layout.addWidget(top_bar)

        # Allow dragging from the whole header area (except interactive buttons).
        for drag_widget in (central_widget, window_shell, top_bar, title_label, sub_label, logo_label):
            drag_widget.mousePressEvent = self._title_mouse_press
            drag_widget.mouseMoveEvent = self._title_mouse_move
            drag_widget.mouseReleaseEvent = self._title_mouse_release
            drag_widget.mouseDoubleClickEvent = self._title_mouse_double_click

        main_content = QWidget()
        main_content.setStyleSheet("background: transparent; border: none;")
        main_content_layout = QHBoxLayout(main_content)
        main_content_layout.setContentsMargins(0, 2, 0, 0)
        main_content_layout.setSpacing(14)

        left_panel = QWidget()
        left_panel.setObjectName("LeftPanel")
        left_panel.setMaximumWidth(480)
        left_panel.setMinimumWidth(360)
        left_panel.setStyleSheet("""
            QWidget#LeftPanel {
                background-color: rgba(8, 24, 64, 0.94);
                border: 1px solid rgba(76, 133, 231, 0.52);
                border-radius: 12px;
                padding: 10px;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(8, 6, 8, 8)

        file_title = QLabel("文件操作")
        file_title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #00CCFF;
                letter-spacing: 0.5px;
                padding: 2px 0 4px 2px;
            }
        """)
        left_layout.addWidget(file_title)

        self.file_path_edit = QTextEdit()
        self.file_path_edit.setText("未打开任何文件")
        self.file_path_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(8, 26, 71, 0.98);
                border: 1px solid rgba(85, 136, 225, 0.56);
                border-radius: 9px;
                color: #E8F1FF;
                font-size: 13px;
                line-height: 1.4;
                padding: 10px 12px;
                min-height: 76px;
                max-height: 96px;
            }
        """)
        self.file_path_edit.setReadOnly(True)
        left_layout.addWidget(self.file_path_edit)

        log_title = QLabel("操作日志")
        log_title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #00CCFF;
                letter-spacing: 0.5px;
                margin-top: 2px;
                padding: 2px 0 4px 2px;
            }
        """)
        left_layout.addWidget(log_title)

        self.operation_log_area = QTextEdit()
        self.operation_log_area.setText("")
        self.operation_log_area.setStyleSheet("""
            QTextEdit {
                background-color: rgba(8, 22, 60, 0.98);
                border: 1px solid rgba(83, 134, 223, 0.58);
                border-radius: 9px;
                color: #DDEBFF;
                font-size: 13px;
                line-height: 1.45;
                padding: 10px 12px;
                min-height: 300px;
                max-height: 440px;
            }
        """)
        self.operation_log_area.setReadOnly(True)
        self.operation_log_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout.addWidget(self.operation_log_area)

        self.file_size_label = QLabel("大小：0 字节")
        self.file_size_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #8AD7B7;
                margin-top: 10px;
                padding-left: 2px;
            }
        """)
        left_layout.addWidget(self.file_size_label)

        self.open_btn = QPushButton("打开BIN文件")
        self.save_btn = QPushButton("保存修改文件")
        self.open_btn.clicked.connect(self.open_bin_file)
        self.save_btn.clicked.connect(self.save_bin_file)
        self.save_btn.setEnabled(False)
        
        for btn in [self.open_btn, self.save_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2A65EE,stop:1 #3F8CFF);
                    color: #FFFFFF;
                    font-size: 15px;
                    font-weight: bold;
                    border: 1px solid rgba(157, 199, 255, 0.38);
                    border-radius: 10px;
                    padding: 11px 0;
                    min-height: 50px;
                    max-height: 54px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3A74F5,stop:1 #51A0FF);
                }
                QPushButton:pressed {
                    background: #2F62D6;
                }
                QPushButton:disabled {
                    background: rgba(49, 62, 86, 0.88);
                    color: #7A869E;
                    border: 1px solid rgba(122, 134, 158, 0.35);
                }
            """)
        left_layout.addStretch()
        left_layout.addWidget(self.open_btn)
        left_layout.addWidget(self.save_btn)

        right_panel = QWidget()
        right_panel.setObjectName("RightPanel")
        right_panel.setStyleSheet("""
            QWidget#RightPanel {
                background-color: rgba(8, 24, 64, 0.94);
                border: 1px solid rgba(76, 133, 231, 0.52);
                border-radius: 12px;
                padding: 14px;
            }
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(10)
        right_layout.setContentsMargins(10, 8, 10, 10)

        search_title = QLabel("搜索ECU型号")
        search_title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #00CCFF;
                padding: 2px 0 4px 2px;
            }
        """)
        right_layout.addWidget(search_title)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        search_label = QLabel("ECU型号：")
        search_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #80FFFF;
                font-weight: bold;
                min-width: 84px;
            }
        """)
        search_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.search_ecu_edit = QLineEdit()
        self.search_ecu_edit.setText("ME7.8.8")
        self.search_ecu_edit.setStyleSheet("""
            QLineEdit {
                background-color: rgba(8, 26, 71, 0.98);
                border: 1px solid rgba(85, 136, 225, 0.58);
                border-radius: 9px;
                color: #E8F1FF;
                font-size: 14px;
                padding: 8px 12px;
                min-height: 46px;
                max-height: 50px;
            }
        """)
        self.search_ecu_edit.returnPressed.connect(self.search_ecu_by_name)
        search_row.addWidget(search_label)
        search_row.addWidget(self.search_ecu_edit)
        right_layout.addLayout(search_row)

        car_layout = QHBoxLayout()
        car_layout.setSpacing(10)
        car_label = QLabel("车系：")
        car_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #80FFFF;
                font-weight: bold;
                min-width: 84px;
            }
        """)
        car_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.car_combobox = InlineSelect("请选择车系")
        self.car_combobox.addItems(ECU_DATABASE.keys())
        self.car_combobox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.car_combobox.setMaxVisibleItems(8)
        self.car_combobox.currentTextChanged.connect(self.update_ecu_combobox)
        self.car_combobox.view().setMinimumWidth(0)
        car_layout.addWidget(car_label)
        car_layout.addWidget(self.car_combobox)
        right_layout.addLayout(car_layout)

        ecu_layout = QHBoxLayout()
        ecu_layout.setSpacing(10)
        ecu_label = QLabel("ECU型号：")
        ecu_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #80FFFF;
                font-weight: bold;
                min-width: 84px;
            }
        """)
        ecu_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.ecu_combobox = InlineSelect("请选择ECU型号")
        self.ecu_combobox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.ecu_combobox.setMaxVisibleItems(8)
        self.ecu_combobox.view().setMinimumWidth(0)
        ecu_layout.addWidget(ecu_label)
        ecu_layout.addWidget(self.ecu_combobox)
        right_layout.addLayout(ecu_layout)

        self.update_ecu_combobox(self.car_combobox.currentText())

        self.identify_btn = QPushButton("识别ECU")
        self.identify_btn.clicked.connect(self.identify_ecu)
        self.identify_btn.setEnabled(False)
        self.identify_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2A65EE,stop:1 #3F8CFF);
                color: #FFFFFF;
                font-size: 16px;
                font-weight: bold;
                border: 1px solid rgba(157, 199, 255, 0.38);
                border-radius: 10px;
                padding: 10px 0;
                min-height: 50px;
                max-height: 54px;
                margin-top: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3A74F5,stop:1 #51A0FF);
            }
            QPushButton:disabled {
                background: rgba(49, 62, 86, 0.88);
                color: #7A869E;
                border: 1px solid rgba(122, 134, 158, 0.35);
            }
        """)
        right_layout.addWidget(self.identify_btn)

        self.result_label = QLabel("识别结果：等待识别")
        self.result_label.setStyleSheet("""
            QLabel {
                font-size: 15px;
                font-weight: bold;
                color: #7EE3B9;
                margin: 8px 2px 6px 2px;
            }
        """)
        right_layout.addWidget(self.result_label)

        func_title = QLabel("功能操作")
        func_title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #00CCFF;
                padding: 2px 0 4px 2px;
            }
        """)
        right_layout.addWidget(func_title)

        self.func_tip_label = QLabel("")
        self.func_tip_label.hide()

        self.func_scroll = QScrollArea()
        self.func_scroll.setWidgetResizable(True)
        self.func_scroll.setFrameShape(QFrame.NoFrame)
        self.func_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.func_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.func_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.func_scroll.setFixedHeight(scaled_px(420))
        self.func_scroll.setStyleSheet("""
            QScrollArea {
                background-color: rgba(8, 22, 52, 0.88);
                border: 1px solid rgba(73, 112, 196, 0.34);
                border-radius: 16px;
            }
            QScrollBar:vertical {
                background: rgba(6, 23, 78, 0.65);
                width: 10px;
                margin: 8px 4px 8px 0;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: rgba(96, 165, 250, 0.72);
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self.func_content = QWidget()
        self.func_content.setStyleSheet("background: transparent; border: none;")
        self.func_content_layout = QVBoxLayout(self.func_content)
        self.func_content_layout.setContentsMargins(12, 16, 12, 16)
        self.func_content_layout.setSpacing(scaled_px(20))
        self.func_content_layout.setAlignment(Qt.AlignTop)
        self.func_scroll.setWidget(self.func_content)
        right_layout.addWidget(self.func_scroll)
        self.show_default_step3_button()

        main_content_layout.addWidget(left_panel)
        main_content_layout.addWidget(right_panel)
        main_content_layout.setStretch(0, 4)
        main_content_layout.setStretch(1, 9)
        main_layout.addWidget(main_content)

        auth_label = QLabel("✓ 登录用户: 未登录 | 会话: 未建立")
        auth_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #00FF99;
                text-shadow: 0 0 6px #00FF99; 
                margin-top: 8px;
            }
        """)
        main_layout.addWidget(auth_label, alignment=Qt.AlignRight)

    def search_ecu_by_name(self):
        keyword = self.search_ecu_edit.text().strip()
        if not keyword:
            return

        found_car = None
        found_ecu = None

        for car_type, ecu_list in ECU_DATABASE.items():
            for ecu_name in ecu_list.keys():
                if keyword in ecu_name:
                    found_car = car_type
                    found_ecu = ecu_name
                    break
            if found_car:
                break

        if not found_car or not found_ecu:
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("输入错误！")
            msg.setStyleSheet("QLabel{color:black; font-size:14px;} QPushButton{background:#0078D7; color:white;}")
            msg.exec_()
            return

        self.car_combobox.setCurrentText(found_car)
        self.update_ecu_combobox(found_car)
        self.ecu_combobox.setCurrentText(found_ecu)
        self.add_operation_log(f"搜索定位：{found_car} → {found_ecu}")

    def open_checksum_dialog(self):
        dialog = ChecksumDialog(self)
        dialog.exec_()

    def _load_remote_pixmap(self, url):
        resolved = _resolve_resource_url(url)
        if not resolved:
            return None
        try:
            request = urllib.request.Request(resolved, headers={"Accept": "image/*"})
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                return pixmap
        except Exception:
            return None
        return None

    def _resource_preview_url(self, item):
        preview_url = (item.get("image_url") or item.get("preview_image_url") or "").strip()
        if preview_url:
            return preview_url
        link = (item.get("url") or item.get("file_url") or "").strip().lower()
        file_name = (item.get("file_name") or "").strip().lower()
        image_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
        if any(link.endswith(ext) for ext in image_exts) or any(file_name.endswith(ext) for ext in image_exts):
            return item.get("url") or item.get("file_url") or ""
        return ""

    def _download_resource_file(self, item):
        link = (item.get("url") or item.get("file_url") or "").strip()
        if not link:
            show_message(self, QMessageBox.Warning, "提示", "当前资源没有可下载文件")
            return False
        resolved = _resolve_resource_url(link)
        if _open_browser_download(resolved):
            self.add_operation_log(f"浏览器下载已打开：{resolved}")
            return True
        show_message(self, QMessageBox.Critical, "下载失败", "无法拉起浏览器下载")
        return False

    def _view_resource_file(self, item):
        link = (self._resource_preview_url(item) or item.get("url") or item.get("file_url") or "").strip()
        if not link:
            show_message(self, QMessageBox.Warning, "提示", "当前资源没有可查看内容")
            return False
        resolved = _resolve_resource_url(link)
        if _open_url(resolved):
            self.add_operation_log(f"资源查看已打开：{resolved}")
            return True
        show_message(self, QMessageBox.Critical, "查看失败", "无法打开资源内容")
        return False

    def _show_resource_detail_dialog(self, item, title_text="资源详情"):
        dialog = QDialog(self)
        dialog.setWindowTitle(title_text)
        apply_logo_to_window(dialog)
        dialog.resize(820, 640)
        dialog.setStyleSheet(
            "QDialog{background:#060B16;} QLabel{color:#E5E7EB;} "
            "QPushButton{background:#2563EB;color:white;border:none;border-radius:8px;padding:9px 18px;font-size:14px;font-weight:bold;} "
            "QFrame{background:rgba(8,24,64,0.94);border:1px solid rgba(76,133,231,0.40);border-radius:12px;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        name = item.get("name") or item.get("title") or "未命名资源"
        desc = item.get("description") or item.get("remark") or "暂无说明"
        file_name = item.get("file_name") or "未提供文件名"
        keywords = item.get("keywords") or "-"

        title_label = QLabel(name)
        title_label.setStyleSheet("font-size:20px;font-weight:bold;color:#93C5FD;")
        layout.addWidget(title_label)

        body = QHBoxLayout()
        body.setSpacing(16)

        preview_frame = QFrame()
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(10)
        preview_label = QLabel("正在加载预览")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_label.setMinimumSize(300, 420)
        preview_label.setWordWrap(True)
        preview_label.setStyleSheet("background:rgba(3,10,28,0.96);border-radius:10px;color:#94A3B8;font-size:13px;")
        pixmap = self._load_remote_pixmap(self._resource_preview_url(item))
        if pixmap and not pixmap.isNull():
            preview_label.setPixmap(pixmap.scaled(320, 460, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            preview_label.setText("当前资源未提供图片预览\n可查看说明并下载到本地使用")
        preview_layout.addWidget(preview_label)
        body.addWidget(preview_frame, 4)

        info_frame = QFrame()
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.setSpacing(12)
        for text_value in [
            f"文件名：{file_name}",
            f"适配关键词：{keywords}",
            f"说明：{desc}",
        ]:
            label = QLabel(text_value)
            label.setWordWrap(True)
            label.setStyleSheet("font-size:14px;line-height:1.7;color:#D1D5DB;")
            info_layout.addWidget(label)
        info_layout.addStretch()
        body.addWidget(info_frame, 5)

        layout.addLayout(body)

        button_row = QHBoxLayout()
        button_row.addStretch()
        download_btn = QPushButton(item.get("button_text") or "下载到本地")
        download_btn.clicked.connect(lambda: self._download_resource_file(item))
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        button_row.addWidget(download_btn)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)
        dialog.exec_()

    def _show_wiring_guide_detail_dialog(self, item):
        self._view_resource_file(item)

    def _open_wiring_guide_list_dialog(self, items):
        dialog = QDialog(self)
        dialog.setWindowTitle("接线图查询")
        apply_logo_to_window(dialog)
        dialog.resize(880, 620)
        dialog.setStyleSheet(
            "QDialog{background:#060B16;} QLabel{color:#E5E7EB;} "
            "QPushButton{background:#2563EB;color:white;border:none;border-radius:8px;padding:10px 18px;font-size:14px;font-weight:bold;} "
            "QLineEdit{background:rgba(3,10,28,0.96);color:#E5E7EB;border:1px solid rgba(96,165,250,0.35);border-radius:8px;padding:12px 14px;font-size:18px;} "
            "QListWidget{background:rgba(8,24,64,0.94);color:#E5E7EB;border:1px solid rgba(76,133,231,0.40);border-radius:12px;font-size:15px;} "
            "QListWidget::item{padding:12px 14px;} QListWidget::item:selected{background:#1D4ED8;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("接线图查询")
        title.setStyleSheet("font-size:24px;font-weight:bold;color:#93C5FD;")
        layout.addWidget(title)

        search_edit = QLineEdit(dialog)
        search_edit.setPlaceholderText("输入接线图关键词")
        layout.addWidget(search_edit)

        result_label = QLabel("请输入关键词后搜索")
        result_label.setStyleSheet("font-size:14px;color:#60A5FA;")
        layout.addWidget(result_label)

        list_widget = QListWidget(dialog)
        layout.addWidget(list_widget)

        selected_items = []

        def render_items():
            keyword = search_edit.text().strip()
            result_items = _filter_resource_items(items, keyword)
            selected_items[:] = result_items
            list_widget.clear()
            if keyword:
                result_label.setText(f"搜索到 {len(result_items)} 条接线图")
            else:
                result_label.setText("请输入关键词后搜索")
            for item in result_items:
                list_widget.addItem(f"{item.get('name') or '-'}")

        def view_selected():
            row = list_widget.currentRow()
            if row < 0 or row >= len(selected_items):
                show_message(dialog, QMessageBox.Warning, "提示", "请先选择接线图")
                return
            self._view_resource_file(selected_items[row])

        search_edit.textChanged.connect(lambda _=None: render_items())
        list_widget.itemDoubleClicked.connect(lambda _: view_selected())
        render_items()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        view_btn = QPushButton("查看")
        view_btn.clicked.connect(view_selected)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(view_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.exec_()

    def _open_resource_list_dialog(self, title_text, items, search_placeholder, detail_title):
        dialog = QDialog(self)
        dialog.setWindowTitle(title_text)
        apply_logo_to_window(dialog)
        dialog.resize(820, 560)
        dialog.setStyleSheet(
            "QDialog{background:#060B16;} QLabel{color:#E5E7EB;} "
            "QPushButton{background:#2563EB;color:white;border:none;border-radius:8px;padding:10px 18px;font-size:14px;font-weight:bold;} "
            "QLineEdit{background:rgba(3,10,28,0.96);color:#E5E7EB;border:1px solid rgba(96,165,250,0.35);border-radius:8px;padding:12px 14px;font-size:18px;} "
            "QListWidget{background:rgba(8,24,64,0.94);color:#E5E7EB;border:1px solid rgba(76,133,231,0.40);border-radius:12px;font-size:15px;} "
            "QListWidget::item{padding:12px 14px;} QListWidget::item:selected{background:#1D4ED8;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(title_text)
        title.setStyleSheet("font-size:24px;font-weight:bold;color:#93C5FD;")
        layout.addWidget(title)

        search_edit = QLineEdit(dialog)
        search_edit.setPlaceholderText(search_placeholder)
        layout.addWidget(search_edit)

        result_label = QLabel("请输入关键词后搜索")
        result_label.setStyleSheet("font-size:14px;color:#60A5FA;")
        layout.addWidget(result_label)

        list_widget = QListWidget(dialog)
        layout.addWidget(list_widget)

        selected_items = []

        def render_items():
            keyword = search_edit.text().strip()
            result_items = _filter_resource_items(items, keyword)
            selected_items[:] = result_items
            list_widget.clear()
            if keyword:
                result_label.setText(f"当前搜索到 {len(result_items)} 条结果")
            else:
                result_label.setText("请输入关键词后搜索")
            for item in result_items:
                file_name = item.get('file_name') or ''
                file_name = str(file_name).strip()
                if file_name.lower().endswith('.bin'):
                    list_widget.addItem(f"{item.get('name') or item.get('title') or '-'} | 下载bin文件")
                else:
                    list_widget.addItem(f"{item.get('name') or item.get('title') or '-'} | 文件: {file_name or '-'}")

        def download_selected():
            row = list_widget.currentRow()
            if row < 0 or row >= len(selected_items):
                show_message(dialog, QMessageBox.Warning, "提示", "请先选择文件")
                return
            self._download_resource_file(selected_items[row])

        search_edit.textChanged.connect(lambda _=None: render_items())
        list_widget.itemDoubleClicked.connect(lambda _: download_selected())
        render_items()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        download_btn = QPushButton("立即下载")
        download_btn.clicked.connect(download_selected)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(download_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.exec_()

    def open_resource_download_dialog(self):
        cfg = getattr(self, "purchase_config", {}) or {}
        downloads = _parse_config_list(cfg.get("virtual_downloads_json"))
        downloads = [item for item in downloads if item.get("is_enabled", 1)]
        self._open_resource_list_dialog("文件下载", downloads, "输入文件关键词，例如 ME7.8.8、EA211、朗逸", "文件详情")

    def open_learning_articles_dialog(self):
        try:
            items = _api_request_json("/learning-articles", token=self.license_data.get("token"))
        except Exception as exc:
            show_message(self, QMessageBox.Warning, "提示", f"学习资料加载失败：{exc}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("学习资料")
        apply_logo_to_window(dialog)
        dialog.resize(960, 720)
        dialog.setStyleSheet(
            "QDialog{background:#060B16;} QLabel{color:#E5E7EB;} "
            "QPushButton{background:#2563EB;color:white;border:none;border-radius:8px;padding:10px 18px;font-size:14px;font-weight:bold;} "
            "QLineEdit{background:rgba(3,10,28,0.96);color:#E5E7EB;border:1px solid rgba(96,165,250,0.35);border-radius:8px;padding:12px 14px;font-size:18px;} "
            "QListWidget{background:rgba(8,24,64,0.94);color:#E5E7EB;border:1px solid rgba(76,133,231,0.40);border-radius:12px;font-size:15px;} "
            "QListWidget::item{padding:10px 12px;} QListWidget::item:selected{background:#1D4ED8;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("学习资料")
        title.setStyleSheet("font-size:24px;font-weight:bold;color:#93C5FD;")
        layout.addWidget(title)

        search_edit = QLineEdit(dialog)
        search_edit.setPlaceholderText("输入学习资料标题关键词")
        layout.addWidget(search_edit)

        result_label = QLabel("请输入关键词后搜索")
        result_label.setStyleSheet("font-size:14px;color:#60A5FA;")
        layout.addWidget(result_label)

        list_widget = QListWidget(dialog)
        list_widget.setIconSize(QSize(scaled_px(96), scaled_px(72)))
        layout.addWidget(list_widget)

        selected_items = []

        def render_items():
            keyword = search_edit.text().strip().lower()
            result_items = []
            for item in items or []:
                title_text = str(item.get("title") or "").lower()
                summary_text = str(item.get("summary") or "").lower()
                if keyword and keyword not in title_text and keyword not in summary_text:
                    continue
                result_items.append(item)

            selected_items[:] = result_items
            list_widget.clear()
            if keyword:
                result_label.setText(f"当前搜索到 {len(result_items)} 条学习资料")
            else:
                result_label.setText("请输入关键词后搜索")

            for item in result_items:
                title_text = item.get("title") or "未命名学习资料"
                summary_text = item.get("summary") or "暂无摘要"
                summary_text = re.sub(r"\s+", " ", str(summary_text)).strip()
                if len(summary_text) > 36:
                    summary_text = summary_text[:36] + "..."
                list_item = QListWidgetItem(f"{title_text}\n{summary_text}")
                cover_pixmap = self._load_remote_pixmap(item.get("cover_image_url"))
                if cover_pixmap and not cover_pixmap.isNull():
                    list_item.setIcon(QIcon(cover_pixmap.scaled(96, 72, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)))
                list_widget.addItem(list_item)

        def open_selected_article():
            row = list_widget.currentRow()
            if row < 0 or row >= len(selected_items):
                show_message(dialog, QMessageBox.Warning, "提示", "请先选择学习资料")
                return
            self._show_learning_article_detail_dialog(selected_items[row])

        search_edit.textChanged.connect(lambda _=None: render_items())
        list_widget.itemDoubleClicked.connect(lambda _: open_selected_article())
        render_items()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        detail_btn = QPushButton("查看资料")
        detail_btn.clicked.connect(open_selected_article)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(detail_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dialog.exec_()

    def _show_learning_article_detail_dialog(self, item):
        dialog = QDialog(self)
        dialog.setWindowTitle(item.get("title") or "学习资料")
        apply_logo_to_window(dialog)
        dialog.resize(980, 760)
        dialog.setStyleSheet(
            "QDialog{background:#060B16;} QLabel{color:#E5E7EB;} "
            "QPushButton{background:#2563EB;color:white;border:none;border-radius:8px;padding:10px 18px;font-size:14px;font-weight:bold;} "
            "QFrame{background:rgba(8,24,64,0.94);border:1px solid rgba(76,133,231,0.40);border-radius:14px;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title_text = item.get("title") or "未命名学习资料"
        title_label = QLabel(title_text)
        title_label.setStyleSheet("font-size:22px;font-weight:bold;color:#93C5FD;")
        layout.addWidget(title_label)

        subtitle = QLabel(item.get("summary") or "暂无摘要")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size:13px;color:#94A3B8;")
        layout.addWidget(subtitle)

        content_frame = QFrame()
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        info_title = QLabel("图文内容")
        info_title.setStyleSheet("font-size:16px;font-weight:bold;color:#CFE4FF;")
        content_layout.addWidget(info_title)

        article_html = _normalize_learning_article_html(item.get('content_html') or '')

        content_view = QTextBrowser()
        content_view.setOpenExternalLinks(True)
        content_view.setOpenLinks(True)
        content_view.setStyleSheet("background:rgba(3,10,28,0.96);color:#E5E7EB;border:none;font-size:14px;padding:8px;")
        content_view.document().setDefaultStyleSheet(
            "html,body{background:transparent;color:#E5E7EB;}"
            "p,div,span,li,td,th{background:transparent;color:#E5E7EB;line-height:1.9;}"
            "h1,h2,h3,h4,h5,h6{background:transparent;color:#CFE4FF;margin:18px 0 10px 0;}"
            "a{color:#7DD3FC;}"
            "table{width:100%;background:transparent;border-collapse:collapse;color:#E5E7EB;margin:12px 0;}"
            "td,th{border:1px solid rgba(148,163,184,0.35);padding:8px;}"
            "img{display:block;background:transparent;border-radius:12px;max-width:260px;max-height:360px;width:auto;height:auto;margin:10px auto;}"
            "ul,ol{margin:8px 0 8px 20px;}"
            "blockquote{border-left:3px solid rgba(125,211,252,0.55);padding-left:12px;color:#CBD5E1;}"
        )
        content_view.setHtml(
            "<html><body style='background:transparent;color:#E5E7EB;'>"
            f"<div style='color:#E5E7EB;font-size:14px;line-height:1.9;'>{article_html or '<p>暂无图文内容</p>'}</div>"
            "</body></html>"
        )
        content_layout.addWidget(content_view, 1)

        layout.addWidget(content_frame, 1)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)
        dialog.exec_()

    def open_wiring_guide_dialog(self):
        cfg = getattr(self, "purchase_config", {}) or {}
        wiring_guides = _parse_config_list(cfg.get("wiring_guides_json"))
        wiring_guides = [item for item in wiring_guides if item.get("is_enabled", 1)]
        self._open_wiring_guide_list_dialog(wiring_guides)

    def open_virtual_download_dialog(self):
        self.open_resource_download_dialog()

    def _ecu_family_key(self, ecu_name):
        if not ecu_name:
            return ""
        name = ecu_name.replace("（", "(").replace("）", ")")
        name = re.sub(r"\(.*?\)", "", name)
        name = name.replace(" ", "").strip().upper()
        return name

    def _expand_same_family_candidates(self, selected_match):
        if not selected_match:
            return []
        car_type = selected_match["car_type"]
        ecu_name = selected_match["ecu_name"]
        identify_code = selected_match["identify_code"]
        family_key = self._ecu_family_key(ecu_name)
        if not family_key or car_type not in ECU_DATABASE:
            return [selected_match]

        expanded = []
        for candidate_name, candidate_info in ECU_DATABASE[car_type].items():
            if self._ecu_family_key(candidate_name) == family_key:
                expanded.append({
                    "car_type": car_type,
                    "ecu_name": candidate_name,
                    "ecu_info": candidate_info,
                    "identify_code": identify_code,
                })
        return expanded or [selected_match]

    def select_ecu_candidate(self, matches):
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        dialog = QDialog(self)
        dialog.setWindowTitle("选择ECU型号")
        apply_logo_to_window(dialog)
        dialog.resize(640, 420)
        dialog.setStyleSheet("""
            QDialog{background:#0B1F55;}
            QLabel{color:#CFE4FF; font-size:15px; font-weight:bold;}
            QListWidget{
                background:#0A245F;
                color:#E8F1FF;
                border:1px solid rgba(90, 139, 226, 0.72);
                border-radius:8px;
                font-size:14px;
            }
            QListWidget::item{padding:8px 10px; min-height:26px;}
            QListWidget::item:selected{background:#2F69E8; color:white;}
            QPushButton{
                color:white;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2A65EE,stop:1 #3F8CFF);
                border:1px solid rgba(157, 199, 255, 0.38);
                border-radius:8px;
                min-width:90px;
                padding:6px 10px;
                font-weight:bold;
            }
            QPushButton:hover{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3A74F5,stop:1 #51A0FF);
            }
        """)

        layout = QVBoxLayout(dialog)
        tip = QLabel("识别到多个匹配 ECU，请选择具体型号：")
        layout.addWidget(tip)

        list_widget = QListWidget(dialog)
        for match in matches:
            list_widget.addItem(f"{match['car_type']}  {match['ecu_name']}")
        list_widget.setCurrentRow(0)
        list_widget.itemDoubleClicked.connect(lambda _: dialog.accept())
        layout.addWidget(list_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        ok_btn = QPushButton("确定")
        cancel_btn.clicked.connect(dialog.reject)
        ok_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        if dialog.exec_() != QDialog.Accepted:
            return None

        row = list_widget.currentRow()
        if row < 0 or row >= len(matches):
            return None
        return matches[row]

    def toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setText("□")
        else:
            self.showMaximized()
            self.max_btn.setText("❐")

    def _title_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def _title_mouse_move(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            if self.isMaximized():
                self.showNormal()
                self.max_btn.setText("□")
                self._drag_pos = QPoint(self.width() // 2, 18)
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def _title_mouse_release(self, event):
        self._dragging = False
        event.accept()

    def _title_mouse_double_click(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_max_restore()
            event.accept()

    def add_operation_log(self, log_content):
        if not log_content:
            return
            
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_log = self.operation_log_area.toPlainText()
        new_log = f"{current_log}\n[{timestamp}] {log_content}" if current_log else f"[{timestamp}] {log_content}"
        self.operation_log_area.setText(new_log)
        self.operation_log_area.verticalScrollBar().setValue(
            self.operation_log_area.verticalScrollBar().maximum()
        )

    def _debug_print_dataset_and_matches(self):
        try:
            car_series_count = len(ECU_DATABASE) if isinstance(ECU_DATABASE, dict) else 0
            ecu_model_count = (
                sum(len(v) for v in ECU_DATABASE.values())
                if isinstance(ECU_DATABASE, dict)
                else 0
            )
            print(
                f"[CLIENT] DATASET SUMMARY car_series={car_series_count}, "
                f"ecu_models={ecu_model_count}"
            )

            if not isinstance(ECU_DATABASE, dict):
                print("[CLIENT] ECU_DATABASE is not a dict, skip match debug.")
                return
            if not self.file_data:
                print("[CLIENT] BIN is empty, skip match debug.")
                return

            matches = []
            for car_type, ecu_list in ECU_DATABASE.items():
                for ecu_name, ecu_info in ecu_list.items():
                    identify_list = ecu_info.get("identify", [])
                    for identify_item in identify_list:
                        addr = int(identify_item.get("addr", 0))
                        length = int(identify_item.get("length", 0))
                        expected_hex = str(identify_item.get("hex_value", "")).upper()
                        if addr < 0 or length <= 0 or (addr + length) > len(self.file_data):
                            continue
                        read_hex = (
                            binascii.hexlify(self.file_data[addr:addr + length])
                            .decode("utf-8")
                            .upper()
                        )
                        if read_hex == expected_hex:
                            matches.append(
                                {
                                    "car_type": car_type,
                                    "ecu_name": ecu_name,
                                    "addr": addr,
                                    "length": length,
                                    "hex": read_hex,
                                }
                            )
                            break

            print(f"[CLIENT] BIN MATCH COUNT {len(matches)}")
            for item in matches[:20]:
                print(
                    "[CLIENT] MATCH "
                    f"{item['car_type']} / {item['ecu_name']} "
                    f"addr=0x{item['addr']:X} len={item['length']} hex={item['hex']}"
                )
        except Exception as e:
            print(f"[CLIENT] DEBUG ERROR {e}")

    def open_bin_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开BIN文件", "", "BIN文件 (*.bin);;所有文件 (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    self.file_data = f.read()
                self.file_path = file_path
                
                self.file_path_edit.setText(file_path)
                file_size = len(self.file_data)
                self.file_size_label.setText(f"大小：{file_size} 字节 ({file_size/1024:.2f} KB)")
                self.identify_btn.setEnabled(True)
                self.save_btn.setEnabled(False)
                self._debug_print_dataset_and_matches()
                
                self.add_operation_log(f"成功打开文件：{file_path}")
                self.add_operation_log(f"文件大小：{file_size} 字节 ({file_size/1024:.2f} KB)")
                
                self.result_label.setText("识别结果：等待识别")
                self.current_ecu_info = None
                self.current_car_type = ""
                self.current_ecu_name = ""
                self.current_identify_code = ""
                self.clear_function_buttons()
                self.show_default_step3_button()
                self.func_tip_label.show()
                
            except Exception as e:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"打开文件失败：{str(e)}")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                self.add_operation_log(f"打开文件失败：{str(e)}")

    def save_bin_file(self):
        if not self.file_data:
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("请先打开文件")
            msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
            msg.exec_()
            return
        
        # 生成规范文件名
        computer_name = get_computer_name()
        random_num = generate_random_num()
        operation_type = "ECU修改"
        if self.current_ecu_name:
            operation_type = f"{self.current_ecu_name}_修复"
            
        default_filename = f"ECUflash_{computer_name}_{operation_type}_{random_num}.bin"
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        default_path = os.path.join(desktop_path, default_filename)
        
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存文件", default_path, "BIN文件 (*.bin);;所有文件 (*.*)"
        )
        if save_path:
            try:
                with open(save_path, 'wb') as f:
                    f.write(self.file_data)
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Information)
                msg.setText("文件保存成功")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                self.add_operation_log(f"保存文件成功：{save_path}")
                self.save_btn.setEnabled(False)
            except Exception as e:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"保存文件失败：{str(e)}")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                self.add_operation_log(f"保存文件失败：{str(e)}")

    def update_ecu_combobox(self, car_type):
        self.ecu_combobox.clear()
        if car_type in ECU_DATABASE:
            self.ecu_combobox.addItems(ECU_DATABASE[car_type].keys())

    def identify_ecu(self):
        try:
            if not self.file_data:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setText("请先打开BIN文件")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                return
                
            if len(self.file_data) == 0:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setText("暂不支持该ECU的数据 请联系售后")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                self.result_label.setText("识别结果：识别失败")
                self.add_operation_log("ECU识别失败：文件为空")
                self.clear_function_buttons()
                self.show_default_step3_button()
                self.func_tip_label.show()
                return
                
            matches = []
            seen = set()
            
            # 遍历所有ECU，匹配特征
            for car_type, ecu_list in ECU_DATABASE.items():
                for ecu_name, ecu_info in ecu_list.items():
                    identify_list = ecu_info.get("identify", [])
                    if not identify_list:
                        continue
                    
                    for identify_item in identify_list:
                        addr = identify_item.get("addr", 0)
                        length = identify_item.get("length", 0)
                        expected_hex = identify_item.get("hex_value", "")
                        
                        if addr < 0 or length <= 0 or (addr + length) > len(self.file_data):
                            continue
                        
                        read_data = self.file_data[addr:addr+length]
                        read_hex = binascii.hexlify(read_data).decode('utf-8').upper()
                        
                        if read_hex == expected_hex.upper():
                            key = (car_type, ecu_name, read_hex)
                            if key not in seen:
                                seen.add(key)
                                matches.append({
                                    "car_type": car_type,
                                    "ecu_name": ecu_name,
                                    "ecu_info": ecu_info,
                                    "identify_code": read_hex,
                                })
                            break
            
            if not matches:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setText("暂不支持该ECU的数据 请联系售后")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                self.result_label.setText("识别结果：识别失败")
                self.add_operation_log("ECU识别失败：暂不支持该ECU数据")
                self.clear_function_buttons()
                self.show_default_step3_button()
                self.func_tip_label.show()
                return

            selected_match = self.select_ecu_candidate(matches)
            if selected_match and len(matches) == 1:
                family_candidates = self._expand_same_family_candidates(selected_match)
                if len(family_candidates) > 1:
                    selected_match = self.select_ecu_candidate(family_candidates)
            if not selected_match:
                self.add_operation_log("ECU识别取消：用户未选择具体型号")
                return

            match_car_type = selected_match["car_type"]
            match_ecu_name = selected_match["ecu_name"]
            match_ecu_info = selected_match["ecu_info"]
            match_identify_code = selected_match["identify_code"]
            
            # 识别成功
            self.current_ecu_info = match_ecu_info
            self.current_car_type = match_car_type
            self.current_ecu_name = match_ecu_name
            self.current_identify_code = match_identify_code
            
            success_msg = create_branded_message_box(self)
            success_msg.setIcon(QMessageBox.Information)
            success_msg.setWindowTitle("识别成功")
            success_msg.setText(f"已识别到ECU型号为：{match_car_type} {match_ecu_name}")
            success_msg.setStyleSheet("""
                QLabel{color:black; font-size:16px; font-weight:bold;} 
                QPushButton{background:#0078D7; color:white; font-size:14px; padding:8px 20px;}
            """)
            success_msg.exec_()
            
            self.car_combobox.setCurrentText(match_car_type)
            self.update_ecu_combobox(match_car_type)
            self.ecu_combobox.setCurrentText(match_ecu_name)
            
            self.result_label.setText(f"识别结果：识别成功 - {match_car_type} {match_ecu_name}")
            self.add_operation_log(f"ECU识别成功：{match_car_type} - {match_ecu_name}")
            
            self.load_function_buttons(match_ecu_info["functions"])
            
        except Exception as e:
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("暂不支持该ECU的数据 请联系售后")
            msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
            msg.exec_()
            self.result_label.setText("识别结果：识别失败")
            self.add_operation_log(f"ECU识别异常：{str(e)}")
            self.clear_function_buttons()
            self.show_default_step3_button()
            self.func_tip_label.show()

    def clear_function_buttons(self):
        while self.func_content_layout.count():
            item = self.func_content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _create_function_card(self, title, is_allowed=False, on_click=None, placeholder=False):
        button = QToolButton()
        button.setText(title)
        button.setCursor(Qt.PointingHandCursor if not placeholder else Qt.ArrowCursor)
        button.setEnabled(True)
        button.setProperty("cardAllowed", bool(is_allowed))
        button.setFixedSize(scaled_px(258), scaled_px(182))
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.setIcon(_get_function_icon(title, 104, muted=(not is_allowed and not placeholder)))
        button.setIconSize(QSize(scaled_px(104), scaled_px(104)))
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setStyleSheet("""
            QToolButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(8, 41, 108, 0.98),
                    stop:0.55 rgba(10, 66, 162, 0.96),
                    stop:1 rgba(6, 23, 78, 0.98));
                color: #EAF4FF;
                font-size: 16px;
                font-weight: 700;
                border: 1px solid rgba(96, 165, 250, 0.42);
                border-radius: 18px;
                padding: 10px 12px 10px 12px;
                text-align: center;
                line-height: 1.5;
            }
            QToolButton:hover:enabled {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(11, 57, 143, 1.0),
                    stop:0.55 rgba(18, 90, 205, 0.98),
                    stop:1 rgba(7, 34, 110, 1.0));
                border: 1px solid rgba(125, 211, 252, 0.78);
            }
            QToolButton:pressed:enabled {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(7, 35, 94, 1.0),
                    stop:0.55 rgba(9, 60, 148, 1.0),
                    stop:1 rgba(5, 20, 68, 1.0));
            }
        """)
        if not is_allowed and not placeholder:
            button.setStyleSheet(button.styleSheet() + "QToolButton{color:rgba(190,198,210,0.92);background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(43,50,63,0.98),stop:0.55 rgba(64,73,88,0.96),stop:1 rgba(34,40,52,0.98));border:1px solid rgba(148,163,184,0.28);} QToolButton:hover:enabled{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(55,64,80,0.98),stop:0.55 rgba(76,87,105,0.96),stop:1 rgba(45,52,66,0.98));border:1px solid rgba(168,180,197,0.38);}")
        if not placeholder:
            effect = QGraphicsDropShadowEffect(button)
            effect.setBlurRadius(24)
            effect.setOffset(0, 8)
            effect.setColor(QColor(7, 20, 52, 78))
            button.setGraphicsEffect(effect)
        if placeholder:
            button.setToolTip("默认功能卡片展示")
        if on_click and not placeholder:
            button.clicked.connect(on_click)
        return button

    def _append_function_row(self, cards):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(scaled_px(18))
        row_layout.setAlignment(Qt.AlignLeft)
        for card in cards:
            row_layout.addWidget(card, 0, Qt.AlignLeft)
        row_layout.addStretch()
        self.func_content_layout.addWidget(row_widget)

    def _append_builtin_cards(self):
        return [self._create_function_card("接线图查询", is_allowed=True, on_click=self.open_wiring_guide_dialog)]

    def show_default_step3_button(self):
        self.clear_function_buttons()
        cards = self._append_builtin_cards()
        cards.append(self._create_function_card("三项未就绪", is_allowed=True, placeholder=True))
        self._append_function_row(cards)

    def load_function_buttons(self, functions):
        self.refresh_user_permissions(silent=True)
        self.clear_function_buttons()
        self.func_tip_label.hide()

        self.func_scroll.verticalScrollBar().setValue(0)
        cards = self._append_builtin_cards()

        runtime_functions = functions if isinstance(functions, dict) else {}
        all_function_names = list(ALL_FUNCTION_NAMES or [])

        if not all_function_names:
            all_function_names = _collect_all_function_names(ECU_DATABASE)

        if not all_function_names:
            if not runtime_functions:
                self.show_default_step3_button()
                return
            all_function_names = list(runtime_functions.keys())

        for func_name in all_function_names:
            runtime_func_info = dict(runtime_functions.get(func_name) or {})
            runtime_func_info.setdefault("name", func_name)
            is_allowed = self.is_function_allowed(runtime_func_info)
            cards.append(
                self._create_function_card(
                    func_name,
                    is_allowed=is_allowed,
                    on_click=lambda checked=False, fn=func_name, fi=runtime_func_info: self.execute_function(fn, fi),
                )
            )

        row_cards = []
        for card in cards:
            row_cards.append(card)
            if len(row_cards) == 4:
                self._append_function_row(row_cards)
                row_cards = []
        if row_cards:
            self._append_function_row(row_cards)

    def execute_function(self, func_name, func_info):
        try:
            self.refresh_user_permissions(silent=True)
            if str((self.purchase_config or {}).get("force_update", "0")) == "1":
                self.add_operation_log(f"功能执行被拦截：{func_name}（强制更新）")
                show_message(self, QMessageBox.Warning, "强制更新", (self.purchase_config or {}).get("update_notice") or "当前版本需要强制更新，请先完成更新。")
                return
            if not self.is_function_allowed(func_info):
                self.add_operation_log(f"功能执行被拦截：{func_name}（无权限）")
                self.show_purchase_dialog(func_name)
                return

            if not self.file_data or not self.current_ecu_info or not self.current_identify_code:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setText("请先打开文件并识别ECU")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                return

            disclaimer_box = create_branded_message_box(self)
            disclaimer_box.setIcon(QMessageBox.Warning)
            disclaimer_box.setWindowTitle("警告")
            disclaimer_box.setText(
                "本功能的开发仅限维修教学测试为目的，拒绝盈利性的非法活动。"
                "教学与维修完成后请自行恢复数据。本公司不承担任何因操作员不合规定的非法操作的任何法律责任。"
                "教学，维修，测试工作完成后，必须自行恢复数据，否则为判定为个人不合规操作行为。"
                "如因操作人员的操作不复合当地法律法规所产生的任何法律责任部由操作人员自行承担。"
                "请认真阅读上述免责内容，确定您已明确知晓上述所有文字内容的声明。"
            )
            disclaimer_box.setInformativeText("")
            disclaimer_box.setStandardButtons(QMessageBox.NoButton)
            agree_btn = disclaimer_box.addButton("同意", QMessageBox.AcceptRole)
            disagree_btn = disclaimer_box.addButton("不同意", QMessageBox.RejectRole)
            disclaimer_box.setStyleSheet("QLabel{color:black; font-size:13px;}")
            button_style = (
                "QPushButton{"
                "color:white;"
                "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2A65EE,stop:1 #3F8CFF);"
                "border:1px solid rgba(157, 199, 255, 0.38);"
                "border-radius:8px;"
                "min-width:220px; padding:7px 10px; font-weight:bold;}"
                "QPushButton:hover{"
                "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3A74F5,stop:1 #51A0FF);}"
            )
            agree_btn.setStyleSheet(button_style)
            disagree_btn.setStyleSheet(button_style)
            disclaimer_box.exec_()
            if disclaimer_box.clickedButton() != agree_btn:
                self.add_operation_log(f"执行功能取消：{func_name}（未同意免责声明）")
                return
            
            # 获取对应版本的修改逻辑
            modifications_map = func_info.get("modifications_map", {})
            modifications = modifications_map.get(self.current_identify_code, [])

            idle_rpm = None
            if func_name == "怠速调整":
                value, ok = QInputDialog.getInt(
                    self,
                    "怠速调整",
                    "请输入目标怠速（800~1000）",
                    850,
                    800,
                    1000,
                    10,
                )
                if not ok:
                    self.add_operation_log("怠速调整取消：用户未输入目标怠速")
                    return
                idle_rpm = value
            
            if not modifications:
                msg = create_branded_message_box(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setText("该版本暂无修改逻辑")
                msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
                msg.exec_()
                return
            
            data_array = bytearray(self.file_data)
            
            for mod in modifications:
                addr = mod.get("addr", 0)
                length = mod.get("length", 0)
                value_hex = mod.get("value", "")

                if func_name == "怠速调整" and idle_rpm is not None:
                    idle_map = _encode_idle_value_hex(idle_rpm)
                    if length in idle_map:
                        value_hex = idle_map[length]
                
                if addr < 0 or length <=0 or (addr+length) > len(data_array):
                    continue
                
                value_bytes = binascii.unhexlify(value_hex)
                data_array[addr:addr+length] = value_bytes
            
            self.file_data = bytes(data_array)
            self.save_btn.setEnabled(True)
            
            success_text = func_info["success_msg"]
            if func_name == "怠速调整" and idle_rpm is not None:
                success_text = f"怠速已调整为 {idle_rpm} RPM，请保存文件。"
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Information)
            msg.setText(success_text)
            msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
            msg.exec_()
            self.add_operation_log(f"执行功能成功：{func_name}" + (f" -> {idle_rpm}RPM" if idle_rpm is not None else ""))
            
        except Exception as e:
            msg = create_branded_message_box(self)
            msg.setIcon(QMessageBox.Critical)
            msg.setText(f"执行功能失败：{str(e)}")
            msg.setStyleSheet("QLabel{color:black;} QPushButton{color:white; background:#0078D7;}")
            msg.exec_()
            self.add_operation_log(f"执行功能失败：{func_name} - {str(e)}")


def show_message(parent, icon, title, text, info_text=""):
    message_box = create_branded_message_box(parent)
    message_box.setIcon(icon)
    message_box.setWindowTitle(title)
    message_box.setText(text)
    if info_text:
        message_box.setInformativeText(info_text)
    message_box.setStyleSheet(
        "QLabel{color:black; font-size:14px;} "
        "QPushButton{color:white; background:#0078D7; min-width:96px; padding:6px 12px;}"
    )
    message_box.exec_()


def _encode_idle_value_hex(idle_rpm):
    base = int(idle_rpm)
    low = base & 0xFF
    high = (base >> 8) & 0xFF
    single = f"{low:02X}"
    pair = f"{low:02X}{high:02X}"
    block12 = pair * 12
    return {
        1: single,
        2: pair,
        24: block12,
    }


class MergedChecksumDialog(ChecksumDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cpu_combobox.clear()
        self.cpu_combobox.addItems(CPU_DISPLAY_TO_KEY.keys())
        self.cpu_combobox.setCurrentIndex(0)

    def calculate_and_save(self):
        if not self.original_file_data:
            self.status_label.setText("状态：请先加载原始数据")
            show_message(self, QMessageBox.Warning, "提示", "请先加载原始数据！")
            return

        if not self.modified_file_data:
            self.status_label.setText("状态：请先加载修改后数据")
            show_message(self, QMessageBox.Warning, "提示", "请先加载修改后数据！")
            return

        cpu_display_name = self.cpu_combobox.currentText()
        cpu_key = CPU_DISPLAY_TO_KEY[cpu_display_name]
        checksum_offset = ECU_CPU_MAP[cpu_key]
        ok, output_data = calculate_checksum(
            bytearray(self.original_file_data),
            bytearray(self.modified_file_data),
            checksum_offset,
        )
        if not ok:
            self.status_label.setText("状态：校验和计算失败")
            show_message(self, QMessageBox.Critical, "错误", "数据错误，请重新加载数据！")
            return

        computer_name = get_computer_name()
        random_num = generate_random_num()
        default_filename = f"ECUflash_{computer_name}_校验和计算_{random_num}.bin"
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        default_path = os.path.join(desktop_path, default_filename)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存校验后文件",
            default_path,
            "BIN文件 (*.bin);;所有文件 (*.*)",
        )
        if not save_path:
            self.status_label.setText("状态：校验和已计算，未保存文件")
            return

        with open(save_path, "wb") as file_obj:
            file_obj.write(output_data)

        self.modified_file_data = bytes(output_data)
        self.status_label.setText(f"状态：文件保存成功 - {os.path.basename(save_path)}")

        result_info = (
            f"CPU型号：{cpu_display_name}\n"
            f"校验地址：0x{checksum_offset:06X}\n"
            f"原始文件CRC32：{binascii.crc32(self.original_file_data) & 0xFFFFFFFF:08X}\n"
            f"新文件CRC32：{binascii.crc32(output_data) & 0xFFFFFFFF:08X}\n"
            f"原始文件MD5：{hashlib.md5(self.original_file_data).hexdigest().upper()}\n"
            f"新文件MD5：{hashlib.md5(output_data).hexdigest().upper()}"
        )
        show_message(self, QMessageBox.Information, "保存成功", "校验和计算并保存完成。")

        parent = self.parent()
        if parent and hasattr(parent, "add_operation_log"):
            parent.add_operation_log(f"校验和工具：计算并保存文件 - {save_path}")
            parent.add_operation_log(result_info.replace("\n", " | "))


class MergedMainWindow(ECUFlashWindow):
    def __init__(self, license_data):
        self.license_data = license_data
        self.allowed_function_ids = set(int(item) for item in license_data.get("permission_function_ids", []))
        self.allowed_function_names = set(str(item).strip() for item in license_data.get("permission_function_names", []) if str(item).strip())
        self.is_admin_user = bool(license_data.get("user", {}).get("is_admin"))
        self.purchase_config = license_data.get("purchase_config") or {}
        super().__init__()
        self._patch_runtime_ui()

    def show_purchase_dialog(self, func_name=""):
        cfg = self.purchase_config or {}
        title = cfg.get("title") or "功能开通"
        message = cfg.get("message") or "当前功能尚未开通，请扫码付款后联系管理员授权。"
        qr_code_url = cfg.get("qr_code_url") or ""
        contact = cfg.get("contact") or ""

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        apply_logo_to_window(dialog)
        dialog.setFixedSize(560, 760)
        dialog.setStyleSheet(
            "QDialog{background:#0F172A;} QLabel{color:#E5E7EB;} QPushButton{background:#2563EB;color:white;border:none;border-radius:8px;padding:10px 18px;font-size:14px;font-weight:bold;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size:22px;font-weight:bold;color:#93C5FD;")
        layout.addWidget(title_label)

        if func_name:
            func_label = QLabel(f"当前功能：{func_name}")
            func_label.setStyleSheet("font-size:15px;color:#FBBF24;")
            layout.addWidget(func_label)

        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("font-size:18px;line-height:1.7;color:#E5E7EB;font-weight:bold;")
        layout.addWidget(message_label)

        if qr_code_url:
            qr_label = QLabel()
            qr_label.setAlignment(Qt.AlignCenter)
            qr_label.setMinimumSize(420, 420)
            qr_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            resolved_qr_code_url = _resolve_resource_url(qr_code_url)
            try:
                request = urllib.request.Request(resolved_qr_code_url, headers={"Accept": "image/*"})
                with urllib.request.urlopen(request, timeout=8) as response:
                    data = response.read()
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    qr_label.setPixmap(pixmap.scaled(420, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    qr_label.setText(f"收款码：{resolved_qr_code_url}")
            except Exception:
                qr_label.setText(f"收款码：{resolved_qr_code_url}")
            qr_label.setStyleSheet("background:#FFFFFF;border-radius:16px;padding:20px;color:#111827;")
            layout.addWidget(qr_label, 0, Qt.AlignCenter)

        layout.addStretch()
        close_btn = QPushButton("我知道了")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec_()

    def refresh_user_permissions(self, silent=False):
        token = self.license_data.get("token")
        if not token:
            return False
        try:
            user = _api_request_json("/auth/me", token=token)
            self.license_data["user"] = user
            self.license_data["name"] = user.get("name") or user.get("phone") or self.license_data.get("name") or "未命名用户"
            self.is_admin_user = bool(user.get("is_admin"))
            permissions = fetch_my_permissions(token)
            self.allowed_function_ids = permissions["ids"]
            self.allowed_function_names = permissions["names"]
            self.license_data["permission_function_ids"] = sorted(self.allowed_function_ids)
            self.license_data["permission_function_names"] = sorted(self.allowed_function_names)
            try:
                self.purchase_config = fetch_purchase_config(token)
                self.license_data["purchase_config"] = self.purchase_config
            except Exception:
                pass
            save_session_data(self.license_data)
            if not silent:
                if self.is_admin_user:
                    self.add_operation_log("权限已刷新：管理员，已开放全部功能")
                else:
                    self.add_operation_log(f"权限已刷新：已授权功能 {len(self.allowed_function_names)} 项")
            return True
        except Exception as exc:
            if not silent:
                self.add_operation_log(f"权限刷新失败：{exc}")
            return False

    def is_function_allowed(self, func_info):
        if self.is_admin_user:
            return True
        if not isinstance(func_info, dict):
            return False
        func_name = str(func_info.get("name") or func_info.get("function_name") or "").strip()
        free_names = set(self.purchase_config.get("free_feature_names") or [])
        if func_name and func_name in free_names:
            return True
        if func_name and func_name in self.allowed_function_names:
            return True
        function_id = func_info.get("function_id")
        if function_id is None:
            return False
        try:
            return int(function_id) in self.allowed_function_ids
        except Exception:
            return False

    def search_ecu_by_name(self):
        keyword = self.search_ecu_edit.text().strip().lower()
        if not keyword:
            return

        found_car = None
        found_ecu = None
        for car_type, ecu_list in ECU_DATABASE.items():
            for ecu_name in ecu_list.keys():
                if keyword in ecu_name.lower():
                    found_car = car_type
                    found_ecu = ecu_name
                    break
            if found_car:
                break

        if not found_car or not found_ecu:
            show_message(self, QMessageBox.Warning, "提示", "未找到匹配的 ECU 型号。")
            return

        self.car_combobox.setCurrentText(found_car)
        self.update_ecu_combobox(found_car)
        self.ecu_combobox.setCurrentText(found_ecu)
        self.add_operation_log(f"搜索定位：{found_car} → {found_ecu}")

    def _mark_update_notice_seen(self):
        latest_version = str((self.purchase_config or {}).get("latest_version") or "").strip()
        if not latest_version:
            return
        self.license_data["last_seen_update_version"] = latest_version
        save_session_data(self.license_data)

    def _should_show_update_notice_once(self):
        cfg = self.purchase_config or {}
        latest_version = str(cfg.get("latest_version") or "").strip()
        notice_text = str(cfg.get("update_notice") or "").strip()
        if not latest_version or not notice_text:
            return False
        if latest_version == str(APP_VERSION).strip():
            return False
        return latest_version != str(self.license_data.get("last_seen_update_version") or "").strip()

    def _patch_runtime_ui(self):
        if hasattr(self, "search_ecu_edit"):
            self.search_ecu_edit.clear()
            self.search_ecu_edit.setPlaceholderText("输入 ECU 型号后回车，例如 ME7.8.8")

        for button in self.findChildren(QPushButton):
            if button.text() in {"操作日志", "更新说明"}:
                button.clicked.connect(self.show_log_dialog)
                break
        if hasattr(self, "logout_btn"):
            self.logout_btn.clicked.connect(self.logout_and_relogin)

        auth_text = (
            f"✓ 登录用户: {self.license_data['name']} | "
            f"会话到期: {self.license_data['expire_time']}"
        )
        for label in self.findChildren(QLabel):
            if "登录用户" in label.text() or "授权用户" in label.text():
                label.setText(auth_text)
                break

        self.add_operation_log("系统启动成功")
        self.add_operation_log(f"登录用户：{self.license_data['name']}")
        if self.is_admin_user:
            self.add_operation_log("权限状态：管理员，已开放全部功能")
        else:
            self.add_operation_log(f"权限状态：已授权功能 {len(self.allowed_function_names)} 项")
        if str((self.purchase_config or {}).get("force_update", "0")) == "1":
            self.add_operation_log("更新状态：当前版本被标记为强制更新")
            show_message(self, QMessageBox.Warning, "强制更新", (self.purchase_config or {}).get("update_notice") or "当前版本需要强制更新，请联系管理员获取最新版。")
        elif self._should_show_update_notice_once():
            latest_version = str((self.purchase_config or {}).get("latest_version") or "").strip()
            self.add_operation_log(f"更新状态：发现新版本公告 {latest_version}，首次提醒")
            self.show_log_dialog(auto_open=True)

    def open_checksum_dialog(self):
        dialog = MergedChecksumDialog(self)
        dialog.exec_()

    def logout_and_relogin(self):
        # 自定义退出对话框，支持解除设备绑定
        dialog = QDialog(self)
        dialog.setWindowTitle("退出登录")
        apply_logo_to_window(dialog)
        dialog.setFixedSize(420, 280)
        dialog.setStyleSheet("""
            QDialog { background-color: #111827; font-family: Microsoft YaHei; }
            QLabel { color: #E5E7EB; font-size: 14px; }
            QCheckBox { color: #D1D5DB; font-size: 13px; spacing: 6px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px;
                border: 1px solid #4B5563; background: #1F2937; }
            QCheckBox::indicator:checked { background: #3B82F6; border-color: #3B82F6; }
            QPushButton { min-height: 40px; border-radius: 8px; font-size: 14px; font-weight: bold; padding: 8px 20px; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        title_label = QLabel("确定要退出当前账号吗？")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_label.setStyleSheet("color: #F3F4F6;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        device_info = self.license_data.get("user", {}).get("device_name") or "当前设备"
        hint_label = QLabel(f"当前绑定设备：{device_info}")
        hint_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint_label)

        unbind_checkbox = QCheckBox("同时解除设备绑定（换电脑时需要）")
        unbind_checkbox.setStyleSheet("color: #FBBF24; font-size: 13px; font-weight: bold;")
        layout.addWidget(unbind_checkbox)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("background-color: #374151; color: #D1D5DB;")
        cancel_btn.clicked.connect(dialog.reject)

        confirm_btn = QPushButton("确认退出")
        confirm_btn.setStyleSheet("background-color: #EF4444; color: white;")
        confirm_btn.clicked.connect(dialog.accept)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        if dialog.exec_() != QDialog.Accepted:
            return

        should_unbind = unbind_checkbox.isChecked()
        token = self.license_data.get("token")

        if should_unbind and token:
            try:
                result = _api_request_json("/auth/unbind-device", method="POST", token=token)
                unbound = result.get("unbound_device", "")[:12]
                self.add_operation_log(f"已解除设备绑定：{unbound}...")
            except Exception as exc:
                self.add_operation_log(f"解除设备绑定失败：{exc}")

        if token:
            try:
                _api_request_json("/auth/logout", method="POST", token=token)
            except Exception as exc:
                self.add_operation_log(f"服务端退出登录失败：{exc}")

        clear_session_data()
        self.add_operation_log("当前账号已退出登录")

        dialog = RegisterDialog()
        if dialog.exec_() != QDialog.Accepted:
            self.close()
            return

        new_session = dialog.session_data or check_license()
        if not new_session:
            show_message(self, QMessageBox.Critical, "错误", "重新登录后未能读取会话信息。")
            self.close()
            return

        replacement = MergedMainWindow(new_session)
        replacement.showMaximized()
        self.close()

    def show_log_dialog(self, auto_open=False):
        cfg = self.purchase_config or {}
        notice_text = (cfg.get("update_notice") or "").strip()
        latest_version = (cfg.get("latest_version") or "").strip()
        latest_download_url = (cfg.get("latest_download_url") or "").strip()
        dialog = QDialog(self)
        dialog.setWindowTitle("更新说明")
        apply_logo_to_window(dialog)
        dialog.resize(860, 620)
        dialog.setStyleSheet(
            "QDialog{background:#111827;} QLabel{color:#E5E7EB;} "
            "QTextEdit{background:#0F172A; color:#E5E7EB; border:1px solid #1D4ED8; "
            "border-radius:6px; font-size:14px; padding:8px;} "
            "QPushButton{background:#2563EB; color:white; border:none; border-radius:6px; "
            "padding:10px 20px; font-size:14px; font-weight:bold;}"
        )

        layout = QVBoxLayout(dialog)
        title = QLabel("更新说明")
        title.setStyleSheet("color:#93C5FD; font-size:18px; font-weight:bold;")
        layout.addWidget(title)

        if latest_version:
            version_label = QLabel(f"当前客户端：{APP_VERSION}    最新版本：{latest_version}")
            version_label.setStyleSheet("font-size:13px;color:#93C5FD;")
            layout.addWidget(version_label)

        if cfg.get("force_update") == "1":
            force_label = QLabel("当前版本要求强制更新，请按公告指引处理。")
            force_label.setStyleSheet("font-size:14px;font-weight:bold;color:#FCA5A5;")
            layout.addWidget(force_label)

        notice_view = QTextEdit(dialog)
        notice_view.setReadOnly(True)
        notice_view.setPlainText(notice_text or "暂无更新说明")
        layout.addWidget(notice_view, 3)

        log_title = QLabel("本地操作日志")
        log_title.setStyleSheet("color:#FBBF24; font-size:16px; font-weight:bold;")
        layout.addWidget(log_title)

        log_view = QTextEdit(dialog)
        log_view.setReadOnly(True)
        log_view.setPlainText(self.operation_log_area.toPlainText() or "暂无操作日志")
        layout.addWidget(log_view, 2)

        button_row = QHBoxLayout()
        button_row.addStretch()
        if latest_download_url:
            download_button = QPushButton("立即更新")
            download_button.clicked.connect(lambda: _open_url(latest_download_url))
            button_row.addWidget(download_button)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)
        if auto_open:
            self._mark_update_notice_seen()
        dialog.exec_()


def main():
    configure_qt_runtime()
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    init_ui_scaling(app)
    app.setFont(QFont("Microsoft YaHei", scaled_point(10)))
    app.setStyle(QStyleFactory.create("Fusion"))

    license_data = check_license()

    if not license_data:
        dialog = RegisterDialog()
        if dialog.exec_() != QDialog.Accepted:
            return 0
        license_data = dialog.session_data or check_license()
        if not license_data:
            show_message(None, QMessageBox.Critical, "错误", "登录完成后未能读取会话信息。")
            return 1

    try:
        load_remote_runtime_dataset(license_data["token"])
    except Exception as exc:
        show_message(None, QMessageBox.Critical, "接口错误", f"无法加载服务端数据：{exc}", f"接口地址：{API_BASE_URL}")
        return 1

    window = MergedMainWindow(license_data)
    window.showMaximized()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())



