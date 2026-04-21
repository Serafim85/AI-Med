# AI-ассистент врача на приеме

MVP веб-приложения, которое во время очного приема записывает диалог врача и пациента,
расшифровывает речь, структурирует протокол, предлагает топ-3 диагноза и план лечения,
после чего формирует PDF.

> **Текущее состояние:** Шаг 5 из 5 (финальный) — полный цикл приёма от согласия пациента
> до PDF-протокола. Реализованы запись и расшифровка речи, LLM-анализ, редактирование
> протокола/плана лечения, подтверждение врачом, генерация PDF и закрытие сессии.

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
открывается список приёмов `http://localhost:5173/app`.

## Полный цикл приёма

Ниже — сценарий, который проходит врач от момента входа в приложение до закрытого
PDF-протокола. Для его воспроизведения понадобится поднятый стенд
(`docker compose up --build`) и seed-врач `demo@clinic.local / demo1234`.

1. **Вход.** На `http://localhost:5173/login` вводим креды демо-врача и попадаем
   на список приёмов `/app`.
2. **Создание сессии.** Кнопка **«+ Новый приём»** открывает форму
   `/app/sessions/new`; заполняем ФИО пациента, возраст, пол и тип приёма
   (первичный/повторный). После отправки создаётся сессия в статусе `draft`.
3. **Согласие на запись.** На странице сессии `/app/sessions/:id` зачитываем
   согласие вслух, отмечаем чекбокс «Зачитал(а) пациенту» и подтверждаем.
   Без согласия запись заблокирована; отказ — возвращает на список.
4. **Запись и расшифровка.** Переключая роль «Врач ↔ Пациент», запускаем запись:
   браузер отправляет чанки в `/transcripts`, каждый чанк распознаётся
   (Whisper либо фейковый ASR в dev-режиме) и появляется в панели расшифровки.
   Реплики можно вручную править или удалять.
5. **AI-анализ.** После остановки записи жмём **«Анализировать»** —
   сессия переходит в `analyzed`, заполняются протокол (жалобы, анамнез, осмотр,
   аллергии, препараты), топ-3 диагноза, красные флаги и черновик плана лечения
   (медикаменты, обследования, немедикаментозные рекомендации, контрольный визит).
   Все блоки можно редактировать: править тексты протокола, выбирать или вводить
   свой диагноз, подтверждать/отклонять красные флаги, добавлять/удалять и
   переупорядочивать пункты плана.
6. **Подтверждение.** По кнопке **«К итоговому протоколу»** попадаем на
   `/app/sessions/:id/confirm` — read-only-карточка со всеми разделами. Если есть
   необработанные красные флаги, пункты плана без галочки «подтверждён» или не
   выбран диагноз — `/confirm` вернёт 422, а UI покажет, чего не хватает.
   Кнопка **«Подтвердить и сформировать PDF»** переводит сессию в `confirmed`
   и сразу скачивает PDF в браузере.
7. **PDF.** Для подтверждённой/закрытой сессии кнопка **«Скачать PDF»** (или
   `GET /api/v1/sessions/:id/pdf`) генерирует документ через WeasyPrint из
   Jinja-шаблона `backend/app/templates/protocol.html`. В шаблоне — шапка с данными
   врача и пациента, разделы протокола, итоговый диагноз с кодом МКБ-10,
   список красных флагов с отметкой «принято/отклонено» и структурированный план
   лечения по категориям.
8. **Завершение приёма.** Кнопка **«Завершить приём»** вызывает
   `POST /api/v1/sessions/:id/close`, сессия переходит в `closed`, дальнейшие
   правки протокола/плана/расшифровки запрещены (HTTP 409), но PDF и
   `/summary` остаются доступны. В списке `/app` такие сессии открываются на
   `/app/sessions/:id/view` — read-only-просмотр с возможностью повторно
   скачать PDF.
9. **Фильтры в списке.** На `/app` доступны табы «Все / Черновики /
   В процессе / Проанализированы / Подтверждённые / Закрытые» и поиск по ФИО
   пациента. Backend поддерживает параметры `?status=` и `?query=` у
   `GET /api/v1/sessions` и возвращает `total`.

