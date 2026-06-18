# 📦 Руководство по развёртыванию Mining Bot

## Быстрый старт

### 1. Получение токена бота

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather)
2. Отправьте команду `/newbot`
3. Следуйте инструкциям:
   - Введите имя бота (например, `Mining Game Bot`)
   - Введите username бота (должен заканчиваться на `bot`, например, `mining_game_bot`)
4. Скопируйте полученный токен (выглядит как `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Настройка проекта

```bash
# Скопируйте пример конфигурации
copy .env.example .env

# Отредактируйте .env файл
notepad .env
```

Вставьте ваш токен:
```
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
DATABASE_URL=sqlite+aiosqlite:///mining_bot.db
```

### 3. Установка зависимостей

```bash
# Создание виртуального окружения (рекомендуется)
python -m venv venv
venv\Scripts\activate

# Установка пакетов
pip install -r requirements.txt
```

### 4. Запуск бота

```bash
python bot.py
```

### 5. Проверка работы

1. Найдите вашего бота в Telegram по username
2. Отправьте команду `/start`
3. Проверьте работу кнопок и меню

## 🐍 Развёртывание на сервере

### Heroku

1. Создайте файл `Procfile`:
```
worker: python bot.py
```

2. Создайте `runtime.txt`:
```
python-3.11.0
```

3. Деплой:
```bash
heroku create your-bot-name
heroku config:set BOT_TOKEN=your_token
git push heroku main
```

### VPS (Ubuntu/Debian)

```bash
# Установка Python и зависимостей
sudo apt update
sudo apt install python3 python3-pip python3-venv -y

# Клонирование проекта
git clone <repository_url>
cd mining_bot

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Настройка .env
cp .env.example .env
nano .env  # Вставьте токен

# Создание systemd сервиса
sudo nano /etc/systemd/system/mining-bot.service
```

Содержимое сервиса:
```ini
[Unit]
Description=Mining Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/mining_bot
Environment="PATH=/home/ubuntu/mining_bot/venv/bin"
ExecStart=/home/ubuntu/mining_bot/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Запуск:
```bash
sudo systemctl daemon-reload
sudo systemctl enable mining-bot
sudo systemctl start mining-bot
sudo systemctl status mining-bot
```

### Docker

Создайте `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

Запуск:
```bash
docker build -t mining-bot .
docker run -d --name mining-bot -e BOT_TOKEN=your_token mining-bot
```

### Docker Compose

`docker-compose.yml`:
```yaml
version: '3.8'

services:
  bot:
    build: .
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - DATABASE_URL=sqlite+aiosqlite:///data/mining_bot.db
    volumes:
      - bot_data:/data
    restart: unless-stopped

volumes:
  bot_data:
```

Запуск:
```bash
docker-compose up -d
```

## 🗄️ Использование PostgreSQL (опционально)

Для продакшена рекомендуется PostgreSQL:

1. Установка PostgreSQL:
```bash
# Ubuntu
sudo apt install postgresql postgresql-contrib -y

# Создание базы данных
sudo -u postgres psql
CREATE DATABASE mining_bot;
CREATE USER mining_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE mining_bot TO mining_user;
\q
```

2. Обновите `.env`:
```
DATABASE_URL=postgresql+asyncpg://mining_user:your_password@localhost:5432/mining_bot
```

3. Установка драйвера:
```bash
pip install asyncpg
```

## 🔧 Настройка и кастомизация

### Изменение параметров игры

Отредактируйте `config.py`:

```python
# Время добычи (в секундах)
BASE_MINING_TIME = 300  # 5 минут

# Задержка между обновлениями (Flood Wait)
FLOOD_WAIT = 120  # 2 минуты

# Шансы выпадения
PLASMA_CHANCE = 5  # 5%
CASE_CHANCE = 2    # 2%

# Цены на руду
ORE_PRICES = {
    "камень": 1,
    "уголь": 3,
    # ...
}
```

### Добавление новых шахт

В `config.py`:
```python
MINES = {
    # ... существующие шахты ...
    8: {
        "name": "Подземелье",
        "level_req": 17,
        "ores": ["алмаз", "платина", "мифрил"]
    },
}
```

### Добавление новых команд

В `handlers.py`:
```python
@router.message(Command("new_command"))
async def cmd_new(message: types.Message, session: AsyncSession):
    await message.answer("Новая команда!")
```

## 📊 Мониторинг

### Логи

```bash
# Просмотр логов (systemd)
sudo journalctl -u mining-bot -f

# Просмотр логов (Docker)
docker logs -f mining-bot
```

### Статистика

Добавьте команду `/stats` для просмотра статистики:
- Количество пользователей
- Активные игроки
- Общая добыча

## 🐛 Решение проблем

### Бот не отвечает

1. Проверьте токен в `.env`
2. Убедитесь, что бот запущен
3. Проверьте логи на ошибки

### Ошибки базы данных

```bash
# Для SQLite - удалите файл БД
del mining_bot.db

# Для PostgreSQL - проверьте подключение
psql -h localhost -U mining_user -d mining_bot
```

### Проблемы с зависимостями

```bash
# Обновление pip
python -m pip install --upgrade pip

# Переустановка зависимостей
pip install -r requirements.txt --force-reinstall
```

## 🔒 Безопасность

1. **Никогда не коммитьте `.env`** в git
2. Используйте переменные окружения для токенов
3. Ограничьте доступ к базе данных
4. Регулярно обновляйте зависимости

## 📈 Масштабирование

### Кэширование

Для больших проектов добавьте Redis:

```python
# config.py
REDIS_URL = "redis://localhost:6379"

# В handlers.py
import redis.asyncio as redis
redis_client = redis.from_url(REDIS_URL)
```

### Шардирование

Для миллионов пользователей рассмотрите:
- Несколько инстансов бота
- Разделение базы данных
- Балансировку нагрузки

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи
2. Поищите решение в документации aiogram
3. Создайте issue в репозитории

---

**Успешного развёртывания! 🚀**
