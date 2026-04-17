# Шаг 4 из 5 — AI-анализ: структурирование, диагнозы, красные флаги, план лечения

> Этот файл самодостаточен. Его можно подавать отдельному агенту без дополнительного контекста.

---

## 1. Контекст проекта

Разрабатываем **веб-приложение — AI-ассистент врача на приеме**.

Во время приёма приложение записывает диалог врача и пациента, расшифровывает его, **структурирует информацию, предлагает топ-3 диагноза, подсвечивает красные флаги и формирует план лечения**. Врач редактирует и подтверждает итоговый протокол, после чего формируется PDF.

**Роли в MVP:** только **врач** (UI) и **пациент** (голос).

**Полный скоуп MVP (все 5 шагов):** авторизация, сессия + пациент, согласие, запись/расшифровка, **структурирование + диагнозы + план (этот шаг)**, подтверждение → PDF, просмотр сессий. **Без** интеграций, истории пациента, мобильного приложения.

---

## 2. Зафиксированный tech stack

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x async, Alembic, PostgreSQL 16, Pydantic v2, `passlib[bcrypt]`, `python-jose`.

**Frontend:** React 18 + TS, Vite, TailwindCSS, React Router v6, TanStack Query, Zustand, axios.

**LLM:** OpenAI `gpt-4o-mini` через OpenAI SDK. Ключ — `OPENAI_API_KEY`. Мы используем **Structured Outputs / JSON-схемы** для надёжного парсинга ответа.

**ASR:** Whisper — используется в Шаге 3, здесь уже не нужен.

**PDF:** WeasyPrint — идёт в Шаге 5.

---

## 3. Структура репозитория и конвенции

```
backend/app/
  api/v1/         # роутеры; префикс /api/v1
  core/           # конфиг, security
  db/
  models/
  schemas/
  services/       # asr.py, llm.py (!), pdf.py
  main.py
frontend/src/
  api/, components/, pages/, store/, routes.tsx, App.tsx
```

- URL: `/api/v1/...`, UUID v4, UTC.
- UI — русский. Медицинские термины в UI тоже на русском.
- Авторизация — Bearer JWT, доступ только к своим сессиям (иначе 404).

---

## 4. Что уже сделано (Шаги 1–3)

**Шаг 1:** монорепо, docker-compose (`backend`, `frontend`, `db`).

**Шаг 2:** модель данных — `users`, `appointment_sessions`, `transcripts`, `protocols`, `diagnosis_suggestions`, `red_flags`, `treatment_plans`, `treatment_plan_items`, `audit_log`. JWT-авторизация, демо-врач.

**Шаг 3:** CRUD сессий, согласие, запись аудио в браузере и распознавание через Whisper, сохранение реплик в `transcripts` с разметкой спикеров, ручная правка. Эндпоинт `POST /sessions/:id/stop-recording` возвращает статус `draft`. Все действия пишутся в `audit_log`.

---

## 5. Ключевые сущности (напоминание)

```
appointment_sessions:
  id, doctor_id, patient_full_name, patient_age, patient_sex,
  appointment_type, status ('draft'|'recording'|'analyzed'|'confirmed'|'closed'),
  consent_given_at, created_at, updated_at

transcripts:
  id, session_id, speaker, text, started_at_ms, ended_at_ms, confidence, edited_by_user

protocols (1:1 session):
  id, session_id, complaints, anamnesis, examination, allergies, medications,
  final_diagnosis, icd10_code, confirmed_at

diagnosis_suggestions:
  id, session_id, title, icd10_code, probability, reasoning,
  supporting_symptoms, contradicting_symptoms, is_selected

red_flags:
  id, session_id, label, description, severity ('low'|'medium'|'high'),
  acknowledged_at, doctor_note

treatment_plans (1:1 session):
  id, session_id
treatment_plan_items:
  id, plan_id, kind ('medication'|'investigation'|'non_drug'|'follow_up'),
  title, details, dosage, duration, order_index, is_confirmed
```

---

## 6. Задача ЭТОГО шага (Шаг 4)

