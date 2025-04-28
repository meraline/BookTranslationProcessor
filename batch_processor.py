#!/usr/bin/env python3
"""
Module for batch processing of large volumes of files.
Provides functionality to process files in smaller chunks
with proper error handling and resumption capabilities.
"""

import os
import time
import logging
import argparse
import traceback
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from concurrent.futures import ThreadPoolExecutor

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   filename='batch_processor.log')
logger = logging.getLogger(__name__)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logger.addHandler(console)

# Import app components
from models import Book, ProcessingJob, db
from app import app
from processing_service import process_book

def get_files_to_process(input_dir, extensions=None):
    """Get all files in directory with specified extensions."""
    if extensions is None:
        extensions = ['.pdf', '.png', '.jpg', '.jpeg']
        
    files = []
    for root, _, filenames in os.walk(input_dir):
        for filename in filenames:
            if any(filename.lower().endswith(ext) for ext in extensions):
                files.append(os.path.join(root, filename))
    return files

def create_book_entry(filename, session):
    """Create a new book entry in the database."""
    title = os.path.basename(filename)
    book = Book(title=title, description=f"Batch processed on {datetime.now()}")
    session.add(book)
    session.commit()
    
    # Create processing job
    job = ProcessingJob(book_id=book.id)
    session.add(job)
    session.commit()
    
    return book, job

def process_file(file_path, batch_id, concurrent=False):
    """Process a single file."""
    try:
        logger.info(f"Processing file: {file_path} (Batch: {batch_id})")
        
        with app.app_context():
            # Create database session
            Session = sessionmaker(bind=db.engine)
            session = Session()
            
            # Create book entry
            book, job = create_book_entry(file_path, session)
            
            # Determine if file is PDF
            is_pdf = file_path.lower().endswith('.pdf')
            
            # Process the book
            if concurrent:
                # Just queue the job, processing happens in worker thread
                logger.info(f"Queued book ID {book.id} for processing")
                return book.id, job.id, is_pdf
            else:
                # Directly process
                process_book(book.id, job.id, is_pdf)
                logger.info(f"Completed processing book ID {book.id}")
                return book.id, job.id, is_pdf
    except Exception as e:
        logger.error(f"Error processing file {file_path}: {str(e)}")
        traceback.print_exc()
        return None, None, None

def batch_process(input_dir, batch_size=5, wait_time=5, max_workers=2):
    """
    Process files in batches with proper pause between batches.
    
    Args:
        input_dir: Directory containing files to process
        batch_size: Number of files to process in each batch
        wait_time: Time to wait between batches (in minutes)
        max_workers: Maximum number of concurrent processing threads
    """
    files = get_files_to_process(input_dir)
    total_files = len(files)
    logger.info(f"Found {total_files} files to process in {input_dir}")
    
    if total_files == 0:
        logger.warning("No files found to process.")
        return
    
    # Process in batches
    batch_number = 1
    processed_count = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i in range(0, total_files, batch_size):
            batch_files = files[i:i+batch_size]
            logger.info(f"Processing batch {batch_number} ({len(batch_files)} files)")
            
            # Submit batch to thread pool
            futures = []
            for file_path in batch_files:
                future = executor.submit(process_file, file_path, batch_number, True)
                futures.append(future)
            
            # Process files submitted to thread pool
            for file_path, future in zip(batch_files, futures):
                try:
                    book_id, job_id, is_pdf = future.result()
                    if book_id is not None:
                        with app.app_context():
                            process_book(book_id, job_id, is_pdf)
                        processed_count += 1
                except Exception as e:
                    logger.error(f"Error in worker thread for {file_path}: {str(e)}")
            
            batch_number += 1
            
            # Wait between batches if not the last batch
            if i + batch_size < total_files:
                wait_sec = wait_time * 60
                logger.info(f"Waiting {wait_time} minutes before next batch...")
                time.sleep(wait_sec)
    
    logger.info(f"Batch processing complete. Processed {processed_count} out of {total_files} files.")

def create_argparser():
    """Create argument parser for command line options."""
    parser = argparse.ArgumentParser(description="Batch processor for OCR and translation")
    parser.add_argument("--input", required=True, help="Input directory containing files to process")
    parser.add_argument("--batch-size", type=int, default=5, help="Number of files to process in each batch")
    parser.add_argument("--wait-time", type=int, default=5, help="Time to wait between batches (in minutes)")
    parser.add_argument("--workers", type=int, default=2, help="Maximum number of concurrent processing threads")
    return parser

if __name__ == "__main__":
    parser = create_argparser()
    args = parser.parse_args()
    
    logger.info(f"Starting batch processor with input dir: {args.input}, batch size: {args.batch_size}")
    batch_process(args.input, args.batch_size, args.wait_time, args.workers)