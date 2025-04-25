import os
import sys
import logging
import traceback
import cv2
import numpy as np
from datetime import datetime
from app import db
from models import Book, BookPage, ProcessingJob, Figure

# Import processor modules
from image_preprocessor import ImagePreprocessor
from text_extractor import TextExtractor
from figure_analyzer import FigureAnalyzer
from translation_manager import TranslationManager
from pdf_generator import PDFGenerator
from poker_book_processor import PokerBookProcessor
import utils
import fitz  # PyMuPDF

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def process_book(book_id, job_id, is_pdf=False):
    """
    Process a book's pages with OCR
    
    This function runs in a separate thread and updates the database with results
    
    Args:
        book_id: ID of the book to process
        job_id: ID of the processing job
        is_pdf: Whether the upload is a PDF file (True) or images (False)
    """
    logger.info(f"Starting processing for book ID: {book_id}, job ID: {job_id}, PDF: {is_pdf}")
    
    # Import app at function level to avoid circular imports
    from app import app
    
    # Create application context for the thread
    with app.app_context():
        try:
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
            
            # Handle differently based on file type (PDF or images)
            processed_documents = []
            
            if is_pdf:
                # We have a PDF file to process
                processed_documents = process_pdf_file(book, output_dir, images_dir, text_dir, 
                                                     diagrams_dir, tables_dir, translated_dir,
                                                     translation_manager, openai_api_key)
            else:
                # We have individual image files
                pages = BookPage.query.filter_by(book_id=book.id).order_by(BookPage.page_number).all()
                
                if not pages:
                    raise ValueError("No pages found for this book")
                
                # Process each page
                for page in pages:
                    try:
                        # Update page status
                        page.status = 'processing'
                        db.session.commit()
                        
                        # Check if image file exists
                        if not os.path.exists(page.image_path):
                            logger.error(f"Image file not found: {page.image_path}")
                            page.status = 'error'
                            db.session.commit()
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
                            'paragraphs': enhanced_text.split('\n\n') if enhanced_text else [],
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
            
            # Update job status if it exists
            try:
                job = ProcessingJob.query.get(job_id)
                if job:
                    job.status = 'failed'
                    job.error_message = str(e)
                    job.completed_at = datetime.utcnow()
                
                # Update book status if it exists
                book = Book.query.get(book_id)
                if book:
                    book.status = 'error'
                
                db.session.commit()
            except Exception as inner_e:
                logger.error(f"Failed to update error status: {str(inner_e)}")
                traceback.print_exc()