Реализовать ядро **ИИ-анализа**: по набору реплик сессии автоматически заполнить `protocols`, создать `diagnosis_suggestions` (топ-3), `red_flags`, `treatment_plan` + `treatment_plan_items`. Дать врачу UI для ревью и редактирования всего этого.

Формирование PDF и финальное подтверждение → в Шаге 5.

### 6.1. LLM-сервис

Файл `app/services/llm.py`.

Абстракция:

```python
class LLMService(Protocol):
    async def analyze_dialogue(
        self,
        patient: PatientContext,   # age, sex, appointment_type
        transcript: list[TranscriptTurn],  # [{speaker, text}]
    ) -> LLMAnalysisResult: ...
```

Реализация `OpenAILLM`:
- Модель `gpt-4o-mini`, temperature 0.2, max_tokens достаточно для ответа.
- Режим — **JSON Schema / Structured Outputs** (через `response_format={"type":"json_schema", ...}`).
- Системный промпт фиксирует:
  - роль: «Ты ИИ-ассистент врача, помогаешь структурировать информацию с приёма на русском языке».
  - безопасность: «Твои предложения — только справочные. Ответственность несёт врач. Если данных недостаточно — честно указывай это».
  - формат: строго по схеме, без свободного текста вне схемы.

**JSON-схема результата (единым вызовом):**

```json
{
  "protocol": {
    "complaints": "string",
    "anamnesis": "string",
    "examination": "string",
    "allergies": "string",
    "medications": "string"
  },
  "red_flags": [
    { "label": "string", "description": "string", "severity": "low|medium|high" }
  ],
  "diagnosis_suggestions": [
    {
      "title": "string",
      "icd10_code": "string|null",
      "probability": 0.0,
      "reasoning": "string",
      "supporting_symptoms": ["string"],
      "contradicting_symptoms": ["string"]
    }
  ],
  "treatment_plan": [
    {
      "kind": "medication|investigation|non_drug|follow_up",
      "title": "string",
      "details": "string",
      "dosage": "string|null",
      "duration": "string|null"
    }
  ]
}
```

Ограничения и валидация:
- `diagnosis_suggestions` ≤ 3, `probability` в [0,1], отсортированы по убыванию probability.
- `red_flags` может быть пустым.
- Если расшифровка слишком короткая (< 30 слов) — LLM должна вернуть пустой `treatment_plan` и `diagnosis_suggestions`, и `red_flags=[]`, и заполнить `complaints = "Недостаточно данных для анализа"`.

### 6.2. Проверка конфликтов (простая, на стороне backend)

После получения результата LLM:
1. Выпарсить из `protocol.allergies` и `protocol.medications` строковый список (разделители: запятая, точка с запятой, перенос).
2. Для каждого `treatment_plan` item с `kind == "medication"` отметить флаг `conflict` если `title` (без регистра) содержит подстроку из аллергий, или совпадает с уже принимаемым препаратом.
3. Флаг передаётся на фронт отдельным полем DTO (в БД не храним в этом шаге).

### 6.3. Backend — эндпоинты анализа и редактирования

**Запуск анализа:**

`POST /api/v1/sessions/{id}/analyze`
- Предусловия: сессия владеется текущим врачом; есть хотя бы одна реплика в `transcripts`.
- Логика:
  1. Если у сессии уже есть `protocols`/`diagnosis_suggestions`/`red_flags`/`treatment_plans` — удалить их и создать заново (перезапуск анализа).
  2. Собрать `transcript` (упорядочить по `started_at_ms`, then `created_at`).
  3. Вызвать `LLMService.analyze_dialogue(...)`.
  4. Сохранить результат в соответствующие таблицы.
  5. Перевести сессию в статус `analyzed`.
  6. Записать в `audit_log` `action="analysis_completed"`, в payload — длина транскрипта и кол-во предложений.
- Ответ: полная «карточка анализа» (см. 6.4).

Допустимо сделать операцию синхронной в рамках MVP (до ~20 секунд ждать в API). Если дольше — можно рассмотреть SSE/WS, но это необязательно.

