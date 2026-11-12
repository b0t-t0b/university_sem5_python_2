# Веб-приложение с HTTP API для асинхронного преобразования файлов из формата WebM в формат GIF

**Практическая работа № 2**  
**Дисциплина:** Прикладная разработка серверных частей веб-приложений на языке Питон  
**Выполнил:** Хромченков Дмитрий Дмитриевич (ИКБО-70-24)  
**Вариант:** № 22  

---

## 1. Общее описание

Проект реализует веб-приложение с HTTP API и CLI-утилиту для асинхронного (фонового через `subprocess`) преобразования видеофайлов из формата WebM в анимированный GIF с кэшированием результатов обработки, проверкой обязательных HTTP-заголовков, двумя взаимозаменяемыми уровнями хранения данных и модельным тестированием на базе Hypothesis.

Архитектура разделена на три последовательных этапа разработки:

1. **Этап 1 — CLI-утилита преобразования WebM в GIF (`src/converter.py`, `src/demo_stage1.py`)**:
   - Читает входной `.webm` файл с помощью PyAV (`av`), извлекает видеокадры, формирует оптимизированную GIF-анимацию с помощью Pillow (`PIL`) и выводит бинарные данные GIF в `stdout`.
   - Скрипт `src/demo_stage1.py` программно генерирует 5 различных WebM-образцов во временной директории, запускает `src.converter` как подпроцесс и проверяет валидность заголовка (`GIF87a` / `GIF89a`) и количества кадров.
2. **Этап 2 — HTTP API на Bottle, файловая СУБД и MBT (`src/server.py`, `src/file_store.py`, `src/task_runner.py`, `src/client.py`, `src/demo_stage2.py`)**:
   - Сервер Bottle реализует все 10 маршрутов таблицы 22 варианта № 22 (`create`, `remove`, `query`, `correct`, `report`) и возвращает ответы в формате JSON.
   - Перед обработкой каждого маршрута проверяются HTTP-заголовки `Accept: text/json` и `Accept-Language: en`. При отсутствии или несоответствии сервер возвращает статус `406 Not Acceptable`.
   - Маршрут `POST /public/api/create/request` (обработчик `2.1`) ставит задачу преобразования в `src/task_runner.py`, который либо мгновенно переиспользует успешный кэш (`cache_hit = 1`), либо запускает CLI-утилиту через `subprocess.run` (или имитирует работу при `--test-mode`).
   - Файловая СУБД `FileDataStore` хранит таблицы `sessions`, `requests`, `answers` на диске в JSON с потокобезопасной блокировкой `threading.Lock`.
   - Клиентская библиотека `HTTPAPIClient` реализует методы, имена которых образованы от маршрутов с заменой `/` и `-` на `_`.
   - В `tests/test_mbt.py` реализовано модельное тестирование (`RuleBasedStateMachine` из библиотеки Hypothesis) с сопоставлением HTTP API и эталонной модели `ReferenceModel`.
3. **Этап 3 — SQLite + SQLAlchemy ORM (`src/sqlite_store.py`, `src/demo_stage3.py`)**:
   - Слой хранения данных заменён на реляционную БД SQLite с использованием ORM SQLAlchemy 2.x (`SessionModel`, `RequestModel`, `AnswerModel`) и каскадным удалением связанных ответов.
   - Аналитический отчёт `GET /public/api/query/report` по формуле `(22)` реляционной алгебры ($\pi_{\text{content},\text{locale}}(\text{Request} \bowtie_{R.\text{session}=S.\text{uid}} \sigma_{\text{timestamp} \ge \text{now}-360}(\text{Session}))$) выполняется на уровне SQL ORM.

### Структура репозитория

