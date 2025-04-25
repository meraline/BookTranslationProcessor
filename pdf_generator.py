#!/usr/bin/env python3
"""
Module for generating PDF files from processed book content.
"""
import os
import logging
import traceback
import re
import cv2
from PIL import Image
import numpy as np

# Use ReportLab for PDF generation with Unicode support
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table
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
        self.output_dir = output_dir
        self.fonts_dir = fonts_dir
        
        # Use standard fonts - always using Times
        self.fonts = {
            'normal': {'name': 'Times', 'style': ''},
            'bold': {'name': 'Times', 'style': 'B'},
            'italic': {'name': 'Times', 'style': 'I'},
            'bold_italic': {'name': 'Times', 'style': 'BI'}
        }
        
        # Use custom fonts if provided
        if fonts_dir and os.path.exists(fonts_dir):
            for font_file in os.listdir(fonts_dir):
                if font_file.endswith('.ttf'):
                    if 'bold' in font_file.lower() and 'italic' in font_file.lower():
                        self.fonts['bold_italic']['path'] = os.path.join(fonts_dir, font_file)
                    elif 'bold' in font_file.lower():
                        self.fonts['bold']['path'] = os.path.join(fonts_dir, font_file)
                    elif 'italic' in font_file.lower():
                        self.fonts['italic']['path'] = os.path.join(fonts_dir, font_file)
                    else:
                        self.fonts['normal']['path'] = os.path.join(fonts_dir, font_file)
    
    def _setup_pdf(self, title=None):
        """
        Set up the PDF document with proper fonts using ReportLab.
        
        Args:
            title (str, optional): Title for the PDF
            
        Returns:
            dict: Configured PDF styles and document
        """
        # Register fonts for Cyrillic support
        try:
            # Try to register Times-Roman for basic support
            pdfmetrics.registerFont(TTFont('Times-Roman', 'Times-Roman'))
            logger.info("Registered Times-Roman font")
        except Exception as e:
            logger.warning(f"Could not register Times-Roman font: {e}")
            
        # Create styles for different text elements
        styles = getSampleStyleSheet()
        
        # Add custom styles for Russian text
        styles.add(ParagraphStyle(
            name='NormalRu',
            fontName='Helvetica',  # Using built-in fonts
            fontSize=12,
            leading=14,
            alignment=TA_JUSTIFY
        ))
        
        styles.add(ParagraphStyle(
            name='HeadingRu',
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=10
        ))
        
        styles.add(ParagraphStyle(
            name='TitleRu',
            fontName='Helvetica-Bold',
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=20
        ))
        
        styles.add(ParagraphStyle(
            name='TOCEntry',
            fontName='Helvetica',
            fontSize=12,
            leading=14,
            alignment=TA_LEFT
        ))
            
        logger.info("PDF styles configured with Unicode support")
        
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
            # Create output filename
            if book_title:
                sanitized_title = re.sub(r'[^\w\s-]', '', book_title).replace(' ', '_')
                filename = f"{sanitized_title}_{language}.pdf"
            else:
                filename = f"poker_book_{language}.pdf"
                
            # self.output_dir is something like 'output/book_5'
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Generate the PDF output path
            output_path = os.path.join(self.output_dir, 'pdf', filename)
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
            toc_entries.append((main_text_title, 1))  # Page numbers are approximate and will be fixed in post-processing
            
            # Process all text content - deduplicate and organize paragraphs
            all_paragraphs = []
            seen_paragraphs = set()
            
            if 'paragraphs' in document_structure:
                for paragraph in document_structure['paragraphs']:
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
                        story.append(Paragraph(paragraph, styles['NormalRu'] if language == 'ru' else styles['Normal']))
                        story.append(Spacer(1, 6))
                    except Exception as e:
                        logger.error(f"Error adding paragraph: {str(e)}")
                        # Try fallback without styling
                        story.append(Paragraph(paragraph, styles['Normal']))
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
                            story.append(Paragraph(figure_caption, styles['Caption'] if language == 'en' else styles['NormalRu']))
                            story.append(Spacer(1, 12))
                        except Exception as e:
                            logger.error(f"Error adding figure image: {str(e)}")
                            story.append(Paragraph(f"[Figure {figure_count} - Image could not be loaded]", styles['Normal']))
                            story.append(Paragraph(figure_caption, styles['Caption'] if language == 'en' else styles['NormalRu']))
                            story.append(Spacer(1, 12))
                    else:
                        # No image, just add caption
                        story.append(Paragraph(f"[Figure {figure_count} - No image available]", styles['Normal']))
                        story.append(Paragraph(figure_caption, styles['Caption'] if language == 'en' else styles['NormalRu']))
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
                            story.append(Paragraph(table_caption, styles['Caption'] if language == 'en' else styles['NormalRu']))
                            story.append(Spacer(1, 12))
                        except Exception as e:
                            logger.error(f"Error adding table image: {str(e)}")
                            story.append(Paragraph(f"[Table {table_count} - Image could not be loaded]", styles['Normal']))
                            story.append(Paragraph(table_caption, styles['Caption'] if language == 'en' else styles['NormalRu']))
                            story.append(Spacer(1, 12))
                    else:
                        # No image, just add caption
                        story.append(Paragraph(f"[Table {table_count} - No image available]", styles['Normal']))
                        story.append(Paragraph(table_caption, styles['Caption'] if language == 'en' else styles['NormalRu']))
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
    
    def _process_content(self, pdf, document_structure, current_page_height, max_page_height):
        """
        Process and add all content to the PDF.
        
        Args:
            pdf: FPDF object
            document_structure: Document content structure
            current_page_height: Current height used on page
            max_page_height: Maximum height before new page
            
        Returns:
            None
        """
        # Add paragraphs
        if 'paragraphs' in document_structure:
            for paragraph in document_structure['paragraphs']:
                current_page_height = self._add_paragraph(pdf, paragraph, current_page_height, max_page_height)
        
        # Add figures
        if 'figures' in document_structure:
            for figure in document_structure['figures']:
                current_page_height = self._add_figure(pdf, figure, current_page_height, max_page_height)
        
        # Add tables
        if 'tables' in document_structure:
            for table in document_structure['tables']:
                current_page_height = self._add_table(pdf, table, current_page_height, max_page_height)
    
    def _add_paragraph(self, pdf, paragraph, current_page_height, max_page_height):
        """
        Add a paragraph to the PDF.
        
        Args:
            pdf: FPDF object
            paragraph: Paragraph text
            current_page_height: Current height used on page
            max_page_height: Maximum height before new page
            
        Returns:
            float: Updated current page height
        """
        # Remove excessive whitespace
        paragraph = paragraph.strip()
        if not paragraph:
            return current_page_height
            
        # Check if we need a new page
        if current_page_height + 10 > max_page_height:
            pdf.add_page()
            current_page_height = 0
        
        # Detect potential headings
        if len(paragraph) < 100 and paragraph.strip().endswith(':'):
            # Probably a heading
            pdf.set_font('Times', 'B', 14)
            pdf.multi_cell(0, 8, paragraph)
            pdf.ln(5)
            pdf.set_font('Times', '', 12)
            return current_page_height + 15
        else:
            # Normal paragraph
            pdf.set_font('Times', '', 12)
            
            # Check for bullet points
            if paragraph.lstrip().startswith('•') or paragraph.lstrip().startswith('-'):
                pdf.set_left_margin(15)
                pdf.multi_cell(0, 6, paragraph)
                pdf.set_left_margin(10)
            else:
                pdf.multi_cell(0, 6, paragraph)
                
            pdf.ln(3)
            
            # Rough height calculation: 6pt line height * number of lines + 3pt after paragraph
            line_count = len(paragraph) / 70  # Approximate chars per line
            paragraph_height = 6 * line_count + 3
            
            return current_page_height + paragraph_height
    
    def _add_heading(self, pdf, heading, current_page_height, max_page_height):
        """
        Add a heading to the PDF.
        
        Args:
            pdf: FPDF object
            heading: Heading text
            current_page_height: Current height used on page
            max_page_height: Maximum height before new page
            
        Returns:
            float: Updated current page height
        """
        # Remove excessive whitespace
        heading = heading.strip()
        if not heading:
            return current_page_height
            
        # Check if we need a new page
        if current_page_height + 20 > max_page_height:
            pdf.add_page()
            current_page_height = 0
        
        # Add heading
        pdf.ln(5)
        pdf.set_font(self.fonts['bold']['name'], self.fonts['bold']['style'], 14)
        pdf.multi_cell(0, 8, heading)
        pdf.ln(5)
        pdf.set_font(self.fonts['normal']['name'], self.fonts['normal']['style'], 12)
        
        return current_page_height + 20
        
    def _add_figure(self, pdf, figure, current_page_height, max_page_height, caption=None):
        """
        Add a figure to the PDF.
        
        Args:
            pdf: FPDF object
            figure: Figure data
            current_page_height: Current height used on page
            max_page_height: Maximum height before new page
            caption: Optional custom caption to use
            
        Returns:
            float: Updated current page height
        """
        figure_type = figure.get('type', 'image')
        description = caption or figure.get('description', '')
        image_path = figure.get('image_path', '')
        
        if not image_path or not os.path.exists(image_path):
            # If image doesn't exist, just add the description
            pdf.set_font(self.fonts['italic']['name'], self.fonts['italic']['style'], 11)
            pdf.multi_cell(0, 6, f"[Figure description: {description}]")
            pdf.ln(5)
            pdf.set_font(self.fonts['normal']['name'], self.fonts['normal']['style'], 12)
            return current_page_height + 15
        
        # Load image to get dimensions
        try:
            img = Image.open(image_path)
            width, height = img.size
            
            # Calculate scaling
            pdf_width = 190  # Max width in mm
            width_ratio = pdf_width / width
            figure_height = height * width_ratio
            
            # Check if we need a new page
            if current_page_height + figure_height + 20 > max_page_height:
                pdf.add_page()
                current_page_height = 0
            
            # Add figure
            pdf.image(image_path, x=10, y=pdf.get_y(), w=pdf_width)
            
            # Add caption
            pdf.set_y(pdf.get_y() + figure_height + 5)
            pdf.set_font(self.fonts['italic']['name'], self.fonts['italic']['style'], 10)
            pdf.multi_cell(0, 5, description)
            pdf.ln(5)
            pdf.set_font(self.fonts['normal']['name'], self.fonts['normal']['style'], 12)
            
            # Update the height
            return current_page_height + figure_height + 20
            
        except Exception as e:
            logger.error(f"Error adding figure to PDF: {str(e)}")
            # Just add the description on error
            pdf.set_font(self.fonts['italic']['name'], self.fonts['italic']['style'], 11)
            pdf.multi_cell(0, 6, f"[Figure: {description}]")
            pdf.ln(5)
            pdf.set_font(self.fonts['normal']['name'], self.fonts['normal']['style'], 12)
            return current_page_height + 15
    
    def _add_table(self, pdf, table, current_page_height, max_page_height, caption=None):
        """
        Add a table to the PDF.
        
        Args:
            pdf: FPDF object
            table: Table data
            current_page_height: Current height used on page
            max_page_height: Maximum height before new page
            caption: Optional custom caption to use
            
        Returns:
            float: Updated current page height
        """
        table_data = table.get('data', '')
        image_path = table.get('image_path', '')
        description = caption or table.get('description', '')
        
        # If we have the table as an image
        if image_path and os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                width, height = img.size
                
                # Calculate scaling
                pdf_width = 190  # Max width in mm
                width_ratio = pdf_width / width
                table_height = height * width_ratio
                
                # Check if we need a new page
                if current_page_height + table_height + 10 > max_page_height:
                    pdf.add_page()
                    current_page_height = 0
                
                # Add table image
                pdf.image(image_path, x=10, y=pdf.get_y(), w=pdf_width)
                
                # Update position
                pdf.set_y(pdf.get_y() + table_height + 5)
                pdf.ln(5)
                
                return current_page_height + table_height + 10
                
            except Exception as e:
                logger.error(f"Error adding table image to PDF: {str(e)}")
                # Fall back to text-based table
        
        # For text tables
        if isinstance(table_data, str):
            # Check if we need a new page
            line_count = len(table_data.split('\n'))
            estimated_height = line_count * 6 + 10
            
            if current_page_height + estimated_height > max_page_height:
                pdf.add_page()
                current_page_height = 0
            
            # Add table as text
            pdf.set_font('Courier', '', 10)  # Monospaced font for tables
            pdf.multi_cell(0, 6, table_data)
            pdf.ln(5)
            pdf.set_font(self.fonts['normal']['name'], self.fonts['normal']['style'], 12)
            
            return current_page_height + estimated_height
            
        elif isinstance(table_data, list):
            # Structured table data
            # Get dimensions
            rows = len(table_data)
            if rows == 0:
                return current_page_height
                
            cols = max(len(row) for row in table_data)
            
            # Calculate dimensions
            cell_width = 190 / cols
            table_height = rows * 8 + 10
            
            # Check if we need a new page
            if current_page_height + table_height > max_page_height:
                pdf.add_page()
                current_page_height = 0
            
            # Add table
            pdf.set_font(self.fonts['normal']['name'], self.fonts['normal']['style'], 10)
            
            for row in table_data:
                for cell in row:
                    pdf.cell(cell_width, 8, str(cell), 1, 0, 'C')
                pdf.ln()
            
            pdf.ln(5)
            pdf.set_font(self.fonts['normal']['name'], self.fonts['normal']['style'], 12)
            
            return current_page_height + table_height
            
        else:
            return current_page_height  # No valid table data