**Получение карточки анализа:**

`GET /api/v1/sessions/{id}/analysis` → возвращает:
```json
{
  "session": { ... },
  "protocol": { ... },
  "diagnosis_suggestions": [ ... ],
  "red_flags": [ ... ],
  "treatment_plan": {
    "id": "...",
    "items": [
      { ..., "conflict": false }
    ]
  }
}
```

**Редактирование протокола:**

`PATCH /api/v1/sessions/{id}/protocol` — тело со всеми текстовыми полями протокола (`complaints`, `anamnesis`, `examination`, `allergies`, `medications`, `final_diagnosis`, `icd10_code`). Любое поле опционально.

**Выбор диагноза:**

`POST /api/v1/sessions/{id}/diagnosis-suggestions/{sid}/select` — ставит `is_selected=true` для выбранного и `false` для остальных. Копирует `title`/`icd10_code` в `protocol.final_diagnosis`/`protocol.icd10_code`. Записывает `audit_log` `action="diagnosis_selected"`.

`POST /api/v1/sessions/{id}/protocol/custom-diagnosis` — врач вводит свой диагноз: `{ title, icd10_code?: string|null, reason?: string }`. Снимает `is_selected` со всех предложений, проставляет `protocol.final_diagnosis` / `icd10_code`. Audit `action="custom_diagnosis_entered"` (в payload — `reason`).

**Red flags:**

`POST /api/v1/sessions/{id}/red-flags/{rid}/acknowledge` — `{ accepted: boolean, note?: string }`. Проставляет `acknowledged_at=now()`, `doctor_note=note`. Если `accepted=false` — `note` обязателен. Audit `action="red_flag_acknowledged"` или `action="red_flag_dismissed"`.

**План лечения — CRUD элементов:**

- `POST   /api/v1/sessions/{id}/treatment-plan/items` — добавить пункт (body: `kind, title, details?, dosage?, duration?, order_index?`). Возвращает пункт.
- `PATCH  /api/v1/sessions/{id}/treatment-plan/items/{iid}` — обновить любой набор полей, включая `is_confirmed`.
- `DELETE /api/v1/sessions/{id}/treatment-plan/items/{iid}` — удалить.
- `POST   /api/v1/sessions/{id}/treatment-plan/reorder` — body `{ ordered_ids: [uuid...] }` — массово переписывает `order_index`.

Все записи → в `audit_log` с соответствующими `action`.

### 6.4. Frontend — UI анализа

На странице сессии `/app/sessions/:id` из Шага 3 добавить **экран «Анализ»**, появляющийся после остановки записи. Рекомендуемый UX:

**Кнопка «Анализировать»** — видна когда `status == draft` и есть реплики. Клик → показывает спиннер «Идёт анализ диалога…» и дёргает `POST /analyze`.

После успеха экран сессии переключается в 4 блока:

1. **Красные флаги** (если есть):
   - Красная полоса вверху.
   - Карточки с `label`, `description`, `severity` (цветовое кодирование).
   - Для каждой: кнопка «Принять» (по умолчанию — зафиксирует `accepted=true`) или «Отклонить» (требует текстовое пояснение).
   - Показывается статус: «Подтверждено врачом» / «Отклонено: <note>».

2. **Структурированный протокол** (редактируемая форма):
   - Поля: жалобы, анамнез, осмотр, аллергии, принимаемые препараты.
   - Каждое поле — `textarea` с автосохранением (debounce 800 мс) через `PATCH /protocol`.

3. **Топ-3 диагноза:**
   - Карточки с `title`, `icd10_code`, `probability` (прогресс-бар), `reasoning`.
   - Раскрывашки: «За» (supporting_symptoms), «Против» (contradicting_symptoms).
   - Кнопка «Выбрать» на каждой карточке.
   - Снизу альтернатива: «Указать свой диагноз» — форма с полем названия, ICD-10 (опционально) и «причина несогласия».
   - Выбранный диагноз визуально подсвечивается.

