# ClassEnrollBot Backend

`ClassEnrollBot` 的後端服務，使用 FastAPI、SQLAlchemy、Redis 與 Celery，負責認證、NTNU 帳號管理、課程監控、任務排程與 WebSocket 即時事件推送。

## 技術棧

- FastAPI
- SQLAlchemy + PostgreSQL
- Redis
- Celery
- WebSocket
- `curl_cffi`、`nodriver`、`ddddocr`

## 主要功能

- 使用者註冊、登入與 JWT 驗證
- NTNU 帳號加密儲存與登入流程
- 課程搜尋、監控與自動搶課任務
- 背景工作排程與任務佇列
- 即時操作日誌與前端通知串流

## 專案結構

```text
backend/
├── app/
│   ├── api/           # REST API 與 WebSocket 路由
│   ├── anti_detection/
│   ├── core/
│   ├── db/
│   ├── schemas/
│   ├── services/
│   ├── tasks/
│   └── websocket/
├── scripts/           # NTNU 端點與流程調查工具
├── tests/
├── Dockerfile
├── Dockerfile.dev
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

## 本地開發

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

如果你是在 parent repo `ClassEnrollBot` 內開發，需要 PostgreSQL 與 Redis 時可從 parent repo 執行：

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis
```

## 測試與檢查

```bash
pytest
ruff format .
ruff check .
mypy app
```

## 環境變數

常用設定包含：

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `ENCRYPTION_KEY`
- `JWT_SECRET_KEY`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

完整說明可參考主專案：

- https://github.com/Camel031/ClassEnrollBot/blob/main/README.md
- https://github.com/Camel031/ClassEnrollBot/blob/main/docs/development.md
- https://github.com/Camel031/ClassEnrollBot/blob/main/API.md
- https://github.com/Camel031/ClassEnrollBot/blob/main/ARCHITECTURE.md
