#!/usr/bin/env python3
"""
Скрипт для проверки корректности работы с русскими символами в различных системах обработки текста.
"""
import os
import json
import logging
import sys
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_json_encoding(output_dir="output/encoding_test"):
    """
    Проверка кодировки русских символов в JSON файлах
    
    Args:
        output_dir (str): Директория для сохранения тестовых файлов
    """
    # Создаем тестовые каталоги
    os.makedirs(output_dir, exist_ok=True)
    
    # Тестовый русский текст
    test_text = "Проверка русских символов: АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    
    # Вывод информации в консоль
    logger.info("Тестовый текст (консоль):")
    logger.info(f""{test_text}"")
    
    # Создаем структуру JSON с русским текстом
    test_data = {
        "paragraphs": [
            test_text,
            "Второй параграф с русским текстом для проверки."
        ],
        "figures": [
            {
                "type": "diagram",
                "description": "Описание диаграммы на русском языке",
                "region": [100, 200, 300, 400],
                "image_path": "test_image.png"
            }
        ]
    }
    
    # Сохраняем в JSON файл
    json_path = os.path.join(output_dir, "russian_test.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=4)
    logger.info(f"JSON файл создан: {json_path}")
    
    # Читаем обратно JSON и выводим
    with open(json_path, 'r', encoding='utf-8') as f:
        loaded_data = json.load(f)
    
    logger.info("Текст из загруженного JSON файла:")
    logger.info(f""{loaded_data['paragraphs'][0]}"")
    
    return json_path, test_data

def test_pdf_generation(test_data, output_dir="output/encoding_test"):
    """
    Проверка кодировки русских символов в PDF
    
    Args:
        test_data (dict): Тестовые данные
        output_dir (str): Директория для сохранения тестовых файлов
    """
    # Путь к файлу PDF
    pdf_path = os.path.join(output_dir, "russian_test.pdf")
    
    # Настраиваем PDF документ
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        title="Тест русской кодировки",
        author="Test Script"
    )
    
    # Получаем стандартные стили
    styles = getSampleStyleSheet()
    
    # Добавляем кастомный стиль для русского текста
    styles.add(ParagraphStyle(
        name='RussianText',
        fontName='Helvetica',  # Стандартный шрифт с поддержкой кириллицы в ReportLab
        fontSize=12,
        leading=14,
        alignment=TA_JUSTIFY
    ))
    
    # Создаем список элементов для добавления в PDF
    story = []
    
    # Добавляем заголовок
    story.append(Paragraph("Тест кодировки русских символов", styles['Title']))
    story.append(Spacer(1, 12))
    
    # Добавляем текст из тестовых данных
    for paragraph in test_data["paragraphs"]:
        story.append(Paragraph(paragraph, styles['RussianText']))
        story.append(Spacer(1, 6))
    
    # Добавляем описания фигур
    if "figures" in test_data and test_data["figures"]:
        story.append(Paragraph("Описания фигур:", styles['Heading2']))
        story.append(Spacer(1, 6))
        
        for i, figure in enumerate(test_data["figures"], 1):
            caption = f"Фигура {i}: {figure.get('description', '')}"
            story.append(Paragraph(caption, styles['RussianText']))
            story.append(Spacer(1, 6))
    
    # Создаем PDF
    doc.build(story)
    logger.info(f"PDF файл создан: {pdf_path}")
    
    return pdf_path

def test_file_encoding(test_data, output_dir="output/encoding_test"):
    """
    Проверка кодировки русских символов в текстовых файлах
    
    Args:
        test_data (dict): Тестовые данные
        output_dir (str): Директория для сохранения тестовых файлов
    """
    # Создаем простой текстовый файл
    txt_path = os.path.join(output_dir, "russian_test.txt")
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("ТЕСТ РУССКОЙ КОДИРОВКИ\n\n")
        for paragraph in test_data["paragraphs"]:
            f.write(f"{paragraph}\n\n")
    
    logger.info(f"Текстовый файл создан: {txt_path}")
    
    # Читаем обратно текстовый файл
    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    logger.info("Текст из созданного файла:")
    logger.info(f""{content[:100]}..."")
    
    return txt_path

def check_environment():
    """Проверка настроек окружения, влияющих на кодировку"""
    logger.info(f"Python version: {sys.version}")
    logger.info(f"File system encoding: {sys.getfilesystemencoding()}")
    logger.info(f"Default encoding: {sys.getdefaultencoding()}")
    logger.info(f"Stdout encoding: {sys.stdout.encoding}")
    logger.info(f"Locale settings: {os.environ.get('LC_ALL')}, {os.environ.get('LANG')}")

if __name__ == "__main__":
    # Проверяем окружение
    check_environment()
    
    # Запускаем тесты кодировки
    json_path, test_data = test_json_encoding()
    txt_path = test_file_encoding(test_data)
    pdf_path = test_pdf_generation(test_data)
    
    logger.info("Все тесты кодировки завершены.")
    logger.info(f"Созданные файлы: {json_path}, {txt_path}, {pdf_path}")