4. **План лечения:**
   - Группировка по `kind`: «Медикаменты», «Обследования», «Немедикаментозные рекомендации», «Контрольный визит».
   - В каждом пункте: заголовок, детали, дозировка/длительность (если есть), чекбокс «Подтверждено».
   - Если backend пометил пункт-медикамент как `conflict: true` (аллергия/конфликт) — карточка в рамке предупреждения с текстом «Внимание: возможный конфликт с аллергией/приёмом препаратов».
   - Кнопки: «Редактировать», «Удалить», «Добавить пункт» (модалка с выбором kind).
   - Drag-n-drop или кнопки «вверх/вниз» для сортировки → `POST /reorder`.

5. **Внизу экрана:**
   - Кнопка **«К итоговому протоколу»** → оставляем её видимой, но в этом шаге она ведёт на **заглушку** `/app/sessions/:id/confirm` с текстом «Подтверждение и PDF — Шаг 5».
   - Кнопка «Перезапустить анализ» (повторно вызывает `POST /analyze`, предупреждение о потере правок предложений).

**Состояние:** расширить `useSessionStore` — добавить `analysis` (protocol, diagnoses, redFlags, planItems). Использовать TanStack Query для загрузки `GET /analysis` + локальные мутации для редактирования.

### 6.5. Тесты

Backend (`pytest`):
- Тест успешного анализа с замоканным `LLMService` (возвращающим фикстурный JSON).
- Тест: повторный вызов `/analyze` чистит старые записи и создаёт новые.
- Тест: `/analyze` без реплик → 400.
- Тест выбора диагноза и проставления `final_diagnosis` в протоколе.
- Тест редактирования пункта плана и изменения порядка.

---

## 7. Definition of Done (критерии приёмки Шага 4)

1. `POST /api/v1/sessions/:id/analyze` принимает реплики из `transcripts`, вызывает LLM (через настоящий OpenAI при наличии ключа и через мок в тестах), сохраняет протокол/диагнозы/красные флаги/план, переводит сессию в `analyzed`.
2. `GET /analysis` возвращает полную карточку со всеми блоками и флагами конфликтов в плане.
3. В UI:
   - после остановки записи видна кнопка «Анализировать»;
   - после анализа видны 4 блока (красные флаги / протокол / диагнозы / план);
   - все поля протокола редактируются с автосохранением;
   - выбор диагноза обновляет `final_diagnosis` в протоколе;
   - свой диагноз вводится через отдельную форму;
   - пункты плана можно добавлять, редактировать, удалять, сортировать и подтверждать;
   - конфликт-пункты подсвечены.
4. Красные флаги можно «принять» или «отклонить» с комментарием.
5. Повторный запуск анализа корректно перезаписывает данные.
6. В `audit_log` появляются: `analysis_completed`, `diagnosis_selected`/`custom_diagnosis_entered`, `red_flag_acknowledged`/`red_flag_dismissed`, события по плану лечения.
7. `pytest` зелёный.
8. Кнопка «К итоговому протоколу» ведёт на заглушку, подготовленную для Шага 5.

---

## 8. Явные ограничения этого шага

- **НЕ генерируем PDF** — это Шаг 5.
- **НЕ подтверждаем протокол финально** (т.е. `protocols.confirmed_at` и `status='confirmed'` — в Шаге 5).
- **НЕ используем** внешние справочники ICD/SNOMED/РЛС — ICD-10 коды приходят текстом из LLM, проверка препаратов делается простым сравнением строк.
- **НЕ реализуем** долгие очереди/фоновые задачи — анализ синхронный.
- **НЕ реализуем** кнопку «полезно/не полезно» по предложениям (UC-15 из планов — это «Could», не в MVP).

---

## 9. Что получит следующий шаг (Шаг 5) на вход

- Сессия в статусе `analyzed` с заполненными `protocol`, `diagnosis_suggestions` (с выбранным), `red_flags` (обработанными), `treatment_plan` с подтверждёнными пунктами.
- Кнопка «К итоговому протоколу» → заглушка `/app/sessions/:id/confirm`, которую Шаг 5 наполнит содержимым.
- Все данные, нужные для PDF, уже есть в БД.
