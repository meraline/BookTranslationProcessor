#!/usr/bin/env python3
"""
Module for generating PDF files from processed book content.
"""
import os
import logging
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
        
        # Custom Russian-friendly font paths
        self.fonts = {
            'normal': {'path': None, 'name': 'DejaVu'},
            'bold': {'path': None, 'name': 'DejaVuB'},
            'italic': {'path': None, 'name': 'DejaVuI'},
            'bold_italic': {'path': None, 'name': 'DejaVuBI'}
        }
        
        # If custom fonts directory specified, look for font files
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
        # Create PDF document
        pdf = FPDF()
        
        # Set info
        if title:
            pdf.set_title(title)
        pdf.set_author("Poker Book Processor")
        
        # Add fonts
        for font_type, font_data in self.fonts.items():
            if font_data['path']:
                # If we have the font file, add it
                pdf.add_font(font_data['name'], '', font_data['path'], uni=True)
            else:
                # Otherwise, use built-in fonts
                if font_type == 'normal':
                    pass  # Default font is already added
                elif font_type == 'bold':
                    pdf.add_font('DejaVuB', '', '', uni=True)
                elif font_type == 'italic':
                    pdf.add_font('DejaVuI', '', '', uni=True)
                elif font_type == 'bold_italic':
                    pdf.add_font('DejaVuBI', '', '', uni=True)
        
        # Set default font
        pdf.set_font('DejaVu', '', 12)
        
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
                filename = f"{book_title}_{language}.pdf"
            else:
                filename = f"poker_book_{language}.pdf"
                
            output_path = os.path.join(self.output_dir, filename)
            
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
                pdf.set_font('DejaVuB', '', 16)
                pdf.cell(0, 10, title, 0, 1, 'C')
                current_page_height += 15
                pdf.set_font('DejaVu', '', 12)
            
            # Add content (paragraphs, figures, tables)
            self._process_content(pdf, document_structure, current_page_height, max_page_height)
            
            # Save PDF
            pdf.output(output_path)
            
            logger.info(f"Generated PDF: {output_path}")
            return output_path
            
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
            pdf.set_font('DejaVuB', '', 14)
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
    
    def _add_figure(self, pdf, figure, current_page_height, max_page_height):
        """
        Add a figure to the PDF.
        
        Args:
            pdf: FPDF object
            figure: Figure data
            current_page_height: Current height used on page
            max_page_height: Maximum height before new page
            
        Returns:
            float: Updated current page height
        """
        figure_type = figure.get('type', 'image')
        description = figure.get('description', '')
        image_path = figure.get('image_path', '')
        
        if not image_path or not os.path.exists(image_path):
            # If image doesn't exist, just add the description
            pdf.set_font('DejaVuI', '', 11)
            pdf.multi_cell(0, 6, f"[Figure description: {description}]")
            pdf.ln(5)
            pdf.set_font('DejaVu', '', 12)
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
            pdf.set_font('DejaVuI', '', 10)
            pdf.multi_cell(0, 5, description)
            pdf.ln(5)
            pdf.set_font('DejaVu', '', 12)
            
            # Update the height
            return current_page_height + figure_height + 20
            
        except Exception as e:
            logger.error(f"Error adding figure to PDF: {str(e)}")
            # Just add the description on error
            pdf.set_font('DejaVuI', '', 11)
            pdf.multi_cell(0, 6, f"[Figure: {description}]")
            pdf.ln(5)
            pdf.set_font('DejaVu', '', 12)
            return current_page_height + 15
    
    def _add_table(self, pdf, table, current_page_height, max_page_height):
        """
        Add a table to the PDF.
        
        Args:
            pdf: FPDF object
            table: Table data
            current_page_height: Current height used on page
            max_page_height: Maximum height before new page
            
        Returns:
            float: Updated current page height
        """
        table_data = table.get('data', '')
        image_path = table.get('image_path', '')
        
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
            pdf.set_font('DejaVu', '', 12)
            
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
            pdf.set_font('DejaVu', '', 10)
            
            for row in table_data:
                for cell in row:
                    pdf.cell(cell_width, 8, str(cell), 1, 0, 'C')
                pdf.ln()
            
            pdf.ln(5)
            pdf.set_font('DejaVu', '', 12)
            
            return current_page_height + table_height
            
        else:
            return current_page_height  # No valid table data
