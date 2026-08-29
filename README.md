# 🏋️ Fitness Bot — Telegram фітнес-тренер

Telegram-бот на **aiogram 3** для планування тренувань, контролю виконання,
харчування та прогресу.

## Функціонал

- **Реєстрація**: стать, вік, вага, зріст, ціль (схуднення / набір маси / витривалість), рівень підготовки
- **Планування тренувань**: генерація програми на 4–8 тижнів з ротацією вправ по тижнях
- **База вправ**: назва, опис, м'язова група, посилання на відео/GIF (`data/exercises.json`)
- **Контроль виконання**: чекліст на день, відмітка «виконано», лог підходів/повторень/ваги
- **Нагадування**: тренування, вода, прийоми їжі (APScheduler)
- **Харчування**: щоденник калорій/БЖУ, орієнтовна денна норма (формула Міффліна-Сан Жеора)
  та персональна база продуктів (БЖУ на 100 г) з автопідрахунком за кількістю грамів
- **Прогрес**: кількість виконаних вправ, історія зміни ваги

## Технічний стек

- Python 3.12+, [aiogram 3](https://docs.aiogram.dev/) (async, FSM для анкет)
- SQLAlchemy 2.0 (async ORM) + SQLite (легкий перехід на PostgreSQL)
- Alembic (версійні міграції БД)
- APScheduler (нагадування за розкладом)
- Docker / docker-compose

## Структура проєкту

```
fitness-bot/
├── bot/
│   ├── handlers/        # start, workout, nutrition, progress, reminders
│   ├── keyboards/       # inline/reply клавіатури
│   ├── states/          # FSM для анкет
│   ├── database/        # моделі, engine, шар доступу до даних (requests.py)
│   ├── services/        # генератор планів тренувань, розрахунок калорій
│   ├── scheduler/       # нагадування (APScheduler)
│   └── config.py
├── alembic/             # міграції БД
├── data/
│   └── exercises.json   # база вправ
├── .env.example
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
└── main.py
```

## Крок 1. Отримати токен бота у @BotFather

1. Відкрий Telegram і знайди [@BotFather](https://t.me/BotFather).
2. Надішли команду `/newbot`.
3. Вкажи ім'я бота (відображуване, будь-яке) — наприклад `Fitness Coach`.
4. Вкажи унікальний username бота, що закінчується на `bot` — наприклад `my_fitness_coach_bot`.
5. BotFather надішле токен у форматі `123456789:AA...`. Скопіюй його — він знадобиться у `.env`.
6. (опційно) командою `/setdescription` та `/setuserpic` налаштуй опис і аватар бота.

## Крок 2. Локальний запуск без Docker

```bash
git clone <URL_вашого_репозиторію>
cd fitness-bot

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Відкрий .env і встав свій BOT_TOKEN

python main.py
```

При першому запуску бот сам створить `data/fitness.db` (SQLite) та наповнить
таблицю вправ даними з `data/exercises.json`.

## Крок 3. Запуск через Docker

```bash
cp .env.example .env
# Встав свій BOT_TOKEN у .env

docker compose up -d --build
docker compose logs -f      # переглянути логи
docker compose down         # зупинити
```

Папка `data/` монтується як volume, тому база даних зберігається між
перезапусками контейнера.

## Перехід на PostgreSQL

1. Додай у `requirements.txt` драйвер `asyncpg`.
2. Зміни `DATABASE_URL` у `.env` на:
   ```
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/fitness_bot
   ```
3. Онови `sqlalchemy.url` у `alembic.ini` на той самий рядок (без `+aiosqlite`).
4. Згенеруй і застосуй міграції:
   ```bash
   alembic revision --autogenerate -m "init"
   alembic upgrade head
   ```

Код моделей і хендлерів залишається без змін — це і є сенс шару SQLAlchemy ORM.

## Основні команди / кнопки бота

| Дія | Опис |
|---|---|
| `/start` | Реєстрація або головне меню |
| 📅 План на тиждень | Генерація/перегляд активного плану тренувань |
| 🏋️ Сьогоднішнє тренування | Чекліст вправ на поточний день |
| 🍽 Харчування | Щоденник калорій/БЖУ, денна норма |
| 📊 Прогрес | Статистика виконаних тренувань, історія ваги |
| ⚙️ Налаштування нагадувань | Увімкнути/вимкнути типи нагадувань |

## Логіка генерації плану тренувань

Для кожної пари (ціль × рівень) визначено шаблон тижня — які дні тижня
тренувальні та на які групи м'язів. Вправи вибираються з `data/exercises.json`
і **ротуються по тижнях** (кожен новий тиждень зсуває вибірку вправ у межах
групи м'язів), щоб програма не була одноманітною. Логіка — у
`bot/services/workout_generator.py`, легко розширюється новими шаблонами.

## Публікація на GitHub

```bash
cd fitness-bot
git init
git add .
git commit -m "Initial commit: fitness bot skeleton"
git branch -M main
git remote add origin https://github.com/<ваш_логін>/fitness-bot.git
git push -u origin main
```

## Подальший розвиток (ідеї)

- Анкета рівня активності поза тренуваннями для точнішого розрахунку калорій
- Індивідуальний час нагадувань через FSM-анкету (зараз — значення за замовчуванням у моделі `ReminderSettings`)
- Графіки прогресу (matplotlib / QuickChart) замість текстової історії
- Адмін-панель для редагування бази вправ