| Путь | Назначение |
| :--- | :--- |
| `src/constants.py` | Именованные константы (HTTP-коды, заголовки, окно времени, лимиты, пути по умолчанию) |
| `src/converter.py` | CLI-конвертер WebM -> GIF с выводом результата в `stdout` |
| `src/task_runner.py` | Исполнитель задач `subprocess`, кэширование результатов по `content`, режим `--test-mode` |
| `src/file_store.py` | Дисковая файловая СУБД `FileDataStore` на JSON |
| `src/sqlite_store.py` | Реляционная СУБД SQLite + ORM SQLAlchemy `SQLiteDataStore` |
| `src/server.py` | Веб-сервер Bottle со всеми 10 маршрутами и валидацией заголовков |
| `src/client.py` | HTTP-клиент `HTTPAPIClient` для работы со всеми маршрутами |
| `src/demo_stage1.py` | Демонстрация этапа 1 на 5 WebM-примерах |
| `src/demo_stage2.py` | Демонстрация этапа 2 (HTTP API + `FileDataStore`) |
| `src/demo_stage3.py` | Демонстрация этапа 3 (HTTP API + `SQLiteDataStore`) |
| `tests/test_mbt.py` | Модельное тестирование Hypothesis (`HTTPAPIStateMachine`) и тесты `subprocess` |
| `requirements.txt` | Список зависимостей проекта |
| `Makefile`, `run.bat`, `run.sh` | Скрипты запуска линтера, демонстраций, тестов и отчёта покрытия |

---

## 2. Описание всех функций и настроек

### 2.1. Модели базы данных (Вариант № 22)

1. **`Session`** (`SessionModel`, таблица `sessions`):
   - `uid` (`int`, PK) — уникальный идентификатор сессии;
   - `timestamp` (`int`) — отметка времени (Unix timestamp);
   - `locale` (`str`) — код локали;
   - `user_agent` (`str`) — строка User-Agent клиента.
2. **`Request`** (`RequestModel`, таблица `requests`):
   - `uid` (`int`, PK) — уникальный идентификатор запроса;
   - `timestamp` (`int`) — отметка времени запроса;
   - `content` (`str`) — путь к входному `.webm` файлу;
   - `session` (`int`, FK -> `sessions.uid`) — идентификатор сессии;
   - `triggered` (`int`) — признак запуска задачи (`1` — запуск конвертации и запись `Answer`, `0` — только регистрация запроса).
3. **`Answer`** (`AnswerModel`, таблица `answers`):
   - `uid` (`int`, PK) — уникальный идентификатор ответа;
   - `timestamp` (`int`) — отметка времени завершения задачи;
   - `output` (`str`) — закодированный в base64 GIF-результат (при успехе);
   - `status` (`str`) — статус выполнения (`"ok"` или `"error"`);
   - `exception` (`str`) — описание ошибки (пустая строка при успехе);
   - `request` (`int`, FK -> `requests.uid`) — ссылка на исходный запрос;
   - `cache_hit` (`int`) — признак попадания в кэш по `content` (`1` — из кэша, `0` — новое выполнение).

### 2.2. Маршруты HTTP API и методы клиента (`src/server.py`, `src/client.py`)

Все маршруты требуют заголовки `Accept: text/json` и `Accept-Language: en`. При любом другом значении возвращается `406 Not Acceptable` с JSON-ошибкой.

| № | HTTP-метод и путь | Параметры | Метод `HTTPAPIClient` | Назначение |
| :-: | :--- | :--- | :--- | :--- |
| 1 | `POST /public/api/create/session` | Query: `uid`, `timestamp`, `locale`, `user_agent` | `public_api_create_session` | Создание записи `Session` |
| 2 | `DELETE /public/api/remove/session/:uid` | Path: `uid` | `public_api_remove_session` | Удаление `Session` (если нет зависимых `Request`) |
| 3 | `GET /public/api/query/session` | Query (опц.): `uid`, `timestamp`, `locale`, `user_agent` | `public_api_query_session` | Выборка `Session` с фильтрами |
| 4 | `POST /public/api/correct/session` | JSON body: `uid` + обновляемые поля | `public_api_correct_session` | Обновление записи `Session` |
| 5 | `POST /public/api/create/request` | Query: `uid`, `timestamp`, `content`, `session`, `triggered` | `public_api_create_request` | Создание `Request` и запуск задачи `2.1` |
| 6 | `DELETE /public/api/remove/request/:uid` | Path: `uid` | `public_api_remove_request` | Удаление `Request` и связанных `Answer` |
| 7 | `GET /public/api/query/request/:session` | Path: `session`; Query (опц.): `uid`, `timestamp`, `content`, `triggered` | `public_api_query_request` | Выборка `Request` внутри сессии |
| 8 | `POST /public/api/correct/request` | JSON body: `uid` + обновляемые поля | `public_api_correct_request` | Обновление записи `Request` |
| 9 | `GET /public/api/query/answer/:request` | Path: `request`; Query (опц.): `uid`, `timestamp`, `output`, `status`, `exception`, `cache_hit` | `public_api_query_answer` | Выборка `Answer` по `request` |
| 10 | `GET /public/api/query/report` | Нет | `public_api_query_report` | Отчёт `(22)`: пары `{content, locale}` за последние 360 сек |

