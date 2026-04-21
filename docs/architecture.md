# Архитектура проекта «AI-ассистент врача»

Документ описывает устройство MVP: сервисы, поток данных, схему БД и
модульную структуру. Все диаграммы — в синтаксисе [Mermaid](https://mermaid.js.org/),
они рендерятся в превью Cursor / VSCode и на GitHub без дополнительных
настроек.

---

## 1. Системная архитектура (сервисы и окружение)

```mermaid
flowchart LR
    User(["Врач<br/>(браузер)"])

    subgraph Frontend["Frontend · aimed-frontend :5173"]
        UI["React 18 + Vite<br/>TailwindCSS<br/>React Router · TanStack Query · Zustand<br/>axios"]
        Recorder["useAudioRecorder<br/>MediaRecorder · stop/start cycle<br/>5-сек WebM/Opus"]
        UI --- Recorder
    end

    subgraph Backend["Backend · aimed-backend :8000"]
        API["FastAPI · /api/v1<br/>auth · sessions · transcripts<br/>analysis · finalization"]
        Services["services/<br/>asr.py · llm.py · pdf.py"]
        DBLayer["SQLAlchemy 2.x async<br/>+ Alembic миграции"]
        Tpl["Jinja2 шаблоны<br/>WeasyPrint"]
        API --> Services
        API --> DBLayer
        Services --> Tpl
    end

    subgraph DB["aimed-db :5432"]
        Postgres[("PostgreSQL 16<br/>users · sessions · transcripts<br/>protocols · diagnoses<br/>red_flags · treatment_plan_items<br/>audit_log")]
    end

    subgraph Whisper["aimed-whisper :9000"]
        FW["faster-whisper-server<br/>Silero VAD + CPU int8<br/>OpenAI-совместимый API"]
    end

    LMStudio[["LM Studio<br/>(хост Mac) :1234<br/>Qwen2.5-7B-Instruct-1M"]]

    User -->|HTTPS / WS| UI
    UI -->|REST JSON + multipart| API
    DBLayer -->|asyncpg| Postgres
    Services -->|OpenAI SDK<br/>/v1/audio/transcriptions| FW
    Services -.->|OpenAI SDK<br/>/v1/chat/completions<br/>JSON Schema| LMStudio

    classDef ext fill:#fef3c7,stroke:#b45309,color:#78350f
    class LMStudio ext
```

Всё, кроме LM Studio, запускается через `docker compose up`. LM Studio
живёт на Mac-хосте, backend-контейнер видит её через
`host.docker.internal` (в `docker-compose.yml` это прописано в
`extra_hosts`).

---

## 2. Жизненный цикл приёма (sequence)

```mermaid
sequenceDiagram
    autonumber
    actor D as Врач
    participant FE as Frontend
    participant API as FastAPI
    participant DB as Postgres
    participant W as Whisper
    participant LLM as LM Studio
    participant PDF as WeasyPrint

    D->>FE: Логин demo@clinic.local
    FE->>API: POST /auth/login
    API->>DB: SELECT users
    API-->>FE: JWT access_token

    D->>FE: "+ Новый приём", ФИО/возраст/пол
    FE->>API: POST /sessions
    API->>DB: INSERT appointment_session<br/>(status=draft)

    D->>FE: Чекбокс «Согласие» + подтверждение
    FE->>API: POST /sessions/:id/consent
    API->>DB: UPDATE consent + audit_log

    D->>FE: Старт записи (каждые 5 сек — цикл stop/start)
    loop каждые 5 секунд
        FE->>API: POST /sessions/:id/transcripts<br/>(multipart webm + speaker)
        API->>W: POST /v1/audio/transcriptions<br/>vad_filter=true
        W-->>API: verbose_json (segments)
        alt пустой текст (VAD или пост-фильтр)
            API-->>FE: 204 No Content
        else распознан текст
            API->>DB: INSERT transcript
            API-->>FE: TranscriptOut
        end
    end

    D->>FE: «Анализировать»
    FE->>API: POST /sessions/:id/analyze
    API->>DB: SELECT transcripts
    API->>LLM: chat.completions<br/>response_format=json_schema
    LLM-->>API: JSON (protocol + diagnoses + flags + plan)
    API->>DB: UPSERT protocol,<br/>INSERT diagnoses/flags/plan_items
    API-->>FE: AnalysisOut

    D->>FE: Правки + выбор диагноза<br/>+ ack красных флагов + подтверждение пунктов плана
    FE->>API: PATCH / POST /diagnoses/select / ...

    D->>FE: «Подтвердить и сформировать PDF»
    FE->>API: POST /sessions/:id/confirm
    API->>DB: UPDATE status=confirmed + audit_log
    FE->>API: GET /sessions/:id/pdf
    API->>DB: SELECT summary
    API->>PDF: render Jinja2 → PDF
    PDF-->>API: application/pdf
    API-->>FE: PDF blob
    FE-->>D: скачивание файла

    D->>FE: «Завершить приём»
    FE->>API: POST /sessions/:id/close
    API->>DB: UPDATE status=closed
```

---

## 3. Машина состояний сессии

```mermaid
stateDiagram-v2
    [*] --> draft : POST /sessions
    draft --> recording : POST /consent + POST /recording/start
    recording --> recording : POST /transcripts (чанк)
    recording --> analyzed : POST /recording/stop → POST /analyze
    analyzed --> analyzed : правки протокола / плана
    analyzed --> confirmed : POST /confirm (+ GET /pdf)
    confirmed --> closed : POST /close
    closed --> [*]

    note right of analyzed
      на этом шаге:
      — выбрать один диагноз
      — ack все red_flags
      — подтвердить/удалить
        все treatment_plan_items
    end note

    note right of confirmed
      read-only в UI,
      но PDF ещё можно перекачать
    end note
```

---

## 4. Схема БД (ER)

```mermaid
erDiagram
    users ||--o{ appointment_sessions : "doctor_id"
    appointment_sessions ||--o{ transcripts : "session_id"
    appointment_sessions ||--o| protocols : "session_id"
    appointment_sessions ||--o{ diagnosis_suggestions : "session_id"
    appointment_sessions ||--o{ red_flags : "session_id"
    appointment_sessions ||--o| treatment_plans : "session_id"
    treatment_plans ||--o{ treatment_plan_items : "plan_id"
    users ||--o{ audit_log : "actor_id"
    appointment_sessions ||--o{ audit_log : "session_id"

    users {
        uuid id PK
        string email UK
        string password_hash
        string full_name
        bool is_active
        timestamptz created_at
    }

    appointment_sessions {
        uuid id PK
        uuid doctor_id FK
        string patient_full_name
        int patient_age
        enum patient_sex
        enum appointment_type
        enum status "draft|recording|analyzed|confirmed|closed"
        timestamptz consent_at
        timestamptz created_at
    }

    transcripts {
        uuid id PK
        uuid session_id FK
        enum speaker "doctor|patient|unknown"
        text text
        int started_at_ms
        int ended_at_ms
        float confidence
        bool edited_by_user
    }

    protocols {
        uuid id PK
        uuid session_id FK "UNIQUE"
        text complaints
        text anamnesis
        text examination
        text allergies
        text medications
        timestamptz updated_at
    }

    diagnosis_suggestions {
        uuid id PK
        uuid session_id FK
        string title
        string icd10_code
        float probability
        text reasoning
        jsonb supporting_symptoms
        jsonb contradicting_symptoms
        bool is_selected
    }

    red_flags {
        uuid id PK
        uuid session_id FK
        string label
        text description
        enum severity "low|medium|high"
        timestamptz acknowledged_at
        text doctor_note
    }

    treatment_plans {
        uuid id PK
        uuid session_id FK "UNIQUE"
    }

    treatment_plan_items {
        uuid id PK
        uuid plan_id FK
        enum kind "medication|investigation|non_drug|follow_up"
        string title
        text details
        string dosage
        string duration
        int order_index
        bool is_confirmed
    }

    audit_log {
        uuid id PK
        uuid session_id FK
        uuid actor_id FK
        string event "session_created, consent_granted, analysis_run, ..."
        jsonb payload
        timestamptz created_at
    }
```

---

## 5. Модульная структура backend'а

```mermaid
flowchart TB
    subgraph app["backend/app/"]
        subgraph api["api/v1/"]
            auth_r["auth.py<br/>/auth/login · /me"]
            sess_r["sessions.py<br/>CRUD · consent · recording<br/>transcripts (vad-filter 204)"]
            ana_r["analysis.py<br/>/analyze · protocol · diagnoses<br/>red_flags · treatment_plan"]
            fin_r["finalization.py<br/>/summary · /confirm · /pdf · /close"]
        end

        subgraph core["core/"]
            cfg["config.py<br/>pydantic-settings<br/>LLM_* · ASR_* · CORS"]
            sec["security.py<br/>bcrypt · JWT · get_current_user"]
        end

        subgraph models["models/ (SQLAlchemy)"]
            m["user · appointment_session<br/>transcript · protocol<br/>diagnosis · red_flag<br/>treatment_plan* · audit_log"]
        end

        subgraph services["services/"]
            asr["asr.py<br/>OpenAI-совместимый<br/>+ VAD · hallucination filter"]
            llm["llm.py<br/>Structured Outputs<br/>parse_llm_response"]
            pdfs["pdf.py<br/>WeasyPrint · Jinja2"]
        end

        subgraph schemas["schemas/ (Pydantic)"]
            sch["auth · user · session<br/>transcript · analysis<br/>protocol · diagnosis<br/>red_flag · treatment_plan<br/>finalization"]
        end

        tpls["templates/<br/>protocol.html · protocol.css"]
        db["db/session.py<br/>async engine/session"]
    end

    api --> services
    api --> models
    api --> schemas
    api --> sec
    services --> cfg
    services --> tpls
    models --> db
    sec --> db
```

---

## 6. Модульная структура frontend'а

```mermaid
flowchart TB
    subgraph src["frontend/src/"]
        subgraph pages["pages/"]
            p1["LoginPage"]
            p2["SessionsListPage<br/>(фильтры статуса · поиск)"]
            p3["SessionCreatePage"]
            p4["SessionDetailPage<br/>consent · recording · AnalysisSection"]
            p5["SessionConfirmPage<br/>(ref-guarded confirm + PDF)"]
            p6["SessionViewPage<br/>(read-only)"]
        end

        subgraph comps["components/"]
            c1["ProtectedRoute · AppLayout"]
            c2["TranscriptItem"]
            c3["analysis/<br/>AnalysisSection · RedFlagsPanel<br/>ProtocolPanel · DiagnosesPanel<br/>TreatmentPlanPanel"]
            c4["SessionSummaryView"]
        end

        subgraph hooks["hooks/"]
            h1["useAudioRecorder<br/>stop/start цикл 5 сек"]
        end

        subgraph store["store/ (Zustand)"]
            s1["auth<br/>token + user"]
            s2["session<br/>pending chunks · recorder state"]
        end

        subgraph api["api/"]
            a1["client.ts<br/>axios + JWT interceptor + 401-redirect"]
            a2["sessions.ts · analysis.ts<br/>finalization.ts"]
        end

        routes["routes.tsx"]
        main["main.tsx<br/>StrictMode · Router · QueryClient"]
    end

    main --> routes
    routes --> pages
    pages --> comps
    pages --> hooks
    pages --> store
    pages --> api
    api --> a1
```

---

## Ключевые архитектурные решения

1. **Никакого персиста аудио.** Байты чанка живут в памяти backend'а
   только во время вызова Whisper — в БД уходит только распознанный
   текст. После запроса `audio_bytes = b""`.
2. **JWT + middleware 401.** Фронт держит токен в `useAuthStore` +
   `localStorage`; axios-интерсептор на 401 чистит стор и уводит на
   `/login`.
3. **Двухслойная гарантия JSON.** `response_format=json_schema` на
   стороне LLM + `parse_llm_response` с локальной валидацией (границы
   вероятности, `≤3` диагноза, enum-ы, сортировка по убыванию
   probability). Даже если LLM вернёт мусор, до БД он не доедет.
4. **Status-based authorization.** Каждый модифицирующий эндпоинт
   сессий, транскриптов, диагнозов, плана проверяет `session.status` и
   возвращает `409`, если статус уже `confirmed` / `closed`. PDF и
   `/summary` доступны в любом терминальном статусе.
5. **`audit_log` на каждое значимое событие:** `session_created`,
   `consent_granted`, `analysis_run`, `diagnosis_selected`,
   `red_flag_ack`, `protocol_confirmed`, `pdf_generated`,
   `session_closed` — облегчит добавление отчётов, уведомлений и
   интеграций в будущем.
6. **Потоковая расшифровка через цикл stop/start.** Каждые 5 секунд
   фронт делает `MediaRecorder.stop()` + `MediaRecorder.start()` на
   одном и том же `MediaStream`. Так каждый загружаемый WebM —
   самодостаточный файл с EBML-заголовками, который faster-whisper
   умеет декодировать. Если бы использовался timeslice-режим, второй и
   последующие чанки были бы «сырыми» фрагментами без заголовков.
7. **VAD + пост-фильтр галлюцинаций.** На стороне Whisper включён
   Silero-VAD (`vad_filter=true`, `no_speech_threshold=0.6`,
   `temperature=0`), а backend дополнительно проверяет текст на типовые
   артефакты («Субтитры сделал DimaTorzok», «Продолжение следует» и
   пр.). При пустом результате API возвращает `204 No Content`, в БД
   ничего не пишется.
