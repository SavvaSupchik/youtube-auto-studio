# YouTube Auto Studio

Локальная студия для автоматической генерации YouTube-видео: каналы, генерация
уникальных сценариев (с памятью, без повторов), мультиязычный перевод, озвучка,
обложка и финальный рендер. Подробный план — в [CLAUDE.md](CLAUDE.md).

## ⚠️ ВАЖНО: проект разделён на две части по разным дискам

Этот репозиторий лежит в папке, смонтированной как **Google Drive File Stream**
(виртуальный диск, не обычная синхронизируемая папка). Через него `npm install`
работает крайне ненадёжно (зависает с `Access is denied` намертво) — поэтому:

| Часть проекта | Где физически лежит | Синхронизируется через Google-аккаунт? |
|---|---|---|
| `backend/` (код), `data/`, `CLAUDE.md`, `README.md`, `scripts/` | здесь, на Google Диске | ✅ Да — видно с любого компьютера под этим аккаунтом |
| **`frontend/` — рабочая копия с `node_modules`** | **локально:** `C:\Users\savva\Projects\YouTube Auto Studio-frontend` | ❌ **Нет** — это только на этом компьютере |
| **backend venv (`.venv` с зависимостями, в т.ч. torch/kokoro)** | **локально:** `C:\Users\savva\Projects\YouTube Auto Studio-backend\.venv` | ❌ **Нет** — пакеты ставятся отдельно на каждом компьютере |

**Что это значит при работе с другого компьютера:**
- `data/projects/` (видео, сценарии, БД), backend-код (`app/`, `requirements.txt`)
  и план проекта подтянутся автоматически через Google Диск.
- Папка `frontend/` на Диске содержит только исходники (без `node_modules`) —
  это просто бэкап, не рабочая копия. Чтобы запустить фронтенд на новом
  компьютере, нужно:
  1. Скопировать `frontend/` куда-нибудь **на локальный диск** этого компьютера
     (не оставлять на Google Диске/File Stream).
  2. Там сделать `npm install` и работать дальше из этой локальной папки.
  3. Поправить путь в `scripts/start.bat` / `scripts/start.sh`, если используешь
     эти скрипты для запуска (сейчас там зашит путь
     `C:\Users\savva\Projects\YouTube Auto Studio-frontend`).
- Если меняешь код фронтенда — меняй именно в локальной рабочей копии. Копия
  на Google Диске не обновляется автоматически и может устареть.
- **venv backend** (особенно с установленным Kokoro — там тянется torch и ещё
  ~70 пакетов) тоже не живёт на Диске: на каждом новом компьютере его нужно
  пересоздать локально (см. «Установка» ниже) — это быстрее и надёжнее, чем
  ставить тяжёлые пакеты через виртуальный том Drive File Stream.

## Что уже реализовано

**Backend (FastAPI + SQLAlchemy + SQLite):**
- CRUD каналов и видео, файловая структура `data/projects/<id>/`
- Клиент LLM (`core/llm.py`): Claude или Gemini (переключатель `LLM_PROVIDER` в `.env`), с учётом токенов и стоимости
- **3-шаговая генерация сценария** по одной теме: ИИ адаптирует 3 шаблона под тему (свои клише, боли ЦА) → подготовка/бриф → написание → авто-аудит и очеловечивание. Шаблоны на английском, общие, редактируются на странице **Настройки**; промты можно поправить вручную перед запуском (форма «Новое видео»). С учётом **памяти канала** (`memory.jsonl`) — без повторов hook/тем
- Анализ сценария (hook, summary, topics, structure) → запись в память
- Перевод (локализация) на экспортные языки
- Озвучка: Kokoro (локально) или ручной режим
- Обложка (Pillow) и финальный mp4 (FFmpeg)
- **AI-визуальный ряд** (опционально, `REPLICATE_API_TOKEN` + FLUX schnell): сценарий разбивается на сцены, картинка по контексту меняется каждые `VISUAL_SEGMENT_MINUTES` минут (Ken Burns, склейка через FFmpeg). Без токена — fallback на статичную обложку
- Оркестратор-пайплайн с логированием стадий и WebSocket-прогрессом
- Статистика по каналу и глобально

**Frontend (Vite + React + TS + Tailwind + TanStack Query):**
- Дашборд со списком каналов и общей статистикой
- Страница канала: вкладки Видео / Настройки / Память / Статистика
- Создание видео с real-time логом пайплайна (WebSocket)
- Просмотр видео: вкладки по языкам, редактор сценария, плеер аудио, анализ, рендер

## Требования

- **Python 3.12** (3.14 пока не подходит — нет колёс для части зависимостей)
- **Node.js 18+**
- **FFmpeg** в PATH (для рендера)
- (опционально) GPU + Kokoro для локальной озвучки

## Установка

```bash
# 1. Конфиг
cp .env.example .env
#   впишите ANTHROPIC_API_KEY (обязательно для генерации сценариев)
#   при желании PEXELS_API_KEY, REPLICATE_API_TOKEN

# 2. Backend — venv создаём НЕ в backend/, а в локальной (не-Drive) папке
py -3.12 -m venv "%USERPROFILE%\Projects\YouTube Auto Studio-backend\.venv"        # Windows
# python3.12 -m venv "$HOME/Projects/YouTube Auto Studio-backend/.venv"            # *nix
cd backend
"%USERPROFILE%\Projects\YouTube Auto Studio-backend\.venv\Scripts\python" -m pip install -r requirements.txt

# 3. Frontend — тоже в локальную (не-Drive) папку
cp -r ../frontend "%USERPROFILE%\Projects\YouTube Auto Studio-frontend"
cd "%USERPROFILE%\Projects\YouTube Auto Studio-frontend"
npm install
```

> ⚠️ Если проект лежит в синхронизируемой папке (Google Drive / OneDrive),
> `npm install` и установка тяжёлых pip-пакетов (torch/kokoro) могут падать
> с `EBADF` / `TAR_ENTRY_ERROR` / зависающим `Access is denied` — Drive
> блокирует файлы во время записи. Решение, проверенное в этом проекте:
> держать `node_modules` и venv **вне** синхронизируемой папки (см. таблицу
> выше), а на Диске оставлять только сам код (`app/`, `src/`, `requirements.txt`,
> `package.json`).

## Запуск

```bash
# Windows: поднимет backend + frontend в двух окнах
scripts\start.bat

# *nix
./scripts/start.sh
```

- Backend: http://127.0.0.1:8000 (Swagger: http://127.0.0.1:8000/docs)
- Frontend: http://localhost:5173

## Установка дополнительных движков (опционально)

```bash
# Локальная озвучка Kokoro + обложки — ставить в локальный venv (см. выше), не в backend/.venv на Диске
"%USERPROFILE%\Projects\YouTube Auto Studio-backend\.venv\Scripts\python" -m pip install kokoro soundfile pillow
```

## Тесты

```bash
cd backend
"%USERPROFILE%\Projects\YouTube Auto Studio-backend\.venv\Scripts\python" -m pytest
```
