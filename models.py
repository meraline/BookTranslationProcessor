from app import db
from datetime import datetime

class Book(db.Model):
    """Model for storing book metadata and processing status"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='new')  # new, processing, completed, error
    pages = db.relationship('BookPage', backref='book', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Book {self.title}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
            'status': self.status,
            'page_count': len(self.pages)
        }

class BookPage(db.Model):
    """Model for storing individual book pages"""
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    page_number = db.Column(db.Integer, nullable=True)
    image_path = db.Column(db.String(255), nullable=False)
    processed_image_path = db.Column(db.String(255), nullable=True)
    text_content = db.Column(db.Text, nullable=True)
    translated_content = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='pending')  # pending, processed, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<BookPage {self.book_id}:{self.page_number}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'page_number': self.page_number,
            'image_path': self.image_path,
            'processed_image_path': self.processed_image_path,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }

class ProcessingJob(db.Model):
    """Model for tracking OCR processing jobs"""
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    status = db.Column(db.String(50), default='queued')  # queued, processing, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    result_file_en = db.Column(db.String(255), nullable=True)  # Path to English PDF
    result_file_ru = db.Column(db.String(255), nullable=True)  # Path to Russian PDF
    
    def __repr__(self):
        return f'<ProcessingJob {self.id}:{self.status}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
            'result_file_en': self.result_file_en,
            'result_file_ru': self.result_file_ru
        }

class Figure(db.Model):
    """Model for storing figures detected in book pages"""
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey('book_page.id'), nullable=False)
    figure_type = db.Column(db.String(50), nullable=False)  # table, chart, diagram, image
    image_path = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    translated_description = db.Column(db.Text, nullable=True)
    region = db.Column(db.String(255), nullable=True)  # JSON string "(x, y, w, h)"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Figure {self.id}:{self.figure_type}>'