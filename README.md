# Poker Book Processor

Система для обработки и перевода покерных книг с использованием OCR и OpenAI API. Проект позволяет извлекать текст и визуализации из изображений или PDF-файлов, переводить их на русский язык и генерировать два PDF-файла: один на языке оригинала, другой на русском.

## Функциональность

- Обработка PDF-файлов и изображений книжных страниц с помощью OCR
- Извлечение текста, таблиц и диаграмм
- Перевод контента с английского на русский с помощью OpenAI API
- Генерация PDF-файлов на двух языках с правильной поддержкой Unicode и кириллицы
- Веб-интерфейс для загрузки, управления и просмотра книг
- Пакетная обработка больших объемов файлов

## Требования к системе

- Python 3.8 или выше
- PostgreSQL 12 или выше
- Tesseract OCR 5.0 или выше
- OpenCV
- OpenAI API ключ
- 4 ГБ ОЗУ или больше (рекомендуется 8 ГБ)
- 10 ГБ свободного дискового пространства

## Установка и настройка

### 1. Клонирование репозитория

```bash
git clone https://github.com/yourusername/poker-book-processor.git
cd poker-book-processor
```

### 2. Установка зависимостей

#### Установка системных зависимостей (Ubuntu/Debian)

```bash
# Установка Tesseract OCR
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-rus

# Установка необходимых библиотек для OpenCV
sudo apt-get install -y libsm6 libxext6 libxrender-dev libgl1-mesa-glx

# Установка PostgreSQL
sudo apt-get install -y postgresql postgresql-contrib
```

#### Создание и активация виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

#### Установка Python-зависимостей

```bash
pip install -r dependencies.txt
```

### 3. Настройка базы данных PostgreSQL

```bash
# Создание пользователя и базы данных
sudo -u postgres psql -c "CREATE USER pokerbook WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "CREATE DATABASE pokerbook OWNER pokerbook;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE pokerbook TO pokerbook;"
```

### 4. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```
# База данных
DATABASE_URL=postgresql://pokerbook:yourpassword@localhost/pokerbook

# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# Настройки приложения
FLASK_APP=app.py
FLASK_DEBUG=0
SECRET_KEY=your_secret_key
```

### 5. Инициализация базы данных

```bash
# Активация контекста приложения
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### 6. Создание необходимых директорий

```bash
mkdir -p uploads output/pdf fonts
```

## Запуск приложения

### Стандартный запуск

```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 main:app
```

Приложение будет доступно по адресу: http://localhost:5000

### Запуск в режиме разработки

```bash
flask run --host=0.0.0.0 --port=5000
```

## Пакетная обработка больших объемов файлов

Для обработки больших объемов файлов (более 100 файлов) рекомендуется использовать пакетный режим:

```bash
# Создание директории для входных файлов
mkdir -p batch_input

# Копирование файлов для обработки
cp /путь/к/вашим/файлам/*.pdf batch_input/

# Запуск пакетной обработки
python batch_processor.py --input batch_input --batch-size 10 --wait-time 2 --workers 3
```

Параметры пакетной обработки:
- `--input`: Директория с входными файлами
- `--batch-size`: Количество файлов в одном пакете (по умолчанию 5)
- `--wait-time`: Время ожидания между пакетами в минутах (по умолчанию 5)
- `--workers`: Максимальное количество параллельных потоков обработки (по умолчанию 2)

## Оптимизация производительности

Для больших объемов данных рекомендуется оптимизировать настройки:

1. **Увеличение ресурсов системы**:
   - Минимум 8 ГБ ОЗУ (для параллельной обработки)
   - Многоядерный процессор (4+ ядер)
   - SSD-диск для быстрого доступа к данным

2. **Настройка PostgreSQL**:
   - Увеличение shared_buffers до 25% от объема ОЗУ
   - Настройка work_mem для сложных запросов
   - Увеличение max_connections для параллельной обработки

3. **Настройка Gunicorn**:
   - Увеличение количества workers (2 × количество ядер CPU + 1)
   - Настройка timeout для длительных операций

## Устранение проблем

### Проблемы с OCR

Если Tesseract не распознает текст корректно:

1. Проверьте установку языковых пакетов: `tesseract --list-langs`
2. Настройте предобработку изображений: измените параметры в `image_preprocessor.py`

### Проблемы с OpenAI API

1. Проверьте валидность API ключа
2. Убедитесь, что у вас достаточно средств на аккаунте OpenAI
3. Увеличьте задержку между запросами при пакетной обработке

### Проблемы с обработкой PDF

1. Проверьте, что ваш PDF не защищен паролем
2. Для очень больших PDF (100+ страниц) рекомендуется разделить файл на части
3. Выделите больше памяти для обработки больших PDF

## Лицензия

MIT License