#!/usr/bin/env python3
"""
Module for generating PDF files from processed book content.
"""
import os
import logging
import traceback
from fpdf import FPDF
import re
import cv2
from PIL import Image
import numpy as np

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
        
        # Use standard fonts
        self.fonts = {
            'normal': {'name': 'Arial', 'style': ''},
            'bold': {'name': 'Arial', 'style': 'B'},
            'italic': {'name': 'Arial', 'style': 'I'},
            'bold_italic': {'name': 'Arial', 'style': 'BI'}
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
        Set up the PDF document with proper fonts.
        
        Args:
            title (str, optional): Title for the PDF
            
        Returns:
            FPDF: Configured PDF object
        """
        # Create PDF document with unicode support
        pdf = FPDF()
        pdf.add_page()
        
        # Enable UTF-8 encoding
        pdf.set_doc_option('core_fonts_encoding', 'utf-8')
        
        # Set info
        if title:
            try:
                pdf.set_title(title)
            except Exception as e:
                logger.warning(f"Could not set PDF title: {e}")
        pdf.set_author("Poker Book Processor")
        
        # Add built-in fonts that support Cyrillic
        try:
            # Use DejaVuSans for everything if Oblique isn't available
            pdf.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
            pdf.add_font('DejaVu', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', uni=True)
            
            # Try to add oblique font, fallback to regular if not available
            try:
                pdf.add_font('DejaVu', 'I', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf', uni=True)
            except Exception as e:
                logger.warning(f"Failed to load italic font, using regular: {e}")
                pdf.add_font('DejaVu', 'I', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
        except Exception as e:
            logger.error(f"Error loading DejaVu fonts: {e}")
            # Fall back to built-in fonts if needed
            pass
        
        # Set default font - catch any error and use built-in fonts as fallback
        try:
            pdf.set_font('DejaVu', '', 12)
        except Exception as e:
            logger.warning(f"Failed to set DejaVu font, using Arial instead: {e}")
            pdf.set_font('Arial', '', 12)
        
        return pdf
    
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
                
            # Make sure the PDF directory exists
            pdf_dir = os.path.join(self.output_dir, 'pdf')
            os.makedirs(pdf_dir, exist_ok=True)
            
            # Create the full output path
            output_path = os.path.join(pdf_dir, filename)
            logger.info(f"PDF will be saved to: {output_path}")
            
            # Setup PDF
            pdf = self._setup_pdf(book_title)
            
            # Add pages as needed
            current_page_height = 0  # Track used height on current page
            max_page_height = 260  # Maximum height to use before adding a new page
            
            # Add first page
            pdf.add_page()
            
            # Add title if available
            if 'title' in document_structure:
                title = document_structure['title']
                pdf.set_font('DejaVu', 'B', 20)
                pdf.cell(0, 12, title, 0, 1, 'C')
                current_page_height += 20
                
                # Add date
                from datetime import datetime
                date_str = datetime.now().strftime("%d.%m.%Y")
                pdf.set_font('DejaVu', 'I', 10)
                pdf.cell(0, 5, f"Создано: {date_str}", 0, 1, 'R')
                current_page_height += 10
                
                # Reset font
                pdf.set_font('DejaVu', '', 12)
                
                # Add a small gap
                pdf.ln(5)
                current_page_height += 5
            
            # Create a table of contents
            toc_page = pdf.page_no()
            pdf.set_font('DejaVu', 'B', 14)
            pdf.cell(0, 10, "Содержание" if language == 'ru' else "Table of Contents", 0, 1)
            current_page_height += 15
            pdf.set_font('DejaVu', '', 12)
            
            # We'll add TOC entries after we know the page numbers
            toc_entries = []
            
            # Add a new page for the content
            pdf.add_page()
            
            # Process all text content first - deduplicate and organize paragraphs
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
            
            # Look for sections and add TOC entries
            section_count = 0
            current_section = None
            
            # Start with main text content
            pdf.set_font('DejaVu', 'B', 16)
            main_text_title = "Текст" if language == 'ru' else "Text"
            pdf.cell(0, 10, main_text_title, 0, 1)
            toc_entries.append((main_text_title, pdf.page_no()))
            current_page_height = 15
            pdf.set_font('DejaVu', '', 12)
            
            # Process paragraphs
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
                    current_section = paragraph.strip().rstrip(':')
                    
                    # Add to TOC
                    toc_entries.append((f"    {current_section}", pdf.page_no()))
                    
                    # Add the heading
                    current_page_height = self._add_heading(pdf, paragraph, current_page_height, max_page_height)
                else:
                    # Regular paragraph
                    current_page_height = self._add_paragraph(pdf, paragraph, current_page_height, max_page_height)
            
            # Now add a section for figures/diagrams
            pdf.add_page()
            current_page_height = 0
            
            # Add figures section if we have any
            figures_title = "Диаграммы и графики" if language == 'ru' else "Diagrams and Charts"
            if 'figures' in document_structure and document_structure['figures']:
                pdf.set_font('DejaVu', 'B', 16)
                pdf.cell(0, 10, figures_title, 0, 1)
                toc_entries.append((figures_title, pdf.page_no()))
                current_page_height = 15
                pdf.set_font('DejaVu', '', 12)
                
                # Process figures
                figure_count = 0
                for figure in document_structure['figures']:
                    figure_count += 1
                    figure_caption = f"Figure {figure_count}: {figure.get('description', '')}" if language == 'en' else f"Рисунок {figure_count}: {figure.get('description', '')}"
                    current_page_height = self._add_figure(pdf, figure, current_page_height, max_page_height, caption=figure_caption)
            
            # Add tables section if we have any
            pdf.add_page()
            current_page_height = 0
            
            tables_title = "Таблицы" if language == 'ru' else "Tables"
            if 'tables' in document_structure and document_structure['tables']:
                pdf.set_font('DejaVu', 'B', 16)
                pdf.cell(0, 10, tables_title, 0, 1)
                toc_entries.append((tables_title, pdf.page_no()))
                current_page_height = 15
                pdf.set_font('DejaVu', '', 12)
                
                # Process tables
                table_count = 0
                for table in document_structure['tables']:
                    table_count += 1
                    table_caption = f"Table {table_count}: {table.get('description', '')}" if language == 'en' else f"Таблица {table_count}: {table.get('description', '')}"
                    current_page_height = self._add_table(pdf, table, current_page_height, max_page_height, caption=table_caption)
            
            # Now go back and fill in the TOC
            pdf.page = toc_page
            current_page_height = 15  # Start after the TOC title
            
            for title, page_num in toc_entries:
                style = 'I' if title.startswith('    ') else ''
                pdf.set_font('DejaVu', style, 12)
                
                # Calculate dot leaders
                dots = '.' * (60 - len(title) - len(str(page_num)))
                
                pdf.cell(0, 8, f"{title} {dots} {page_num}", 0, 1)
                current_page_height += 8
                
                if current_page_height > max_page_height:
                    pdf.add_page()
                    current_page_height = 0
            
            # Make sure the output directory exists
            output_dir = os.path.dirname(output_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            # Save PDF
            try:
                pdf.output(output_path)
                logger.info(f"Generated PDF: {output_path}")
                
                # Verify the file was created
                if os.path.exists(output_path):
                    logger.info(f"Verified PDF exists at: {output_path}, size: {os.path.getsize(output_path)} bytes")
                    return output_path
                else:
                    logger.error(f"PDF file was not created at: {output_path}")
                    return None
            except Exception as e:
                logger.error(f"Error outputting PDF: {str(e)}")
                traceback.print_exc()
                return None
            
        except Exception as e:
            logger.error(f"Error generating PDF: {str(e)}")
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
            pdf.set_font('DejaVu', 'B', 14)
            pdf.multi_cell(0, 8, paragraph)
            pdf.ln(5)
            pdf.set_font('DejaVu', '', 12)
            return current_page_height + 15
        else:
            # Normal paragraph
            pdf.set_font('DejaVu', '', 12)
            
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
