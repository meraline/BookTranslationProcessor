#!/usr/bin/env python3
"""
Module for analyzing and processing figures, diagrams, and tables from images.
"""
import cv2
import numpy as np
import logging
import os
import pytesseract
import re
from PIL import Image, ImageDraw

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FigureAnalyzer:
    """Handles detection and analysis of figures, charts, diagrams, and tables."""
    
    def __init__(self, min_figure_size=(100, 100)):
        """
        Initialize figure analyzer.
        
        Args:
            min_figure_size (tuple): Minimum size (width, height) for a valid figure
        """
        self.min_figure_size = min_figure_size
    
    def detect_figures(self, img, original_img):
        """
        Detect figures, diagrams, and charts in an image.
        
        Args:
            img: Processed binary image
            original_img: Original color image
            
        Returns:
            list: List of detected figures [(type, region, description), ...]
        """
        try:
            # Convert to grayscale if needed
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img
                
            # Apply canny edge detection
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            
            # Apply dilation to connect edges
            kernel = np.ones((5, 5), np.uint8)
            dilated = cv2.dilate(edges, kernel, iterations=2)
            
            # Find contours
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter and categorize contours
            figures = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Skip if too small
                if w < self.min_figure_size[0] or h < self.min_figure_size[1]:
                    continue
                
                # Get the region of interest
                roi = original_img[y:y+h, x:x+w]
                
                # Determine figure type and validity
                figure_type, is_valid = self._analyze_figure_type(roi)
                
                if is_valid:
                    # Extract text in the figure for description
                    figure_text = pytesseract.image_to_string(roi)
                    
                    # Get description
                    description = self._analyze_figure_content(roi, figure_text, figure_type)
                    
                    figures.append((figure_type, (x, y, w, h), description))
            
            return figures
            
        except Exception as e:
            logger.error(f"Error detecting figures: {str(e)}")
            return []
    
    def _analyze_figure_type(self, roi):
        """
        Analyze the type of figure (chart, diagram, table).
        
        Args:
            roi: Region of interest (the potential figure)
            
        Returns:
            tuple: (figure_type, is_valid)
        """
        # Convert to grayscale for analysis
        if len(roi.shape) == 3:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi
        
        # Get image dimensions
        height, width = gray.shape[:2]
        
        # Extract text to help with classification
        text = pytesseract.image_to_string(roi)
        text_length = len(text.strip())
        
        # ИСПРАВЛЕНИЕ: Если это похоже на большой блок текста, не классифицировать его как фигуру
        # Проверим, много ли текста и есть ли много слов
        if text_length > 100 and len(text.split()) > 20:
            # Текстовые блоки не являются фигурами
            if "\n" in text and not text.count("\n") > text.count(" ") / 5:
                # Если не слишком много переносов строк относительно пробелов,
                # то это, вероятно, обычный текст, а не таблица или диаграмма
                return ("text_block", False)
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Check for table by looking for grid structure
        horizontal_lines = self._detect_lines(gray, True)
        vertical_lines = self._detect_lines(gray, False)
        
        # If we have a good number of horizontal and vertical lines, it's probably a table
        # ИСПРАВЛЕНИЕ: Увеличим требуемое количество линий для более точного определения таблиц
        if len(horizontal_lines) > 4 and len(vertical_lines) > 4:
            # Также убедимся, что линии формируют сетку
            horizontal_coverage = sum([line[2] for line in horizontal_lines]) / width
            vertical_coverage = sum([line[2] for line in vertical_lines]) / height
            
            # Если хорошее покрытие линиями
            if horizontal_coverage > 0.4 and vertical_coverage > 0.4:
                return ("table", True)
        
        # Check for charts - look for axes, points, and lines
        # More complex detection based on edge density and distribution
        edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
        
        # Hough line transform to detect straight lines
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, minLineLength=50, maxLineGap=10)
        
        # Check if it's an image or photo (high color variance)
        if len(roi.shape) == 3:  # Color image
            variance = np.var(roi)
            if variance > 2000:  # Повышенное значение для фото
                return ("image", True)
        
        # ИСПРАВЛЕНИЕ: Более строгие критерии для диаграмм
        if lines is not None and len(lines) > 15:
            # Проверяем, что линии образуют структуру
            line_angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
                line_angles.append(angle)
            
            # Если много горизонтальных/вертикальных линий
            horizontal_lines = sum(1 for angle in line_angles if abs(angle) < 10 or abs(angle) > 170)
            vertical_lines = sum(1 for angle in line_angles if abs(abs(angle) - 90) < 10)
            
            if (horizontal_lines > 5 and vertical_lines > 3) or edge_density > 0.1:
                return ("diagram", True)
            
        # If moderate edge density without many lines, might be a chart or graph
        if edge_density > 0.08 and (lines is None or len(lines) < 15):
            return ("chart", True)
        
        # If nothing matches, assume it's not a valid figure
        return ("unknown", False)
    
    def _detect_lines(self, gray, horizontal=True):
        """
        Detect horizontal or vertical lines for table analysis.
        
        Args:
            gray: Grayscale image
            horizontal (bool): If True, detect horizontal lines, otherwise vertical
            
        Returns:
            list: Detected lines
        """
        # Set minimum line length
        h, w = gray.shape
        min_length = w // 3 if horizontal else h // 3
        
        # Apply threshold
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Create structure element based on orientation
        if horizontal:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_length, 1))
        else:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_length))
            
        # Apply morphology
        detected = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # Find contours of lines
        contours, _ = cv2.findContours(detected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Extract line positions
        lines = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if horizontal:
                lines.append(y)
            else:
                lines.append(x)
                
        return lines
    
    def _analyze_figure_content(self, roi, figure_text, figure_type):
        """
        Analyze the content of a figure to generate a description.
        
        Args:
            roi: Region of interest (the figure)
            figure_text: Text extracted from the figure
            figure_type: Type of figure (chart, diagram, table)
            
        Returns:
            str: Description of the figure
        """
        # Basic description based on figure type
        if figure_type == "table":
            # Extract table data structure
            return self._analyze_table(roi, figure_text)
        elif figure_type == "chart" or figure_type == "diagram":
            # Look for meaningful labels, titles, etc.
            return self._analyze_chart_or_diagram(roi, figure_text)
        elif figure_type == "image":
            # Basic image description
            return "Image in poker book"
        else:
            return "Unknown figure type"
    
    def _analyze_table(self, roi, figure_text):
        """
        Analyze a table figure and extract structured data.
        
        Args:
            roi: Region of interest (the table)
            figure_text: Text extracted from the table
            
        Returns:
            str: Structured description of the table
        """
        # Try to detect rows and columns
        if not figure_text.strip():
            return "Table with no readable text"
        
        # Look for patterns in the text that indicate table structure
        lines = figure_text.split('\n')
        lines = [line for line in lines if line.strip()]
        
        if len(lines) < 2:
            return f"Table with content: {figure_text}"
        
        # Very basic table structure extraction
        # Look for consistent separator patterns
        separators = []
        for line in lines:
            # Look for common table separators
            if '|' in line:
                separators.append('|')
            elif '\t' in line:
                separators.append('\t')
            elif line.count(' ') > 3 and re.search(r'\s{2,}', line):
                separators.append('space')
                
        # Find the most common separator
        if separators:
            from collections import Counter
            common_sep = Counter(separators).most_common(1)[0][0]
            
            # Describe based on separator
            if common_sep == '|':
                row_count = len(lines)
                col_count = max(len(line.split('|')) for line in lines)
                return f"Table with {row_count} rows and {col_count} columns. Content: {figure_text}"
            elif common_sep == '\t':
                row_count = len(lines)
                col_count = max(len(line.split('\t')) for line in lines)
                return f"Table with {row_count} rows and {col_count} columns. Content: {figure_text}"
            elif common_sep == 'space':
                # Harder to determine columns with spaces
                return f"Table with approximately {len(lines)} rows. Content: {figure_text}"
        
        return f"Table content: {figure_text}"
    
    def _analyze_chart_or_diagram(self, roi, figure_text):
        """
        Analyze a chart or diagram and extract key information.
        
        Args:
            roi: Region of interest (the chart/diagram)
            figure_text: Text extracted from the chart/diagram
            
        Returns:
            str: Description of the chart/diagram
        """
        # Extract any titles, labels, and figure references
        title_pattern = r'(?:Fig(?:ure)?|Рис(?:унок)?)\.?\s*(\d+[-\.]\d+|\d+)'
        title_match = re.search(title_pattern, figure_text, re.IGNORECASE)
        
        # Extract figure number if found
        if title_match:
            figure_number = title_match.group(1)
            figure_text = figure_text.replace(title_match.group(0), '')  # Remove the figure reference
            description = f"Figure {figure_number}: "
        else:
            description = "Diagram/Chart: "
        
        # Extract any remaining text for content description
        content_text = figure_text.strip()
        if content_text:
            # Check for poker-specific diagrams
            poker_terms = ['pot', 'bet', 'fold', 'check', 'raise', 'call', 
                          'hand', 'equity', 'range', 'EV', 'stack', 'BB', 'SB']
                          
            found_terms = []
            for term in poker_terms:
                if re.search(r'\b' + re.escape(term) + r'\b', content_text, re.IGNORECASE):
                    found_terms.append(term)
            
            if found_terms:
                poker_description = f"Poker diagram related to: {', '.join(found_terms)}. "
                description += poker_description
            
            # Add the full text content
            description += f"Content: {content_text}"
        else:
            # If no text found, provide a basic visual description
            description += "Visual element with no readable text"
            
        return description
    
    def save_figure(self, original_img, figure_data, output_dir, image_basename):
        """
        Save a detected figure to file.
        
        Args:
            original_img: Original image
            figure_data: Tuple of (type, region, description)
            output_dir: Directory to save to
            image_basename: Base filename to use
            
        Returns:
            str: Path to saved figure
        """
        try:
            figure_type, region, description = figure_data
            x, y, w, h = region
            
            # Extract figure from original image
            figure_img = original_img[y:y+h, x:x+w]
            
            # Create filename
            timestamp = os.path.splitext(image_basename)[0]
            figure_filename = f"{timestamp}_{figure_type}_{os.path.basename(output_dir)}_{x}_{y}.png"
            figure_path = os.path.join(output_dir, figure_filename)
            
            # Save figure
            cv2.imwrite(figure_path, figure_img)
            
            # Save description
            desc_filename = os.path.splitext(figure_filename)[0] + ".txt"
            desc_path = os.path.join(output_dir, desc_filename)
            with open(desc_path, 'w', encoding='utf-8') as f:
                f.write(description)
                
            return figure_path
            
        except Exception as e:
            logger.error(f"Error saving figure: {str(e)}")
            return None
