"""
Module for sanitizing and cleaning text for PDF generation.
"""
import re
import unicodedata
import logging

logger = logging.getLogger(__name__)

def sanitize_text_for_pdf(text):
    """
    Sanitize text for PDF generation, replacing problematic characters.
    
    Args:
        text (str): Text to sanitize
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ""
        
    # Normalize unicode characters to their closest representation
    text = unicodedata.normalize('NFKC', text)
    
    # Replace common problem characters
    # Replace square/black characters often used as placeholders
    text = re.sub(r'[■□▪▫◾◽◼◻]', '', text)
    
    # Replace unprintable control characters
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    
    # Replace invisible separator characters
    text = re.sub(r'[\u200B-\u200F\u2028-\u202E]', '', text)
    
    # Create XML-safe text (required by ReportLab)
    # Replace reserved XML characters
    replacements = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&apos;',
    }
    
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    
    # Check if any text remains after cleaning
    if not text.strip():
        logger.warning("Text was completely empty after sanitization")
        return ""
        
    return text

def aggressive_text_cleanup(text):
    """
    More aggressive text cleanup for problematic text.
    Removes all non-ASCII characters and other problematic symbols.
    
    Args:
        text (str): Text to clean
        
    Returns:
        str: Cleaned text
    """
    if not text:
        return ""
        
    # Step 1: Basic sanitization
    text = sanitize_text_for_pdf(text)
    
    # Step 2: Keep only basic Latin alphabet, Cyrillic characters, numbers, and common punctuation
    # This is a fallback for serious encoding issues
    text = re.sub(r'[^a-zA-Z0-9\u0400-\u04FF\s.,;:!?\'\"()\-]', '', text)
    
    # Step 3: Remove excess whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    if not text:
        return "Text content could not be processed due to encoding issues."
        
    return text