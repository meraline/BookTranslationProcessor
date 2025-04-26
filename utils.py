#!/usr/bin/env python3
"""
Utility functions for the poker book processor.
"""
import os
import logging
import time
import json
import cv2
import numpy as np
from datetime import datetime
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_timestamp():
    """
    Create a timestamp string for file naming.
    
    Returns:
        str: Timestamp string
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def save_to_json(data, output_path):
    """
    Save data to a JSON file.
    
    Args:
        data: Data to save
        output_path: Path to save to
        
    Returns:
        bool: Success status
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving JSON: {str(e)}")
        return False

def load_from_json(input_path):
    """
    Load data from a JSON file.
    
    Args:
        input_path: Path to load from
        
    Returns:
        dict: Loaded data or None on error
    """
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON: {str(e)}")
        return None

def extract_page_number(filename):
    """
    Extract page number from filename for proper sequencing.
    
    Args:
        filename (str): Filename to parse
        
    Returns:
        int: Page number or -1 if not found
    """
    # Try to match patterns like page_0171 or page-171
    match = re.search(r'page[_-]0*(\d+)', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # Try to match just numeric part
    match = re.search(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    
    # No valid page number found
    return -1

def sort_files_by_page(file_list):
    """
    Sort a list of files by page number.
    
    Args:
        file_list (list): List of file paths
        
    Returns:
        list: Sorted list of file paths
    """
    return sorted(file_list, key=lambda x: extract_page_number(os.path.basename(x)))

def estimate_language(text):
    """
    Estimate the language of a text (English or Russian).
    
    Args:
        text (str): Text to analyze
        
    Returns:
        str: Language code ('en' or 'ru')
    """
    # Count Cyrillic characters
    cyrillic_count = sum(1 for c in text if ord('а') <= ord(c.lower()) <= ord('я'))
    
    # Count Latin characters
    latin_count = sum(1 for c in text if ord('a') <= ord(c.lower()) <= ord('z'))
    
    # Compare counts
    if cyrillic_count > latin_count:
        return 'ru'
    else:
        return 'en'

def is_processing_needed(input_path, output_path, force=False):
    """
    Check if processing is needed based on file modification times.
    
    Args:
        input_path: Input file path
        output_path: Output file path
        force (bool): Force processing regardless of timestamps
        
    Returns:
        bool: True if processing is needed
    """
    if force:
        return True
        
    if not os.path.exists(output_path):
        return True
        
    input_mtime = os.path.getmtime(input_path)
    output_mtime = os.path.getmtime(output_path)
    
    # If input is newer than output, we need to process
    return input_mtime > output_mtime

def is_valid_image(file_path):
    """
    Check if a file is a valid image that can be processed.
    
    Args:
        file_path (str): Path to the file
        
    Returns:
        bool: True if valid image
    """
    try:
        # Check extension
        _, ext = os.path.splitext(file_path)
        valid_extensions = ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']
        
        if ext.lower() not in valid_extensions:
            return False
            
        # Try to open with OpenCV
        img = cv2.imread(file_path)
        if img is None:
            return False
            
        # Check dimensions
        height, width = img.shape[:2]
        if height < 100 or width < 100:
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error checking image validity: {str(e)}")
        return False

def find_optimal_layout(figures, page_width, page_height, padding=10):
    """
    Find optimal layout for multiple figures on a page.
    
    Args:
        figures (list): List of figure objects with dimensions
        page_width (float): Width of the page
        page_height (float): Height of the page
        padding (float): Padding between figures
        
    Returns:
        list: List of (x, y) positions for each figure
    """
    # Simple layout algorithm for demonstration
    positions = []
    current_x = padding
    current_y = padding
    row_height = 0
    
    for figure in figures:
        width = figure.get('width', 100)
        height = figure.get('height', 100)
        
        # Check if we need to move to next row
        if current_x + width + padding > page_width:
            current_x = padding
            current_y += row_height + padding
            row_height = 0
        
        # Check if we need a new page
        if current_y + height + padding > page_height:
            # This would actually need to start a new page in PDF generation
            current_x = padding
            current_y = padding
            row_height = 0
        
        # Add position
        positions.append((current_x, current_y))
        
        # Update position for next figure
        current_x += width + padding
        row_height = max(row_height, height)
    
    return positions

def compute_image_hash(img_path):
    """
    Compute a simple hash for an image file for duplicate detection.
    
    Args:
        img_path (str): Path to the image file
        
    Returns:
        str: MD5 hash string or None on failure
    """
    try:
        import hashlib
        
        # Читаем файл небольшими кусками для экономии памяти
        md5_hash = hashlib.md5()
        with open(img_path, "rb") as f:
            # Читаем файл по 4KB за раз
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except Exception as e:
        logger.error(f"Ошибка при вычислении хеша изображения: {str(e)}")
        return None

def compute_text_similarity(text1, text2):
    """
    Compute similarity between two text strings.
    
    Args:
        text1 (str): First text
        text2 (str): Second text
        
    Returns:
        float: Similarity score between 0.0 and 1.0
    """
    try:
        # Проверка входных параметров
        if not isinstance(text1, str) or not isinstance(text2, str):
            return 0.0
        
        if not text1 or not text2:
            return 0.0
        
        # Normalize texts
        text1 = text1.lower().strip()
        text2 = text2.lower().strip()
        
        if not text1 or not text2:
            return 0.0
        
        # Точное совпадение
        if text1 == text2:
            return 1.0
        
        # Если тексты сильно различаются по длине, они, вероятно, не похожи
        len1, len2 = len(text1), len(text2)
        if len1 > 2 * len2 or len2 > 2 * len1:
            return 0.0
        
        # Calculate Jaccard similarity on words
        # Сначала фильтруем слова, чтобы избавиться от коротких, которые могут быть шумом
        words1 = set(w for w in text1.split() if len(w) > 2)
        words2 = set(w for w in text2.split() if len(w) > 2)
        
        if not words1 or not words2:
            return 0.0
        
        # Compute Jaccard similarity (intersection / union)
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        if union == 0:
            return 0.0
        
        return intersection / union
    except Exception as e:
        logger.error(f"Ошибка при вычислении похожести текстов: {str(e)}")
        return 0.0

def is_text_duplicate(text, existing_texts, threshold=0.85):
    """
    Check if a text is a duplicate of any existing text.
    
    Args:
        text (str): Text to check
        existing_texts (list): List of existing texts
        threshold (float): Similarity threshold (0.0 to 1.0)
        
    Returns:
        tuple: (is_duplicate, most_similar_text, similarity_score)
    """
    try:
        # Проверка входных данных на корректность
        if not isinstance(text, str) or text is None:
            return False, None, 0.0
            
        if not isinstance(existing_texts, list) or not existing_texts:
            return False, None, 0.0
        
        # Нормализация текста
        normalized_text = text.lower().strip()
        if not normalized_text:
            return False, None, 0.0
            
        max_similarity = 0.0
        most_similar_text = None
        
        # Быстрая проверка на точное совпадение
        for existing_text in existing_texts:
            # Пропускаем некорректные значения
            if not isinstance(existing_text, str) or not existing_text:
                continue
                
            # Проверка на точное совпадение
            if normalized_text == existing_text.lower().strip():
                return True, existing_text, 1.0
        
        # Если текст очень короткий, используем только точное совпадение
        if len(normalized_text) < 30:
            return False, None, 0.0
            
        # Для более длинных текстов проверяем похожесть
        for existing_text in existing_texts:
            # Пропускаем некорректные значения
            if not isinstance(existing_text, str) or not existing_text:
                continue
                
            try:
                similarity = compute_text_similarity(normalized_text, existing_text)
                if similarity > max_similarity:
                    max_similarity = similarity
                    most_similar_text = existing_text
            except Exception as e:
                # Логируем и игнорируем ошибки при сравнении
                logger.error(f"Ошибка при сравнении текстов: {str(e)}")
                continue
        
        is_duplicate = max_similarity >= threshold
        
        return is_duplicate, most_similar_text, max_similarity
    
    except Exception as e:
        # В случае любой ошибки возвращаем "не дубликат"
        logger.error(f"Ошибка при проверке дубликатов: {str(e)}")
        return False, None, 0.0
