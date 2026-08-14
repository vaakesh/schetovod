# Счетовод

Суммовой учёт товаров в розничных ценах.

Добавлена загрузка накладных из JSON, проверка данных и расчёт розничных цен.
Backend — FastAPI и PostgreSQL, frontend — React.

## Запуск

Нужны Docker и Docker Compose. В корне проекта создайте `.env`:

```dotenv
POSTGRES_USER=schetovod
POSTGRES_PASSWORD=change_me
POSTGRES_DB=schetovod
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
APP_PORT=8001
FRONTEND_PORT=8080
CLOUDBEAVER_PORT=8978
CB_SERVER_NAME=schetovod
CB_ADMIN_NAME=admin
CB_ADMIN_PASSWORD=change_me
```

```sh
docker compose up --build -d
```

Миграции применяются автоматически. С указанными портами:

- Приложение: http://localhost:8080
- Документация API: http://localhost:8001/docs
- CloudBeaver для просмотра БД: http://localhost:8978

## API

| Метод и путь | Назначение |
| --- | --- |
| `GET /invoice` | Список накладных, фильтр по статусу и поиск |
| `POST /invoice` | Создать черновик из JSON |
| `POST /invoice/{id}/confirm`, `POST /invoice/{id}/decline` | Провести или отклонить |
| `GET /invoice/{id}/confirmed` | Открыть проведённую накладную |
| `GET /supplier`, `GET /supplier/{id}/products` | Поиск поставщиков и их товаров |



Форматы запросов доступны в `/docs`.
Разработка и проверки — в [app/README.md](app/README.md).
