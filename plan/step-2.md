# Шаг 2 из 5 — База данных, основные сущности, авторизация врача

> Этот файл самодостаточен. Его можно подавать отдельному агенту без дополнительного контекста.

---

## 1. Контекст проекта

Разрабатываем **веб-приложение — AI-ассистент врача на приеме**.

Во время приема приложение записывает диалог врача и пациента, расшифровывает его, структурирует, предлагает диагноз и план лечения, а затем формирует PDF-протокол после подтверждения врачом.

**Роли в MVP:** только **врач** и **пациент** (пациент не взаимодействует с UI).

**Скоуп MVP (итоговый, все 5 шагов):** авторизация врача, создание сессии с ручным вводом данных пациента, согласие, запись и расшифровка диалога, структурирование протокола, топ-3 диагноза + красные флаги, план лечения, подтверждение → PDF, просмотр своих сессий. **Без** интеграций, истории пациента, мобильного приложения.

---

## 2. Зафиксированный tech stack

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x (async), Alembic, PostgreSQL 16, Pydantic v2, `passlib[bcrypt]`, `python-jose`, `pytest` + `httpx`.

**Frontend:** React 18 + TypeScript, Vite, TailwindCSS, React Router v6, TanStack Query, Zustand, axios.

**ASR/LLM:** OpenAI API (Whisper + gpt-4o-mini). **В этом шаге не используется.**

**PDF:** WeasyPrint. **В этом шаге не используется.**

**Инфра:** Docker Compose (`backend`, `frontend`, `db`).

---

## 3. Согласованная структура репозитория (напоминание)

```
backend/app/
  api/            # роутеры FastAPI v1
  core/           # конфиг, JWT, безопасность
  db/             # сессия SQLAlchemy, base
  models/         # SQLAlchemy модели
  schemas/        # Pydantic-схемы
  services/       # бизнес-логика
  main.py
backend/alembic/  # миграции
frontend/src/
  api/            # http-клиент
  components/
  pages/
  store/          # zustand
  routes.tsx
  App.tsx
  main.tsx
```

URL: `/api/v1/...`, идентификаторы — UUID v4, timestamps — UTC.

---

## 4. Что уже сделано (результат Шага 1)

- Монорепозиторий поднят, `docker compose up --build` запускает `backend`, `frontend`, `db`.
- FastAPI приложение отдаёт `GET /api/v1/health` → `{"status":"ok"}`.
- Frontend на Vite/React/Tailwind с главной страницей и кнопкой проверки health.
- Настроены `pydantic-settings` (читает `.env`: `DATABASE_URL`, `JWT_SECRET`, `OPENAI_API_KEY`, `CORS_ORIGINS`).
- Подключение к Postgres через async SQLAlchemy проверено.
- Alembic настроен, но миграций нет.
- Готовые пустые папки `app/models`, `app/schemas`, `app/services`.

---

## 5. Задача ЭТОГО шага (Шаг 2)

Реализовать **полную модель данных MVP, миграции, авторизацию врача и экран логина**. В этом шаге нет ни аудио, ни LLM, ни PDF.

### 5.1. Модель данных (все таблицы MVP — заводим сразу)

Создать SQLAlchemy-модели и миграцию Alembic для следующих таблиц. Все PK — UUID v4, все временные метки — `timestamptz`, default `now()`.

**`users`** (врачи)
- `id` UUID PK
- `email` text, unique, not null
- `password_hash` text, not null
- `full_name` text, not null
- `is_active` bool, default true
- `created_at`, `updated_at`

**`appointment_sessions`** (сессия приема)
- `id` UUID PK
- `doctor_id` UUID FK → `users.id`, not null
- `patient_full_name` text, not null
- `patient_age` int, not null
- `patient_sex` enum(`male`, `female`, `other`), not null
- `appointment_type` enum(`primary`, `follow_up`), not null
- `status` enum(`draft`, `recording`, `analyzed`, `confirmed`, `closed`), default `draft`
- `consent_given_at` timestamptz, nullable
- `created_at`, `updated_at`

**`transcripts`** (расшифровки реплик)
- `id` UUID PK
- `session_id` UUID FK → `appointment_sessions.id`, cascade delete
- `speaker` enum(`doctor`, `patient`, `unknown`), not null
- `text` text, not null
- `started_at_ms` int (offset от начала записи), nullable
- `ended_at_ms` int, nullable
- `confidence` float, nullable
- `edited_by_user` bool, default false
- `created_at`

**`protocols`** (структурированный протокол; 1:1 с сессией)
- `id` UUID PK
- `session_id` UUID FK → `appointment_sessions.id`, unique, cascade delete
- `complaints` text, default `''`
- `anamnesis` text, default `''`
- `examination` text, default `''`
- `allergies` text, default `''`
- `medications` text, default `''`
- `final_diagnosis` text, nullable
- `icd10_code` text, nullable
- `confirmed_at` timestamptz, nullable
- `created_at`, `updated_at`

**`diagnosis_suggestions`** (топ-N диагнозов от ИИ)
- `id` UUID PK
- `session_id` UUID FK → `appointment_sessions.id`, cascade delete
- `title` text, not null
- `icd10_code` text, nullable
- `probability` float (0..1)
- `reasoning` text
- `supporting_symptoms` text (plain или JSON-строка)
- `contradicting_symptoms` text
- `is_selected` bool, default false
- `created_at`

**`red_flags`**
- `id` UUID PK
- `session_id` UUID FK → `appointment_sessions.id`, cascade delete
- `label` text, not null
- `description` text
- `severity` enum(`low`, `medium`, `high`)
- `acknowledged_at` timestamptz, nullable
- `doctor_note` text, nullable
- `created_at`

