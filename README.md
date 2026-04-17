# AI-ассистент врача на приеме

MVP веб-приложения, которое во время очного приема записывает диалог врача и пациента,
расшифровывает речь, структурирует протокол, предлагает топ-3 диагноза и план лечения,
после чего формирует PDF.

> **Текущее состояние:** Шаг 2 из 5 — модель данных MVP, миграции, авторизация врача и
> экран логина. Распознавание речи, LLM-анализ и генерация PDF появятся в следующих шагах.

## Скоуп MVP (по всем пяти шагам)

- авторизация врача (логин/пароль);
- создание сессии приема с ручным вводом данных пациента (ФИО, возраст, пол);
- фиксация согласия пациента на запись;
- запись аудио и потоковая расшифровка с разделением говорящих;
- ручная правка расшифровки;
- автоматическое структурирование протокола (жалобы, анамнез, осмотр);
- топ-3 диагноза и красные флаги;
- план лечения (медикаменты, дообследование, рекомендации);
- подтверждение протокола врачом → генерация PDF;
- просмотр своих завершенных сессий.

В MVP **нет**: интеграций с МИС/ЕГИСЗ/лабораториями, истории пациента между сессиями,
ролей администратора и медэксперта, электронной подписи, мобильного приложения,
мультиязычности.

## Tech stack

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x (async), Alembic, PostgreSQL 16,
Pydantic v2, Uvicorn.

**Frontend:** React 18 + TypeScript, Vite, TailwindCSS, React Router v6,
TanStack Query, Zustand, axios.

**Инфра:** Docker + Docker Compose (dev-режим), PostgreSQL 16.

## Структура репозитория

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/         # роутеры FastAPI (health, …)
│   │   ├── core/           # конфиг через pydantic-settings
│   │   ├── db/             # async SQLAlchemy engine/session, Base
│   │   ├── models/         # SQLAlchemy модели (в Шаге 1 пусто)
│   │   ├── schemas/        # Pydantic-схемы (в Шаге 1 пусто)
│   │   ├── services/       # ASR / LLM / PDF (в Шаге 1 пусто)
│   │   └── main.py         # FastAPI app, CORS, /api/v1
│   ├── alembic/            # конфиг миграций (миграций пока нет)
│   ├── tests/
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/            # axios-клиент и запросы (health)
│   │   ├── components/
│   │   ├── pages/          # HomePage
│   │   ├── store/          # zustand (пусто в Шаге 1)
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── routes.tsx
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── tsconfig.json
│   ├── package.json
│   ├── Dockerfile
│   └── .env.example
├── plan/                   # пошаговые спецификации (не редактировать)
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## Требования к окружению

- **Docker** 24+ и **Docker Compose v2** — основной способ запуска.
- (Опционально, для локального запуска без Docker) **Python 3.11+** и **Node 20+**.

## Запуск с нуля

1. Клонируйте репозиторий и перейдите в его корень.
2. Скопируйте файлы окружения:

   ```bash
   cp .env.example .env
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

   Корневой `.env` используется `docker-compose` для подстановки переменных.
   Локальные `.env` в `backend/` и `frontend/` нужны, если вы запускаете сервисы без Docker.

3. Запустите всё окружение:

   ```bash
   docker compose up --build
   ```

   Поднимутся три сервиса:

   - `db` — PostgreSQL 16 на порту `5432`;
   - `backend` — FastAPI (uvicorn с автоперезагрузкой) на `http://localhost:8000`;
   - `frontend` — Vite dev-server на `http://localhost:5173`.

4. Проверьте backend напрямую:

   ```bash
   curl http://localhost:8000/api/v1/health
   # {"status":"ok"}
   ```

5. Откройте `http://localhost:5173` — увидите заголовок **«AI-ассистент врача»**
   и кнопку «Проверить health-check». По клику на экране появится ответ `{"status":"ok"}`.

## Применение миграций

В репозитории лежит начальная миграция `0001_initial_schema`, которая создаёт
все таблицы MVP (`users`, `appointment_sessions`, `transcripts`, `protocols`,
`diagnosis_suggestions`, `red_flags`, `treatment_plans`, `treatment_plan_items`,
`audit_log`) и соответствующие Postgres ENUM-типы.

Применить миграции на свежей БД:

```bash
docker compose up -d db backend
docker compose exec backend alembic upgrade head
```

Проверить текущую ревизию:

```bash
docker compose exec backend alembic current
```

Откат последней миграции:

```bash
docker compose exec backend alembic downgrade -1
```

Создать следующую автомиграцию в будущих шагах:

```bash
docker compose exec backend alembic revision --autogenerate -m "что-то новое"
```

## Seed демо-врача

Для локальной разработки положите в БД одного врача командой:

```bash
docker compose exec backend python -m scripts.seed_demo_doctor
```

Креды: `demo@clinic.local` / `demo1234`, ФИО «Демо Врач». Скрипт идемпотентный —
повторный запуск не падает и не создаёт дубликат.

## Запуск тестов

```bash
pip install -e "backend[dev]"      # один раз, в локальном venv
pytest backend/tests
```

Тесты используют in-memory SQLite через `aiosqlite` и не требуют поднятого Postgres.

## Авторизация

После применения миграций и seed-скрипта можно залогиниться на
`http://localhost:5173/login` под `demo@clinic.local` / `demo1234`. После входа
фронт покажет шапку с ФИО врача и заглушку «Здесь будет список приёмов (Шаг 3)».

## Переменные окружения

| Переменная          | Где используется | Назначение                                                  |
| ------------------- | ---------------- | ----------------------------------------------------------- |
| `DATABASE_URL`      | backend          | Async SQLAlchemy DSN (asyncpg)                              |
| `JWT_SECRET`        | backend          | Секрет для подписи JWT (используется в Шаге 2)              |
| `OPENAI_API_KEY`    | backend          | Ключ OpenAI (Whisper / gpt-4o-mini) — задействован в Шаге 3 |
| `CORS_ORIGINS`      | backend          | Список разрешённых origin'ов, через запятую                 |
| `VITE_API_BASE_URL` | frontend         | Базовый URL REST API                                        |

## Конвенции

- URL: `/api/v1/...`, kebab-case в путях.
- Формат ответов — JSON; ошибки — `{ "detail": "..." }`.
- UI — русский; идентификаторы и коды — английские.
- Идентификаторы сущностей — UUID v4.
- Timestamps в БД — UTC; отображение — локальное в UI.
- Коммиты — Conventional Commits (`feat:`, `fix:`, `chore:` …).

## Остановка

```bash
docker compose down           # остановить контейнеры
docker compose down -v        # + удалить volume с данными Postgres
```
