/**
 * ChunkedUploader - Компонент для загрузки файлов по частям
 * Позволяет загружать большие объемы файлов без превышения лимитов сервера
 */
class ChunkedUploader {
    constructor(options = {}) {
        this.options = {
            apiEndpoint: '/api/upload-chunk',
            maxFilesPerBatch: 10,
            delayBetweenBatches: 500, // ms
            onProgress: null,
            onBatchComplete: null,
            onComplete: null,
            onError: null,
            ...options
        };
        
        this.files = [];
        this.bookId = null;
        this.bookTitle = '';
        this.bookDescription = '';
        this.currentBatchIndex = 0;
        this.totalUploaded = 0;
        this.uploading = false;
    }
    
    /**
     * Инициализация загрузки списка файлов
     * @param {FileList|Array} files - Список файлов для загрузки
     * @param {Object} metadata - Метаданные для загрузки (название книги и т.д.)
     */
    startUpload(files, metadata = {}) {
        if (this.uploading) {
            console.warn('Загрузка уже выполняется');
            return false;
        }
        
        this.files = Array.from(files);
        this.bookId = metadata.bookId || 'new';
        this.bookTitle = metadata.bookTitle || 'Загруженная книга';
        this.bookDescription = metadata.description || '';
        this.currentBatchIndex = 0;
        this.totalUploaded = 0;
        this.uploading = true;
        
        console.log(`Начинаем загрузку ${this.files.length} файлов...`);
        this._uploadNextBatch();
        
        return true;
    }
    
    /**
     * Загружает следующую партию файлов
     * @private
     */
    _uploadNextBatch() {
        if (!this.uploading) return;
        
        const start = this.currentBatchIndex;
        const end = Math.min(this.currentBatchIndex + this.options.maxFilesPerBatch, this.files.length);
        const currentBatch = this.files.slice(start, end);
        
        console.log(`Загрузка партии ${start + 1}-${end} из ${this.files.length} файлов`);
        
        if (currentBatch.length === 0) {
            // Все файлы загружены
            this.uploading = false;
            if (typeof this.options.onComplete === 'function') {
                this.options.onComplete({
                    totalFiles: this.files.length,
                    uploadedFiles: this.totalUploaded,
                    bookId: this.bookId
                });
            }
            return;
        }
        
        // Загружаем все файлы в текущей партии
        let batchUploaded = 0;
        
        currentBatch.forEach((file, idx) => {
            const isLastFile = (end === this.files.length && idx === currentBatch.length - 1);
            this._uploadSingleFile(file, start + idx, isLastFile)
                .then(() => {
                    batchUploaded++;
                    this.totalUploaded++;
                    
                    if (typeof this.options.onProgress === 'function') {
                        this.options.onProgress({
                            totalFiles: this.files.length,
                            uploadedFiles: this.totalUploaded,
                            progress: Math.round((this.totalUploaded / this.files.length) * 100)
                        });
                    }
                    
                    // Проверяем, загружена ли вся партия
                    if (batchUploaded === currentBatch.length) {
                        this.currentBatchIndex = end;
                        
                        if (typeof this.options.onBatchComplete === 'function') {
                            this.options.onBatchComplete({
                                batchIndex: Math.floor(start / this.options.maxFilesPerBatch),
                                batchSize: currentBatch.length,
                                totalUploaded: this.totalUploaded,
                                totalFiles: this.files.length
                            });
                        }
                        
                        // Если это не последняя партия, загружаем следующую с небольшой задержкой
                        if (end < this.files.length) {
                            setTimeout(() => {
                                this._uploadNextBatch();
                            }, this.options.delayBetweenBatches);
                        } else {
                            this.uploading = false;
                            if (typeof this.options.onComplete === 'function') {
                                this.options.onComplete({
                                    totalFiles: this.files.length,
                                    uploadedFiles: this.totalUploaded,
                                    bookId: this.bookId
                                });
                            }
                        }
                    }
                })
                .catch(error => {
                    console.error(`Ошибка при загрузке файла ${start + idx}:`, error);
                    
                    if (typeof this.options.onError === 'function') {
                        this.options.onError({
                            fileIndex: start + idx,
                            fileName: file.name,
                            error: error
                        });
                    }
                });
        });
    }
    
