# YouTube Auto Studio - План проекта

> Локальная студия для автоматической генерации YouTube-видео.
> Один пользователь, много каналов, память между видео, мультиязычность.

---

## 1. Цели проекта

Построить локальное приложение которое:

- Управляет несколькими **каналами (проектами)** с разной тематикой и стилем
- Генерирует **уникальные сценарии** (без повторов) на 10-30+ минут
- Озвучивает их **локально (Kokoro)** или с подключаемыми платными API
- Поддерживает **мультиязычный экспорт** (RU/EN/ES и т.д.) одной кнопкой
- Создаёт видеоряд (от стоков до AI), обложку, финальный рендер
- Показывает удобный **GUI** со статистикой, превью, историей
- Помнит контекст канала и прошлые сценарии (сжато, экономя токены)

---

## 2. Технологический стек

### Backend
- **Python 3.11+**
- **FastAPI** - API сервер
- **SQLAlchemy 2.0** + **Alembic** - ORM и миграции
- **SQLite** - локальная БД (один файл, ничего настраивать не надо)
- **Pydantic v2** - валидация и схемы
- **APScheduler** или FastAPI `BackgroundTasks` - фоновые задачи генерации

### Frontend
- **Vite + React 18 + TypeScript**
- **Tailwind CSS** + **shadcn/ui** - компоненты
- **TanStack Query** - запросы к API
- **Zustand** - локальный state
- **Recharts** - графики статистики
- **Lucide React** - иконки

### AI / ML
- **Anthropic Claude API** (Sonnet 4.5) - сценарии, переводы, саммари
- **Kokoro TTS** локально - озвучка (бесплатно, GPU)
- **Pexels API** - стоковое видео (бесплатно)
- **Replicate API** (Flux) - обложки (опционально, pay-per-use)

### Видео
- **FFmpeg** (системный) + **MoviePy** - сборка, монтаж
- **faster-whisper** - авто-субтитры из аудио

### Структура запуска
- Backend: `uvicorn` на `localhost:8000`
- Frontend: `vite dev` на `localhost:5173`
- Один скрипт `start.sh` / `start.bat` поднимает оба

---

## 3. Структура папок

```
youtube-auto/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entry
│   │   ├── api/
│   │   │   ├── projects.py          # CRUD каналов
│   │   │   ├── videos.py            # CRUD видео
│   │   │   ├── generation.py        # запуск пайплайна
│   │   │   ├── tts.py               # озвучка
│   │   │   ├── memory.py            # история сценариев
│   │   │   └── stats.py             # статистика
│   │   ├── core/
│   │   │   ├── config.py            # настройки, ключи API
│   │   │   ├── database.py          # SQLAlchemy engine
│   │   │   ├── llm.py               # Claude API клиент
│   │   │   └── paths.py             # пути к проектам
│   │   ├── models/                  # SQLAlchemy модели
│   │   │   ├── project.py
│   │   │   ├── video.py
│   │   │   ├── script.py
│   │   │   ├── audio.py
│   │   │   └── generation_log.py
│   │   ├── schemas/                 # Pydantic схемы
│   │   ├── services/                # бизнес-логика
│   │   │   ├── script_generator.py  # генерация сценария + проверка уникальности
│   │   │   ├── script_analyzer.py   # извлечение hook, summary, topics
│   │   │   ├── tts_service.py       # обёртка над Kokoro + manual
│   │   │   ├── translator.py        # перевод сценария на N языков
│   │   │   ├── video_builder.py     # сборка финального mp4
│   │   │   ├── thumbnail_gen.py     # обложка
│   │   │   ├── memory_service.py    # сжатие истории, выборка контекста
│   │   │   └── pipeline.py          # оркестратор всех шагов
│   │   └── utils/
│   ├── alembic/                     # миграции БД
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx        # главная (все проекты)
│   │   │   ├── ProjectView.tsx      # один канал
│   │   │   ├── VideoView.tsx        # одно видео
│   │   │   ├── NewVideo.tsx         # форма создания
│   │   │   └── Settings.tsx
│   │   ├── components/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── ProjectCard.tsx
│   │   │   ├── VideoCard.tsx
│   │   │   ├── ScriptEditor.tsx
│   │   │   ├── AudioPlayer.tsx
│   │   │   ├── StatsPanel.tsx
│   │   │   ├── MemoryViewer.tsx
│   │   │   └── ui/                  # shadcn компоненты
│   │   ├── lib/
│   │   │   ├── api.ts               # клиент к FastAPI
│   │   │   └── types.ts
│   │   ├── store/
│   │   │   └── projectStore.ts
│   │   └── App.tsx
│   ├── package.json
│   └── tailwind.config.ts
├── data/
│   ├── db.sqlite                    # вся БД
│   └── projects/
│       └── <project_id>/
│           ├── config.json
│           ├── memory.jsonl         # сжатые саммари сценариев
│           └── videos/
│               └── <video_id>/
│                   ├── script_ru.md
│                   ├── script_en.md
│                   ├── analysis.json    # hook, summary, topics
│                   ├── audio/
│                   │   ├── ru.wav
│                   │   └── en.wav
│                   ├── assets/         # картинки, видео-куски
│                   ├── thumbnail.png
│                   └── final_ru.mp4
├── scripts/
│   ├── start.sh                     # запуск backend+frontend
│   ├── start.bat
│   └── init_db.py
├── .env.example
├── README.md
└── CLAUDE.md                        # инструкции для Claude Code
```

