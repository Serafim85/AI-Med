# Шаг 3 из 5 — Сессия приема, согласие, запись и расшифровка (ASR)

> Этот файл самодостаточен. Его можно подавать отдельному агенту без дополнительного контекста.

---

## 1. Контекст проекта

Разрабатываем **веб-приложение — AI-ассистент врача на приеме**.

**Идея:** во время приема приложение записывает диалог врача и пациента, расшифровывает его в реальном времени с разделением говорящих, структурирует в протокол, предлагает топ-3 диагноза и план лечения. Врач редактирует и подтверждает итоговый протокол, после чего формируется PDF.

**Роли в MVP:** только **врач** (UI) и **пациент** (голос).

**Полный скоуп MVP (все 5 шагов):** авторизация, создание сессии с ручным вводом пациента, согласие, запись и расшифровка, структурирование, диагнозы + красные флаги, план лечения, подтверждение → PDF, просмотр сессий. **Без** интеграций, истории пациента, мобильного приложения.

---

## 2. Зафиксированный tech stack

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x async, Alembic, PostgreSQL 16, Pydantic v2, `passlib[bcrypt]`, `python-jose`.

**Frontend:** React 18 + TS, Vite, TailwindCSS, React Router v6, TanStack Query, Zustand, axios.

**ASR:** OpenAI Whisper API (`whisper-1`) — используется в **этом шаге**. Ключ в `OPENAI_API_KEY`.

**LLM:** OpenAI gpt-4o-mini — **не используется в этом шаге** (идёт в Шаге 4).

**PDF:** WeasyPrint — не используется в этом шаге.

---

## 3. Структура репозитория и конвенции

```
backend/app/
  api/v1/         # роутеры; префикс /api/v1
  core/           # конфиг, security (JWT)
  db/             # async session, base
  models/         # SQLAlchemy
  schemas/        # Pydantic
  services/       # asr.py, llm.py, pdf.py
  main.py
frontend/src/
  api/            # axios-клиент + хуки react-query
  components/
  pages/
  store/          # zustand
  routes.tsx
  App.tsx
```

- URL: `/api/v1/...`, идентификаторы — UUID v4.
- Timestamps — UTC в БД.
- UI — русский.
- Axios автоматически добавляет Bearer-токен; 401 → редирект на `/login`.

---

## 4. Что уже сделано (результаты Шагов 1–2)

**Шаг 1:** монорепо, docker-compose (`backend`, `frontend`, `db`), `GET /api/v1/health`, Tailwind + TanStack Query на фронте, настроенный Alembic.

**Шаг 2:** таблицы БД — `users`, `appointment_sessions`, `transcripts`, `protocols`, `diagnosis_suggestions`, `red_flags`, `treatment_plans`, `treatment_plan_items`, `audit_log`. Авторизация врача: `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, JWT HS256, 12 часов. Демо-врач `demo@clinic.local / demo1234`. Фронт: страницы `/login` и защищённый `/app` с шапкой и заглушкой «Здесь будет список приёмов».

---

## 5. Ключевые сущности (напоминание из Шага 2)

```
appointment_sessions:
  id, doctor_id, patient_full_name, patient_age, patient_sex ('male'|'female'|'other'),
  appointment_type ('primary'|'follow_up'),
  status ('draft'|'recording'|'analyzed'|'confirmed'|'closed'),
  consent_given_at, created_at, updated_at

transcripts:
  id, session_id, speaker ('doctor'|'patient'|'unknown'),
  text, started_at_ms, ended_at_ms, confidence, edited_by_user, created_at

audit_log:
  id, user_id, session_id, action, payload_json, created_at
