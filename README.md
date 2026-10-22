# Google Classroom → Google Sheets Sync

Автоматический сбор заданий и важных объявлений из Google Classroom с мгновенной записью в Google Таблицы.

## 🚀 Возможности

- **Авторизация** — единый OAuth 2.0 для Classroom API и Google Sheets API
- **Задания (CourseWork)** — сбор всех опубликованных заданий с дедлайнами, баллами, темами, статусом сдачи
- **Объявления (Announcements)** — умная фильтрация по ключевым словам ("сделать", "сдать", "дедлайн", "дз", "лаба" и др.)
- **Google Sheets** — красивое оформление: закреплённые заголовки, цветовая подсветка статусов, гиперссылки, фильтры
- **Локальный CSV** — резервная копия в `classroom_tasks.csv` (utf-8-sig для Excel)
- **Сортировка** — по срочности: просроченные → ближайшие дедлайны → без срока → сданные/оцененные

---

## 📋 Требования

- Python 3.8+
- Google Cloud проект с включёнными API:
  - Google Classroom API
  - Google Sheets API
  - Google Drive API (для создания таблиц)
- OAuth Client ID (Desktop App) — файл `credentials.json`

---

## 🛠 Установка

### 1. Клонируйте/скачайте проект

```bash
cd E:\All\Nadenenko\classroom
```

### 2. Создайте виртуальное окружение

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

### 4. Настройте Google Cloud Console

Убедитесь, что в Google Cloud Console:
- Включены **Google Classroom API**, **Google Sheets API**, **Google Drive API**
- Настроен **OAuth Consent Screen** (External, Test users добавлены)
- Созданы **OAuth 2.0 Client ID** (Тип: Desktop App)
- Скачанный `credentials.json` положен в папку проекта

**Необходимые scopes** (уже в коде):
```
https://www.googleapis.com/auth/classroom.courses.readonly
https://www.googleapis.com/auth/classroom.coursework.me
https://www.googleapis.com/auth/classroom.announcements.readonly
https://www.googleapis.com/auth/classroom.rosters.readonly
https://www.googleapis.com/auth/classroom.topics.readonly
https://www.googleapis.com/auth/classroom.profile.emails
https://www.googleapis.com/auth/spreadsheets
```

### 5. (Опционально) Настройте `.env`

Скопируйте `.env.example` в `.env` и укажите ID существующей таблицы:

```bash
copy .env.example .env
```

Отредактируйте `.env`:
```env
SPREADSHEET_ID=your_google_sheet_id_here
```

> **ID таблицы** — это длинная строка в URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

Если не указать — скрипт создаст новую таблицу автоматически.

---

## ▶️ Запуск

### Базовый запуск (полная синхронизация)

```bash
python main.py
```

При первом запуске откроется браузер для авторизации. Разрешите доступ. Токен сохранится в `token.json`.

### Только локальный CSV (без Google Sheets)

```bash
python main.py --csv-only
```

### Использовать конкретную таблицу

```bash
python main.py --sheet-id YOUR_SPREADSHEET_ID
```

### Принудительная переавторизация

```bash
python main.py --reauth
```

### Посмотреть информацию о токене

```bash
python main.py --token-info
```

---

## 📊 Структура выходной таблицы

| Столбец | Описание | Пример |
|---------|----------|--------|
| **Предмет** | Название курса | "Математика 101" |
| **Тема / Раздел** | Тема из Classroom | "Алгебра: Уравнения" |
| **Тип** | Задание / Объявление / Тест / Вопрос | "Задание" |
| **Название / Суть** | Заголовок задания или выжимка из объявления | "ДЗ №5: Квадратные уравнения" |
| **Дедлайн / Срок** | Дата и время (ГГГГ-ММ-ДД ЧЧ:ММ) | "2026-10-25 23:59" |
| **Статус** | К сдаче / Сдано / На проверке / Просрочено / Оценено / Требует внимания | "К сдаче" |
| **Оценка** | Получено / Макс. балл | "85/100" |
| **Ссылка** | Кликабельная ссылка на задание в Classroom | `=HYPERLINK(...)` |