---

## 4. Схема базы данных

### `projects` - каналы
```
id              UUID, PK
name            str, unique         # "Космос для всех"
description     text
niche           str                 # "научпоп", "ASMR", "разборы фильмов"
target_audience str
style_prompt    text                # системный промпт под канал
language_primary str                 # "ru"
languages_export json                # ["ru", "en", "es"]
voice_settings  json                # {ru: "rf_alpha", en: "af_heart"}
tts_mode        str                 # "local" / "manual"
created_at      datetime
updated_at      datetime
```

### `videos`
```
id              UUID, PK
project_id      FK -> projects
title           str
topic_brief     text                # тема для генерации
status          str                 # draft/generating/ready/error
duration_sec    int, nullable
created_at      datetime
published_at    datetime, nullable
```

### `scripts`
```
id              UUID, PK
video_id        FK -> videos
language        str                 # "ru", "en"
content_md      text                # сам сценарий
word_count      int
duration_estimate_sec int
is_primary      bool                # основной язык или перевод
created_at      datetime
```

### `script_analysis`
```
id              UUID, PK
script_id       FK -> scripts (unique)
hook            str                 # первые 1-2 предложения
summary_short   str                 # 1 предложение - суть
summary_long    text                # 3-5 предложений
key_points      json                # ["тезис1", "тезис2", ...]
topics          json                # ["квантовая физика", "история"]
structure       json                # ["intro", "point1", ...]
tone            str                 # "образовательный", "развлекательный"
created_at      datetime
```

### `audio_tracks`
```
id              UUID, PK
script_id       FK -> scripts
file_path       str
duration_sec    int
voice_id        str
engine          str                 # "kokoro" / "manual" / "elevenlabs"
status          str                 # ready/failed
created_at      datetime
```

### `video_assets`
```
id              UUID, PK
video_id        FK -> videos
language        str, nullable       # для финальных рендеров
type            str                 # "thumbnail", "final", "footage"
file_path       str
metadata        json
created_at      datetime
```

### `generation_logs`
```
id              UUID, PK
video_id        FK -> videos
stage           str                 # "script", "analysis", "tts", "render"
model_used      str, nullable
input_tokens    int, nullable
output_tokens   int, nullable
cost_usd        float, nullable
duration_sec    int
status          str
error_message   text, nullable
created_at      datetime
```

---

## 5. Память и история сценариев

> **Ключевая фича** - сценарии не должны повторяться. Память должна быть сжата, чтобы не сжигать токены при каждом запросе.

### Двухуровневое хранение

**Уровень 1: полный сценарий** - в файле `script_<lang>.md`, читается только когда нужно (просмотр, экспорт)

**Уровень 2: сжатая память** - в `memory.jsonl`, одна строка на видео:
```json
{
  "video_id": "uuid",
  "created_at": "2026-06-28",
  "title": "Почему квантовая запутанность - не магия",
  "hook": "Эйнштейн назвал это жутким действием на расстоянии...",
  "summary_short": "Объяснение квантовой запутанности через простые аналогии",
  "key_points": ["EPR парадокс", "теорема Белла", "практика - квантовая криптография"],
  "topics": ["квантовая физика", "Эйнштейн", "криптография"],
  "structure": ["загадочный hook", "история", "эксперимент", "применение", "вывод"]
}
```

### Алгоритм генерации без повторов

