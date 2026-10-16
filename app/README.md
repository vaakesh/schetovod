# Разработка

Назначение приложения, запуск в Docker и основные роуты — в [корневом README](../README.md).
Для локальной разработки нужны Python 3.14+, uv, Node.js и PostgreSQL.
Настройки подключения берутся из `.env` в корне проекта.

Backend из каталога `app/`:

```sh
uv sync
uv run alembic upgrade head
uv run fastapi dev main.py --port 8001
```

Frontend из каталога `frontend/`:

```sh
npm ci
npm run dev
```

Vite по умолчанию проксирует `/api` на `http://127.0.0.1:8001`.

Проверки backend из каталога `app/`:

```sh
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```
