#!/usr/bin/env python3
"""
Main module for processing poker books with OCR.
"""
from dotenv import load_dotenv
load_dotenv()  # Load variables from .env file

import os
import logging
import time
from datetime import datetime
import glob
import json
import cv2
from tqdm import tqdm

# Import custom modules
from image_preprocessor import ImagePreprocessor
from text_extractor import TextExtractor
from figure_analyzer import FigureAnalyzer
from translation_manager import TranslationManager
from pdf_generator import PDFGenerator
import utils

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PokerBookProcessor:
    """Main class for processing poker books with OCR and translation."""
    
    def __init__(self, output_dir='output', openai_api_key=None, target_language='ru'):
        """
        Initialize the poker book processor.
        
        Args:
            output_dir (str): Directory for saving results
            openai_api_key (str): OpenAI API key for OCR improvement and translation
            target_language (str): Target language for translation (default: ru)
        """
        self.output_dir = output_dir
        self.target_language = target_language
        self.openai_api_key = openai_api_key
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Create subdirectories
        self.text_dir = os.path.join(output_dir, 'text')
        self.images_dir = os.path.join(output_dir, 'images')
        self.tables_dir = os.path.join(output_dir, 'tables')
        self.diagrams_dir = os.path.join(output_dir, 'diagrams')
        self.translated_dir = os.path.join(output_dir, 'translated')
        self.pdf_dir = os.path.join(output_dir, 'pdf')
        self.cache_dir = os.path.join(output_dir, 'cache')
        
        for directory in [self.text_dir, self.images_dir, self.tables_dir, 
                          self.diagrams_dir, self.translated_dir, self.pdf_dir,
                          self.cache_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
        
        # Initialize components
        self.image_preprocessor = ImagePreprocessor()
        self.text_extractor = TextExtractor()
        self.figure_analyzer = FigureAnalyzer()
        self.translation_manager = TranslationManager(
            openai_api_key=openai_api_key,
            target_language=target_language,
            cache_dir=self.cache_dir
        )
        self.pdf_generator = PDFGenerator(output_dir=self.pdf_dir)
    
    def process_image(self, image_path):
        """
        Process a single image from a poker book.
        
        Args:
            image_path (str): Path to the image
            
        Returns:
            dict: Processed data including text and figures
        """
        logger.info(f"Processing image: {image_path}")
        
        try:
            # Generate base filename
            basename = os.path.splitext(os.path.basename(image_path))[0]
            timestamp = utils.create_timestamp()
            output_basename = f"{basename}_{timestamp}"
            
            # Preprocess image
            original_img, processed_img = self.image_preprocessor.preprocess_image(image_path)
            
            # Save preprocessed image for debugging
            debug_image_path = os.path.join(self.images_dir, f"{output_basename}_preprocessed.png")
            cv2.imwrite(debug_image_path, processed_img)
            
            # Detect text regions
            text_regions = self.image_preprocessor.detect_text_regions(processed_img)
            
            # Extract text from the entire image
            full_text = self.text_extractor.extract_text(processed_img)
            
            # Save raw OCR text
            raw_text_path = os.path.join(self.text_dir, f"{output_basename}_raw.txt")
            with open(raw_text_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            
            # Improve OCR result with OpenAI if available
            if self.openai_api_key:
                enhanced_text = self.translation_manager.translate_text(full_text, purpose="ocr_correction")
                corrected_text_path = os.path.join(self.text_dir, f"{output_basename}_corrected.txt")
                with open(corrected_text_path, 'w', encoding='utf-8') as f:
                    f.write(enhanced_text)
            else:
                enhanced_text = full_text
                
            # Detect figures and diagrams
            figures = self.figure_analyzer.detect_figures(processed_img, original_img)
            
            # Process detected figures
            processed_figures = []
            for idx, figure_data in enumerate(figures):
                figure_type, region, description = figure_data
                
                # Save figure
                figure_dir = self.diagrams_dir if figure_type in ['chart', 'diagram'] else self.tables_dir
                figure_path = self.figure_analyzer.save_figure(
                    original_img, figure_data, figure_dir, output_basename
                )
                
                if figure_path:
                    processed_figures.append({
                        'type': figure_type,
                        'region': region,
                        'description': description,
                        'image_path': figure_path
                    })
            
            # Create document structure
            document_structure = {
                'page_number': utils.extract_page_number(image_path),
                'original_image': image_path,
                'processed_image': debug_image_path,
                'paragraphs': enhanced_text.split('\n\n'),
                'figures': processed_figures
            }
            
            # Save document structure
            structure_path = os.path.join(self.text_dir, f"{output_basename}_structure.json")
            utils.save_to_json(document_structure, structure_path)
            
            # Translate content
            if self.target_language != 'en':
                translated_structure = self.translation_manager.translate_document(document_structure)
                
                # Save translated structure
                translated_path = os.path.join(self.translated_dir, f"{output_basename}_translated.json")
                utils.save_to_json(translated_structure, translated_path)
                
                document_structure['translated'] = translated_structure
            
            return document_structure
            
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {str(e)}")
            return None
    
    def batch_process(self, image_paths, book_title="Quantum Poker"):
        """
        Process a batch of images from a poker book.
        
        Args:
            image_paths (list): List of paths to images
            book_title (str): Title of the book
            
        Returns:
            dict: Processing results
        """
        if not image_paths:
            logger.error("No images provided for processing")
            return None
            
        # Sort images by page number
        sorted_images = utils.sort_files_by_page(image_paths)
        
        logger.info(f"Starting batch processing of {len(sorted_images)} images")
        
        # Process each image
        processed_documents = []
        failed_images = []
        
        for image_path in tqdm(sorted_images, desc="Processing images"):
            try:
                # Skip if not a valid image
                if not utils.is_valid_image(image_path):
                    logger.warning(f"Skipping invalid image: {image_path}")
                    continue
                    
                # Process the image
                document = self.process_image(image_path)
                
                if document:
                    processed_documents.append(document)
                else:
                    failed_images.append(image_path)
                    
            except Exception as e:
                logger.error(f"Error processing {image_path}: {str(e)}")
                failed_images.append(image_path)
        
        # Create book structure
        book_structure = {
            'title': book_title,
            'pages': processed_documents,
            'language': 'en'
        }
        
        # Create translated book structure if needed
        if self.target_language != 'en' and processed_documents:
            translated_pages = []
            
            for document in processed_documents:
                if 'translated' in document:
                    translated_pages.append(document['translated'])
            
            translated_book = {
                'title': self.translation_manager.translate_text(book_title),
                'pages': translated_pages,
                'language': self.target_language
            }
        else:
            translated_book = None
        
        # Generate PDFs
        try:
            # Generate English PDF
            english_pdf = self.generate_pdf(book_structure, 'en')
            
            # Generate translated PDF if available
            translated_pdf = None
            if translated_book:
                translated_pdf = self.generate_pdf(translated_book, self.target_language)
            
            # Prepare result summary
            result = {
                'processed_images': len(processed_documents),
                'total_images': len(sorted_images),
                'failed_images': failed_images,
                'english_pdf': english_pdf,
                'translated_pdf': translated_pdf,
                'book_structure': os.path.join(self.text_dir, f"{book_title.replace(' ', '_')}_structure.json")
            }
            
            # Save book structure
            utils.save_to_json(book_structure, result['book_structure'])
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating PDFs: {str(e)}")
            return None
    
    def generate_pdf(self, book_structure, language):
        """
        Generate a PDF from the book structure.
        
        Args:
            book_structure (dict): Book structure
            language (str): Language code
            
        Returns:
            str: Path to the generated PDF
        """
        # Prepare content for PDF
        content = {
            'title': book_structure.get('title', 'Poker Book'),
            'paragraphs': [],
            'figures': [],
            'tables': []
        }
        
        # Collect content from all pages
        for page in book_structure.get('pages', []):
            # Add paragraphs
            if 'paragraphs' in page:
                content['paragraphs'].extend(page['paragraphs'])
            
            # Add figures
            if 'figures' in page:
                content['figures'].extend(page['figures'])
                
        # Generate PDF
        pdf_path = self.pdf_generator.generate_pdf(
            content, 
            language, 
            book_structure.get('title', 'Poker Book')
        )
        
        return pdf_path