1. Загружаем `memory.jsonl` проекта - последние **30-50 записей**
2. Передаём в Claude **только сжатые саммари** (не полные тексты)
3. Системный промпт:
   ```
   Вот темы и хуки последних видео на канале:
   {memory_jsonl_compact}
   
   Сгенерируй новый сценарий по теме: "{topic_brief}"
   Запрещено: повторять hook, structure, key_topics из списка выше.
   ```
4. После генерации - вызываем `script_analyzer` (отдельный быстрый запрос к Claude):
   - извлекает hook, summary, topics, structure
   - сохраняет в `script_analysis` + добавляет в `memory.jsonl`

### Опционально: семантический поиск

Если канал разрастётся до 200+ видео:
- Эмбеддинги (`sentence-transformers/all-MiniLM` локально)
- При новой теме - найти top-5 похожих прошлых, передать их саммари в промпт

> На старте достаточно простого временного хвоста (последние N).

### Сжатие токенов

Один компактный JSON на видео ≈ **150-250 токенов**.
30 видео ≈ 6 000 токенов контекста - копейки по сравнению с генерацией 10 000-токенного сценария.

---

## 6. Мультиязычность

### Сценарий генерации на нескольких языках

1. Сценарий пишется на **primary language** канала
2. Если в `languages_export` есть другие - **переводятся** через Claude:
   - Не дословный перевод, а **локализация**: идиомы, культурные референсы
   - Системный промпт: "Переведи как носитель языка, сохраняя стиль и темп речи"
3. Каждый перевод сохраняется как отдельный `scripts` row (`is_primary=false`)
4. Озвучка делается **для каждого языка отдельно**:
   - Kokoro поддерживает `en-us`, `ja`, `zh`, `es`, `fr`, `hi`, `it`, `pt` (русский через workaround)
   - В `voice_settings` проекта - маппинг язык -> голос
5. Финальный рендер собирается под каждый язык:
   - `final_ru.mp4`, `final_en.mp4`, `final_es.mp4`
   - Видеоряд один, меняется только аудио и (опционально) обложка

### UI

- В карточке видео - вкладки по языкам
- Можно догенерить новый язык в любой момент
- Прогресс рендеринга для каждого языка отдельно

---

## 7. Pipeline генерации видео (оркестратор)

`services/pipeline.py` - последовательность стадий, каждая в БД логируется:

```
[1] LOAD_CONTEXT
    - читаем спецификацию канала
    - читаем memory.jsonl последние 30
    
[2] GENERATE_SCRIPT (primary lang)
    - вызов Claude с контекстом канала + памятью
    - сохранение script_ru.md + БД row
    
[3] ANALYZE_SCRIPT
    - отдельный запрос: hook, summary, topics, structure
    - запись в script_analysis + дозапись в memory.jsonl
    
[4] TRANSLATE (если есть other languages)
    - для каждого языка - вызов Claude
    - сохранение script_en.md, ...
    
[5] TTS (для каждого языка параллельно)
    - Kokoro или ручной режим
    - сохранение audio/<lang>.wav
    
[6] BUILD_VISUALS
    - подбор стокового видео по topics (Pexels API)
    - или картинки + Ken Burns эффект
    - сохранение в assets/
    
[7] GENERATE_THUMBNAIL
    - prompt = title + hook + style
    - Flux/Ideogram или Pillow с шаблоном
    
[8] RENDER (для каждого языка)
    - MoviePy/ffmpeg: видеоряд + аудио + субтитры
    - сохранение final_<lang>.mp4

[9] UPDATE_STATS
    - длительность, размер, стоимость токенов
```

Каждая стадия:
- идемпотентна (можно перезапустить)
- логируется в `generation_logs`
- видна в GUI с прогресс-баром

---

## 8. Frontend - страницы и UX

### Dashboard (главная)
- Карточки проектов: иконка канала, название, ниша, кол-во видео, последняя активность
- Кнопка **+ Новый канал**
- Виджет **общая статистика**: всего видео, токенов потрачено, средняя длина

### ProjectView (один канал)
**Tab: Видео**
- Сетка/список видео с превью обложки
- Статус (черновик/генерация/готово), длительность, доступные языки (флажки)
- Фильтры: статус, язык, дата
- Кнопка **+ Создать видео**

**Tab: Настройки канала**
- Имя, ниша, описание
- Целевая аудитория
- Style prompt (большое текстовое поле)
- Primary language, экспортные языки (мультиселект)
- Voice settings (выбор голоса под каждый язык)
- TTS mode (local/manual)

**Tab: Память**
- Список всех saved hooks/topics из memory.jsonl
- Облако тегов (использованные темы)
- Поиск по hook/summary
- Можно вручную удалить запись или пометить как "не учитывать"

