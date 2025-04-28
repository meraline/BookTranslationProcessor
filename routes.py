import os
import json
import logging
import threading
from flask import render_template, request, redirect, url_for, flash, send_file, jsonify, session
from werkzeug.utils import secure_filename
from app import app, db
from models import Book, BookPage, ProcessingJob, Figure, FileHash
from datetime import datetime
from processing_service import process_book

# Add context processor to provide current date/time to all templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# Setup logging
logger = logging.getLogger(__name__)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    """Main application page"""
    # Get books from database
    books = Book.query.order_by(Book.created_at.desc()).all()
    
    # Get jobs for each book
    book_jobs = {}
    for book in books:
        # Get the latest job for each book
        job = ProcessingJob.query.filter_by(book_id=book.id).order_by(ProcessingJob.created_at.desc()).first()
        if job:
            book_jobs[book.id] = job
    
    return render_template('index.html', books=books, book_jobs=book_jobs)

@app.route('/upload', methods=['GET', 'POST'])
def upload_book():
    """Handle book file upload (images or PDF)"""
    if request.method == 'POST':
        # Check if this is a chunked upload via AJAX
        is_chunked = request.form.get('chunk_upload', 'false') == 'true'
        
        # For regular POST uploads
        if not is_chunked:
            # Check if book title is provided
            book_title = request.form.get('book_title', 'Untitled Book')
            description = request.form.get('description', '')
            file_type = request.form.get('file_type', 'images')
            translate_to_russian = request.form.get('translate_to_russian') == 'yes'
            
            # Create new book record
            new_book = Book(title=book_title, description=description)
            db.session.add(new_book)
            db.session.commit()
            
            uploaded_count = 0
            is_pdf = False
            
            # Обработка в зависимости от типа файла (изображения или PDF)
            if file_type == 'images':
                # Обработка загруженных изображений
                if 'book_images' not in request.files:
                    flash('Файлы не выбраны', 'error')
                    return redirect(request.url)
            
                files = request.files.getlist('book_images')
            
                # Check if at least one file is selected
                if len(files) == 0 or files[0].filename == '':
                    flash('Не выбрано ни одного файла', 'error')
                    return redirect(request.url)
            
            # Import necessary modules for duplicate detection
            from text_extractor import TextExtractor
            from utils import is_text_duplicate, compute_image_hash
            
            # Collect existing page texts from the database for this book
            existing_texts = []
            
            # Keep track of skipped duplicates
            duplicate_count = 0
            
            # Process each file
            for idx, file in enumerate(files):
                if file and allowed_file(file.filename):
                    # Secure filename and save file to a temporary location for checking
                    temp_filename = secure_filename(file.filename)
                    temp_filepath = os.path.join('/tmp', temp_filename)
                    file.save(temp_filepath)
                    
                    # Сначала проверяем дубликаты по хешу файла, что быстрее и надежнее
                    try:
                        app.logger.info(f"Проверка дубликатов для файла: {temp_filename}")
                        # Временно отключаем проверку дубликатов, чтобы решить проблему с загрузкой
                        is_duplicate = False
                        similarity = 0.0
                        duplicate_file = None
                        file_hash = compute_image_hash(temp_filepath)
                        
                        # Логируем хеш для отладки
                        if file_hash:
                            app.logger.info(f"Вычислен хеш файла: {file_hash[:10]}...")
                        else:
                            app.logger.info("Не удалось вычислить хеш файла")
                        
                        # Проверяем, есть ли уже такой хеш в базе данных
                        try:
                            if file_hash:
                                # Ищем хеш в базе данных
                                existing_file_hash = FileHash.query.filter_by(file_hash=file_hash).first()
                                
                                if existing_file_hash and False:  # Временно отключаем, чтобы все файлы добавлялись
                                    is_duplicate = True
                                    similarity = 1.0
                                    duplicate_file = existing_file_hash
                                    app.logger.info(f"Обнаружен дубликат по хешу файла: {temp_filename}")
                                    app.logger.info(f"Оригинальный файл: {existing_file_hash.original_filename}")
                                else:
                                    app.logger.info(f"Уникальный файл, добавляем: {temp_filename}")
                            
                        except Exception as e:
                            app.logger.error(f"Ошибка при проверке хеша в БД: {str(e)}")
                            is_duplicate = False
                            similarity = 0.0
                        
                        # Если не нашли дубликат по хешу, пробуем через OCR
                        if not is_duplicate:
                            try:
                                # Временно отключаем OCR для избежания ошибок с pytesseract
                                app.logger.info(f"Пропускаем OCR для файла: {temp_filename}")
                                page_text = ""  # Пустой текст вместо OCR
                                
                                # Отключаем проверку дубликатов по тексту
                                is_duplicate = False
                                similar_text = None
                                similarity = 0.0
                                
                                # Закомментировано для отладки
                                # # Check if this image is a duplicate based on text content
                                # is_duplicate, similar_text, similarity = is_text_duplicate(
                                #     page_text, existing_texts, threshold=0.80  # 80% similarity threshold
                                # )
                                
                                # Если это новый файл, сохраняем его хеш в БД для будущих проверок
                                if not is_duplicate and file_hash:
                                    try:
                                        # Проверяем, нет ли уже такого хеша
                                        existing_hash = FileHash.query.filter_by(file_hash=file_hash).first()
                                        
                                        if not existing_hash:
                                            # Сохраняем новый хеш в БД с отложенным связыванием c book_id и page_id
                                            # Они будут связаны после успешного создания страницы
                                            new_file_hash = FileHash(
                                                file_hash=file_hash,
                                                original_filename=temp_filename,
                                                content_type='image'
                                            )
                                            db.session.add(new_file_hash)
                                            # Откладываем commit до создания страницы
                                            # db.session.commit()
                                            app.logger.info(f"Добавлен новый хеш в базу для файла: {temp_filename}")
                                    except Exception as e:
                                        app.logger.error(f"Ошибка при сохранении хеша в БД: {str(e)}")
                                    
                            except Exception as e:
                                app.logger.error(f"Ошибка при проверке текстовых дубликатов: {str(e)}")
                                page_text = ""
                                is_duplicate = False
                                similarity = 0.0
                        else:
                            # Если дубликат найден по хешу, OCR не нужен
                            page_text = ""
                                
                    except Exception as e:
                        app.logger.error(f"Ошибка при проверке дубликатов по хешу: {str(e)}")
                        page_text = ""
                        is_duplicate = False
                        similarity = 0.0
                        
                        # Отключаем запасной вариант через OCR из-за проблем с tesseract
                        try:
                            app.logger.info(f"Пропускаем запасной вариант OCR для файла: {temp_filename}")
                            page_text = ""
                            is_duplicate = False  # Принудительно считаем уникальным
                            similar_text = None
                            similarity = 0.0
                        except Exception as e2:
                            app.logger.error(f"Ошибка при обработке файла: {str(e2)}")
                            # Оставляем значения по умолчанию
                    
                    if is_duplicate:
                        # This is a duplicate, skip it
                        app.logger.info(f"Skipping duplicate image: {temp_filename} (similarity: {similarity:.2f})")
                        duplicate_count += 1
                        # Clean up temp file
                        os.remove(temp_filepath)
                        continue
                    
                    # Not a duplicate, save permanently
                    filename = f"{new_book.id}_{idx}_{secure_filename(file.filename)}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    # Проверяем директорию uploads и создаем, если она отсутствует
                    uploads_folder = app.config['UPLOAD_FOLDER']
                    if not os.path.exists(uploads_folder):
                        os.makedirs(uploads_folder, exist_ok=True)
                        app.logger.info(f"Создана директория для загрузок: {uploads_folder}")
                    
                    # Улучшенная обработка копирования файла с проверками
                    try:
                        import shutil
                        # Обеспечиваем безопасное имя файла и не слишком длинный путь
                        safe_filename = secure_filename(file.filename)
                        if len(safe_filename) > 50:  # Ограничиваем длину имени файла
                            extension = safe_filename.rsplit('.', 1)[1] if '.' in safe_filename else ''
                            safe_filename = safe_filename[:40] + '.' + extension if extension else safe_filename[:50]
                        
                        # Формируем окончательный путь к файлу
                        filename = f"{new_book.id}_{idx}_{safe_filename}"
                        file_path = os.path.join(uploads_folder, filename)
                        
                        # Копируем файл
                        shutil.copy2(temp_filepath, file_path)
                        app.logger.info(f"Файл успешно скопирован в {file_path}")
                        
                        # Проверяем, что файл действительно был скопирован
                        if not os.path.exists(file_path):
                            app.logger.error(f"Файл не был скопирован в {file_path}")
                            raise Exception("Не удалось скопировать файл")
                            
                        # Проверяем права доступа и устанавливаем их, если необходимо
                        try:
                            os.chmod(file_path, 0o644)  # rw-r--r--
                        except Exception as chmod_error:
                            app.logger.warning(f"Не удалось изменить права доступа: {str(chmod_error)}")
                            
                        # Удаляем временный файл
                        os.remove(temp_filepath)
                        app.logger.info(f"Временный файл удален: {temp_filepath}")
                    except Exception as copy_error:
                        app.logger.error(f"Ошибка при копировании файла: {str(copy_error)}")
                        # Если возникла ошибка при копировании, пробуем другой метод
                        try:
                            with open(temp_filepath, 'rb') as src_file:
                                file_content = src_file.read()
                                
                            with open(file_path, 'wb') as dst_file:
                                dst_file.write(file_content)
                                
                            app.logger.info(f"Файл успешно скопирован альтернативным методом в {file_path}")
                            
                            # Удаляем временный файл
                            os.remove(temp_filepath)
                        except Exception as alt_copy_error:
                            app.logger.error(f"Альтернативный метод копирования также не сработал: {str(alt_copy_error)}")
                            # В случае ошибки продолжаем выполнение, но файл может быть не сохранен
                    
                    # Add to existing texts to check future pages against
                    if page_text:
                        existing_texts.append(page_text)
                    
                    # Try to extract page number from filename
                    page_number = idx + 1  # Default to the order of upload
                    
                    # Create book page record
                    new_page = BookPage(
                        book_id=new_book.id,
                        page_number=page_number,
                        image_path=file_path,
                        status='pending',
                        text_content=page_text  # Store extracted text for future reference
                    )
                    db.session.add(new_page)
                    uploaded_count += 1
            
            # Save all pages
            db.session.commit()
            
            if uploaded_count > 0:
                if duplicate_count > 0:
                    flash_message = f'Загружено {uploaded_count} изображений, пропущено {duplicate_count} дубликатов, начата обработка'
                else:
                    flash_message = f'Загружено {uploaded_count} изображений, начата обработка'
            else:
                flash('Не загружено ни одного подходящего файла', 'error')
                return redirect(request.url)
                
        elif file_type == 'pdf':
            # Обработка загруженного PDF-файла
            if 'book_pdf' not in request.files:
                flash('PDF файл не выбран', 'error')
                return redirect(request.url)
                
            pdf_file = request.files['book_pdf']
            
            if pdf_file.filename == '':
                flash('PDF файл не выбран', 'error')
                return redirect(request.url)
                
            if pdf_file and allowed_file(pdf_file.filename):
                # Временно проинициализируем переменную перед использованием
                pdf_hash = None
                import hashlib
                
                try:
                    import fitz  # PyMuPDF для проверки PDF
                except ImportError:
                    app.logger.error("Ошибка импорта PyMuPDF (fitz). Возможно, библиотека не установлена.")
                    # Продолжаем без проверки дубликатов для PDF
                
                # Сначала сохраняем PDF во временный файл для проверки
                temp_filename = secure_filename(pdf_file.filename)
                temp_filepath = os.path.join('/tmp', temp_filename)
                pdf_file.save(temp_filepath)
                app.logger.info(f"PDF файл временно сохранен в {temp_filepath}")
                
                # Проверяем директорию uploads и создаем, если она отсутствует
                uploads_folder = app.config['UPLOAD_FOLDER']
                if not os.path.exists(uploads_folder):
                    os.makedirs(uploads_folder, exist_ok=True)
                    app.logger.info(f"Создана директория для загрузок PDF: {uploads_folder}")
                
                # Временно отключаем проверку дубликатов для PDF
                pdf_is_duplicate = False
                duplicate_book = None
                
                try:
                    # Временно отключаем извлечение текста из PDF из-за возможных проблем с fitz
                    app.logger.info(f"Обработка PDF без извлечения текста: {temp_filename}")
                    
                    # Вычисляем хеш на основе имени файла и размера для быстрой проверки
                    file_size = os.path.getsize(temp_filepath)
                    pdf_hash = hashlib.md5(f"{temp_filename}_{file_size}".encode('utf-8')).hexdigest()
                    app.logger.info(f"Вычислен упрощенный хеш PDF: {pdf_hash[:10]}...")
                    
                    # Сначала проверяем хеш в таблице FileHash
                    existing_file_hash = FileHash.query.filter_by(file_hash=pdf_hash).first()
                    if existing_file_hash and existing_file_hash.book_id:
                        # Нашли дубликат по хешу в БД
                        pdf_is_duplicate = True
                        duplicate_book = Book.query.get(existing_file_hash.book_id)
                        if duplicate_book:
                            app.logger.info(f"Найден дубликат PDF по хешу в базе данных: {duplicate_book.title}")
                    else:
                        # Ищем похожие PDF-книги в базе данных (запасной вариант)
                        existing_books = Book.query.all()
                        for book in existing_books:
                            # Проверяем только для книг, у которых есть PDF-страницы
                            if book.pages and book.pages[0].image_path and book.pages[0].image_path.lower().endswith('.pdf'):
                                # Упрощаем проверку существующих PDF без доступа к содержимому
                                try:
                                    # Получаем размер файла для сравнения
                                    if os.path.exists(book.pages[0].image_path):
                                        existing_file_size = os.path.getsize(book.pages[0].image_path)
                                        existing_filename = os.path.basename(book.pages[0].image_path)
                                        
                                        # Вычисляем упрощенный хеш существующего PDF
                                        existing_hash = hashlib.md5(f"{existing_filename}_{existing_file_size}".encode('utf-8')).hexdigest()
                                        app.logger.info(f"Сравниваем хеши: {pdf_hash[:10]}... и {existing_hash[:10]}...")
                                        
                                        # Если хеши совпадают, это дубликат
                                        if pdf_hash == existing_hash:
                                            pdf_is_duplicate = True
                                            duplicate_book = book
                                        
                                        # Сохраняем хеш в БД для будущего использования
                                        try:
                                            new_file_hash = FileHash(
                                                file_hash=pdf_hash,
                                                original_filename=temp_filename,
                                                content_type='pdf',
                                                book_id=book.id
                                            )
                                            db.session.add(new_file_hash)
                                            db.session.commit()
                                        except Exception as e:
                                            app.logger.error(f"Ошибка при сохранении хеша PDF в БД: {str(e)}")
                                        
                                        break
                                except Exception as e:
                                    app.logger.error(f"Ошибка при проверке дубликата PDF: {str(e)}")
                except Exception as e:
                    app.logger.error(f"Ошибка при проверке дубликата PDF: {str(e)}")
                
                if pdf_is_duplicate and duplicate_book:
                    # Удаляем временный файл и созданную книгу, т.к. найден дубликат
                    os.remove(temp_filepath)
                    db.session.delete(new_book)
                    db.session.commit()
                    
                    flash(f'PDF файл уже существует в системе (книга "{duplicate_book.title}"). Повторная загрузка пропущена.', 'warning')
                    return redirect(url_for('view_book', book_id=duplicate_book.id))
                
                # Не дубликат, сохраняем окончательно
                # Проверяем директорию uploads и создаем, если она отсутствует
                uploads_folder = app.config['UPLOAD_FOLDER']
                if not os.path.exists(uploads_folder):
                    os.makedirs(uploads_folder, exist_ok=True)
                    app.logger.info(f"Создана директория для загрузок PDF: {uploads_folder}")
                
                # Улучшенная обработка копирования PDF файла
                try:
                    import shutil
                    # Обеспечиваем безопасное имя файла и не слишком длинный путь
                    safe_filename = secure_filename(pdf_file.filename)
                    if len(safe_filename) > 50:  # Ограничиваем длину имени файла
                        extension = safe_filename.rsplit('.', 1)[1] if '.' in safe_filename else ''
                        safe_filename = safe_filename[:40] + '.' + extension if extension else safe_filename[:50]
                    
                    # Формируем окончательный путь к файлу
                    filename = f"{new_book.id}_pdf_{safe_filename}"
                    file_path = os.path.join(uploads_folder, filename)
                    
                    # Копируем файл
                    shutil.copy2(temp_filepath, file_path)
                    app.logger.info(f"PDF файл успешно скопирован в {file_path}")
                    
                    # Проверяем, что файл действительно был скопирован
                    if not os.path.exists(file_path):
                        app.logger.error(f"PDF файл не был скопирован в {file_path}")
                        raise Exception("Не удалось скопировать PDF файл")
                        
                    # Проверяем права доступа и устанавливаем их
                    try:
                        os.chmod(file_path, 0o644)  # rw-r--r--
                    except Exception as chmod_error:
                        app.logger.warning(f"Не удалось изменить права доступа для PDF: {str(chmod_error)}")
                        
                    # Удаляем временный файл
                    os.remove(temp_filepath)
                    app.logger.info(f"Временный PDF файл удален: {temp_filepath}")
                except Exception as copy_error:
                    app.logger.error(f"Ошибка при копировании PDF файла: {str(copy_error)}")
                    # Если возникла ошибка при копировании, пробуем другой метод
                    try:
                        with open(temp_filepath, 'rb') as src_file:
                            file_content = src_file.read()
                            
                        with open(file_path, 'wb') as dst_file:
                            dst_file.write(file_content)
                            
                        app.logger.info(f"PDF файл успешно скопирован альтернативным методом в {file_path}")
                        
                        # Удаляем временный файл
                        os.remove(temp_filepath)
                    except Exception as alt_copy_error:
                        app.logger.error(f"Альтернативный метод копирования PDF также не сработал: {str(alt_copy_error)}")
                        # В случае ошибки продолжаем выполнение, но файл может быть не сохранен
                
                # Create single book page record for PDF
                new_page = BookPage(
                    book_id=new_book.id,
                    page_number=1,  # Since we don't know the page count yet
                    image_path=file_path,
                    status='pending'
                )
                db.session.add(new_page)
                
                # Сохраняем хеш PDF в базе данных для будущего обнаружения дубликатов
                if pdf_hash:
                    try:
                        new_file_hash = FileHash(
                            file_hash=pdf_hash,
                            original_filename=temp_filename,
                            content_type='pdf',
                            book_id=new_book.id,
                            page_id=new_page.id
                        )
                        db.session.add(new_file_hash)
                    except Exception as e:
                        app.logger.error(f"Ошибка при сохранении хеша PDF в БД: {str(e)}")
                
                db.session.commit()
                
                is_pdf = True
                uploaded_count = 1
                flash_message = 'PDF файл загружен, начата обработка'
            else:
                flash('Загруженный файл не является PDF', 'error')
                return redirect(request.url)
        else:
            flash('Неизвестный тип файла', 'error')
            return redirect(request.url)
        
        if uploaded_count > 0:
            # Create processing job
            job = ProcessingJob(book_id=new_book.id, status='queued')
            db.session.add(job)
            db.session.commit()
            
            # Start processing in background with translation flag
            thread = threading.Thread(target=process_book, args=(new_book.id, job.id, is_pdf, translate_to_russian))
            thread.daemon = True
            thread.start()
            
            flash(flash_message, 'success')
            return redirect(url_for('view_book', book_id=new_book.id))
        else:
            flash('Не загружено ни одного файла', 'error')
        
        return redirect(url_for('index'))
    
    return render_template('upload.html')

