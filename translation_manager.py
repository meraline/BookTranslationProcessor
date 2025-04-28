#!/usr/bin/env python3
"""
Module for managing translations using OpenAI.
"""
import os
import logging
import re
import json
import time
import openai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TranslationManager:
    """Handles translation from English to Russian using OpenAI API."""
    
    # Словарь покерных терминов для проверки и замены
    POKER_GLOSSARY = {
        "EV": "Expected Value (математическое ожидание)",
        "AEV": "Average Expected Value (среднее математическое ожидание)",
        "AFV": "Average Function Value (функция среднего значения)",
        "pot odds": "pot odds (шансы банка)",
        "implied odds": "implied odds (потенциальные шансы)",
        "GTO": "Game Theory Optimal (оптимальная игра по теории игр)",
        "VPIP": "Voluntarily Put Money In Pot (добровольный вклад в банк)",
        "PFR": "Pre-Flop Raise (повышение на префлопе)",
        "3-bet": "3-bet (3-бет, ререйз)",
        "4-bet": "4-bet (4-бет, ререйз на 3-бет)",
        "WTSD": "Went To Showdown (дошел до вскрытия)",
        "MTTTL": "Move To The Top Level (переход на высший уровень)",
        
        # Расширенные определения для SWASED и других терминов
        "SWASED": "SWASED (Система анализа покерных решений - Street, WTSD, Actualization, Sizing, EV, Downstream)",
        "ECD": "ECD (Execution, Calculation, Decision - компоненты принятия решений в покере)",
        "CEE": "CEE (Calculation, Execution, Evaluation - методика оценки игры)",
        "Eo": "Eo (Equity optimization - оптимизация эквити)",
        "ea": "ea (equity awareness - осознание эквити)",
        "Fn": "Fn (Function notation - функциональная нотация)",
        "i": "i (iteration - итерация)",
        "Do": "Do (Downstream optimization - оптимизация последующих действий)",
        "CD": "CD (Calculation and Decision - расчеты и принятие решений)",
        
        "UTG": "Under The Gun (первая позиция после блайндов)",
        "BB": "Big Blind (большой блайнд)",
        "SB": "Small Blind (малый блайнд)",
        "BTN": "Button (позиция баттона)",
        "CO": "Cut-off (позиция катоффа)",
        "HJ": "Hijack (позиция хайджека)",
        "MP": "Middle Position (средняя позиция)",
        "EP": "Early Position (ранняя позиция)",
        "Barrel": "Barrel (ставка, обычно делаемая после ставки на предыдущей улице)",
        "10,000 Hour Rule": "10,000 Hour Rule (правило 10,000 часов - для становления экспертом в любой области)",
        "Actualization": "Actualization (актуализация - способность полностью и точно рассчитать наилучший курс действий сейчас и в будущем)",
        "Autopilot": "Autopilot (автопилот - действия без реального обдумывания)",
        "Average Enumerated Value": "Average Enumerated Value (среднее перечисляемое значение)",
    }
    
    def __init__(self, openai_api_key=None, target_language='ru', cache_dir=None):
        """
        Initialize translation manager.
        
        Args:
            openai_api_key (str): OpenAI API key
            target_language (str): Target language for translations (default: ru)
            cache_dir (str): Directory for caching translations
        """
        self.target_language = target_language
        self.cache = {}
        self.cache_dir = cache_dir
        
        # Setup OpenAI API
        self.openai_api_key = openai_api_key
        if openai_api_key:
            try:
                # Try to use new API client
                openai.api_key = openai_api_key
                # Test if API key is valid
                self._test_openai_connection()
            except Exception as e:
                logger.error(f"Error setting up OpenAI API: {str(e)}")
        
        # Create cache directory if specified
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            
        # Load existing cache if available
        self._load_cache()
    
    def _test_openai_connection(self):
        """
        Test if the OpenAI connection is working.
        
        Returns:
            bool: True if connection works, False otherwise
        """
        try:
            # Try to use the new API client with a minimal request
            try:
                client = openai.OpenAI(api_key=self.openai_api_key)
            except TypeError:
                # Fallback для случаев когда proxies вызывает ошибку
                client = openai.OpenAI()
                client.api_key = self.openai_api_key
                
            response = client.chat.completions.create(
                model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Say hello"}
                ],
                max_tokens=10,
                temperature=0.1
            )
            return True
        except Exception as e:
            logger.error(f"OpenAI API connection test failed: {str(e)}")
            return False
    
    def _load_cache(self):
        """Load translation cache from disk if available."""
        if not self.cache_dir:
            return
            
        cache_file = os.path.join(self.cache_dir, 'translation_cache.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} cached translations")
            except Exception as e:
                logger.error(f"Error loading translation cache: {str(e)}")
                self.cache = {}
    
    def _save_cache(self):
        """Save translation cache to disk."""
        if not self.cache_dir:
            return
            
        cache_file = os.path.join(self.cache_dir, 'translation_cache.json')
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving translation cache: {str(e)}")
    
    def translate_text(self, text, purpose="translation", retry_count=3):
        """
        Translate text using OpenAI.
        
        Args:
            text (str): Text to translate
            purpose (str): Purpose of translation (translation, figure_description)
            retry_count (int): Number of retries on failure
            
        Returns:
            str: Translated text
        """
        if not text.strip():
            return ""
            
        if not self.openai_api_key:
            logger.warning("No OpenAI API key provided. Cannot translate text.")
            return text
        
        # Check cache first
        cache_key = f"{purpose}:{text}"
        if cache_key in self.cache:
            logger.debug("Using cached translation")
            return self.cache[cache_key]
        
        # Clean text for better translations
        cleaned_text = self._clean_text_for_translation(text)
        if not cleaned_text.strip():
            return ""
            
        # Build prompt based on purpose
        prompt = self._build_translation_prompt(cleaned_text, purpose)
        
        # Try translation with retries
        for attempt in range(retry_count):
            try:
                # Try to use new API client
                try:
                    client = openai.OpenAI(api_key=self.openai_api_key)
                    response = client.chat.completions.create(
                        model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
                        messages=[
                            {"role": "system", "content": "Вы специалист по переводу текстов по покеру с английского на русский."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=4000,
                        temperature=0.1
                    )
                    translated_text = response.choices[0].message.content.strip()
                # If new API doesn't work, raise exception to trigger retry
                except Exception as new_api_error:
                    logger.error(f"Error with new API: {str(new_api_error)}. Cannot use old API.")
                    raise ValueError(f"OpenAI API error: {str(new_api_error)}")
                
                # Post-process the translation
                processed_translation = self._post_process_translation(translated_text)
                
                # Cache the result
                self.cache[cache_key] = processed_translation
                self._save_cache()
                
                return processed_translation
                
            except Exception as e:
                logger.error(f"Translation attempt {attempt+1} failed: {str(e)}")
                if attempt < retry_count - 1:
                    # Wait before retrying (exponential backoff)
                    time.sleep(2 ** attempt)
                else:
                    logger.error("All translation attempts failed")
                    return text  # Return original text on complete failure
    
    def _clean_text_for_translation(self, text):
        """
        Clean text before translation.
        
        Args:
            text (str): Text to clean
            
        Returns:
            str: Cleaned text
        """
        # Remove excessively repeated characters
        text = re.sub(r'(.)\1{3,}', r'\1\1', text)
        
        # Remove lines with mostly special characters
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Count special characters
            special_chars = sum(1 for c in line if not c.isalnum() and not c.isspace())
            total_chars = len(line)
            
            # Keep if less than 40% special characters
            if total_chars == 0 or special_chars / total_chars < 0.4:
                cleaned_lines.append(line)
        
        text = '\n'.join(cleaned_lines)
        
        # Предварительная обработка покерных терминов и аббревиатур
        text = self._preprocess_poker_terms(text)
        
        return text
        
    def _preprocess_poker_terms(self, text):
        """
        Предварительная обработка покерных терминов для повышения качества перевода.
        
        Args:
            text (str): Исходный текст
            
        Returns:
            str: Обработанный текст с правильно отмеченными покерными терминами
        """
        # Проверка и обработка аббревиатур в глоссарии
        for term, translation in self.POKER_GLOSSARY.items():
            # Ищем термин в начале слова или как отдельное слово
            pattern = r'\b' + re.escape(term) + r'\b'
            
            # Если термин уже встречается в тексте, заменяем его на версию с переводом при первом вхождении
            if re.search(pattern, text, re.IGNORECASE):
                # Найдем первое вхождение
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # Получим оригинальный текст (с учетом регистра)
                    original_match = match.group(0)
                    # Заменим только первое вхождение
                    text = text.replace(original_match, translation, 1)
        
        # Специальная обработка для последовательности аббревиатур SWASED ECD CEE и т.д.
        # Этот паттерн часто встречается в покерной литературе и нужна особая обработка
        special_swased_pattern = r'\bSWASED\s+ECD\s+CEE(?:\s+Eo)?(?:\s+ea)?(?:\s+Fn)?(?:\s+i)?(?:\s+Do)?(?:\s+CD)?\b'
        swased_match = re.search(special_swased_pattern, text)
        
        if swased_match:
            full_match = swased_match.group(0)
            logger.info(f"Found special SWASED sequence: {full_match}")
            
            # Создаем расширенное объяснение последовательности
            replacement = "SWASED (Система анализа покерных решений - Street, WTSD, Actualization, Sizing, EV, Downstream), "
            replacement += "ECD (Execution, Calculation, Decision - компоненты принятия решений в покере), "
            replacement += "CEE (Calculation, Execution, Evaluation - методика оценки игры)"
            
            # Добавляем остальные элементы, если они есть в исходной последовательности
            if "Eo" in full_match:
                replacement += ", Eo (Equity optimization - оптимизация эквити)"
            if "ea" in full_match:
                replacement += ", ea (equity awareness - осознание эквити)"
            if "Fn" in full_match:
                replacement += ", Fn (Function notation - функциональная нотация)"
            if "i" in full_match and " i " in full_match:  # Проверяем, что это отдельное слово
                replacement += ", i (iteration - итерация)"
            if "Do" in full_match:
                replacement += ", Do (Downstream optimization - оптимизация последующих действий)"
            if "CD" in full_match:
                replacement += ", CD (Calculation and Decision - расчеты и принятие решений)"
            
            # Заменяем весь блок аббревиатур на развернутое объяснение
            text = text.replace(full_match, replacement)
            logger.info(f"Replaced SWASED sequence with expanded explanation")
            
        # Обработка других последовательностей аббревиатур (для общего случая)
        abbr_pattern = r'\b([A-Z]{2,}(?:\s+[A-Z]{2,})+)\b'
        abbr_matches = list(re.finditer(abbr_pattern, text))
        
        for match in abbr_matches:
            # Проверяем, не обработали ли мы уже эту последовательность выше
            if swased_match and swased_match.start() <= match.start() <= swased_match.end():
                continue
                
            abbr_sequence = match.group(0)
            # Разделим последовательность на отдельные аббревиатуры
            abbrs = abbr_sequence.split()
            
            # Проверим, есть ли эти аббревиатуры в нашем глоссарии
            processed_abbrs = []
            for abbr in abbrs:
                if abbr in self.POKER_GLOSSARY:
                    processed_abbrs.append(self.POKER_GLOSSARY[abbr])
                else:
                    # Если нет в глоссарии, просто добавляем пометку
                    processed_abbrs.append(f"{abbr} (покерный термин)")
            
            # Заменим всю последовательность
            replacement = " ".join(processed_abbrs)
            text = text.replace(abbr_sequence, replacement)
            logger.info(f"Processed abbreviation sequence: {abbr_sequence}")
        
        return text
    
    def _build_translation_prompt(self, text, purpose):
        """
        Build a translation prompt based on purpose.
        
        Args:
            text (str): Text to translate
            purpose (str): Purpose of translation
            
        Returns:
            str: Prompt for the translation
        """
        if purpose == "translation":
            return f"""Переведите следующий текст на русский язык. 
            Сохраните структуру и форматирование оригинала.
            Покерные термины следует оставить на английском, 
            а затем дать их перевод в скобках при первом упоминании.
            Все числа, формулы и названия должны быть переведены корректно. 
            Сохраните все абзацы, списки и структуры переносов строк.
            
            Оригинал:
            {text}
            
            Перевод на русский:"""
            
        elif purpose == "figure_description":
            return f"""Переведите следующее описание диаграммы/таблицы/графика из книги по покеру на русский язык.
            Сохраните точность терминологии.
            Покерные термины следует оставить на английском, 
            а затем дать их перевод в скобках при первом упоминании.
            
            Оригинал:
            {text}
            
            Перевод на русский:"""
            
        elif purpose == "technical_content":
            return f"""Переведите следующий технический текст из книги по покеру на русский язык.
            Сохраните все формулы, числа и специальные обозначения в точном виде.
            Покерные термины и математические обозначения следует оставить на английском, 
            а затем дать их перевод в скобках при первом упоминании.
            
            Оригинал:
            {text}
            
            Перевод на русский:"""
            
        else:
            return f"""Переведите следующий текст на русский язык.
            
            Оригинал:
            {text}
            
            Перевод на русский:"""
    
    def _split_into_chunks(self, text, chunk_size=1800):
        """
        Split a long text into chunks of approximately equal size, trying to break at paragraph boundaries.
        
        Args:
            text (str): The text to split
            chunk_size (int): Approximate size of each chunk in characters
            
        Returns:
            list: List of text chunks
        """
        # If text is shorter than chunk_size, return it as is
        if len(text) <= chunk_size:
            return [text]
            
        chunks = []
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for paragraph in paragraphs:
            # If adding this paragraph exceeds chunk size and we already have content,
            # add current chunk to results and start a new one
            if len(current_chunk) + len(paragraph) > chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = paragraph + '\n\n'
            else:
                current_chunk += paragraph + '\n\n'
                
        # Add the last chunk if not empty
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
        
    def improve_extracted_text(self, text):
        """
        Improve OCR extracted text using OpenAI API.
        This function ensures text remains in the original language (English).
        
        Args:
            text (str): Raw OCR text
            
        Returns:
            str: Improved text in English
        """
        if not text or not text.strip():
            return ""
            
        if not self.openai_api_key:
            logger.warning("No OpenAI API key provided, returning original text")
            return text
            
        # Generate cache key
        cache_key = f"improve_en_{hash(text)}"
        
        # Check cache
        if cache_key in self.cache:
            logger.debug("Using cached improvement")
            return self.cache[cache_key]
        
        # Предотвращаем рекурсию - разделяем большие тексты вручную
        # If text is very long, just return it as is to avoid recursion errors
        if len(text) > 2000:
            logger.info(f"Text too long ({len(text)} chars), returning without OpenAI processing")
            return text
            
        try:
            logger.info("Improving OCR text with OpenAI API (keeping English language)")
            
            try:
                client = openai.OpenAI(api_key=self.openai_api_key)
            except TypeError:
                # Fallback для случаев когда proxies вызывает ошибку
                client = openai.OpenAI()
                client.api_key = self.openai_api_key
            
            prompt = f"""Fix OCR errors and improve the following English text from a poker book.
            IMPORTANT: This is ENGLISH text - do NOT translate to any other language.
            Maintain the original English language, fix spelling, and correct formatting.
            If sentences are incomplete or garbled, do your best to reconstruct them.
            Do not add new information or content not present in the original.
            ALWAYS KEEP THE TEXT IN ENGLISH - DO NOT TRANSLATE.
            
            Original OCR text:
            {text}
            
            Improved English text:"""
            
            # Try with new API
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
                    messages=[
                        {"role": "system", "content": "You are an expert at correcting OCR errors in English poker texts. Do not translate the text."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000,
                    temperature=0.1
                )
                improved_text = response.choices[0].message.content.strip()
                
            # If new API doesn't work, return original text
            except Exception as new_api_error:
                logger.error(f"Error with new API: {str(new_api_error)}. Cannot use old API.")
                logger.warning("OpenAI API error occurred. Returning original text.")
                return text
            
            # Cache the result
            self.cache[cache_key] = improved_text
            self._save_cache()
            
            return improved_text
            
        except Exception as e:
            logger.error(f"Error improving OCR text: {str(e)}")
            return text  # Return original text on error
    
    def _post_process_translation(self, translation):
        """
        Apply post-processing to the translation.
        
        Args:
            translation (str): Raw translation
            
        Returns:
            str: Processed translation
        """
        # Fix spacing after/before punctuation in Russian
        translation = re.sub(r'\s+([.,;:!?)])', r'\1', translation)
        translation = re.sub(r'([({[])(?=\S)', r'\1 ', translation)
        
        # Fix poker terms with translations
        # Look for patterns like "term (перевод)" and ensure they're formatted consistently
        term_patterns = re.finditer(r'([A-Za-z][A-Za-z0-9\s\-\_]+)\s*\(([^)]+)\)', translation)
        replacements = {}
        
        for match in term_patterns:
            english_term = match.group(1).strip()
            russian_trans = match.group(2).strip()
            
            # Format consistently
            replacements[match.group(0)] = f"{english_term} ({russian_trans})"
        
        # Apply replacements
        for old, new in replacements.items():
            translation = translation.replace(old, new)
        
        # Корректировка проблемных мест с аббревиатурами
        # Исправление случаев, когда аббревиатуры переведены некорректно
        for term, correct_form in self.POKER_GLOSSARY.items():
            # Ищем варианты неправильных переводов термина
            variations = [
                f"{term.lower()} ",  # аббревиатура в нижнем регистре
                f"{term.upper()} ",  # аббревиатура в верхнем регистре
                f"{term} ",          # аббревиатура как в глоссарии
            ]
            
            for var in variations:
                if var.strip() in translation and correct_form not in translation:
                    # Заменяем только если неправильная форма есть, а правильной нет
                    translation = translation.replace(var.strip(), correct_form)
        
        # Проверяем нетипичные аббревиатуры и последовательности заглавных букв (как SWASED ECD CEE)
        abbr_sequences = re.finditer(r'\b([A-Z]{2,}(?:\s+[A-Z]{2,})+)\b', translation)
        for match in abbr_sequences:
            abbr_sequence = match.group(0)
            # Проверяем, не заменили ли мы это раньше
            if "покерный термин" not in translation[match.start()-20:match.end()+20]:
                # Добавляем пояснение
                translation = translation.replace(
                    abbr_sequence, 
                    f"{abbr_sequence} (покерные термины и обозначения)"
                )
        
        # Убираем случайные символы, которые могли попасть в текст из-за OCR ошибок
        translation = re.sub(r'(\w)_(\w)', r'\1 \2', translation)  # Заменяем a_b на "a b"
        translation = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', translation)  # Убираем непечатные символы
        
        # Убираем повторы пробелов
        translation = re.sub(r' {2,}', ' ', translation)
        
        return translation
    
    def translate_document(self, document_structure):
        """
        Translate an entire document structure.
        
        Args:
            document_structure (dict): Document structure with text content
            
        Returns:
            dict: Translated document structure
        """
        translated_structure = {}
        
        # Translate title if present
        if 'title' in document_structure:
            translated_structure['title'] = self.translate_text(document_structure['title'])
        
        # Translate paragraphs
        if 'paragraphs' in document_structure:
            translated_structure['paragraphs'] = []
            for paragraph in document_structure['paragraphs']:
                translated_paragraph = self.translate_text(paragraph)
                translated_structure['paragraphs'].append(translated_paragraph)
        
        # Translate figures
        if 'figures' in document_structure:
            translated_structure['figures'] = []
            for figure in document_structure['figures']:
                figure_type = figure['type']
                description = figure['description']
                region = figure['region']
                
                translated_description = self.translate_text(description, purpose="figure_description")
                
                translated_figure = {
                    'type': figure_type,
                    'description': translated_description,
                    'region': region,
                    'image_path': figure.get('image_path', '')
                }
                
                translated_structure['figures'].append(translated_figure)
        
        # Translate tables
        if 'tables' in document_structure:
            translated_structure['tables'] = []
            for table in document_structure['tables']:
                table_data = table['data']
                
                # For simple tables, translate the whole thing
                if isinstance(table_data, str):
                    translated_data = self.translate_text(table_data, purpose="technical_content")
                else:
                    # For structured tables, translate each cell
                    translated_data = []
                    for row in table_data:
                        translated_row = []
                        for cell in row:
                            translated_cell = self.translate_text(cell, purpose="technical_content")
                            translated_row.append(translated_cell)
                        translated_data.append(translated_row)
                
                translated_table = {
                    'data': translated_data,
                    'image_path': table.get('image_path', '')
                }
                
                translated_structure['tables'].append(translated_table)
        
        return translated_structure
