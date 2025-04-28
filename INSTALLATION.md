# Подробная инструкция по установке и настройке

Эта инструкция предназначена для подробного развертывания проекта Poker Book Processor на вашем сервере.

## 1. Требования к серверу

### Минимальные требования:
- CPU: 2 ядра
- RAM: 4 ГБ
- Дисковое пространство: 10 ГБ
- ОС: Ubuntu 20.04 или новее / Debian 11 или новее

### Рекомендуемые требования (для обработки больших объемов):
- CPU: 4+ ядер
- RAM: 8+ ГБ
- Дисковое пространство: 20+ ГБ (SSD предпочтительно)
- ОС: Ubuntu 22.04 / Debian 12

## 2. Подготовка системы

### 2.1. Установка базовых инструментов

```bash
sudo apt-get update
sudo apt-get install -y git curl build-essential
```

### 2.2. Клонирование репозитория

```bash
git clone https://github.com/yourusername/poker-book-processor.git
cd poker-book-processor
```

## 3. Автоматическая установка

Для автоматической установки запустите установочный скрипт:

```bash
chmod +x setup.sh
sudo ./setup.sh
```

После выполнения скрипта:
1. Проверьте файл `.env` и добавьте ваш API-ключ OpenAI
2. Перезапустите сервис: `sudo systemctl restart pokerbook.service`
3. Проверьте доступность сервиса по адресу: http://YOUR_SERVER_IP:5000

## 4. Ручная установка

Если вы предпочитаете ручную установку или автоматическая установка завершилась с ошибками, следуйте инструкциям ниже.

### 4.1. Установка зависимостей Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r dependencies.txt
```

### 4.2. Установка Tesseract OCR

```bash
sudo apt-get install -y tesseract-ocr
sudo apt-get install -y tesseract-ocr-rus  # для русского языка
```

Проверка установки:
```bash
tesseract --version
tesseract --list-langs  # должен показать доступные языки, включая rus
```

### 4.3. Настройка PostgreSQL

```bash
sudo apt-get install -y postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER pokerbook WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "CREATE DATABASE pokerbook OWNER pokerbook;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE pokerbook TO pokerbook;"
```

### 4.4. Настройка переменных окружения

Создайте файл `.env` в корневой директории проекта:

```
DATABASE_URL=postgresql://pokerbook:yourpassword@localhost/pokerbook
OPENAI_API_KEY=your_openai_api_key
FLASK_APP=app.py
FLASK_DEBUG=0
SECRET_KEY=your_random_secret_key
```

### 4.5. Инициализация базы данных

```bash
source venv/bin/activate
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### 4.6. Создание необходимых директорий

```bash
mkdir -p uploads output/pdf fonts batch_input
```

## 5. Запуск приложения

### 5.1. Запуск через systemd (рекомендуется для production)

Создайте файл `/etc/systemd/system/pokerbook.service`:

```ini
[Unit]
Description=Poker Book Processor
After=network.target postgresql.service

[Service]
User=your_username
Group=your_username
WorkingDirectory=/path/to/poker-book-processor
Environment="PATH=/path/to/poker-book-processor/venv/bin"
ExecStart=/path/to/poker-book-processor/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Запуск и активация сервиса:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pokerbook.service
sudo systemctl start pokerbook.service
```

Проверка статуса:
```bash
sudo systemctl status pokerbook.service
```

Просмотр логов:
```bash
sudo journalctl -u pokerbook.service -f
```

### 5.2. Запуск вручную (для разработки/тестирования)

```bash
source venv/bin/activate
gunicorn --bind 0.0.0.0:5000 --workers 2 main:app
```

## 6. Настройка Nginx (опционально)

Для доступа к приложению через веб-сервер Nginx:

```bash
sudo apt-get install -y nginx
```

Создайте файл конфигурации `/etc/nginx/sites-available/pokerbook`:

```nginx
server {
    listen 80;
    server_name your_domain.com;  # или IP-адрес сервера

    client_max_body_size 50M;  # Увеличиваем максимальный размер загружаемых файлов

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активация конфигурации:
```bash
sudo ln -s /etc/nginx/sites-available/pokerbook /etc/nginx/sites-enabled/
sudo nginx -t  # проверка конфигурации
sudo systemctl restart nginx
```

## 7. Настройка пакетной обработки

Для обработки больших объемов файлов рекомендуется использовать пакетную обработку:

1. Создайте директорию для входных файлов и скопируйте туда необходимые файлы:
```bash
mkdir -p batch_input
cp /path/to/your/files/*.pdf batch_input/
```

2. Запустите пакетную обработку:
```bash
source venv/bin/activate
python batch_processor.py --input batch_input --batch-size 10 --wait-time 2 --workers 3
```

## 8. Настройка для высокой нагрузки

### 8.1. Оптимизация PostgreSQL

Отредактируйте файл `/etc/postgresql/{version}/main/postgresql.conf`:

```
shared_buffers = 2GB  # Рекомендуется 25% от ОЗУ
work_mem = 64MB  # Увеличиваем для сложных запросов
maintenance_work_mem = 256MB
effective_cache_size = 6GB  # Примерно 75% от ОЗУ
max_connections = 100
```

Перезапустите PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### 8.2. Оптимизация Gunicorn

Создайте файл `gunicorn_config.py`:

```python
# Количество рабочих процессов (2 × кол-во ядер CPU + 1)
workers = 9
# Тайм-аут для долгих запросов (обработка PDF)
timeout = 300
# Максимальное количество одновременных соединений
max_requests = 1000
# Перезапуск после определенного количества запросов
max_requests_jitter = 50
# Ограничение использования ОЗУ
worker_class = 'gthread'
worker_connections = 1000
threads = 4
```

Обновите systemd-сервис для использования этой конфигурации:
```
ExecStart=/path/to/poker-book-processor/venv/bin/gunicorn -c gunicorn_config.py main:app
```

## 9. Устранение проблем

### 9.1. Проблемы с доступом к базе данных

Проверьте настройки подключения к PostgreSQL:
```bash
psql -U pokerbook -h localhost -d pokerbook
```

Если не удается подключиться, проверьте настройки аутентификации в файле `/etc/postgresql/{version}/main/pg_hba.conf`.

### 9.2. Проблемы с Tesseract OCR

Убедитесь, что Tesseract правильно установлен:
```bash
tesseract --version
tesseract --list-langs
```

Проверьте права доступа к временным директориям:
```bash
chmod -R 755 /tmp
```

### 9.3. Проблемы с OpenAI API

- Убедитесь, что ваш API-ключ действителен и имеет достаточный баланс
- Проверьте наличие переменной окружения `OPENAI_API_KEY` в файле `.env`
- Проверьте, не блокируется ли ваш IP-адрес на стороне OpenAI

### 9.4. Недостаточно места на диске

Очистите временные файлы и старые выходные данные:
```bash
rm -rf output/*/temp/*
find uploads -type f -mtime +30 -delete  # Удаляет файлы старше 30 дней
```