    /**
     * Загружает один файл на сервер
     * @param {File} file - Файл для загрузки
     * @param {number} index - Индекс файла в общем списке
     * @param {boolean} isLastFile - Является ли это последним файлом в загрузке
     * @private
     */
    _uploadSingleFile(file, index, isLastFile = false) {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('book_id', this.bookId);
            formData.append('book_title', this.bookTitle);
            formData.append('description', this.bookDescription);
            formData.append('file_index', index);
            formData.append('total_files', this.files.length);
            formData.append('is_last_file', isLastFile);
            
            fetch(this.options.apiEndpoint, {
                method: 'POST',
                body: formData,
                // Отключаем автоматические заголовки Content-Type, чтобы браузер сам установил правильный multipart/form-data
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Ошибка ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Если это первый файл и bookId был 'new', сохраняем полученный bookId
                    if (index === 0 && this.bookId === 'new' && data.book_id) {
                        this.bookId = data.book_id;
                    }
                    resolve(data);
                } else {
                    reject(new Error(data.error || 'Неизвестная ошибка при загрузке файла'));
                }
            })
            .catch(error => {
                reject(error);
            });
        });
    }
    
    /**
     * Отменяет текущую загрузку
     */
    cancelUpload() {
        if (!this.uploading) return;
        
        this.uploading = false;
        console.log('Загрузка отменена');
    }
}

/**
 * Инициализация интерфейса загрузки файлов по частям
 */
document.addEventListener('DOMContentLoaded', function() {
    // Находим форму загрузки
    const uploadForm = document.getElementById('upload-form');
    if (!uploadForm) return; // Если нет формы загрузки, выходим
    
    // Добавляем кнопку для режима массовой загрузки
    const formControls = uploadForm.querySelector('.form-group:last-child');
    if (formControls) {
        const chunkedUploadBtn = document.createElement('button');
        chunkedUploadBtn.type = 'button';
        chunkedUploadBtn.className = 'btn btn-primary ml-2';
        chunkedUploadBtn.id = 'chunked-upload-btn';
        chunkedUploadBtn.innerHTML = 'Загрузить партиями';
        
        // Элементы индикации загрузки
        const progressContainer = document.createElement('div');
        progressContainer.className = 'mt-3 d-none';
        progressContainer.id = 'upload-progress-container';
        progressContainer.innerHTML = `
            <div class="progress">
                <div id="upload-progress-bar" class="progress-bar" role="progressbar" style="width: 0%"></div>
            </div>
            <div class="mt-2 text-center">
                <span id="upload-progress-text">0 из 0 файлов загружено (0%)</span>
            </div>
            <div class="mt-2">
                <button type="button" id="cancel-upload-btn" class="btn btn-sm btn-danger">Отменить загрузку</button>
            </div>
        `;
        
        formControls.appendChild(chunkedUploadBtn);
        uploadForm.appendChild(progressContainer);
        
        // Инициализируем загрузчик
        const uploader = new ChunkedUploader({
            onProgress: function(data) {
                const progressBar = document.getElementById('upload-progress-bar');
                const progressText = document.getElementById('upload-progress-text');
                
                if (progressBar) {
                    progressBar.style.width = `${data.progress}%`;
                    progressBar.setAttribute('aria-valuenow', data.progress);
                }
                
                if (progressText) {
                    progressText.textContent = `${data.uploadedFiles} из ${data.totalFiles} файлов загружено (${data.progress}%)`;
                }
            },
            onComplete: function(data) {
                // Показываем сообщение об успешной загрузке
                alert(`Загрузка завершена! Загружено ${data.uploadedFiles} файлов.`);
                
                // Перенаправляем на страницу книги
                window.location.href = `/book/${data.bookId}`;
            },
            onError: function(data) {
                alert(`Ошибка при загрузке файла ${data.fileName}: ${data.error.message}`);
            }
        });
        
        // Обработчик кнопки загрузки партиями
        chunkedUploadBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            const fileInput = document.getElementById('book_images');
            const titleInput = document.getElementById('book_title');
            const descriptionInput = document.getElementById('description');
            
            if (!fileInput || fileInput.files.length === 0) {
                alert('Пожалуйста, выберите файлы для загрузки');
                return;
            }
            
            // Показываем индикатор загрузки
            const progressContainer = document.getElementById('upload-progress-container');
            if (progressContainer) {
                progressContainer.classList.remove('d-none');
            }
            
            // Начинаем загрузку
            uploader.startUpload(fileInput.files, {
                bookTitle: titleInput ? titleInput.value : '',
                description: descriptionInput ? descriptionInput.value : ''
            });
        });
        
        // Обработчик кнопки отмены загрузки
        const cancelBtn = document.getElementById('cancel-upload-btn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', function() {
                uploader.cancelUpload();
                
                // Скрываем индикатор загрузки
                const progressContainer = document.getElementById('upload-progress-container');
                if (progressContainer) {
                    progressContainer.classList.add('d-none');
                }
            });
        }
    }
});