**Tab: Статистика**
- График количества видео по месяцам
- Топ-10 тем
- Средняя длина видео
- Расход токенов / стоимость
- Время генерации (среднее по стадиям)

### NewVideo (форма создания)
- Поле "О чём видео" (topic_brief, 1-3 предложения)
- Опционально: целевая длительность
- Языки (по умолчанию из настроек канала, можно override)
- Чекбоксы стадий (хочу ли сейчас рендерить или только сценарий)
- Кнопка **Запустить пайплайн**
- Сразу - real-time лог в правой панели

### VideoView (одно видео)
**Левая колонка**
- Превью обложки (можно перегенерить)
- Метаданные: статус, длина, языки, дата
- Кнопки: Скачать mp4, Перерендерить, Удалить

**Центр**
- Tabs по языкам (RU/EN/ES)
- Внутри таба:
  - **Сценарий** (Markdown viewer + edit mode)
  - **Аудио** (плеер с волной)
  - **Анализ**: hook, summary, key points, topics
  - **Готовое видео** (плеер mp4)

**Правая колонка**
- Лог генерации (стадии с галочками и временем)
- Стоимость

### Sidebar (постоянный)
- Список каналов (с активным выделен)
- "Все видео" (глобальный список)
- Настройки (API ключи, пути, TTS параметры)

### Визуальный стиль
- **Тёмная тема** по умолчанию (студийная атмосфера)
- shadcn/ui с лёгкой кастомизацией
- Акцентный цвет под каждый канал (выбирается при создании)
- Минимум анимаций, максимум информации
- Mobile - не требуется, целевая платформа десктоп

---

## 9. Статистика - что показывать

### По видео
- Длительность аудио / финального видео
- Word count, estimated read time
- Hook (полным текстом)
- Summary short + long
- Key points (список)
- Topics (теги)
- Структура (intro/основа/outro с таймкодами)
- Стоимость генерации (tokens, $)
- Время каждой стадии

### По каналу
- Всего видео (готовых / в процессе / черновики)
- Суммарная длительность контента
- Топ тем (облако)
- Какие хуки уже использованы
- Распределение длительностей (гистограмма)
- Языки (сколько видео на каждом)
- Расход токенов по месяцам

### Глобально
- Всего проектов
- Всего видео
- Расход токенов / месяц
- Использование диска (data/)

---

## 10. API Endpoints (FastAPI)

### Projects
```
GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
PATCH  /api/projects/{id}
DELETE /api/projects/{id}
GET    /api/projects/{id}/memory       # memory.jsonl
GET    /api/projects/{id}/stats
```

### Videos
```
GET    /api/projects/{pid}/videos
POST   /api/projects/{pid}/videos      # создаёт черновик + запускает пайплайн
GET    /api/videos/{id}
PATCH  /api/videos/{id}
DELETE /api/videos/{id}
GET    /api/videos/{id}/scripts        # все языки
GET    /api/videos/{id}/scripts/{lang}
PATCH  /api/videos/{id}/scripts/{lang} # ручное редактирование
GET    /api/videos/{id}/analysis
GET    /api/videos/{id}/logs           # log generation_logs
POST   /api/videos/{id}/rerun          # перезапуск с конкретной стадии
```

### Generation
```
POST   /api/generate/script            # только сценарий
POST   /api/generate/translate         # перевод существующего
POST   /api/generate/tts               # озвучка существующего
POST   /api/generate/thumbnail
POST   /api/generate/render            # финальный mp4
WS     /api/ws/jobs/{video_id}         # реалтайм статус пайплайна
```

### Stats
```
GET    /api/stats/global
GET    /api/stats/projects/{id}
```

### Files (статика)
```
GET    /files/projects/{pid}/...       # отдача аудио, видео, картинок
```

---

## 11. Конфигурация (.env)

```
# Claude API
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-5

# Pexels (для стокового видео)
PEXELS_API_KEY=...

# Replicate (опционально, для обложек)
REPLICATE_API_TOKEN=

# Пути
DATA_DIR=./data
DB_PATH=./data/db.sqlite

# Kokoro
KOKORO_MODEL_PATH=  # пусто = автозагрузка
KOKORO_DEVICE=cuda  # cuda / cpu

# FFmpeg
FFMPEG_PATH=ffmpeg
```

---

## 12. Фазы разработки (для Claude Code - roadmap)

