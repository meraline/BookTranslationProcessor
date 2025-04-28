#!/usr/bin/env python3
"""
Module for generating PDF files from processed book content.
Uses ReportLab for better Unicode and Russian text support.
"""
import os
import logging
import traceback
import re
import cv2
from PIL import Image
import numpy as np
import unicodedata
# Import text sanitization functions
from text_sanitizer import sanitize_text_for_pdf, aggressive_text_cleanup

# Use ReportLab for PDF generation with Unicode support
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PDFGenerator:
    """Handles generation of PDF files from processed content."""
    
    def __init__(self, output_dir, fonts_dir=None):
        """
        Initialize PDF generator.
        
        Args:
            output_dir (str): Directory to save PDFs
            fonts_dir (str, optional): Directory with custom fonts
        """
        # Инициализируем логгер, если он доступен
        try:
            from logger_config import pdf_logger
            self.logger = pdf_logger
            self.use_custom_logger = True
        except ImportError:
            self.logger = logger
            self.use_custom_logger = False
            
        # Проверяем, содержит ли output_dir уже 'pdf' в пути
        # Это помогает избежать дублирования пути 'pdf/pdf'
        if output_dir.endswith('pdf') or '/pdf/' in output_dir or '\\pdf\\' in output_dir:
            self.output_dir = output_dir
            if self.use_custom_logger:
                self.logger.info(f"Путь уже содержит 'pdf', используем как есть: {output_dir}")
        else:
            self.output_dir = os.path.join(output_dir, 'pdf')
            if self.use_custom_logger:
                self.logger.info(f"Добавлен 'pdf' к пути: {self.output_dir}")
                
        self.fonts_dir = fonts_dir
        
        # Создадим директорию, если она не существует
        os.makedirs(self.output_dir, exist_ok=True)
        if self.use_custom_logger:
            self.logger.info(f"Создана директория для PDF: {self.output_dir}")
            self.logger.info(f"Проверка существования директории: {os.path.exists(self.output_dir)}")
    
    def _setup_pdf(self, title=None):
        """
        Set up the PDF document with standard fonts using ReportLab.
        
        Args:
            title (str, optional): Title for the PDF
            
        Returns:
            dict: Configured PDF styles and document
        """
        # Используем стандартные шрифты ReportLab, которые встроены
        # Helvetica, Times-Roman, Courier - они всегда доступны
        
        # Регистрация шрифтов для обеспечения поддержки кириллицы
        # Сначала проверим, зарегистрирован ли уже шрифт DejaVuSans
        registered_fonts = pdfmetrics.getRegisteredFontNames()
        
        if 'DejaVuSans' not in registered_fonts:
            try:
                # Попытка зарегистрировать шрифт DejaVuSans из системных директорий
                dejavu_paths = [
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # Linux
                    'C:\\Windows\\Fonts\\DejaVuSans.ttf',  # Windows
                    '/System/Library/Fonts/DejaVuSans.ttf',  # macOS
                    'fonts/DejaVuSans.ttf',  # Локальная директория проекта
                    os.path.join(os.path.dirname(__file__), 'fonts', 'DejaVuSans.ttf')  # Относительно скрипта
                ]
                
                for font_path in dejavu_paths:
                    if os.path.exists(font_path):
                        pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
                        logger.info(f"Зарегистрирован шрифт DejaVuSans из {font_path}")
                        break
            except Exception as e:
                logger.warning(f"Не удалось зарегистрировать шрифт DejaVuSans: {str(e)}")
                logger.info("Будет использован стандартный шрифт Helvetica")
        
        # Создаем стили для различных элементов текста
        styles = getSampleStyleSheet()
        
        # Определяем базовый шрифт в зависимости от доступности
        base_font = 'DejaVuSans' if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
        bold_font = f'{base_font}-Bold' if 'DejaVuSans' in base_font else 'Helvetica-Bold'
        italic_font = f'{base_font}-Italic' if 'DejaVuSans' in base_font else 'Helvetica-Oblique'
        
        logger.info(f"Используемый базовый шрифт: {base_font}")
        
        # Добавляем пользовательские стили для текста с поддержкой Юникода/кириллицы
        styles.add(ParagraphStyle(
            name='NormalRu',
            fontName=base_font,
            fontSize=12,
            leading=14,
            alignment=TA_JUSTIFY,
            wordWrap='CJK',  # Улучшенный перенос слов для не-латинских символов
            encoding='utf-8'
        ))
        
        styles.add(ParagraphStyle(
            name='HeadingRu',
            fontName=bold_font,
            fontSize=16,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=10,
            encoding='utf-8'
        ))
        
        styles.add(ParagraphStyle(
            name='TitleRu',
            fontName=bold_font,
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=20,
            encoding='utf-8'
        ))
        
        styles.add(ParagraphStyle(
            name='TOCEntry',
            fontName=base_font,
            fontSize=12,
            leading=14,
            alignment=TA_LEFT,
            encoding='utf-8'
        ))
        
        styles.add(ParagraphStyle(
            name='CaptionRu',
            fontName=italic_font,
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
            spaceAfter=6,
            encoding='utf-8'
        ))
            
        logger.info("PDF styles configured with enhanced Unicode/Russian text support")
        
        # Create PDF document setup
        return {
            'styles': styles,
            'title': title
        }
    
    def generate_pdf(self, document_structure, language, book_title=None):
        """
        Generate PDF from document structure.
        
        Args:
            document_structure (dict): Document structure with content
            language (str): Language code (en/ru)
            book_title (str, optional): Title of the book
            
        Returns:
            str: Path to the generated PDF
        """
        try:
            # Create a safe, short output filename using UUID to prevent path-too-long errors
            import uuid
            
            # Get a short prefix from the book title (max 15 chars)
            prefix = ""
            if book_title:
                # Take just the first word or first 15 chars
                first_part = book_title.split()[0] if ' ' in book_title else book_title[:15]
                prefix = re.sub(r'[^\w\s-]', '', first_part).replace(' ', '_')
                
                # Make sure we don't exceed max length
                if len(prefix) > 15:
                    prefix = prefix[:15]
            else:
                prefix = "book"
                
            # Generate a short unique filename
            unique_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID
            filename = f"{prefix}_{unique_id}_{language}.pdf"
                
            # self.output_dir is something like 'output/book_5'
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Генерируем путь к PDF файлу, избегая дублирования частей пути
            output_path = os.path.join(self.output_dir, filename)
            
            # Логируем путь
            if self.use_custom_logger:
                self.logger.info(f"PDF будет сохранен по пути: {output_path}")
                self.logger.info(f"self.output_dir = {self.output_dir}")
                self.logger.info(f"filename = {filename}")
            else:
                logger.info(f"PDF will be saved to: {output_path}")
            
            # Make sure the directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Setup PDF with ReportLab
            pdf_setup = self._setup_pdf(book_title)
            styles = pdf_setup['styles']
            
            # Create a document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                title=book_title or "Poker Book",
                author="Poker Book Processor"
            )
            
            # Create story (content elements)
            story = []
            
            # Add title if available
            if 'title' in document_structure:
                title = document_structure['title']
                story.append(Paragraph(title, styles['TitleRu'] if language == 'ru' else styles['Title']))
                
                # Add date
                from datetime import datetime
                date_str = datetime.now().strftime("%d.%m.%Y")
                date_paragraph = Paragraph(f"Создано: {date_str}" if language == 'ru' else f"Created: {date_str}", 
                                         styles['Italic'])
                story.append(date_paragraph)
                story.append(Spacer(1, 12))
            
            # Add table of contents header
            toc_title = "Содержание" if language == 'ru' else "Table of Contents"
            story.append(Paragraph(toc_title, styles['Heading1']))
            story.append(Spacer(1, 12))
            
            # Collect TOC entries for later
            toc_entries = []
            
            # Add main text section header
            main_text_title = "Текст" if language == 'ru' else "Text"
            story.append(Paragraph(main_text_title, styles['Heading1']))
            story.append(Spacer(1, 12))
            toc_entries.append((main_text_title, 1))  # Page numbers are approximate
            
            # Process all text content - deduplicate and organize paragraphs
            all_paragraphs = []
            seen_paragraphs = set()
            
            # Выбираем источник текста в зависимости от языка
            paragraphs_source = 'paragraphs'  # По умолчанию - обработанный текст (улучшенный англ. или переведенный рус.)
            
            # Для русского языка всегда используем переведенные параграфы
            # Для английского можем использовать оригинальные или улучшенные параграфы
            if language == 'en' and 'original_paragraphs' in document_structure:
                # Используем улучшенные параграфы на английском, не перевод
                logger.info("Using English paragraphs for English PDF")
                paragraphs_source = 'paragraphs'  # Это улучшенный английский текст
            elif language == 'ru':
                logger.info("Using translated paragraphs for Russian PDF")
                paragraphs_source = 'paragraphs'  # Для русского PDF используем переведенные параграфы
            
            # Log more information about the document structure for debugging
            logger.info(f"Document structure keys: {list(document_structure.keys())}")
            if 'enhanced_text' in document_structure:
                logger.info(f"Enhanced text length: {len(document_structure['enhanced_text'])}")
            if 'original_text' in document_structure:
                logger.info(f"Original text length: {len(document_structure['original_text'])}")
                
            # Проверяем наличие параграфов
            if paragraphs_source not in document_structure or not document_structure[paragraphs_source]:
                logger.warning(f"Параграфы не найдены в документе: {paragraphs_source}")
                # Пробуем использовать другой источник текста
                if 'enhanced_text' in document_structure and document_structure['enhanced_text']:
                    logger.info("Используем enhanced_text как запасной вариант")
                    # Разбиваем текст на параграфы по двойному переносу строки
                    enhanced_text = document_structure['enhanced_text']
                    document_structure[paragraphs_source] = enhanced_text.split('\n\n') if enhanced_text else []
                    logger.info(f"Создано {len(document_structure[paragraphs_source])} параграфов из enhanced_text")
                elif 'original_text' in document_structure and document_structure['original_text']:
                    logger.info("Используем original_text как запасной вариант")
                    # Разбиваем текст на параграфы по двойному переносу строки
                    original_text = document_structure['original_text']
                    document_structure[paragraphs_source] = original_text.split('\n\n') if original_text else []
                    logger.info(f"Создано {len(document_structure[paragraphs_source])} параграфов из original_text")
                
            if paragraphs_source in document_structure:
                for paragraph in document_structure[paragraphs_source]:
                    # Skip empty paragraphs
                    paragraph = paragraph.strip()
                    if not paragraph:
                        continue
                        
                    # Skip very short paragraphs that are likely artifacts
                    if len(paragraph) < 10 and not (paragraph.endswith(':') or paragraph.strip().isupper()):
                        continue
                        
                    # Skip if we've seen this paragraph before
                    paragraph_hash = paragraph[:100]  # Use first 100 chars as "hash"
                    if paragraph_hash in seen_paragraphs:
                        continue
                        
                    # Add to our list and mark as seen
                    all_paragraphs.append(paragraph)
                    seen_paragraphs.add(paragraph_hash)
            
            # Process paragraphs
            section_count = 0
            for paragraph in all_paragraphs:
                # Check if this looks like a heading
                is_heading = False
                if len(paragraph) < 100 and paragraph.strip().endswith(':'):
                    is_heading = True
                elif len(paragraph) < 60 and paragraph.strip().isupper():
                    is_heading = True
                    
                if is_heading:
                    # This is a heading - start a new section
                    section_count += 1
                    heading_text = paragraph.strip().rstrip(':')
                    
                    # Add heading and to TOC
                    story.append(Spacer(1, 10))
                    story.append(Paragraph(heading_text, styles['HeadingRu'] if language == 'ru' else styles['Heading2']))
                    story.append(Spacer(1, 6))
                    
                    toc_entries.append((f"    {heading_text}", 1))  # Page numbers are approximate
                else:
                    # Regular paragraph - using NormalRu style for Russian text support
                    try:
                        # Заменяем проблемные символы Unicode на их правильные представления
                        sanitized_text = sanitize_text_for_pdf(paragraph)
                        if not sanitized_text:
                            logger.warning(f"Пустой параграф после санитизации: '{paragraph[:50]}...'")
                            continue
                        
                        # Используем подходящий стиль в зависимости от языка
                        style_to_use = styles['NormalRu'] if language == 'ru' else styles['Normal']
                        story.append(Paragraph(sanitized_text, style_to_use))
                        story.append(Spacer(1, 6))
                    except Exception as e:
                        logger.error(f"Error adding paragraph: {str(e)}")
                        try:
                            # Пробуем более агрессивную очистку текста
                            safe_text = aggressive_text_cleanup(paragraph)
                            story.append(Paragraph(safe_text, styles['Normal']))
                            story.append(Spacer(1, 6))
                        except Exception as e2:
                            logger.error(f"Failed even with aggressive cleanup: {str(e2)}")
                            # Добавляем параграф с простым текстом без форматирования
                            story.append(Paragraph("Text content was removed due to encoding issues", styles['Normal']))
                            story.append(Spacer(1, 6))
            
            # Add figures section if any
            if 'figures' in document_structure and document_structure['figures']:
                story.append(Spacer(1, 12))
                figures_title = "Диаграммы и графики" if language == 'ru' else "Diagrams and Charts"
                story.append(Paragraph(figures_title, styles['Heading1']))
                story.append(Spacer(1, 12))
                toc_entries.append((figures_title, 1))  # Page numbers are approximate
                
                # Process figures
                figure_count = 0
                for figure in document_structure['figures']:
                    figure_count += 1
                    
                    # Create figure caption
                    figure_caption = f"Figure {figure_count}: {figure.get('description', '')}" if language == 'en' else f"Рисунок {figure_count}: {figure.get('description', '')}"
                    
                    # Get image path and add to PDF
                    image_path = figure.get('path')
                    if image_path and os.path.exists(image_path):
                        try:
                            img = RLImage(image_path, width=400, height=300)
                            story.append(img)
                            story.append(Paragraph(figure_caption, styles['CaptionRu'] if language == 'ru' else styles['Italic']))
                            story.append(Spacer(1, 12))
                        except Exception as e:
                            logger.error(f"Error adding figure image: {str(e)}")
                            story.append(Paragraph(f"[Figure {figure_count} - Image could not be loaded]", styles['Normal']))
                            story.append(Paragraph(figure_caption, styles['CaptionRu'] if language == 'ru' else styles['Italic']))
                            story.append(Spacer(1, 12))
                    else:
                        # No image, just add caption
                        story.append(Paragraph(f"[Figure {figure_count} - No image available]", styles['Normal']))
                        story.append(Paragraph(figure_caption, styles['CaptionRu'] if language == 'ru' else styles['Italic']))
                        story.append(Spacer(1, 12))
            
            # Add tables section if any
            if 'tables' in document_structure and document_structure['tables']:
                story.append(Spacer(1, 12))
                tables_title = "Таблицы" if language == 'ru' else "Tables"
                story.append(Paragraph(tables_title, styles['Heading1']))
                story.append(Spacer(1, 12))
                toc_entries.append((tables_title, 1))  # Page numbers are approximate
                
                # Process tables
                table_count = 0
                for table in document_structure['tables']:
                    table_count += 1
                    
                    # Create table caption
                    table_caption = f"Table {table_count}: {table.get('description', '')}" if language == 'en' else f"Таблица {table_count}: {table.get('description', '')}"
                    
                    # Get table image or data
                    image_path = table.get('path')
                    if image_path and os.path.exists(image_path):
                        try:
                            img = RLImage(image_path, width=450, height=300)
                            story.append(img)
                            story.append(Paragraph(table_caption, styles['CaptionRu'] if language == 'ru' else styles['Italic']))
                            story.append(Spacer(1, 12))
                        except Exception as e:
                            logger.error(f"Error adding table image: {str(e)}")
                            story.append(Paragraph(f"[Table {table_count} - Image could not be loaded]", styles['Normal']))
                            story.append(Paragraph(table_caption, styles['CaptionRu'] if language == 'ru' else styles['Italic']))
                            story.append(Spacer(1, 12))
                    else:
                        # No image, just add caption
                        story.append(Paragraph(f"[Table {table_count} - No image available]", styles['Normal']))
                        story.append(Paragraph(table_caption, styles['CaptionRu'] if language == 'ru' else styles['Italic']))
                        story.append(Spacer(1, 12))
            
            # Build the PDF
            try:
                doc.build(story)
                logger.info(f"Generated PDF: {output_path}")
                
                # Verify the file was created
                if os.path.exists(output_path):
                    logger.info(f"Verified PDF exists at: {output_path}, size: {os.path.getsize(output_path)} bytes")
                    return output_path
                else:
                    logger.error(f"PDF file was not created at: {output_path}")
                    return None
            except Exception as e:
                logger.error(f"Error building PDF: {str(e)}")
                traceback.print_exc()
                
                # Try saving a minimal PDF for debugging
                try:
                    minimal_doc = SimpleDocTemplate(output_path)
                    minimal_doc.build([Paragraph("Test PDF with minimal content", styles['Normal'])])
                    logger.info(f"Generated minimal test PDF: {output_path}")
                    return output_path
                except Exception as e2:
                    logger.error(f"Even minimal PDF failed: {str(e2)}")
                    return None
            
        except Exception as e:
            logger.error(f"Error generating PDF: {str(e)}")
            traceback.print_exc()
            return None