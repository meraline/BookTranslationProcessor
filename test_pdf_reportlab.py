#!/usr/bin/env python3
"""
Тестовый скрипт для проверки генерации PDF с русским текстом через ReportLab
"""
import os
import logging
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_pdf_generation(output_path="test_ru_output.pdf"):
    """
    Создаёт тестовый PDF файл с русским текстом
    
    Args:
        output_path (str): Путь для сохранения PDF
    """
    try:
        # Создаем каталог, если его нет
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        # Настраиваем PDF документ
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            title="Тестовый PDF с русским текстом",
            author="PDF Generator"
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
        story.append(Paragraph("Тестовый PDF документ с русским текстом", styles['Title']))
        story.append(Spacer(1, 12))
        
        # Добавляем подзаголовок
        story.append(Paragraph("Пример работы с кириллицей", styles['Heading2']))
        story.append(Spacer(1, 12))
        
        # Добавляем русский текст
        russian_text = """
        Это тестовый документ, содержащий русский текст. 
        Мы проверяем возможность правильного отображения кириллических символов в PDF.
        
        Тестируем различные символы: АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ абвгдеёжзийклмнопрстуфхцчшщъыьэюя
        
        Строки обычно переносятся автоматически, но для примера можно задать переносы явно.
        """
        
        # Добавляем параграф с русским текстом
        story.append(Paragraph(russian_text, styles['RussianText']))
        story.append(Spacer(1, 12))
        
        # Добавляем ещё один заголовок
        story.append(Paragraph("Дополнительная информация", styles['Heading2']))
        story.append(Spacer(1, 6))
        
        # Добавляем ещё текста для проверки
        more_text = """
        Проверка работы с разными стилями и форматированием в русском тексте.
        
        Текст может быть длинным и содержать различные символы и знаки препинания:
        1. Пункт первый - проверка списков;
        2. Пункт второй - проверка специальных символов: @, #, $, %, ^, &, *, (, ), «кавычки»;
        3. Пункт третий - проверка смешанного текста: English and Русский вместе.
        """
        
        story.append(Paragraph(more_text, styles['RussianText']))
        
        # Создаем PDF
        doc.build(story)
        
        logger.info(f"Тестовый PDF успешно сгенерирован: {output_path}")
        logger.info(f"Размер файла: {os.path.getsize(output_path)} байт")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при генерации PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Запускаем тест
    test_pdf_generation()