Все ключевые действия пишутся в таблицу `audit_log`: `session_created`,
`consent_granted`, `analysis_run`, `diagnosis_selected`, `red_flag_ack`,
`protocol_confirmed`, `pdf_generated`, `session_closed` и т.д.

## Переменные окружения

| Переменная          | Где используется | Назначение                                                                     |
| ------------------- | ---------------- | ------------------------------------------------------------------------------ |
| `DATABASE_URL`      | backend          | Async SQLAlchemy DSN (asyncpg)                                                 |
| `JWT_SECRET`        | backend          | Секрет для подписи JWT                                                         |
| `OPENAI_API_KEY`    | backend          | Legacy-ключ OpenAI; используется как fallback, если `LLM_API_KEY`/`ASR_API_KEY` пусты |
| `LLM_API_KEY`       | backend          | Ключ LLM-провайдера (OpenAI / DeepSeek / Groq). Для LM Studio можно оставить пустым |
| `LLM_BASE_URL`      | backend          | OpenAI-совместимый endpoint LLM (должен содержать `/v1`)                       |
| `LLM_MODEL`         | backend          | Имя/слаг модели (для LM Studio — как отображается в его интерфейсе)            |
| `LLM_JSON_MODE`     | backend          | `json_schema` (OpenAI, строгая схема) или `json_object` (LM Studio / Ollama / DeepSeek) |
| `ASR_API_KEY`       | backend          | Ключ ASR (для локального faster-whisper-server не нужен)                       |
| `ASR_BASE_URL`      | backend          | OpenAI-совместимый endpoint Whisper                                            |
| `ASR_MODEL`         | backend          | Имя модели Whisper (например, `Systran/faster-whisper-small` или `whisper-1`)  |
| `CORS_ORIGINS`      | backend          | Список разрешённых origin'ов, через запятую                                    |
| `VITE_API_BASE_URL` | frontend         | Базовый URL REST API                                                           |

### Провайдеры LLM/ASR

По умолчанию стенд настроен на **полностью локальный** вариант: LM Studio на Mac-хосте
для LLM и контейнер `whisper` (faster-whisper-server) для распознавания речи. Это бесплатно
и не требует регистраций/оплаты.

**LM Studio (LLM).** Установите [LM Studio](https://lmstudio.ai), скачайте модель
(рекомендую `Qwen2.5 7B Instruct` или `Llama 3.1 8B Instruct` — хорошо держат JSON-режим
и русский) и запустите локальный сервер в разделе **Developer → Local Server** (порт `1234`).
В `.env`:

```
LLM_BASE_URL=http://host.docker.internal:1234/v1
LLM_MODEL=qwen2.5-7b-instruct
LLM_JSON_MODE=json_object
```

Из контейнера backend LM Studio доступна по `host.docker.internal` — соответствующий
`extra_hosts` уже прописан в `docker-compose.yml`.

**faster-whisper-server (ASR).** Запускается вместе с остальными сервисами через
`docker compose up`. При первом вызове `/transcripts` контейнер скачает модель
(`Systran/faster-whisper-small`, ≈460 MB) в volume `whisper_models`. На Apple Silicon
контейнер стартует через Rosetta (`platform: linux/amd64`), работает в CPU-режиме —
для коротких реплик ~5 сек этого достаточно.

**Переключение на облачных провайдеров** (если/когда появится доступ):

- **OpenAI:** `LLM_BASE_URL=https://api.openai.com/v1`, `LLM_MODEL=gpt-4o-mini`,
  `LLM_JSON_MODE=json_schema`; `ASR_BASE_URL=https://api.openai.com/v1`,
  `ASR_MODEL=whisper-1`; ключи — `LLM_API_KEY` / `ASR_API_KEY` (или один `OPENAI_API_KEY`).
- **DeepSeek** (только LLM): `LLM_BASE_URL=https://api.deepseek.com/v1`,
  `LLM_MODEL=deepseek-chat`, `LLM_JSON_MODE=json_object`.
- **Groq:** `LLM_BASE_URL=https://api.groq.com/openai/v1`,
  `LLM_MODEL=llama-3.1-70b-versatile`, `LLM_JSON_MODE=json_object`;
  ASR на Groq — `ASR_BASE_URL=https://api.groq.com/openai/v1`,
  `ASR_MODEL=whisper-large-v3`.

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