### Phase 1: Core backend (1 неделя)
- [ ] FastAPI skeleton + конфиг
- [ ] SQLAlchemy модели + Alembic
- [ ] CRUD API для projects + videos
- [ ] Файловая структура `data/projects/<id>/`
- [ ] Claude API клиент (`core/llm.py`)
- [ ] Тесты для моделей

### Phase 2: Script generation + memory (1 неделя)
- [ ] `script_generator.py` - генерация по topic_brief
- [ ] `script_analyzer.py` - извлечение hook/summary/topics
- [ ] `memory_service.py` - чтение/запись memory.jsonl
- [ ] Интеграция: новое видео -> сценарий -> анализ -> память
- [ ] API endpoints для генерации
- [ ] Тесты на воспроизводимость без повторов

### Phase 3: TTS (3-5 дней)
- [ ] Интеграция Kokoro (взять из tts_engine.py)
- [ ] Manual mode
- [ ] Конфиг голосов под язык
- [ ] WebSocket прогресс

### Phase 4: Translation + multi-language (3-5 дней)
- [ ] `translator.py` - перевод сценария
- [ ] Сборка пайплайна для нескольких языков
- [ ] Отдельные audio_tracks для каждого

### Phase 5: Frontend MVP (1.5 недели)
- [ ] Vite + React + Tailwind + shadcn setup
- [ ] Sidebar, Dashboard, ProjectView
- [ ] NewVideo форма + лог пайплайна (WS)
- [ ] VideoView с табами по языкам
- [ ] ScriptEditor с подсветкой
- [ ] AudioPlayer

### Phase 6: Stats + Memory UI (3-5 дней)
- [ ] StatsPanel компонент
- [ ] Recharts графики
- [ ] MemoryViewer (теги, hooks, поиск)

### Phase 7: Видеоряд + рендер (1.5 недели)
- [ ] Pexels интеграция
- [ ] MoviePy сборка с Ken Burns
- [ ] Авто-субтитры (faster-whisper)
- [ ] Финальный рендер mp4 для каждого языка
- [ ] Прогресс рендера в UI

### Phase 8: Обложка (3-5 дней)
- [ ] Pillow шаблонная обложка (text overlay)
- [ ] Опционально - Flux через Replicate
- [ ] Превью в UI

### Phase 9: Polish (1 неделя)
- [ ] Обработка ошибок везде
- [ ] Сохранение черновиков, продолжение с любой стадии
- [ ] Экспорт/импорт проектов
- [ ] start.sh / start.bat скрипты
- [ ] README с инструкциями

---

## 13. Критерии готовности MVP

1. Создал канал "X" с настройками
2. Создал 5 видео подряд по разным темам - **сценарии не повторяют hooks/topics** прошлых
3. На каждом видео виден hook, summary, key points (статистика работает)
4. Озвучка локальная (Kokoro) работает + ручной режим как fallback
5. Сценарий на RU автоматически переведён на EN
6. Каждый язык озвучен своим голосом
7. Финальный mp4 для RU и EN экспортируется
8. UI: переключение между каналами, видео, языками - всё работает без перезагрузки
9. Статистика показывает корректные цифры
10. Перезапуск приложения - все данные на месте (БД + файлы)

---

## 14. Инструкция для Claude Code

> Этот файл (`CLAUDE.md`) лежит в корне проекта. Claude Code должен следовать ему при разработке.

### Принципы кода
- **Python**: type hints везде, docstrings на русском, mypy-friendly
- **React**: TypeScript strict mode, функциональные компоненты, hooks
- **Без оверинжиниринга**: SQLite, BackgroundTasks, никаких Redis/Celery пока не упрётся
- **Логирование**: `loguru` в backend, понятные сообщения на русском
- **Ошибки**: обрабатывать явно, показывать пользователю в UI с понятным текстом

### Стиль
- Комментарии и UI - на русском
- Имена переменных/функций - английский
- Файлы данных - UTF-8 без BOM

### Что НЕ делать
- Не использовать localStorage в React (state только через Zustand + БД)
- Не хардкодить ключи API - только через .env
- Не дублировать промпты - выносить в `prompts/` папку как .txt шаблоны
- Не делать сложную auth - приложение локальное, для одного пользователя

### Тестирование
- Pytest для backend (минимум: модели, memory_service, pipeline mocked)
- Frontend - без unit тестов на старте, ручная проверка

### Документация
- README.md - как установить и запустить
- API docs - автоматически через FastAPI Swagger (`/docs`)
- В коде - docstrings и комментарии где сложная логика
