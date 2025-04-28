#!/usr/bin/env python3
"""
Module for text extraction from images using Tesseract OCR.
"""
import os
import cv2
import pytesseract
import numpy as np
import logging
import re
import traceback
from PIL import Image

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TextExtractor:
    """Handles extraction of text from images using OCR."""
    
    def __init__(self, tesseract_config='--oem 1 --psm 3'):
        """
        Initialize the text extractor.
        
        Args:
            tesseract_config (str): Tesseract configuration string
        """
        self.tesseract_config = tesseract_config
        
        # Specific configuration for different content types
        self.tech_config = '--oem 1 --psm 6 -c tessedit_char_whitelist="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-+=%()[]{}.:,;/<>*& "' 
        self.number_config = '--oem 1 --psm 7 -c tessedit_char_whitelist="0123456789.,-+/%"'
        
    @staticmethod
    def quick_extract_text(image_path):
        """
        Quickly extract text from an image for duplicate detection.
        Does not use advanced preprocessing to keep it fast.
        
        Args:
            image_path (str): Path to the image
            
        Returns:
            str: Extracted text
        """
        try:
            # Load image with OpenCV (faster than PIL for this specific use)
            image = cv2.imread(image_path)
            if image is None:
                logger.warning(f"Could not load image: {image_path}")
                return ""
                
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Simple threshold for faster processing
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Extract text with default config (faster)
            # Убираем параметр lang, так как он может быть не поддержан или вызывать ошибки
            text = pytesseract.image_to_string(thresh)
            
            # Clean text
            text = text.strip()
            return text
            
        except Exception as e:
            logger.error(f"Error in quick text extraction: {str(e)}")
            return ""
        
    def extract_text(self, img, region=None, force_mode=None):
        """
        Extract text from an image or a specific region.
        
        Args:
            img: Image to process
            region (tuple, optional): Region to extract text from (x, y, w, h)
            force_mode (str, optional): Force a specific mode ('standard', 'aggressive')
            
        Returns:
            str: Extracted text
        """
        try:
            # Если указан специальный режим распознавания
            config = self.tesseract_config
            if force_mode == 'aggressive':
                # Более агрессивные настройки для сложных случаев
                config = '--oem 1 --psm 3 -c tessedit_char_blacklist=|~^`$#@&*{}[]()<>\'\"\\/ -c page_separator=""'
                logger.info("Используется агрессивный режим OCR")
            
            # Дополнительная предобработка изображения для улучшения OCR
            processed = img.copy()
            # Применяем адаптивную бинаризацию
            if force_mode == 'aggressive':
                processed = cv2.adaptiveThreshold(processed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                cv2.THRESH_BINARY, 11, 2)
                # Увеличиваем контраст
                alpha = 1.5  # Коэффициент контраста
                beta = 10    # Яркость
                processed = cv2.convertScaleAbs(processed, alpha=alpha, beta=beta)
            
            # If region specified, extract that part of the image
            if region:
                x, y, w, h = region
                roi = processed[y:y+h, x:x+w]
                text = pytesseract.image_to_string(roi, config=config)
            else:
                text = pytesseract.image_to_string(processed, config=config)
            
            # Логируем информацию о распознавании
            logger.info(f"OCR выполнен с config: {config}")
            logger.info(f"Результат OCR: {len(text)} символов")
                
            # Clean up text
            text = self._clean_text(text)
            return text
            
        except Exception as e:
            logger.error(f"Error extracting text: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return ""
    
    def extract_numbers_and_formulas(self, img, region=None):
        """
        Specialized extraction for numbers and formulas.
        
        Args:
            img: Image to process
            region (tuple, optional): Region to extract from (x, y, w, h)
            
        Returns:
            str: Extracted numerical content
        """
        try:
            # Extract the region if specified
            if region:
                x, y, w, h = region
                roi = img[y:y+h, x:x+w]
                target_img = roi
            else:
                target_img = img
                
            # Use specialized config for numbers
            text = pytesseract.image_to_string(target_img, config=self.number_config)
            
            # Clean up and return
            text = self._clean_text(text)
            return text
            
        except Exception as e:
            logger.error(f"Error extracting numbers: {str(e)}")
            return ""
    
    def extract_technical_content(self, img, region=None):
        """
        Specialized extraction for technical content like code or formulas.
        
        Args:
            img: Image to process
            region (tuple, optional): Region to extract from (x, y, w, h)
            
        Returns:
            str: Extracted technical content
        """
        try:
            # Extract the region if specified
            if region:
                x, y, w, h = region
                roi = img[y:y+h, x:x+w]
                target_img = roi
            else:
                target_img = img
                
            # Use specialized config for technical content
            text = pytesseract.image_to_string(target_img, config=self.tech_config)
            
            # Clean up and return
            text = self._clean_text(text)
            return text
            
        except Exception as e:
            logger.error(f"Error extracting technical content: {str(e)}")
            return ""
    
    def _clean_text(self, text):
        """
        Clean up extracted text.
        
        Args:
            text (str): Raw OCR text
            
        Returns:
            str: Cleaned text
        """
        if not text:
            return ""
            
        # Remove unnecessary whitespace
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r' +', ' ', text)
        
        # Fix common OCR errors
        text = text.replace('|', 'I')  # Pipe to I
        text = text.replace('l', 'l')  # Lowercase L cleanup
        
        # Fix spacing around punctuation
        text = re.sub(r'\s+([.,;:!?)])', r'\1', text)
        text = re.sub(r'([({[])\s+', r'\1', text)
        
        # Clear garbage characters (common OCR artifacts)
        text = re.sub(r'[^\x00-\x7F]+', '', text)
        
        # Remove lines with excessive special characters
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Count special characters
            special_chars = sum(1 for c in line if not c.isalnum() and not c.isspace())
            total_chars = len(line)
            
            # If less than 30% special characters, or very short line with numbers (likely a data point)
            if (total_chars > 0 and special_chars / total_chars < 0.3) or (total_chars < 10 and any(c.isdigit() for c in line)):
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def extract_structured_text(self, img):
        """
        Extract text with structure information (paragraphs, formatting).
        
        Args:
            img: Image to process
            
        Returns:
            dict: Structure with text elements
        """
        try:
            # Use Tesseract's hOCR output to get structure
            hocr = pytesseract.image_to_pdf_or_hocr(
                img, extension='hocr', config=self.tesseract_config
            )
            
            # Parse hOCR to extract structured text
            # This is simplified - full parsing would be more complex
            paragraphs = []
            current_paragraph = []
            
            # Simple parsing of hOCR output
            for line in hocr.decode('utf-8').split('\n'):
                if 'ocr_line' in line:
                    # Extract text from line
                    text_match = re.search(r'>\s*(.*?)\s*<', line)
                    if text_match:
                        text = text_match.group(1).strip()
                        if text:
                            current_paragraph.append(text)
                elif 'ocr_par' in line and current_paragraph:
                    paragraphs.append(' '.join(current_paragraph))
                    current_paragraph = []
            
            # Don't forget the last paragraph
            if current_paragraph:
                paragraphs.append(' '.join(current_paragraph))
            
            return {'paragraphs': paragraphs}
            
        except Exception as e:
            logger.error(f"Error extracting structured text: {str(e)}")
            return {'paragraphs': []}
