import os
import json
import logging
import threading
from flask import request, jsonify
from werkzeug.utils import secure_filename
from app import app, db
from models import Book, BookPage, ProcessingJob, Figure, FileHash
from datetime import datetime
from utils import compute_image_hash
from processing_service import process_book

# Setup logging
logger = logging.getLogger(__name__)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/api/upload-chunk', methods=['POST'])
def upload_chunk():
    """API endpoint для загрузки файлов по частям"""
    try:
        # Получаем информацию о книге
        book_id = request.form.get('book_id')
        create_new_book = book_id is None or book_id == 'new'
        
        if create_new_book:
            # Создаем новую книгу, если book_id не указан или равен 'new'
            book_title = request.form.get('book_title', 'Книга - загружена по частям')
            description = request.form.get('description', 'Загрузка через API по частям')
            
            new_book = Book(title=book_title, description=description)
            db.session.add(new_book)
            db.session.commit()
            book_id = new_book.id
            app.logger.info(f"Создана новая книга для пакетной загрузки, ID: {book_id}")
        else:
            # Проверяем существующую книгу
            book_id = int(book_id)
            book = Book.query.get(book_id)
            if not book:
                return jsonify({'success': False, 'error': f'Книга с ID {book_id} не найдена'}), 404
        
        # Получаем номер файла в последовательности
        file_index = int(request.form.get('file_index', 0))
        total_files = int(request.form.get('total_files', 1))
        is_last_file = request.form.get('is_last_file', 'false') == 'true'
        
        # Получаем загруженный файл
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Файл не найден в запросе'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Не выбран файл'}), 400
            
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Недопустимый тип файла'}), 400
        
        # Сохраняем файл во временную директорию для обработки
        temp_filename = secure_filename(file.filename)
        temp_filepath = os.path.join('/tmp', temp_filename)
        file.save(temp_filepath)
        
        # Проверка хеша файла (упрощенная, без проверки дубликатов)
        try:
            file_hash = compute_image_hash(temp_filepath)
            app.logger.info(f"Вычислен хеш файла {file_index}: {file_hash[:10]}...")
        except Exception as e:
            app.logger.error(f"Ошибка при вычислении хеша файла: {str(e)}")
            file_hash = None
            
        # Сохраняем файл в постоянную директорию
        try:
            # Обеспечиваем безопасное имя файла и не слишком длинный путь
            safe_filename = secure_filename(file.filename)
            if len(safe_filename) > 50:  # Ограничиваем длину имени файла
                extension = safe_filename.rsplit('.', 1)[1] if '.' in safe_filename else ''
                safe_filename = safe_filename[:40] + '.' + extension if extension else safe_filename[:50]
            
            # Формируем окончательный путь к файлу
            filename = f"{book_id}_{file_index}_{safe_filename}"
            uploads_folder = app.config['UPLOAD_FOLDER']
            if not os.path.exists(uploads_folder):
                os.makedirs(uploads_folder, exist_ok=True)
                
            file_path = os.path.join(uploads_folder, filename)
            
            # Копируем файл
            import shutil
            shutil.copy2(temp_filepath, file_path)
            app.logger.info(f"Файл {file_index} успешно скопирован в {file_path}")
            
            # Удаляем временный файл
            os.remove(temp_filepath)
            app.logger.info(f"Временный файл удален: {temp_filepath}")
            
            # Создаем запись страницы в БД
            page = BookPage(
                book_id=book_id,
                page_number=file_index + 1,  # Страница начиная с 1
                image_path=file_path,
                status='pending'
            )
            db.session.add(page)
            
            # Если у нас есть хеш файла, добавляем его в БД
            if file_hash:
                file_hash_record = FileHash(
                    file_hash=file_hash,
                    original_filename=safe_filename,
                    content_type='image',
                    book_id=book_id,
                    page_id=page.id if page.id else None
                )
                db.session.add(file_hash_record)
            
            db.session.commit()
            
            # Если это последний файл, запускаем обработку
            if is_last_file or file_index == total_files - 1:
                app.logger.info(f"Последний файл загружен, запускаем обработку книги {book_id}")
                
                # Создаем задачу на обработку
                job = ProcessingJob(book_id=book_id, status='queued')
                db.session.add(job)
                
                # Обновляем статус книги
                book = Book.query.get(book_id)
                book.status = 'queued'
                
                db.session.commit()
                
                # Запускаем обработку в отдельном потоке
                threading.Thread(target=process_book, args=(book_id, job.id, False)).start()
                
                return jsonify({
                    'success': True, 
                    'message': 'Все файлы загружены, обработка запущена',
                    'book_id': book_id,
                    'job_id': job.id,
                    'total_files': total_files
                })
            else:
                # Обычный успешный ответ для промежуточного файла
                return jsonify({
                    'success': True, 
                    'message': f'Файл {file_index+1} из {total_files} успешно загружен',
                    'book_id': book_id,
                    'file_index': file_index,
                    'total_files': total_files
                })
                
        except Exception as e:
            app.logger.error(f"Ошибка при обработке файла: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
            
    except Exception as e:
        app.logger.error(f"Ошибка API загрузки: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500