#!/usr/bin/env python3
"""
Тестовый скрипт для проверки генерации PDF с русским текстом через ReportLab
с использованием шрифта DejaVu Sans.
"""
import os
import logging
import sys
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_dejavu_pdf_generation(output_path="dejavu_test_output.pdf"):
    """
    Создаёт тестовый PDF файл с русским текстом, используя шрифт DejaVu Sans
    
    Args:
        output_path (str): Путь для сохранения PDF
    """
    try:
        # Определяем путь к шрифту DejaVu Sans
        dejavu_paths = [
            "/mnt/nixmodules/nix/store/8zlvngilj5pvnnkyapgbbmv5rnamvgxk-dejavu-fonts-minimal-2.37/share/fonts/truetype/DejaVuSans.ttf",
            "/mnt/nixmodules/nix/store/am3y2gs2rj2fd13jvd3j2m9g5646dnw6-dejavu-fonts-minimal-2.37/share/fonts/truetype/DejaVuSans.ttf"
        ]
        
        # Проверяем какой путь существует
        dejavu_path = None
        for path in dejavu_paths:
            if os.path.exists(path):
                dejavu_path = path
                break
        
        if not dejavu_path:
            logger.error("Не удалось найти шрифт DejaVu Sans в системе")
            return False
        
        logger.info(f"Используем шрифт DejaVu Sans из: {dejavu_path}")
        
        # Регистрируем шрифт
        pdfmetrics.registerFont(TTFont('DejaVuSans', dejavu_path))
        
        # Создаем каталог, если его нет
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        # Настраиваем PDF документ
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            title="Тестовый PDF с русским текстом (DejaVu Sans)",
            author="PDF Generator"
        )
        
        # Получаем стандартные стили
        styles = getSampleStyleSheet()
        
        # Добавляем кастомный стиль для русского текста с DejaVu Sans
        styles.add(ParagraphStyle(
            name='RussianText',
            fontName='DejaVuSans',  # Используем зарегистрированный шрифт
            fontSize=12,
            leading=14,
            alignment=TA_JUSTIFY
        ))
        
        # Создаем список элементов для добавления в PDF
        story = []
        
        # Добавляем заголовок
        story.append(Paragraph("Тестовый PDF документ с русским текстом (DejaVu Sans)", styles['Title']))
        story.append(Spacer(1, 12))
        
        # Добавляем подзаголовок
        story.append(Paragraph("Пример работы с кириллицей", styles['RussianText']))
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
        story.append(Paragraph("Дополнительная информация", styles['RussianText']))
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
        
        logger.info(f"Тестовый PDF (DejaVu) успешно сгенерирован: {output_path}")
        logger.info(f"Размер файла: {os.path.getsize(output_path)} байт")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при генерации PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Проверяем окружение
    logger.info(f"Python version: {sys.version}")
    logger.info(f"File system encoding: {sys.getfilesystemencoding()}")
    logger.info(f"Default encoding: {sys.getdefaultencoding()}")
    
    # Запускаем тест
    test_dejavu_pdf_generation()