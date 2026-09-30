# Счетовод

Суммовой учёт товаров в розничных ценах: загрузка накладных из JSON или фото,
проверка и проведение, продажи, списания, переучёт, переоценка и отчёты XLSX.
Backend — FastAPI и PostgreSQL, frontend — React.

## Запуск

Нужны Git, Bash, Make, Docker и Docker Compose. Скопируйте проект и подготовьте
настройки одной командой:

```sh
git clone https://github.com/vaakesh/schetovod.git && cd schetovod && bash install.sh
```

`install.sh` копирует `.env.example` в `.env`, а `.openai-token.example` — в
`.openai-token`. Существующие файлы сохраняются. Порты и пароли можно изменить
в `.env`; при выключенном распознавании `.openai-token` может быть пустым.

После подготовки настроек установщик покажет команду запуска контейнеров:

```sh
make up
```

`make up` собирает и запускает API, frontend и PostgreSQL в фоне.
Миграции применяются автоматически. С портами из `.env.example`:

- Приложение: http://localhost:8080
- Документация API: http://localhost:8001/docs

CloudBeaver для просмотра БД запускается отдельно:

```sh
make cloudbeaver
```

После запуска он доступен на http://localhost:8978.
Остановить все контейнеры, сохранив данные:

```sh
make down
```

Для распознавания фото запишите токен OpenAI в `.openai-token`, установите
`INCLUDE_API_OPENAI=1` в `.env` и выполните `docker compose up -d app`.
Фото одной накладной передаются вместе в multipart-поле `files`.

## Основные роуты API

| Метод и путь | Назначение |
| --- | --- |
| `GET /invoice` | Список накладных, фильтр по статусу и поиск |
| `POST /invoice` | Создать черновик из JSON |
| `POST /invoice/image` | Распознать фото и создать черновик |
| `GET /invoice/{id}`, `PUT /invoice/{id}` | Открыть или сохранить черновик |
| `POST /invoice/{id}/confirm`, `POST /invoice/{id}/decline` | Провести или отклонить |
| `GET /invoice/{id}/confirmed` | Открыть проведённую накладную |
| `GET /supplier`, `GET /supplier/{id}/products` | Поиск поставщиков и их товаров |
| `GET /ledger`, `GET /ledger/balance` | Журнал операций и остаток |
| `POST /ledger/sale`, `POST /ledger/write-off` | Продажа или списание |
| `POST /ledger/stocktake`, `POST /ledger/revaluation` | Переучёт или переоценка |
| `POST /ledger/{id}/reverse` | Сторнировать операцию |
| `GET /ledger/report`, `GET /ledger/report.xlsx` | Отчёт за период в JSON или XLSX |

На frontend API доступен с префиксом `/api`. Форматы запросов описаны в `/docs`;
пример структуры распознавания — в [промпте](app/extraction_prompt.md).
Запуск для разработки и проверки — в [app/README.md](app/README.md).
