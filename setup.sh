#!/bin/bash
# Скрипт настройки системы для проекта Poker Book Processor
# Выполняйте с правами sudo

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Функция для вывода статусов
function echo_status() {
    echo -e "${GREEN}[+] $1${NC}"
}

function echo_error() {
    echo -e "${RED}[!] $1${NC}"
}

function echo_warning() {
    echo -e "${YELLOW}[!] $1${NC}"
}

# Проверка запуска от имени пользователя с sudo правами
if [ "$EUID" -ne 0 ]; then
  echo_error "Пожалуйста, запустите скрипт с правами sudo"
  exit 1
fi

# Получение имени текущего пользователя (не root)
CURRENT_USER=$(logname || echo $SUDO_USER)

echo_status "Установка начата. Текущий пользователь: $CURRENT_USER"

# Установка системных зависимостей
echo_status "Установка системных зависимостей..."
apt-get update
apt-get install -y python3 python3-venv python3-pip \
    tesseract-ocr tesseract-ocr-rus \
    libsm6 libxext6 libxrender-dev libgl1-mesa-glx \
    postgresql postgresql-contrib

# Настройка PostgreSQL
echo_status "Настройка PostgreSQL..."
# Создание пользователя и базы данных
su - postgres -c "psql -c \"CREATE USER pokerbook WITH PASSWORD 'pokerbook';\""
su - postgres -c "psql -c \"CREATE DATABASE pokerbook OWNER pokerbook;\""
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE pokerbook TO pokerbook;\""

# Создание директорий проекта
echo_status "Создание директорий проекта..."
mkdir -p uploads output/pdf fonts batch_input
chown -R $CURRENT_USER:$CURRENT_USER uploads output fonts batch_input

# Настройка файла окружения
echo_status "Создание файла .env..."
cat > .env <<EOL
# База данных
DATABASE_URL=postgresql://pokerbook:pokerbook@localhost/pokerbook

# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# Настройки приложения
FLASK_APP=app.py
FLASK_DEBUG=0
SECRET_KEY=$(openssl rand -hex 24)
EOL

chown $CURRENT_USER:$CURRENT_USER .env
echo_warning "Пожалуйста, отредактируйте файл .env и добавьте ваш API ключ OpenAI"

# Настройка виртуального окружения
echo_status "Настройка виртуального окружения Python..."
su - $CURRENT_USER -c "cd $(pwd) && python3 -m venv venv"
su - $CURRENT_USER -c "cd $(pwd) && source venv/bin/activate && pip install -r dependencies.txt"

# Инициализация базы данных
echo_status "Инициализация базы данных..."
su - $CURRENT_USER -c "cd $(pwd) && source venv/bin/activate && python -c \"from app import app, db; app.app_context().push(); db.create_all()\""

# Создание systemd сервиса для запуска приложения
echo_status "Создание systemd сервиса..."
cat > /etc/systemd/system/pokerbook.service <<EOL
[Unit]
Description=Poker Book Processor
After=network.target postgresql.service

[Service]
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$(pwd)
Environment="PATH=$(pwd)/venv/bin"
ExecStart=$(pwd)/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Активация и запуск сервиса
systemctl daemon-reload
systemctl enable pokerbook.service
systemctl start pokerbook.service

echo_status "Установка завершена!"
echo_status "Сервис запущен и доступен по адресу: http://localhost:5000"
echo_warning "Не забудьте отредактировать файл .env и добавить ваш API ключ OpenAI"
echo_status "Для просмотра логов используйте: sudo journalctl -u pokerbook.service -f"