@app.route('/book/<int:book_id>')
def view_book(book_id):
    """Display book details and processing status"""
    book = Book.query.get_or_404(book_id)
    pages = BookPage.query.filter_by(book_id=book_id).order_by(BookPage.page_number).all()
    job = ProcessingJob.query.filter_by(book_id=book_id).order_by(ProcessingJob.created_at.desc()).first()
    
    return render_template('book.html', book=book, pages=pages, job=job)

@app.route('/book/<int:book_id>/reprocess', methods=['POST'])
def reprocess_book(book_id):
    """Reprocess a book"""
    book = Book.query.get_or_404(book_id)
    
    # Create new processing job
    job = ProcessingJob(book_id=book.id, status='queued')
    db.session.add(job)
    
    # Update book status
    book.status = 'processing'
    
    # Reset page status
    for page in book.pages:
        page.status = 'pending'
    
    db.session.commit()
    
    # Check if it's a PDF file
    is_pdf = False
    if book.pages and book.pages[0].image_path:
        is_pdf = book.pages[0].image_path.lower().endswith('.pdf')
    
    # По умолчанию используем перевод при повторной обработке
    # В будущем можно добавить выбор этой опции в форму повторной обработки
    translate_to_russian = True
    
    # Start processing in background with translation flag
    thread = threading.Thread(target=process_book, args=(book.id, job.id, is_pdf, translate_to_russian))
    thread.daemon = True
    thread.start()
    
    flash(f'Обработка начата для книги: {book.title}', 'success')
    return redirect(url_for('view_book', book_id=book.id))