```

---

## 6. Задача ЭТОГО шага (Шаг 3)

Реализовать жизненный цикл сессии приема **до момента готовой и отредактированной расшифровки** (включая):

- CRUD сессий приема (только свои),
- ввод данных пациента,
- фиксацию согласия,
- запись аудио в браузере,
- потоковую отправку чанков на backend и распознавание через Whisper,
- разделение говорящих (упрощённо — см. 6.4),
- сохранение реплик в `transcripts`,
- отображение расшифровки в реальном времени,
- ручную правку и смену говорящего,
- завершение записи.

Топ-3 диагноза, план лечения и PDF в этом шаге **не делаются**.

### 6.1. Backend — эндпоинты сессии

`POST /api/v1/sessions` — создать сессию  
Вход: `{ patient_full_name, patient_age, patient_sex, appointment_type }`. Возвращает созданную сессию в статусе `draft`.

`GET /api/v1/sessions` — список сессий текущего врача (с пагинацией `limit`, `offset`, сортировка по `created_at desc`).

`GET /api/v1/sessions/{id}` — детали сессии (со всеми её `transcripts`).

`PATCH /api/v1/sessions/{id}` — обновить данные пациента (только если `status in ('draft','recording')`).

`POST /api/v1/sessions/{id}/consent` — зафиксировать согласие.  
Вход: `{ granted: true }`. Проставляет `consent_given_at = now()`. Запись в `audit_log` (`action="consent_granted"`).  
Если `granted=false` — возвращает 400, согласие не фиксируется, запись `action="consent_denied"`.

`POST /api/v1/sessions/{id}/start-recording` — переводит `status` в `recording`. Требует `consent_given_at != null`. Запись в `audit_log` (`action="recording_started"`).

`POST /api/v1/sessions/{id}/stop-recording` — переводит `status` в `draft` → `analyzed` **не здесь**; в этом шаге только возвращаем в `draft` (переход в `analyzed` будет в Шаге 4). Запись `action="recording_stopped"`.

`DELETE /api/v1/sessions/{id}/audio` — «удалить запись» (сценарий отказа пациента в процессе). Удаляет все строки `transcripts` этой сессии и возвращает `status = draft`. Запись `action="audio_deleted"`.

Все эндпоинты требуют авторизации; сессию можно читать/менять только её владельцу (`doctor_id == current_user.id`), иначе 404 (не 403, чтобы не утекала информация о существовании).

### 6.2. Backend — распознавание речи

Сервис `app/services/asr.py` с интерфейсом:

```python
class ASRService(Protocol):
    async def transcribe_chunk(self, audio_bytes: bytes, mime: str, language: str = "ru") -> ASRResult: ...
