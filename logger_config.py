#!/usr/bin/env python3
"""
Конфигурация системы логирования для приложения.
"""
import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(name='app', log_dir='logs', level=logging.DEBUG):
    """
    Настройка логгера с записью в файл.
    
    Args:
        name (str): Имя логгера
        log_dir (str): Директория для сохранения логов
        level: Уровень логирования (DEBUG, INFO и т.д.)
        
    Returns:
        logging.Logger: Настроенный логгер
    """
    # Создаем директорию, если не существует
    os.makedirs(log_dir, exist_ok=True)
    
    # Конфигурация логгера
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Создаем обработчик для файла
    log_file = os.path.join(log_dir, f"{name}.log")
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(level)
    
    # Создаем форматтер для логов
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Добавляем обработчик к логгеру (если еще не добавлен)
    if not logger.handlers:
        logger.addHandler(file_handler)
    
    # Создаем консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # Добавляем консольный обработчик, если еще не добавлен
    has_console_handler = False
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            has_console_handler = True
            break
    
    if not has_console_handler:
        logger.addHandler(console_handler)
    
    return logger

# Создаем логгеры для разных компонентов
file_logger = setup_logger('file_operations', 'logs')
pdf_logger = setup_logger('pdf_operations', 'logs')
app_logger = setup_logger('app', 'logs')