def process_pdf_file(book, output_dir, images_dir, text_dir, diagrams_dir, tables_dir, 
                 translated_dir, translation_manager, openai_api_key):
    """
    Process PDF file and extract text, images, and figures
    
    Args:
        book: Book model instance
        output_dir: Main output directory
        images_dir: Directory for extracted images
        text_dir: Directory for extracted text
        diagrams_dir: Directory for extracted diagrams
        tables_dir: Directory for extracted tables
        translated_dir: Directory for translated content
        translation_manager: TranslationManager instance
        openai_api_key: OpenAI API key
        
    Returns:
        list: List of processed document structures
    """
    # Initialize components for processing
    image_preprocessor = ImagePreprocessor()
    text_extractor = TextExtractor()
    figure_analyzer = FigureAnalyzer()
    
    # Get the first page which contains the PDF path
    page = BookPage.query.filter_by(book_id=book.id).first()
    if not page or not os.path.exists(page.image_path):
        raise ValueError(f"PDF file not found at {page.image_path}")
    
    # Update page status
    page.status = 'processing'
    db.session.commit()
    
    processed_documents = []
    timestamp = utils.create_timestamp()
    
    try:
        # Open PDF with PyMuPDF
        pdf_document = fitz.open(page.image_path)
        page_count = len(pdf_document)
        logger.info(f"Processing PDF with {page_count} pages")
        
        # Create new BookPage records for each page in the PDF
        for page_idx in range(page_count):
            if page_idx == 0:
                # First page already exists in the database
                pdf_page = page
                pdf_page.page_number = page_idx + 1
            else:
                # Create a new page record for additional pages
                pdf_page = BookPage(
                    book_id=book.id,
                    page_number=page_idx + 1,
                    image_path=page.image_path,  # Reference to the same PDF
                    status='pending'
                )
                db.session.add(pdf_page)
        db.session.commit()
        
        # Process each page in the PDF
        for page_idx in range(page_count):
            current_page = pdf_document[page_idx]
            
            # Get the database record for this page
            if page_idx == 0:
                db_page = page
            else:
                db_page = BookPage.query.filter_by(book_id=book.id, page_number=page_idx+1).first()
                if not db_page:
                    logger.error(f"Database record not found for page {page_idx+1}")
                    continue
            
            # Update page status
            db_page.status = 'processing'
            db.session.commit()
            
            # Generate output basename
            output_basename = f"book_{book.id}_page_{page_idx+1}_{timestamp}"
            
            try:
                # Extract page as an image
                pix = current_page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
                img_path = os.path.join(images_dir, f"{output_basename}.png")
                pix.save(img_path)
                
                # Convert to OpenCV format
                with open(img_path, 'rb') as img_file:
                    img_data = np.frombuffer(img_file.read(), np.uint8)
                original_img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
                
                # Preprocess image
                _, processed_img = image_preprocessor.preprocess_image(img_path)
                
                # Save preprocessed image
                debug_image_path = os.path.join(images_dir, f"{output_basename}_preprocessed.png")
                cv2_write_result = cv2.imwrite(debug_image_path, processed_img)
                if not cv2_write_result:
                    logger.warning(f"Failed to save preprocessed image to {debug_image_path}")
                
                # Set processed image path in database
                db_page.processed_image_path = debug_image_path
                
                # Extract text from the page (using both PyMuPDF and OCR)
                # First try native PDF text extraction
                pdf_text = current_page.get_text()
                # Then try OCR
                ocr_text = text_extractor.extract_text(processed_img)
                
                # Use the one with more content
                full_text = pdf_text if len(pdf_text) > len(ocr_text) else ocr_text
                
                # Save raw text
                raw_text_path = os.path.join(text_dir, f"{output_basename}_raw.txt")
                with open(raw_text_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                
                # Improve text with OpenAI if available
                if openai_api_key:
                    enhanced_text = translation_manager.translate_text(full_text, purpose="ocr_correction")
                    corrected_text_path = os.path.join(text_dir, f"{output_basename}_corrected.txt")
                    with open(corrected_text_path, 'w', encoding='utf-8') as f:
                        f.write(enhanced_text)
                else:
                    enhanced_text = full_text
                
                # Save text content to database
                db_page.text_content = enhanced_text
                
                # Detect figures and diagrams
                figures = figure_analyzer.detect_figures(processed_img, original_img)
                
                # Process detected figures
                processed_figures = []
                for fig_idx, figure_data in enumerate(figures):
                    figure_type, region, description = figure_data
                    
                    # Save figure
                    figure_dir = diagrams_dir if figure_type in ['chart', 'diagram'] else tables_dir
                    figure_path = figure_analyzer.save_figure(
                        original_img, figure_data, figure_dir, output_basename
                    )
                    
                    if figure_path:
                        # Create figure record in database
                        db_figure = Figure(
                            page_id=db_page.id,
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
                    'page_number': db_page.page_number,
                    'original_image': img_path,
                    'processed_image': debug_image_path,
                    'paragraphs': enhanced_text.split('\n\n') if enhanced_text else [],
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
                    db_page.translated_content = '\n\n'.join(
                        translated_structure.get('paragraphs', []))
                    
                    document_structure['translated'] = translated_structure
                
                processed_documents.append(document_structure)
                
                # Update page status
                db_page.status = 'processed'
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error processing PDF page {page_idx}: {str(e)}")
                traceback.print_exc()
                db_page.status = 'error'
                db.session.commit()
        
        # Close the PDF document
        pdf_document.close()
        
    except Exception as e:
        logger.error(f"Error processing PDF file: {str(e)}")
        traceback.print_exc()
        page.status = 'error'
        db.session.commit()
        raise e
    
    return processed_documents


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
                if figure.get('type') in ['chart', 'diagram']:
                    content['figures'].append(figure)
                elif figure.get('type') == 'table':
                    content['tables'].append(figure)
    
    # Generate PDF
    pdf_path = pdf_generator.generate_pdf(
        content, 
        language, 
        book_structure.get('title', 'Poker Book')
    )
    
    return pdf_path