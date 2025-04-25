# Добавьте эти строки в начало test_ocr.py и poker_book_processor.py
from dotenv import load_dotenv
load_dotenv()  # Загружает переменные из .env файла

import cv2
import pytesseract
import numpy as np
import pandas as pd
import re
import json
import os
import time
import argparse
import requests
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from matplotlib import pyplot as plt
from fpdf import FPDF
import openai
from tqdm import tqdm
import glob
import sys

class PokerBookProcessor:
    def __init__(self, output_dir='output', openai_api_key=None, target_language='ru'):
        """
        Инициализация процессора для OCR и переводов книг по покеру.
        
        Args:
            output_dir (str): Директория для сохранения результатов
            openai_api_key (str): API ключ OpenAI для улучшения OCR и перевода
            target_language (str): Язык перевода (по умолчанию: ru)
        """
        self.output_dir = output_dir
        self.target_language = target_language
        
        # Настройка OpenAI
        self.openai_api_key = openai_api_key
        if openai_api_key:
            try:
                # Пытаемся использовать новый API клиент
                openai.api_key = openai_api_key
            except Exception as e:
                print(f"Ошибка при настройке OpenAI API: {str(e)}")
        
        # Создаем директории для выходных файлов
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Создаем поддиректории
        self.text_dir = os.path.join(output_dir, 'text')
        self.images_dir = os.path.join(output_dir, 'images')
        self.tables_dir = os.path.join(output_dir, 'tables')
        self.diagrams_dir = os.path.join(output_dir, 'diagrams')
        self.translated_dir = os.path.join(output_dir, 'translated')
        self.pdf_dir = os.path.join(output_dir, 'pdf')
        
        for directory in [self.text_dir, self.images_dir, self.tables_dir, 
                          self.diagrams_dir, self.translated_dir, self.pdf_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
    
    def preprocess_image(self, image_path):
        """
        Предобработка изображения для улучшения OCR.
        
        Args:
            image_path (str): Путь к изображению
            
        Returns:
            tuple: (original_resized, eroded) - исходное и обработанное изображения
        """
        try:
            # Загрузка изображения
            img = cv2.imread(image_path)
            
            # Проверка успешности загрузки
            if img is None:
                raise ValueError(f"Не удалось загрузить изображение: {image_path}")
                
            # Получение размера изображения
            height, width = img.shape[:2]
            
            # Увеличение размера для улучшения распознавания, если изображение маленькое
            if width < 1000:
                scale_factor = 1000 / width
                img = cv2.resize(img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
            
            # Создаем копию оригинала для последующей обработки
            original_resized = img.copy()
            
            # Преобразование в оттенки серого
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Применение гауссовского размытия для уменьшения шума
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Адаптивное пороговое преобразование
            binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                          cv2.THRESH_BINARY, 11, 2)
            
            # Шумоподавление
            denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
            
            # Морфологические операции для улучшения текста
            kernel = np.ones((1, 1), np.uint8)
            dilated = cv2.dilate(denoised, kernel, iterations=1)
            eroded = cv2.erode(dilated, kernel, iterations=1)
            
            return original_resized, eroded
        except Exception as e:
            print(f"Ошибка при предобработке изображения {image_path}: {str(e)}")
            raise
    
    def enhance_with_openai(self, text, purpose="ocr_correction"):
        """
        Улучшение текста с помощью OpenAI.
        
        Args:
            text (str): Исходный текст
            purpose (str): Цель улучшения (ocr_correction, translation, diagram_description)
            
        Returns:
            str: Улучшенный текст
        """
        if not self.openai_api_key:
            print("OpenAI API ключ не указан. Пропускаем улучшение текста.")
            return text
            
        try:
            if purpose == "ocr_correction":
                prompt = f"""You are processing text extracted from a poker book called "Quantum Poker".
                Below is text extracted via OCR. Please correct errors, maintain proper formatting,
                and preserve all poker terminology. Remove any OCR artifacts or noise.
                DO NOT ADD ANY CONTENT that isn't clearly part of the original text.
                DO NOT add your own commentary, just clean the text.
                
                TEXT FROM OCR:
                {text}
                
                CLEANED TEXT:"""
                
            elif purpose == "translation":
                prompt = f"""Переведите следующий текст на русский язык. 
                Сохраните структуру и форматирование оригинала.
                Покерные термины следует сначала оставить на английском, 
                а затем дать их перевод в скобках.
                Все числа, формулы и названия должны быть переведены корректно. 
                Не добавляйте ничего, что не видно в оригинале.
                Не добавляйте свои комментарии или интерпретации.
             
                
                Оригинал:
                {text}
                
                Перевод на русский:"""
                
            elif purpose == "diagram_description":
                prompt = f"""Проанализируйте текст из диаграммы/графика книги по покеру.
                Опишите подробно, что изображено на графике, игнорируя случайные символы или ошибки OCR.
                Включите все видимые элементы, надписи, связи между ними.
                Определите, какую концепцию покера иллюстрирует график.
                Не добавляйте ничего, что не видно на графике.
                Не добавляйте свои комментарии или интерпретации.
                Сформулируйте ответ в виде краткого описания.
                
                
                Текст из диаграммы:
                {text}
                
                Описание графика:"""
            
            # Пытаемся использовать новый API клиент
            try:
                client = openai.OpenAI(api_key=self.openai_api_key)
                response = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": "Вы специалист по распознаванию и обработке текста из книг по покеру."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000,
                    temperature=0.1
                )
                enhanced_text = response.choices[0].message.content.strip()
            # Если новый API не работает, пробуем старый
            except Exception as new_api_error:
                print(f"Ошибка с новым API: {str(new_api_error)}. Пробуем старый API.")
                response = openai.ChatCompletion.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": "Вы специалист по распознаванию и обработке текста из книг по покеру."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000,
                    temperature=0.1
                )
                enhanced_text = response.choices[0].message.content.strip()
                
            # Убираем случайный текст и мусор
            if purpose == "ocr_correction":
                # Удаляем строки с большим количеством специальных символов
                lines = enhanced_text.split('\n')
                cleaned_lines = []
                for line in lines:
                    # Подсчитываем количество специальных символов
                    special_chars = sum(1 for c in line if not c.isalnum() and not c.isspace())
                    total_chars = len(line)
                    
                    # Если доля специальных символов меньше определенного порога, сохраняем строку
                    if total_chars > 0 and special_chars / total_chars < 0.3:
                        cleaned_lines.append(line)
                
                enhanced_text = '\n'.join(cleaned_lines)
                
            return enhanced_text
            
        except Exception as e:
            print(f"Ошибка при использовании OpenAI API: {str(e)}")
            # Возвращаем исходный текст в случае ошибки
            return text
    
    def detect_text_regions(self, img):
        """
        Обнаружение регионов с текстом на изображении.
        
        Args:
            img: Обработанное изображение
            
        Returns:
            list: Список регионов с текстом в формате [(x, y, w, h), ...]
        """
        # Конвертация в серое изображение, если необходимо
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
            
        # Применение морфологических операций для выделения текстовых блоков
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        dilate = cv2.dilate(gray, kernel, iterations=3)
        
        # Поиск контуров
        cnts, _ = cv2.findContours(~dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Фильтрация контуров
        text_regions = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            # Фильтруем слишком маленькие области
            if w > 100 and h > 20:
                text_regions.append((x, y, w, h))
                
        return text_regions
        
    def detect_figures(self, img, original_img):
        """
        Enhanced algorithm to detect only meaningful diagrams and charts,
        not just text fragments.
        """
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
            
        # Binarization
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Morphological operations to find connected components
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(binary, kernel, iterations=2)
        
        # Find contours
        cnts, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        figures = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            aspect_ratio = w / float(h)
            
            # Improved criteria for real diagrams/figures
            if (w > 200 and h > 200 and aspect_ratio > 0.5 and aspect_ratio < 2):
                # Add padding
                x_start = max(0, x - 10)
                y_start = max(0, y - 10)
                x_end = min(original_img.shape[1], x + w + 10)
                y_end = min(original_img.shape[0], y + h + 10)
                
                figure_roi = original_img[y_start:y_end, x_start:x_end]
                
                # Additional verification for valid figures
                if self.is_valid_figure(figure_roi):
                    figures.append({
                        'bbox': (x_start, y_start, x_end - x_start, y_end - y_start),
                        'roi': figure_roi
                    })
                    
        return figures
    
    def is_valid_figure(self, img):
        """
        Improved validation to distinguish actual figures from text fragments.
        """
        if img is None or img.size == 0:
            return False
        
        # Convert to grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
            
        # Calculate texture and pattern metrics
        std_dev = np.std(gray)  # Contrast measure
        edges = cv2.Canny(gray, 50, 150)
        edge_count = np.sum(edges > 0)
        area = gray.shape[0] * gray.shape[1]
        edge_density = edge_count / area
        
        # Calculate text density
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        text_density = np.sum(binary > 0) / area
        
        # Check for graphics patterns versus text patterns
        horizontal_lines = self.detect_horizontal_lines(gray)
        vertical_lines = self.detect_vertical_lines(gray)
        has_lines = horizontal_lines > 2 or vertical_lines > 2
        
        # Graphs, charts, and diagrams have a balance of edges and aren't just text
        return (std_dev > 30 and edge_density > 0.05 and text_density < 0.4) or has_lines
    
    def detect_horizontal_lines(self, gray_img):
        # Detect horizontal lines characteristic of charts and graphs
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        horizontal_count = np.sum(horizontal_lines > 0)
        return horizontal_count

    def detect_vertical_lines(self, gray_img):
        # Detect vertical lines characteristic of charts and graphs
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        vertical_lines = cv2.morphologyEx(gray_img, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        vertical_count = np.sum(vertical_lines > 0)
        return vertical_count

    
    def detect_figure_text_blocks(self, gray_img):
        """
        Обнаружение текстовых блоков на изображении фигуры/графика.
        
        Args:
            gray_img: Изображение в оттенках серого
            
        Returns:
            list: Список обнаруженных текстовых блоков
        """
        # Бинаризация
        _, binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Морфологические операции для выделения текстовых блоков
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
        dilated = cv2.dilate(binary, kernel, iterations=1)
        
        # Поиск контуров
        cnts, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Фильтрация контуров
        text_blocks = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            # Фильтруем слишком большие и слишком маленькие области
            if w > 5 and h > 5 and w < gray_img.shape[1] // 2 and h < gray_img.shape[0] // 2:
                text_blocks.append((x, y, w, h))
                
        return text_blocks
    
    def detect_tables(self, img, original_img):
        """
        Обнаружение таблиц на изображении.
        
        Args:
            img: Обработанное изображение
            original_img: Исходное изображение
            
        Returns:
            list: Список обнаруженных таблиц
        """
        # Поиск горизонтальных и вертикальных линий
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        
        # Бинаризация
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        
        # Определение горизонтальных линий
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        # Определение вертикальных линий
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        vertical_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        
        # Объединение линий
        table_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
        
        # Поиск контуров таблицы
        cnts, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        tables = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            # Фильтр для исключения ложных срабатываний
            if w > 200 and h > 100:
                # Добавляем отступ для полного захвата таблицы
                padding = 10
                x_start = max(0, x - padding)
                y_start = max(0, y - padding)
                x_end = min(original_img.shape[1], x + w + padding)
                y_end = min(original_img.shape[0], y + h + padding)
                
                table_roi = original_img[y_start:y_end, x_start:x_end]
                tables.append({
                    'bbox': (x_start, y_start, x_end - x_start, y_end - y_start),
                    'roi': table_roi
                })
                
        return tables
    
    def extract_text(self, img, improve_with_ai=True):
        """
        Извлечение текста с изображения с помощью Tesseract и опционально OpenAI.
        
        Args:
            img: Изображение для OCR
            improve_with_ai (bool): Улучшение с помощью OpenAI
            
        Returns:
            str: Извлеченный текст
        """
        # Преобразование OpenCV изображения в формат PIL
        pil_img = Image.fromarray(img)
        
        # Извлечение текста с помощью Tesseract с дополнительными параметрами
        text = pytesseract.image_to_string(
            pil_img,
            lang='eng',
            config='--psm 6 --oem 3 -c preserve_interword_spaces=1'
        )
        
        # Первичная очистка текста без использования OpenAI
        # Убираем случайные специальные символы и последовательности
        text = self.clean_ocr_text(text)
        
        # Улучшение текста с помощью OpenAI, если включено
        if improve_with_ai and self.openai_api_key:
            text = self.enhance_with_openai(text, purpose="ocr_correction")
            
        return text
    
    def clean_ocr_text(self, text):
        # More aggressive cleaning for PDF output
        # Remove lines with too many special characters
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            if not line.strip():
                continue
                
            # More strict filtering for PDF generation
            special_chars = sum(1 for char in line if not char.isalnum() and not char.isspace())
            total_chars = len(line)
            
            if total_chars > 0 and special_chars / total_chars < 0.3:
                # Additional check for garbage text patterns
                if not re.search(r'[^\w\s\.\,\:\;\'\"\-\(\)\[\]\{\}\!\?\$\%\&\+\=\/<>@#]{3,}', line):
                    cleaned_lines.append(line)
                    
        return '\n'.join(cleaned_lines)
    
    def extract_poker_terms(self, text):
        """
        Извлечение покерных терминов из текста с улучшенным алгоритмом.
        
        Args:
            text (str): Текст для анализа
            
        Returns:
            list: Список обнаруженных терминов
        """
        # Шаблон для обнаружения терминов в формате "Термин - определение"
        term_pattern = r'([A-Z][a-zA-Z\s]+)\s+[-–]\s+([^\n]+)'
        
        # Избегаем использования look-behind с переменной длиной 
        # и используем простое разбиение по строкам и проверку начала строки
        terms = []
        
        # Поиск по основному шаблону
        for match in re.finditer(term_pattern, text):
            term = match.group(1).strip()
            definition = match.group(2).strip()
            
            # Проверка на релевантность термина
            if len(term.split()) <= 4 and not any(t['term'] == term for t in terms):
                terms.append({
                    'term': term,
                    'definition': definition
                })
        
        # Альтернативный подход для поиска терминов в начале строк
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
                
            # Проверка на капитализированное слово в начале строки
            if re.match(r'^[A-Z][a-zA-Z\s]+\s+[A-Z]', line):
                parts = re.split(r'\s+(?=[A-Z])', line, 1)  # Разделяем по первому слову, начинающемуся с заглавной буквы
                if len(parts) == 2:
                    term = parts[0].strip()
                    definition = parts[1].strip()
                    
                    # Проверка на релевантность
                    if len(term.split()) <= 4 and not any(t['term'] == term for t in terms):
                        terms.append({
                            'term': term,
                            'definition': definition
                        })
        
        return terms
    
    def extract_tables_data(self, table_img, improve_with_ai=True):
        """
        Извлечение данных из таблиц с помощью Tesseract и OpenAI.
        
        Args:
            table_img: Изображение таблицы
            improve_with_ai (bool): Улучшение с помощью OpenAI
            
        Returns:
            list: Данные таблицы
        """
        try:
            # Преобразование и улучшение изображения
            if len(table_img.shape) == 3:
                gray = cv2.cvtColor(table_img, cv2.COLOR_BGR2GRAY)
            else:
                gray = table_img
                
            # Бинаризация для улучшения распознавания
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Используем Tesseract с конфигурацией для таблиц
            raw_text = pytesseract.image_to_string(
                binary,
                lang='eng',
                config='--psm 6 --oem 3'
            )
            
            # Улучшение и структурирование с помощью OpenAI
            if improve_with_ai and self.openai_api_key:
                enhanced_text = self.enhance_with_openai(raw_text, purpose="ocr_correction")
                
                # Запрос к OpenAI для структурирования таблицы
                prompt = f"""Ниже представлен текст, извлеченный из изображения таблицы из книги по покеру. 
                Преобразуйте его в структурированную таблицу. 
                Верните результат в формате JSON-массива, где каждый элемент - это строка таблицы.
                Уберите все случайные символы и мусор, сохраняя только осмысленные данные.
                
                Текст:
                {enhanced_text}
                
                Структурированная таблица (JSON):"""
                
                try:
                    # Пытаемся использовать новый API клиент
                    try:
                        client = openai.OpenAI(api_key=self.openai_api_key)
                        response = client.chat.completions.create(
                            model="gpt-4-turbo",
                            messages=[
                                {"role": "system", "content": "Вы специалист по извлечению структурированных данных из таблиц."},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=2000,
                            temperature=0.3
                        )
                        ai_response = response.choices[0].message.content.strip()
                    # Если новый API не работает, пробуем старый
                    except Exception as new_api_error:
                        print(f"Ошибка с новым API для таблиц: {str(new_api_error)}. Пробуем старый API.")
                        response = openai.ChatCompletion.create(
                            model="gpt-4-turbo",
                            messages=[
                                {"role": "system", "content": "Вы специалист по извлечению структурированных данных из таблиц."},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=2000,
                            temperature=0.3
                        )
                        ai_response = response.choices[0].message.content.strip()
                    
                    # Извлечение JSON из ответа
                    json_match = re.search(r'```json\s*([\s\S]*?)\s*```|(\[\s*{[\s\S]*?}\s*\])', ai_response)
                    if json_match:
                        json_str = json_match.group(1) or json_match.group(2)
                        table_data = json.loads(json_str)
                    else:
                        # Если формат не соответствует, используем строки
                        table_data = enhanced_text.split('\n')
                except Exception as e:
                    print(f"Ошибка при структурировании таблицы с OpenAI: {str(e)}")
                    table_data = enhanced_text.split('\n')
            else:
                # Без улучшения просто разбиваем по строкам
                table_data = raw_text.split('\n')
            
            # Фильтрация пустых строк и строк с мусором
            table_data = [row for row in table_data if row.strip() and not self.is_garbage_text(row)]
            
            return table_data
        except Exception as e:
            print(f"Ошибка при извлечении данных таблицы: {str(e)}")
            return []
    
    def is_garbage_text(self, text):
        """
        Определяет, является ли текст мусорным (случайными символами).
        
        Args:
            text (str): Проверяемый текст
            
        Returns:
            bool: True, если текст является мусорным
        """
        # Проверка на текст, состоящий преимущественно из специальных символов
        special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
        total_chars = len(text)
        
        if total_chars == 0:
            return True
            
        # Если более 40% символов - специальные, вероятно это мусор
        if special_chars / total_chars > 0.4:
            return True
            
        # Проверка на случайные последовательности символов
        if re.search(r'[^\w\s\.\,\:\;\'\"\-\(\)\[\]\{\}\!\?\$\%\&\+\=\/<>@#]{4,}', text):
            return True
            
        return False
    
    def analyze_figure_content(self, figure_img):
        """
        Анализ содержимого схемы/диаграммы с помощью OCR и OpenAI.
        
        Args:
            figure_img: Изображение схемы/диаграммы
            
        Returns:
            str: Описание содержимого
        """
        try:
            # Извлечение текста из изображения схемы
            if len(figure_img.shape) == 3:
                gray = cv2.cvtColor(figure_img, cv2.COLOR_BGR2GRAY)
            else:
                gray = figure_img
                
            # Бинаризация для улучшения распознавания
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Удаление шума
            denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
            
            # Извлечение текста
            figure_text = pytesseract.image_to_string(
                denoised,
                lang='eng',
                config='--psm 11 --oem 3'
            )
            
            # Улучшение и интерпретация с помощью OpenAI
            if self.openai_api_key:
                enhanced_description = self.enhance_with_openai(figure_text, purpose="diagram_description")
                return enhanced_description
            else:
                return self.clean_ocr_text(figure_text)
        except Exception as e:
            print(f"Ошибка при анализе содержимого схемы: {str(e)}")
            return ""
    
    def translate_text(self, text):
        """
        Перевод текста на целевой язык с помощью OpenAI.
        
        Args:
            text (str): Исходный текст
            
        Returns:
            str: Переведенный текст
        """
        if not self.openai_api_key or not text.strip():
            return text
            
        try:
            translated_text = self.enhance_with_openai(text, purpose="translation")
            return translated_text
        except Exception as e:
            print(f"Ошибка при переводе текста: {str(e)}")
            return text
    
    def save_results(self, image_path, text, terms, figures, tables):
        """
        Сохранение результатов обработки.
        
        Args:
            image_path (str): Путь к обработанному изображению
            text (str): Извлеченный текст
            terms (list): Список терминов
            figures (list): Список фигур
            tables (list): Список таблиц
            
        Returns:
            dict: Сводка результатов
        """
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Создаем словарь для хранения путей к файлам
        result_files = {}
        
        # Сохранение извлеченного текста
        text_file = os.path.join(self.text_dir, f"{base_name}_{timestamp}.txt")
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(text)
        result_files['text'] = text_file
        
        # Сохранение терминов в JSON
        terms_file = os.path.join(self.text_dir, f"{base_name}_terms_{timestamp}.json")
        with open(terms_file, 'w', encoding='utf-8') as f:
            json.dump(terms, f, indent=2, ensure_ascii=False)
        result_files['terms'] = terms_file
        
        # Сохранение извлеченных изображений и их описаний
        figure_files = []
        for i, figure in enumerate(figures):
            # Сохранение изображения
            figure_file = os.path.join(self.diagrams_dir, f"{base_name}_figure_{i}_{timestamp}.png")
            cv2.imwrite(figure_file, figure['roi'])
            
            # Анализ и сохранение описания
            description = ""
            if 'description' in figure:
                description = figure['description']
            elif self.openai_api_key:
                description = self.analyze_figure_content(figure['roi'])
                
            description_file = os.path.join(self.diagrams_dir, f"{base_name}_figure_{i}_desc_{timestamp}.txt")
            with open(description_file, 'w', encoding='utf-8') as f:
                f.write(description)
                
            figure_files.append({
                'image': figure_file,
                'description': description_file,
                'bbox': figure['bbox']
            })
            
        result_files['figures'] = figure_files
        
        # Сохранение извлеченных таблиц
        table_files = []
        for i, table in enumerate(tables):
            # Сохранение изображения таблицы
            table_file = os.path.join(self.tables_dir, f"{base_name}_table_{i}_{timestamp}.png")
            cv2.imwrite(table_file, table['roi'])
            
            # Извлечение и сохранение данных таблицы
            table_data = self.extract_tables_data(table['roi'], improve_with_ai=True)
            
            table_data_file = os.path.join(self.tables_dir, f"{base_name}_table_{i}_data_{timestamp}.json")
            with open(table_data_file, 'w', encoding='utf-8') as f:
                json.dump(table_data, f, indent=2, ensure_ascii=False)
                
            table_files.append({
                'image': table_file,
                'data': table_data_file,
                'bbox': table['bbox']
            })
            
        result_files['tables'] = table_files
        
        # Перевод текста, если указан целевой язык
        if self.target_language != 'en' and self.openai_api_key:
            translated_text = self.translate_text(text)
            translated_file = os.path.join(self.translated_dir, f"{base_name}_translated_{timestamp}.txt")
            with open(translated_file, 'w', encoding='utf-8') as f:
                f.write(translated_text)
            result_files['translated_text'] = translated_file
            
            # Перевод терминов
            translated_terms = []
            for term in terms:
                translated_term = {
                    'term': term['term'],  # Оригинальный термин
                    'original_definition': term['definition'],
                    'translated_definition': self.translate_text(term['definition'])
                }
                translated_terms.append(translated_term)
                
            translated_terms_file = os.path.join(self.translated_dir, f"{base_name}_terms_translated_{timestamp}.json")
            with open(translated_terms_file, 'w', encoding='utf-8') as f:
                json.dump(translated_terms, f, indent=2, ensure_ascii=False)
            result_files['translated_terms'] = translated_terms_file
            
            # Перевод описаний фигур
            for i, figure in enumerate(figure_files):
                with open(figure['description'], 'r', encoding='utf-8') as f:
                    description = f.read()
                
                translated_description = self.translate_text(description)
                translated_desc_file = os.path.join(self.translated_dir, f"{base_name}_figure_{i}_desc_translated_{timestamp}.txt")
                with open(translated_desc_file, 'w', encoding='utf-8') as f:
                    f.write(translated_description)
                figure_files[i]['translated_description'] = translated_desc_file
        
        # Создание сводного отчета
        summary = {
            'image': image_path,
            'result_files': result_files,
            'total_terms': len(terms),
            'total_figures': len(figures),
            'total_tables': len(tables),
            'timestamp': timestamp
        }
        
        summary_file = os.path.join(self.output_dir, f"{base_name}_summary_{timestamp}.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
            
        return summary
    
    
    def add_tables_to_pdf(self, pdf, summary):
        # Add tables to PDF
        if 'tables' in summary['result_files']:
            for table in summary['result_files']['tables']:
                try:
                    # Add table image
                    pdf.image(table['image'], x=10, y=None, w=180)
                    pdf.ln(5)
                    
                    # Add table data if available
                    with open(table['data'], 'r', encoding='utf-8') as f:
                        table_data = json.load(f)
                        
                    # Format table data in PDF
                    if isinstance(table_data, list) and len(table_data) > 0:
                        pdf.set_font_size(9)
                        pdf.cell(0, 10, "Table data:", 0, 1)
                        
                        for row in table_data[:10]:  # Show first 10 rows max
                            if isinstance(row, dict):
                                row_text = ", ".join([f"{k}: {v}" for k, v in row.items()])
                            else:
                                row_text = str(row)
                            pdf.multi_cell(0, 5, row_text)
                        
                        pdf.set_font_size(12)
                        pdf.ln(5)
                except Exception as e:
                    print(f"Error adding table to PDF: {str(e)}")
                    continue
    
    def create_pdf(self, summaries, language='original'):
        # Сортировка сводок по имени файла для правильного порядка страниц
        sorted_summaries = sorted(summaries, key=lambda x: os.path.basename(x['image']))
        # Create a better structure for the PDF
        pdf = FPDF()
        pdf.add_page()
        
        # Configure font
        try:
            pdf.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
            pdf.set_font('DejaVu', '', 12)
        except Exception:
            pdf.set_font('Arial', '', 12)
        
        # Add title
        pdf.set_font_size(16)
        pdf.cell(190, 10, 'QUANTUM POKER', 0, 1, 'C')
        pdf.ln(10)
        pdf.set_font_size(12)
        
        # Process each page in order
        for summary in sorted_summaries:
            # Get the appropriate text
            if language == 'translated' and 'translated_text' in summary['result_files']:
                text_file = summary['result_files']['translated_text']
            else:
                text_file = summary['result_files']['text']
                    
            # Read and clean the text for PDF
            with open(text_file, 'r', encoding='utf-8') as f:
                page_text = f.read()
            
            # Extra cleaning for PDF output
            page_text = self.clean_text_for_pdf(page_text)
            
            # Add text to PDF
            pdf.multi_cell(0, 10, page_text)
            pdf.ln(5)
            
            # Только добавляем текстовую ссылку на фигуры, а не сами изображения
            if 'figures' in summary['result_files'] and summary['result_files']['figures']:
                base_name = os.path.splitext(os.path.basename(summary['image']))[0]
                pdf.set_font_size(10)
                for i, figure in enumerate(summary['result_files']['figures']):
                    pdf.multi_cell(0, 8, f"[Страница {base_name}, Рисунок {i+1}]")
                pdf.set_font_size(12)
                pdf.ln(5)
            
            # Только добавляем текстовую ссылку на таблицы, а не сами изображения
            if 'tables' in summary['result_files'] and summary['result_files']['tables']:
                base_name = os.path.splitext(os.path.basename(summary['image']))[0]
                pdf.set_font_size(10)
                for i, table in enumerate(summary['result_files']['tables']):
                    pdf.multi_cell(0, 8, f"[Страница {base_name}, Таблица {i+1}]")
                pdf.set_font_size(12)
                pdf.ln(5)
            
            # Add page break
            pdf.add_page()
                
        # Create output path and save
        output_name = f"quantum_poker_{language}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = os.path.join(self.pdf_dir, output_name)
        pdf.output(output_path)
        return output_path
        
    def clean_text_for_pdf(self, text):
        # More aggressive cleaning for PDF output
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Filter out OCR artifacts and page numbers
            if not re.match(r'^Page \d+ of \d+', line) and not re.match(r'^\d+ minute', line):
                if not re.search(r'[^\w\s\.\,\:\;\'\"\-\(\)\[\]\{\}\!\?\$\%\&\+\=\/<>@#]{4,}', line):
                    cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def add_diagrams_to_pdf(self, pdf, summary, language):
        # Only add substantive diagrams/figures, not text fragments
        if 'figures' in summary['result_files']:
            for figure in summary['result_files']['figures']:
                # Verify this is a true diagram and not a text fragment
                if self.is_valid_diagram(figure['image']):
                    try:
                        pdf.image(figure['image'], x=10, y=None, w=180)
                        
                        # Add description if available
                        if language == 'translated' and 'translated_description' in figure:
                            desc_file = figure['translated_description']
                        else:
                            desc_file = figure['description']
                            
                        with open(desc_file, 'r', encoding='utf-8') as f:
                            description = f.read()
                            
                        pdf.set_font_size(10)
                        pdf.multi_cell(0, 8, description)
                        pdf.set_font_size(12)
                        pdf.ln(5)
                    except Exception:
                        continue

    def is_valid_diagram(self, image_path):
        # Determine if an image is a true diagram or just a text fragment
        img = cv2.imread(image_path)
        if img is None:
            return False
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Calculate metrics
        std_dev = np.std(gray)  # Contrast measure
        edges = cv2.Canny(gray, 50, 150)
        edge_count = np.sum(edges > 0)
        area = gray.shape[0] * gray.shape[1]
        edge_density = edge_count / area
        
        # Check text density
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        text_density = np.sum(binary > 0) / area
        
        # True diagrams have moderate edge density and aren't just text
        return (edge_density > 0.05 and text_density < 0.3) or std_dev > 40
    
    def process_image(self, image_path):
        """
        Обработка одного изображения.
        
        Args:
            image_path (str): Путь к изображению
            
        Returns:
            dict: Сводка результатов обработки
        """
        print(f"Обработка изображения: {image_path}")
        
        try:
            # Предобработка изображения
            original_img, processed_img = self.preprocess_image(image_path)
            
            # Обнаружение текстовых регионов
            text_regions = self.detect_text_regions(processed_img)
            
            # Обнаружение фигур и диаграмм
            figures = self.detect_figures(processed_img, original_img)
            
            # Обнаружение таблиц
            tables = self.detect_tables(original_img, original_img)
            
            # Извлечение полного текста
            full_text = self.extract_text(processed_img, improve_with_ai=True)
            
            # Извлечение покерных терминов
            terms = self.extract_poker_terms(full_text)
            
            # Анализ содержимого схем
            for figure in figures:
                figure['description'] = self.analyze_figure_content(figure['roi'])
            
            # Визуализация результатов
            self.visualize_results(original_img, text_regions, figures, tables)
            
            # Сохранение результатов
            summary = self.save_results(image_path, full_text, terms, figures, tables)
            
            print(f"Обработка завершена. Найдено терминов: {len(terms)}, фигур: {len(figures)}, таблиц: {len(tables)}")
            return summary
            
        except Exception as e:
            print(f"Ошибка при обработке {image_path}: {str(e)}")
            return None
    
    def visualize_results(self, img, text_regions, figures, tables):
        """
        Визуализация результатов обнаружения для отладки.
        
        Args:
            img: Исходное изображение
            text_regions (list): Список регионов с текстом
            figures (list): Список фигур
            tables (list): Список таблиц
        """
        # Создаем копию изображения для рисования
        viz_img = img.copy()
        
        # Рисуем текстовые регионы зеленым
        for (x, y, w, h) in text_regions:
            cv2.rectangle(viz_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        # Рисуем фигуры красным
        for figure in figures:
            x, y, w, h = figure['bbox']
            cv2.rectangle(viz_img, (x, y), (x + w, y + h), (0, 0, 255), 2)
        
        # Рисуем таблицы синим
        for table in tables:
            x, y, w, h = table['bbox']
            cv2.rectangle(viz_img, (x, y), (x + w, y + h), (255, 0, 0), 2)
        
        # Сохраняем визуализацию
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(self.output_dir, f"visualization_{timestamp}.png")
        cv2.imwrite(output_path, viz_img)
        
    def batch_process(self, image_paths):
        """
        Improved batch processor with better page handling for PDF
        """
        results = []
        
        # Sort images by filename to maintain correct page order
        sorted_images = sorted(image_paths)
        
        # Process images with progress tracking
        for path in tqdm(sorted_images, desc="Processing pages"):
            try:
                result = self.process_image(path)
                if result:
                    results.append(result)
            except Exception as e:
                print(f"Error processing {path}: {str(e)}")
        
        if not results:
            print("No images were successfully processed.")
            return None
        
        # Create consolidated report
        final_report = {
            'total_images': len(image_paths),
            'processed_images': len(results),
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
        
        # Save report
        report_path = os.path.join(self.output_dir, f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(final_report, f, indent=2, ensure_ascii=False)
        
        # Create PDFs
        if results:
            try:
                # Применение AI-организации перед созданием PDF
                try:
                    result_tuple = self.process_with_ai_organization(results)
                    if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
                        organized_results, organization = result_tuple
                    else:
                        organized_results = result_tuple
                        organization = None
                except Exception as e:
                    print(f"Warning: AI organization skipped: {str(e)}")
                    organized_results = results
                    organization = None
                
                # Original language PDF
                eng_pdf = self.create_pdf(organized_results, language='original')
                print(f"PDF created: {eng_pdf}")
                
                # Translated PDF if applicable
                if self.target_language != 'en' and self.openai_api_key:
                    ru_pdf = self.create_pdf(organized_results, language='translated')
                    print(f"Translated PDF created: {ru_pdf}")
            except Exception as e:
                print(f"Error creating PDF: {str(e)}")
        
        return final_report
    
    
    def process_with_ai_organization(self, results):
        """
        Use AI to organize book content in a more meaningful way
        """
        if not self.openai_api_key:
            return results, None
        
        try:
            # Extract text from all processed pages
            all_text = ""
            for result in results:
                text_file = result['result_files']['text']
                with open(text_file, 'r', encoding='utf-8') as f:
                    all_text += f.read() + "\n\n"
            
            # Ask AI to organize structure
            client = openai.OpenAI(api_key=self.openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert book editor organizing content for a poker book."},
                    {"role": "user", "content": f"""
                    I've extracted content from a poker book titled 'Quantum Poker'. Please analyze this content
                    and create metadata for better organization:
                    1. Identify chapter breaks
                    2. Identify major sections
                    3. Create a table of contents
                    4. Note where diagrams and tables should appear
                    
                    BOOK CONTENT:
                    {all_text[:15000]}  # Sending first part due to token limits
                    
                    ORGANIZATION:
                    """}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            
            organization = response.choices[0].message.content.strip()
            
            # Save organization metadata
            org_path = os.path.join(self.output_dir, f"book_organization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(org_path, 'w', encoding='utf-8') as f:
                f.write(organization)
            
            # Use this for enhanced PDF creation
            return results, organization
        
        except Exception as e:
            print(f"Error in AI organization: {str(e)}")
            return results, None


def main():
    """
    Основная функция для запуска обработки изображений покерной книги.
    """
    # Установка значений по умолчанию
    default_images = ['/home/analityk/Документы/github/AmazonBookParser/kindle_screenshots/*.png']
    default_output = 'output'
    default_openai_key = None  # Заменить на свой ключ при необходимости
    default_lang = 'ru'
    
    # Создание парсера с аргументами для возможности переопределения
    parser = argparse.ArgumentParser(description='Процессор покерной книги для OCR и перевода')
    parser.add_argument('--images', nargs='+', default=default_images, help='Пути к изображениям для обработки')
    parser.add_argument('--output', default=default_output, help='Директория для сохранения результатов')
    parser.add_argument('--openai-key', default=default_openai_key, help='API ключ OpenAI для улучшения OCR и перевода')
    parser.add_argument('--lang', default=default_lang, help='Язык перевода (по умолчанию: ru)')
    
    args = parser.parse_args()
    
    # Использование значений из аргументов, которые уже содержат значения по умолчанию
    openai_key = args.openai_key or os.environ.get('OPENAI_API_KEY')
    
    # Расширение масок файлов для изображений
    all_images = []
    for path_pattern in args.images:
        # Проверяем, содержит ли путь маску
        if '*' in path_pattern:
            # Получаем базовую директорию
            base_dir = os.path.dirname(path_pattern)
            # Получаем маску файла
            file_pattern = os.path.basename(path_pattern)
            # Если путь существует, находим все подходящие файлы
            if os.path.exists(base_dir):
                matching_files = glob.glob(os.path.join(base_dir, file_pattern))
                all_images.extend(matching_files)
        else:
            all_images.append(path_pattern)
    
    # Сообщение при отсутствии подходящих изображений
    if not all_images:
        print(f"Предупреждение: не найдено изображений по указанным путям: {args.images}")
        print("Проверьте пути и убедитесь, что файлы существуют.")
        return
    
    processor = PokerBookProcessor(
        output_dir=args.output,
        openai_api_key=openai_key,
        target_language=args.lang
    )
    
    processor.batch_process(all_images)


if __name__ == "__main__":
    main()
    
    print("Обработка завершена.")