```

Реализация `OpenAIWhisperASR`: отправляет аудиочанк в OpenAI `audio/transcriptions` (`model=whisper-1`, `language=ru`), возвращает `{ text, confidence?: float | None }`.

**Эндпоинт загрузки чанка:**

`POST /api/v1/sessions/{id}/transcripts` (multipart/form-data)
- Файл поля: `audio` — blob фрагмента записи (webm/opus или wav).
- Поля формы: `speaker` (`doctor`|`patient`|`unknown`), `started_at_ms` (int), `ended_at_ms` (int).
- Серверный путь:
  1. Проверить что сессия в статусе `recording`.
  2. Отправить байты в `ASRService.transcribe_chunk`.
  3. Сохранить результат как новую запись `transcripts` с полученным `text` и `speaker` из формы.
  4. Вернуть созданный `transcript`.

> В MVP **диаризация упрощена**: говорящий определяется клиентом — через выбор активного микрофона или через кнопку «Переключить говорящего». Поле `speaker` всегда приходит от клиента. При желании — дополнительно можно сохранять `speaker='unknown'` и дать врачу поправить.

**Правка расшифровки:**

`PATCH /api/v1/sessions/{id}/transcripts/{tid}` — тело `{ text?: string, speaker?: 'doctor'|'patient'|'unknown' }`. При сохранении `edited_by_user = true`.

`DELETE /api/v1/sessions/{id}/transcripts/{tid}` — удаляет реплику.

### 6.3. Backend — прочее

- Схема Pydantic и типы enum'ов единообразны с БД.
- Все действия логируются в `audit_log` с `session_id`.
- Тесты (`pytest`): создание сессии, запрет доступа чужой сессии (404), фиксация согласия, невозможность start-recording без согласия. ASR-сервис в тестах подменяется фейковой реализацией через `app.dependency_overrides`.

### 6.4. Frontend — страницы и флоу

**Список приёмов `/app`** (вместо заглушки из Шага 2):
- Таблица/карточки с колонками: пациент, тип приёма, статус, дата создания.
- Кнопка «Новый приём» → открывает модалку/страницу создания.

**Создание сессии `/app/sessions/new`:**
- Поля: ФИО пациента (required), возраст (required, int 0..120), пол (radio), тип приёма (radio: первичный/повторный).
- Кнопка «Создать» → `POST /sessions` → редирект на `/app/sessions/:id`.

**Страница сессии `/app/sessions/:id`:**
Лейаут из трёх секций:
1. **Шапка сессии:** данные пациента, статус, кнопки действий.
2. **Блок согласия** (виден пока `consent_given_at == null`):
   - Текст-шаблон согласия на аудиозапись.
   - Чекбокс «Зачитал(а) пациенту, согласие получено».
   - Кнопка «Согласие получено» → `POST /consent { granted: true }`.
   - Кнопка «Отказ» → `POST /consent { granted: false }` → возврат к списку (сессию можно оставить без записи).
3. **Блок записи** (виден когда `consent_given_at != null`):
   - Переключатель активного говорящего: «Врач» ↔ «Пациент» (UI-состояние, передаётся в поле `speaker` при отправке чанка).
   - Кнопки «Начать запись» / «Пауза» / «Остановить».
   - Индикатор уровня звука.
   - Лента расшифровки — реплики идут сверху вниз в хронологическом порядке:
     - цветовая маркировка врач/пациент,
     - timestamp,
     - кнопки «Редактировать», «Сменить говорящего», «Удалить»,
     - visual hint для реплик с `confidence < 0.6` (если вернулось).
4. **Внизу:** кнопка «Удалить запись» (= `DELETE /audio`) с подтверждением.

**Запись аудио в браузере:**
- Использовать `MediaRecorder` с форматом `audio/webm;codecs=opus`.
- Разбивать поток на **чанки по ~5 секунд** (через `mediaRecorder.start(5000)` и `ondataavailable`).
- Каждый чанк сразу отправлять на `POST /sessions/:id/transcripts` с текущим выбранным `speaker` и `started_at_ms`/`ended_at_ms`.
- Полученную распознанную реплику добавлять в ленту (оптимистичный UI + подтверждение).
- При клике «Остановить» — прекратить запись, вызвать `POST /stop-recording`.

**Правка:**
- Инлайн-редактирование текста реплики (двойной клик → `textarea` → Enter/кнопка сохранить).
- Смена говорящего — dropdown на реплике.
- Удаление реплики — иконка корзины с подтверждением.

**Состояние сессии** хранить в Zustand-сторе `useSessionStore` (активная сессия, список реплик, isRecording, currentSpeaker).

### 6.5. Тесты и проверки
- Backend: см. 6.3.
- Frontend: достаточно прокликать руками, автоматические тесты не обязательны.

---

## 7. Definition of Done (критерии приёмки Шага 3)

1. Врач создаёт сессию, видит её в списке приёмов.
2. На экране сессии доступен блок согласия; после фиксации он скрывается, показывается блок записи.
3. Без согласия невозможно запустить запись — кнопка недоступна/запрос возвращает 400.
4. При старте записи браузер запрашивает микрофон; после разрешения идёт поток аудио.
5. Чанки по 5 секунд отправляются на backend, реплики появляются в ленте с правильным спикером и таймингом.
6. Врач может: редактировать текст, сменить говорящего, удалить реплику.
7. «Остановить запись» переводит сессию в `draft` и останавливает микрофон.
8. «Удалить запись» удаляет все `transcripts` и сбрасывает статус в `draft`.
9. Чужую сессию открыть нельзя (404).
10. В `audit_log` есть записи: `consent_granted`/`consent_denied`, `recording_started`, `recording_stopped`, `audio_deleted`.
11. `pytest` зелёный.

---

## 8. Явные ограничения этого шага

- **НЕ делаем** LLM-анализ, структурированный протокол, диагнозы, план лечения, красные флаги — это Шаг 4.
- **НЕ делаем** PDF — это Шаг 5.
- **НЕ делаем** продвинутую диаризацию — говорящего определяет клиент вручную.
- **НЕ храним** сырой аудиофайл долго: после успешной отправки чанка в Whisper бэкенд **не сохраняет аудио на диск** (только текст расшифровки идёт в БД). Это упрощает соответствие требованиям по медданным.
- **НЕ реализуем** офлайн-режим.

---

## 9. Что получит следующий шаг (Шаг 4) на вход

- Полный цикл записи: сессия с согласием и набором реплик в `transcripts`, привязанных к `session_id`, с разметкой по спикерам и таймингом.
- Endpoint `POST /sessions/:id/stop-recording`, возвращающий сессию в `draft` (Шаг 4 изменит переход: `stop-recording` будет триггером для анализа и перевода в `analyzed`).