---

## 🎨 Форматирование Google Sheets

Скрипт автоматически применяет:

- ❄️ **Закреплена первая строка** (заголовки)
- 🎨 **Стильные заголовки** — тёмный фон, белый жирный текст, по центру
- 📏 **Оптимальные ширины столбцов**
- 🌈 **Условное форматирование** (по столбцу "Статус"):
  - 🔴 **Просрочено** — нежно-красный фон
  - 🟠 **К сдаче** (срок قريب) — нежно-оранжевый фон
  - 🟢 **Сдано** — нежно-зелёный фон
  - ✅ **Оценено** — зелёный фон
- 🔍 **Фильтр** на заголовках для сортировки/фильтрации
- 🔗 **Гиперссылки** в столбце "Ссылка" (формула `=HYPERLINK`)

---

## 🔍 Логика фильтрации объявлений

Объявление считается "требующим действия", если в тексте есть **любое** из ключевых слов:

```
сделать, прислать, сдать, выполнить, дедлайн, до ,
дз, задание, лаба, практическая, проект,
домашнее, работа, отправить, загрузить, оформить,
подготовить, написать, решить, изучить, прочитать,
посмотреть, послушать, сделай, сдай, пришли,
deadline, homework, assignment, lab, project,
task, submit, upload, complete, finish
```

Регистр не важен. Слово "до " (с пробелом) отсекает ложные срабатывания в словах типа "родной".

---

## 📁 Структура проекта

```
classroom/
├── credentials.json       # OAuth Client ID (от Google Cloud)
├── token.json             # Создаётся автоматически после первой авторизации
├── .env                   # Опционально: SPREADSHEET_ID
├── requirements.txt       # Зависимости Python
├── config.py              # Конфигурация (scopes, keywords, colors)
├── auth.py                # OAuth 2.0 авторизация
├── classroom_api.py       # Работа с Classroom API
├── sheets_api.py          # Работа с Google Sheets API
├── main.py                # Точка входа, оркестрация
├── classroom_tasks.csv    # Локальная резервная копия (создаётся при запуске)
└── README.md              # Эта инструкция
```

---

## ⚠️ Частые проблемы

### "Credentials file not found"
Убедитесь, что `credentials.json` лежит в папке проекта.

### "Access blocked: authorization error"
- Добавьте свой email в **Test users** в OAuth Consent Screen
- Или опубликуйте приложение (потребует верификации)

### "Quota exceeded" / "Rate limit"
- Classroom API имеет лимиты. При множестве курсов добавьте задержки (TODO)
- Попробуйте запустить позже

### Таблица не создаётся / ошибка доступа
- Убедитесь, что включен **Google Drive API**
- Проверьте, что у аккаунта есть доступ к Google Диску

### Ошибка "invalid_grant: Token has been expired or revoked"
```bash
python main.py --reauth
```

---

## 🔄 Автоматизация (планировщик)

### Windows (Task Scheduler)
1. Откройте **Task Scheduler** → **Create Basic Task**
2. Trigger: Daily / At log on / etc.
3. Action: Start a program
   - Program: `C:\path\to\venv\Scripts\python.exe`
   - Arguments: `C:\path\to\classroom\main.py`
   - Start in: `C:\path\to\classroom`

### Linux/macOS (cron)
```bash
crontab -e
# Каждый день в 7:00
0 7 * * * /path/to/venv/bin/python /path/to/classroom/main.py >> /path/to/classroom/cron.log 2>&1
```

---

## 📝 Лицензия

MIT License — свободно используйте и модифицируйте.

---

## 🤝 Поддержка

Если возникли проблемы:
1. Проверьте логи в консоли (цветной вывод покажет этап ошибки)
2. Убедитесь, что все API включены в Google Cloud
3. Попробуйте `--reauth` для обновления токена
4. Проверьте `token.json` — не должен быть пустым/повреждённым