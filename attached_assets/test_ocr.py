#!/usr/bin/env python3
"""
Скрипт для тестового запуска OCR на 5 изображениях
"""
# Добавьте эти строки в начало test_ocr.py и poker_book_processor.py
from dotenv import load_dotenv
load_dotenv()  # Загружает переменные из .env файла

import os
import glob
import sys
from poker_book_processor import PokerBookProcessor

def main():
    # Базовый путь к изображениям
    base_path = '/home/analityk/Документы/github/AmazonBookParser/kindle_screenshots'
    
    # Проверка существования директории
    if not os.path.exists(base_path):
        print(f"Ошибка: директория {base_path} не существует")
        sys.exit(1)
    
    # Получение списка всех PNG-файлов в директории
    all_images = glob.glob(os.path.join(base_path, '*.png'))
    
    if not all_images:
        print(f"Ошибка: не найдено PNG-файлов в директории {base_path}")
        sys.exit(1)
    
    # Выбор только 5 изображений для теста
    test_images = all_images[:5]
    
    print(f"Начинаем тестовую обработку следующих 5 изображений:")
    for i, img_path in enumerate(test_images, 1):
        print(f"{i}. {os.path.basename(img_path)}")
    
    # Здесь необходимо указать ваш API ключ для OpenAI
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    if not openai_api_key:
        print("Предупреждение: API ключ OpenAI не найден в переменных окружения.")
        print("Для лучшего качества распознавания текста рекомендуется использовать OpenAI API.")
        print("Продолжаем обработку без улучшения с помощью OpenAI.")
    
    # Создание и запуск процессора
    processor = PokerBookProcessor(
        output_dir='test_output',
        openai_api_key=openai_api_key,  # Используем API ключ из переменных окружения
        target_language='ru'
    )
    
    # Запуск обработки
    results = processor.batch_process(test_images)
    
    if results:
        print("\nТестирование успешно завершено!")
        print(f"Обработано изображений: {results['processed_images']} из {results['total_images']}")
        print(f"Результаты сохранены в директории: test_output")
    else:
        print("\nОшибка при обработке изображений.")

if __name__ == "__main__":
    main()