**`treatment_plans`** (1:1 с сессией)
- `id` UUID PK
- `session_id` UUID FK → `appointment_sessions.id`, unique, cascade delete
- `created_at`, `updated_at`

**`treatment_plan_items`**
- `id` UUID PK
- `plan_id` UUID FK → `treatment_plans.id`, cascade delete
- `kind` enum(`medication`, `investigation`, `non_drug`, `follow_up`)
- `title` text, not null
- `details` text
- `dosage` text, nullable
- `duration` text, nullable
- `order_index` int, default 0
- `is_confirmed` bool, default false
- `created_at`, `updated_at`

**`audit_log`** (любые значимые действия: логин, старт записи, подтверждение, отказ от записи, отклонение red_flag и т.п.)
- `id` UUID PK
- `user_id` UUID FK → `users.id`, nullable
- `session_id` UUID FK → `appointment_sessions.id`, nullable
- `action` text, not null
- `payload_json` JSONB, nullable
- `created_at`

> Обязательно обеспечить индексы на `appointment_sessions.doctor_id`, `transcripts.session_id`, `diagnosis_suggestions.session_id`, `red_flags.session_id`, `treatment_plan_items.plan_id`.

### 5.2. Миграции

- Сгенерировать автомиграцию Alembic «initial schema».
- Убедиться, что `alembic upgrade head` применяется чисто на пустой БД.
- Добавить в README раздел «Применение миграций».

### 5.3. Seed-скрипт для демо-врача

- Создать консольную команду/скрипт `backend/scripts/seed_demo_doctor.py`, который создаёт одного врача: `demo@clinic.local` / `demo1234`, `full_name = "Демо Врач"`.
- Запуск: `docker compose exec backend python -m scripts.seed_demo_doctor`.

### 5.4. Авторизация врача (backend)

- Реализовать в `app/core/security.py`:
  - хеширование пароля через bcrypt,
  - выпуск JWT access-токена (HS256, срок 12 часов, поле `sub=user_id`),
  - зависимость `get_current_user`, достающая пользователя из Bearer-токена.
- Роутер `app/api/v1/auth.py`:
  - `POST /api/v1/auth/login` — принимает `{email, password}`, возвращает `{access_token, token_type: "bearer", user: {id, email, full_name}}`.
  - `GET /api/v1/auth/me` — возвращает текущего пользователя (через `get_current_user`).
- Ошибки логина → 401 с `{"detail": "Неверные учётные данные"}`.
- Логировать успешный логин в `audit_log` (`action = "login"`).

**Регистрацию через UI НЕ делаем** — только seed-скрипт.

### 5.5. Frontend — экран логина и защита маршрутов

- Страница `/login`: форма (email, пароль), кнопка «Войти».
- При успехе — сохранить токен в `localStorage` (ключ `auth_token`) и `user` в Zustand-сторе `useAuthStore`.
- axios-инстанс должен автоматически добавлять `Authorization: Bearer <token>` ко всем запросам.
- Обработка 401 в axios-интерсепторе: чистим стор и редиректим на `/login`.
- Компонент `<ProtectedRoute>`: если нет токена — редирект на `/login`.
- Главный лейаут `/app` после логина: верхний бар с `full_name` врача и кнопкой «Выйти»; в центре — заглушка **«Здесь будет список приёмов (Шаг 3)»**.
- Роутинг:
  - `/` → редирект на `/app` (если авторизован) или `/login`.
  - `/login` — форма.
  - `/app` — защищённый лейаут.
- При загрузке приложения, если есть токен, дёрнуть `GET /auth/me` и восстановить пользователя в сторе.

### 5.6. Тесты

- Backend: минимум один `pytest` на успешный логин и один на невалидный пароль (через `httpx.AsyncClient`). Поднимать тестовую БД (например, через `pytest-asyncio` + временная схема или SQLite — на ваш выбор, но предпочтительно тот же Postgres через `docker compose`).
- Frontend: не обязательно в этом шаге.

---

## 6. Definition of Done (критерии приёмки Шага 2)

1. `alembic upgrade head` создаёт все таблицы из раздела 5.1 без ошибок.
2. `python -m scripts.seed_demo_doctor` создаёт демо-врача идемпотентно (повторный запуск не падает).
3. `POST /api/v1/auth/login` c корректными кредами возвращает токен; с неверными — 401.
4. `GET /api/v1/auth/me` с валидным токеном возвращает профиль, без токена — 401.
5. На фронте можно зайти под `demo@clinic.local` / `demo1234`, увидеть шапку с ФИО и заглушку «Здесь будет список приёмов».
6. При ручной очистке `localStorage` и обновлении страницы происходит редирект на `/login`.
7. В `audit_log` появляется запись `action="login"` после успешного логина.
8. Pytest зелёный, `docker compose up` работает без ошибок.

---

## 7. Явные ограничения этого шага

- **НЕ делаем** регистрацию/восстановление пароля/смену пароля — только логин.
- **НЕ делаем** refresh-токены — один access-токен на 12 часов.
- **НЕ трогаем** аудио, расшифровки, LLM, PDF — таблицы есть, эндпоинтов нет.
- **НЕ делаем** роли, права, админ-панели — все врачи равны.

---

## 8. Что получит следующий шаг (Шаг 3) на вход

- Полностью готовая схема БД и миграции.
- Авторизация врача работает, фронт умеет логиниться и держит сессию.
- Есть защищённый лейаут `/app` с заглушкой, куда Шаг 3 будет добавлять список приёмов и экраны записи.
