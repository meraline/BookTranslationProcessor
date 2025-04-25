import os
import sys
import logging
import traceback
import cv2
from datetime import datetime
from app import db
from models import Book, BookPage, ProcessingJob, Figure

# Import processor modules
from image_preprocessor import ImagePreprocessor
from text_extractor import TextExtractor
from figure_analyzer import FigureAnalyzer
from translation_manager import TranslationManager
from pdf_generator import PDFGenerator
import utils

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def process_book(book_id, job_id):
    """
    Process a book's pages with OCR
    
    This function runs in a separate thread and updates the database with results
    """
    logger.info(f"Starting processing for book ID: {book_id}, job ID: {job_id}")
    
    # Get book and job from database
    book = Book.query.get(book_id)
    job = ProcessingJob.query.get(job_id)
    
    if not book or not job:
        logger.error(f"Book or job not found. Book ID: {book_id}, Job ID: {job_id}")
        return
    
    # Update job and book status
    job.status = 'processing'
    book.status = 'processing'
    db.session.commit()
    
    try:
        # Create output directories
        output_dir = os.path.join('output', f"book_{book.id}")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Create subdirectories
        text_dir = os.path.join(output_dir, 'text')
        images_dir = os.path.join(output_dir, 'images')
        tables_dir = os.path.join(output_dir, 'tables')
        diagrams_dir = os.path.join(output_dir, 'diagrams')
        translated_dir = os.path.join(output_dir, 'translated')
        pdf_dir = os.path.join(output_dir, 'pdf')
        cache_dir = os.path.join(output_dir, 'cache')
        
        for directory in [text_dir, images_dir, tables_dir, diagrams_dir, 
                         translated_dir, pdf_dir, cache_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                
        # Initialize components
        image_preprocessor = ImagePreprocessor()
        text_extractor = TextExtractor()
        figure_analyzer = FigureAnalyzer()
        
        # Get OpenAI API key from environment
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        if not openai_api_key:
            logger.warning("OpenAI API key not found. Processing will continue without OpenAI enhancements.")
        
        translation_manager = TranslationManager(
            openai_api_key=openai_api_key,
            target_language='ru',
            cache_dir=cache_dir
        )
        
        pdf_generator = PDFGenerator(output_dir=pdf_dir)
        
        # Get pages for this book
        pages = BookPage.query.filter_by(book_id=book.id).order_by(BookPage.page_number).all()
        
        if not pages:
            raise ValueError("No pages found for this book")
        
        # Process each page
        processed_documents = []
        for page in pages:
            try:
                # Update page status
                page.status = 'processing'
                db.session.commit()
                
                # Check if image file exists
                if not os.path.exists(page.image_path):
                    logger.error(f"Image file not found: {page.image_path}")
                    page.status = 'error'
                    continue
                
                # Generate base filename
                basename = os.path.splitext(os.path.basename(page.image_path))[0]
                timestamp = utils.create_timestamp()
                output_basename = f"{basename}_{timestamp}"
                
                # Preprocess image
                original_img, processed_img = image_preprocessor.preprocess_image(page.image_path)
                
                # Save preprocessed image
                debug_image_path = os.path.join(images_dir, f"{output_basename}_preprocessed.png")
                cv2_write_result = cv2.imwrite(debug_image_path, processed_img)
                if not cv2_write_result:
                    logger.warning(f"Failed to save preprocessed image to {debug_image_path}")
                
                # Set processed image path in database
                page.processed_image_path = debug_image_path
                
                # Extract text from the entire image
                full_text = text_extractor.extract_text(processed_img)
                
                # Save raw OCR text
                raw_text_path = os.path.join(text_dir, f"{output_basename}_raw.txt")
                with open(raw_text_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                
                # Improve OCR result with OpenAI if available
                if openai_api_key:
                    enhanced_text = translation_manager.translate_text(full_text, purpose="ocr_correction")
                    corrected_text_path = os.path.join(text_dir, f"{output_basename}_corrected.txt")
                    with open(corrected_text_path, 'w', encoding='utf-8') as f:
                        f.write(enhanced_text)
                else:
                    enhanced_text = full_text
                
                # Save text content to database
                page.text_content = enhanced_text
                
                # Detect figures and diagrams
                figures = figure_analyzer.detect_figures(processed_img, original_img)
                
                # Process detected figures
                processed_figures = []
                for idx, figure_data in enumerate(figures):
                    figure_type, region, description = figure_data
                    
                    # Save figure
                    figure_dir = diagrams_dir if figure_type in ['chart', 'diagram'] else tables_dir
                    figure_path = figure_analyzer.save_figure(
                        original_img, figure_data, figure_dir, output_basename
                    )
                    
                    if figure_path:
                        # Create figure record in database
                        db_figure = Figure(
                            page_id=page.id,
                            figure_type=figure_type,
                            image_path=figure_path,
                            description=description,
                            region=str(region)
                        )
                        db.session.add(db_figure)
                        
                        # If translation is available, translate description
                        if openai_api_key:
                            translated_desc = translation_manager.translate_text(
                                description, purpose="figure_description")
                            db_figure.translated_description = translated_desc
                        
                        processed_figures.append({
                            'type': figure_type,
                            'region': region,
                            'description': description,
                            'image_path': figure_path
                        })
                
                # Create document structure
                document_structure = {
                    'page_number': page.page_number,
                    'original_image': page.image_path,
                    'processed_image': debug_image_path,
                    'paragraphs': enhanced_text.split('\n\n'),
                    'figures': processed_figures
                }
                
                # Save document structure
                structure_path = os.path.join(text_dir, f"{output_basename}_structure.json")
                utils.save_to_json(document_structure, structure_path)
                
                # Translate content if OpenAI API key is available
                if openai_api_key:
                    translated_structure = translation_manager.translate_document(document_structure)
                    
                    # Save translated structure
                    translated_path = os.path.join(translated_dir, f"{output_basename}_translated.json")
                    utils.save_to_json(translated_structure, translated_path)
                    
                    # Save translated content to database
                    page.translated_content = '\n\n'.join(
                        translated_structure.get('paragraphs', []))
                    
                    document_structure['translated'] = translated_structure
                
                processed_documents.append(document_structure)
                
                # Update page status
                page.status = 'processed'
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error processing page {page.id}: {str(e)}")
                traceback.print_exc()
                page.status = 'error'
                db.session.commit()
        
        # Create book structure for PDF generation
        book_structure = {
            'title': book.title,
            'pages': processed_documents,
            'language': 'en'
        }
        
        # Save book structure
        book_structure_path = os.path.join(text_dir, f"{book.title.replace(' ', '_')}_structure.json")
        utils.save_to_json(book_structure, book_structure_path)
        
        # Generate PDFs
        english_pdf = None
        russian_pdf = None
        
        # Generate English PDF
        try:
            english_pdf = generate_pdf(pdf_generator, book_structure, 'en')
            job.result_file_en = english_pdf
        except Exception as e:
            logger.error(f"Error generating English PDF: {str(e)}")
            traceback.print_exc()
        
        # Generate Russian PDF if translations available
        if openai_api_key:
            try:
                # Create translated book structure
                translated_pages = []
                for document in processed_documents:
                    if 'translated' in document:
                        translated_pages.append(document['translated'])
                
                translated_book = {
                    'title': translation_manager.translate_text(book.title),
                    'pages': translated_pages,
                    'language': 'ru'
                }
                
                russian_pdf = generate_pdf(pdf_generator, translated_book, 'ru')
                job.result_file_ru = russian_pdf
            except Exception as e:
                logger.error(f"Error generating Russian PDF: {str(e)}")
                traceback.print_exc()
        
        # Update job status
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        
        # Update book status
        book.status = 'completed'
        
        db.session.commit()
        
        logger.info(f"Processing completed for book ID: {book_id}")
        
    except Exception as e:
        logger.error(f"Processing failed for book ID: {book_id}: {str(e)}")
        traceback.print_exc()
        
        # Update job status
        job.status = 'failed'
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        
        # Update book status
        book.status = 'error'
        
        db.session.commit()

def generate_pdf(pdf_generator, book_structure, language):
    """
    Generate a PDF from book structure
    
    Args:
        pdf_generator: PDFGenerator instance
        book_structure: Book content structure
        language: Language code (en/ru)
        
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
            for figure in page['figures']:
                if figure['type'] in ('chart', 'diagram'):
                    content['figures'].append(figure)
                elif figure['type'] == 'table':
                    content['tables'].append({
                        'data': figure['description'],
                        'image_path': figure['image_path']
                    })
    
    # Generate PDF
    pdf_path = pdf_generator.generate_pdf(
        content, 
        language, 
        book_structure.get('title', 'Poker Book')
    )
    
    return pdf_path