Для совместимости с правилом замены первого `/` на `_` в `HTTPAPIClient` также доступны псевдонимы вида `_public_api_create_session` и т.д.

### 2.3. Параметры CLI и настройки (`src/constants.py`)

**CLI-конвертер `python -m src.converter`:**
- `input_file` — путь ко входному `.webm` файлу (позиционный аргумент);
- `--fps` — частота кадров выходного GIF (по умолчанию `10`);
- `--width` — опциональная максимальная ширина в пикселях с сохранением пропорций.

**HTTP-сервер `python -m src.server`:**
- `--host` — сетевой адрес прослушивания (по умолчанию `127.0.0.1`);
- `--port` — порт сервера (по умолчанию `8080`);
- `--db-mode` — выбор движка хранения: `sqlite` (по умолчанию) или `file`;
- `--db-path` — путь/URL базы данных (по умолчанию `sqlite:///storage.db` или `storage_db.json`);
- `--test-mode` — включает фиктивное выполнение конвертации без реального запуска подпроцесса для быстрого прогона MBT.

**Ключевые константы (`src/constants.py`):**
- `QUERY_TIME_WINDOW_SECONDS = 360` — временное окно фильтрации сессий в отчёте `(22)`;
- `REQUIRED_ACCEPT_HEADER = "text/json"`, `REQUIRED_ACCEPT_LANGUAGE = "en"` — обязательные заголовки;
- `CLI_TIMEOUT_SECONDS = 30` — таймаут подпроцесса конвертации WebM -> GIF.

---

## 3. Описание команд для сборки проекта и запуска тестов

### 3.1. Подготовка виртуального окружения

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3.2. Запуск проверок, демонстраций и тестов

- **Полный автоматический прогон (Windows):**
  ```bat
  run.bat
  ```
- **Полный автоматический прогон (Linux / macOS):**
  ```bash
  bash run.sh
  ```
- **Через `Makefile`:**
  - `make lint` — проверка PEP8 и цикломатической сложности (`flake8 --max-line-length=79 --max-complexity=10 src tests`);
  - `make demo` — поочерёдный запуск демонстраций этапов 1, 2 и 3;
  - `make test` — запуск `pytest` с измерением ветвевого покрытия `coverage --branch`;
  - `make all` — `lint` + `demo` + `test`.

---

## 4. Примеры использования

### Пример 1. Преобразование WebM в GIF через CLI

```bash
python -m src.converter input.webm --fps 10 --width 320 > output.gif
```

### Пример 2. Запуск HTTP-сервера с SQLite

```bash
python -m src.server --host 127.0.0.1 --port 8080 --db-mode sqlite --db-path sqlite:///storage.db
```

### Пример 3. Работа с API через `HTTPAPIClient`

```python
from src.client import HTTPAPIClient

client = HTTPAPIClient("http://127.0.0.1:8080")
client.public_api_create_session(1, 1700000000, "en", "DemoClient/1.0")
client.public_api_create_request(10, 1700000005, "sample.webm", 1, 1)
print(client.public_api_query_answer(10).json())
print(client.public_api_query_report().json())
```

### Пример 4. Запрос через `curl` с обязательными заголовками

```bash
curl -X POST "http://127.0.0.1:8080/public/api/create/session?uid=1&timestamp=1700000000&locale=en&user_agent=Curl" ^
  -H "Accept: text/json" ^
  -H "Accept-Language: en"
```