@app.route('/book/<int:book_id>/delete', methods=['POST'])
def delete_book(book_id):
    """Delete a book and all associated data"""
    book = Book.query.get_or_404(book_id)
    
    try:
        # Get all pages
        pages = BookPage.query.filter_by(book_id=book_id).all()
        
        # Delete associated files
        for page in pages:
            # Delete image file if it exists and it's not a PDF
            if page.image_path and os.path.exists(page.image_path) and not page.image_path.lower().endswith('.pdf'):
                os.remove(page.image_path)
            
            # Delete processed image if it exists
            if page.processed_image_path and os.path.exists(page.processed_image_path):
                os.remove(page.processed_image_path)
            
            # Delete associated figures
            figures = Figure.query.filter_by(page_id=page.id).all()
            for figure in figures:
                if figure.image_path and os.path.exists(figure.image_path):
                    os.remove(figure.image_path)
                db.session.delete(figure)
        
        # Delete jobs and their output files
        jobs = ProcessingJob.query.filter_by(book_id=book_id).all()
        for job in jobs:
            if job.result_file_en and os.path.exists(job.result_file_en):
                os.remove(job.result_file_en)
            if job.result_file_ru and os.path.exists(job.result_file_ru):
                os.remove(job.result_file_ru)
            db.session.delete(job)
            
        # Удаляем хеши файлов, связанные с этой книгой
        file_hashes = FileHash.query.filter_by(book_id=book_id).all()
        for file_hash in file_hashes:
            db.session.delete(file_hash)
        
        # Delete output directory if it exists
        output_dir = os.path.join('output', f"book_{book_id}")
        if os.path.exists(output_dir):
            import shutil
            shutil.rmtree(output_dir)
        
        # Delete PDF file if this is a PDF book (only delete first page's file, as all pages reference the same file)
        if pages and pages[0].image_path and pages[0].image_path.lower().endswith('.pdf') and os.path.exists(pages[0].image_path):
            os.remove(pages[0].image_path)
        
        # Delete all pages
        for page in pages:
            db.session.delete(page)
        
        # Finally delete the book
        book_title = book.title
        db.session.delete(book)
        db.session.commit()
        
        flash(f'Книга "{book_title}" успешно удалена', 'success')
    except Exception as e:
        logger.error(f"Error deleting book {book_id}: {str(e)}")
        flash(f'Ошибка при удалении книги: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('index'))

@app.route('/download/<int:job_id>/<language>')
def download_pdf(job_id, language):
    """Download processed PDF"""
    job = ProcessingJob.query.get_or_404(job_id)
    
    if language == 'en' and job.result_file_en:
        logger.debug(f"Sending English PDF file: {job.result_file_en}")
        if not os.path.exists(job.result_file_en):
            logger.error(f"Файл не существует: {job.result_file_en}")
            flash('Файл не найден на сервере', 'error')
            return redirect(url_for('view_book', book_id=job.book_id))
        return send_file(job.result_file_en, as_attachment=True)
    elif language == 'ru' and job.result_file_ru:
        logger.debug(f"Sending Russian PDF file: {job.result_file_ru}")
        if not os.path.exists(job.result_file_ru):
            logger.error(f"Файл не существует: {job.result_file_ru}")
            flash('Файл не найден на сервере', 'error')
            return redirect(url_for('view_book', book_id=job.book_id))
        return send_file(job.result_file_ru, as_attachment=True)
    else:
        flash('Файл не доступен', 'error')
        return redirect(url_for('view_book', book_id=job.book_id))

@app.route('/page/<int:page_id>')
def view_page(page_id):
    """View details of a single page"""
    page = BookPage.query.get_or_404(page_id)
    figures = Figure.query.filter_by(page_id=page_id).all()
    
    return render_template('page.html', page=page, figures=figures)

@app.route('/api/book/<int:book_id>/status')
def book_status(book_id):
    """API endpoint to check book processing status"""
    book = Book.query.get_or_404(book_id)
    job = ProcessingJob.query.filter_by(book_id=book_id).order_by(ProcessingJob.created_at.desc()).first()
    
    if not job:
        return jsonify({
            'status': 'unknown',
            'message': 'No processing job found'
        })
    
    response = {
        'book_id': book.id,
        'book_title': book.title,
        'status': job.status,
        'created_at': job.created_at.isoformat(),
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'result_files': {
            'en': job.result_file_en is not None,
            'ru': job.result_file_ru is not None
        }
    }
    
    if job.error_message:
        response['error'] = job.error_message
    
    return jsonify(response)

@app.route('/images/<path:filename>')
def get_image(filename):
    """Serve uploaded and processed images"""
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(image_path):
        return send_file(image_path)
    else:
        # Return a placeholder image if the requested image doesn't exist
        return send_file(os.path.join('static', 'img', 'image-not-found.png'))

@app.route('/output/<path:filename>')
def get_output_file(filename):
    """Serve output files"""
    output_dir = 'output'
    output_path = os.path.join(output_dir, filename)
    if os.path.exists(output_path):
        return send_file(output_path)
    else:
        # Return a placeholder image if the requested file doesn't exist
        return send_file(os.path.join('static', 'img', 'image-not-found.png'))
        
@app.route('/book/<int:book_id>/read')
def read_book(book_id):
    """Sequential reading mode for the entire book"""
    book = Book.query.get_or_404(book_id)
    pages = BookPage.query.filter_by(book_id=book_id).order_by(BookPage.page_number).all()
    page_count = len(pages)
    
    # Get current page number from query parameters, default to 1
    current_page_num = request.args.get('page', 1, type=int)
    
    # Ensure page number is valid
    if current_page_num < 1:
        current_page_num = 1
    elif current_page_num > page_count:
        current_page_num = page_count
    
    # Get the current page (index is page_num - 1)
    current_page = pages[current_page_num - 1] if pages else None
    
    # Get figures for the current page
    figures = []
    if current_page:
        figures = Figure.query.filter_by(page_id=current_page.id).all()
    
    # Calculate previous and next page numbers
    prev_page = current_page_num - 1 if current_page_num > 1 else None
    next_page = current_page_num + 1 if current_page_num < page_count else None
    
    return render_template(
        'read.html', 
        book=book, 
        page=current_page,
        figures=figures,
        current_page_num=current_page_num,
        total_pages=page_count,
        prev_page=prev_page,
        next_page=next_page
    )

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error_code=404, message='Page not found'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error_code=500, message='Server error'), 500