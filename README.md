# ECUFlash 服务端接口

## 最新下载
- Release 页面：<https://github.com/Gliangquan/ecuflash-pi-build/releases>
- 最新构建：<https://github.com/Gliangquan/ecuflash-pi-build/releases/tag/latest-build>
- Windows：`ECUFlash-windows.zip`
- macOS：`ECUFlash-macos.zip`
- Linux：`ECUFlash-linux.tar.gz`

> GitHub 首页用户可直接点右侧 Releases 或上面链接下载，不需要进 Packages。

## 1. 安装依赖
```bash
cd /www/wwwroot/ecuflash/server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置环境变量
```bash
cp .env.example .env
# 修改 .env 里的 MySQL 连接信息
```

## 3. 启动服务
```bash
cd /www/wwwroot/ecuflash/server
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 4. 宝塔/Nginx 反向代理示例
- 代理目标: `http://107.148.176.142:8000`
- 建议路径: `/api/` 和 `/health`

## 5. 管理后台（新增）

### 默认管理员
- 账号：`admin`
- 密码：`admin1234`

### 可配置环境变量
- `ADMIN_PHONE`
- `ADMIN_NAME`
- `ADMIN_PASSWORD`
- `AUTH_PASSWORD_SALT`
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MINIO_BUCKET`
- `MINIO_SECURE`
- `MINIO_PUBLIC_BASE_URL`

### 访问地址
- 后台页面：`/admin`
- 登录接口：`POST /api/v1/auth/login`
- 当前用户：`GET /api/v1/auth/me`
- 我的权限：`GET /api/v1/auth/my-permissions`
- 管理接口前缀：`/api/v1/admin`
- 接线图管理页：`/admin` → `接线图管理`

### 当前已支持
- 账号登录
- 退出登录
- 用户管理
- 按功能授权
- ECU 功能按钮权限控制（未授权项灰显禁用）
- 仪表盘
- 操作日志
- 接线图管理（后台 CRUD + MinIO 上传）

### 启动初始化
服务启动时会自动初始化以下表：
- `app_user`
- `app_session`
- `app_user_function_permission`
- `app_operation_log`

## 6. 接口列表
- `GET /health`
- `GET /api/v1/car-series`
- `GET /api/v1/car-series/{car_series_id}/ecu-models`
- `GET /api/v1/search/ecu-models?keyword=ME7`
- `GET /api/v1/ecu-models/{ecu_model_id}/identify-rules`
- `GET /api/v1/ecu-models/{ecu_model_id}/functions`
- `GET /api/v1/functions/{function_id}/patches?identify_hex=463031523030444D3733`
- `GET /api/v1/cpu-checksums`
- `GET /api/v1/wiring-guides?keyword=ME7`
- `GET /api/v1/wiring-guides/{guide_id}/download`
- `GET /api/v1/admin/wiring-guides`
- `POST /api/v1/admin/wiring-guides/upload`
- `POST /api/v1/admin/wiring-guides`
- `PUT /api/v1/admin/wiring-guides/{guide_id}`
- `DELETE /api/v1/admin/wiring-guides/{guide_id}`

## 6. 典型调用顺序（客户端）
1. 拉取车系 `/car-series`
2. 选中车系后拉取 ECU `/car-series/{id}/ecu-models`
3. 选中 ECU 后拉取识别规则 `/ecu-models/{id}/identify-rules`
4. 客户端在本地 BIN 文件中读地址做匹配，得到 `identify_hex`
5. 拉取功能列表 `/ecu-models/{id}/functions`
6. 用户点击某功能时，请求补丁 `/functions/{function_id}/patches?identify_hex=...`
7. 拉取校验地址 `/cpu-checksums`

补充：客户端在登录恢复、识别渲染功能按钮前、执行功能前，都会刷新一次 `/api/v1/auth/my-permissions`，确保后台授权变更可快速生效。

## 8. 说明
- 客户端不再内置 ECU JSON 数据，全部通过接口获取。
- BIN 文件可继续仅在客户端本地处理，不上传服务端。
- 若后续需要“服务端识别 BIN”，可再加 `POST /api/v1/identify`。
