#!/usr/bin/env python3
"""
Module for image preprocessing to improve OCR quality.
"""
import cv2
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ImagePreprocessor:
    """Handles preprocessing of images to optimize OCR results."""
    
    @staticmethod
    def preprocess_image(image_path):
        """
        Preprocess an image for better OCR results.
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            tuple: (original_resized, processed_image) - original and processed images
        """
        try:
            # Load the image
            img = cv2.imread(image_path)
            
            # Check if image loaded successfully
            if img is None:
                raise ValueError(f"Failed to load image: {image_path}")
                
            # Get image dimensions
            height, width = img.shape[:2]
            
            # Resize image for better recognition if it's too small
            if width < 1000:
                scale_factor = 1000 / width
                img = cv2.resize(img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
            
            # Copy original for later use
            original_resized = img.copy()
            
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive thresholding and noise reduction
            processed = ImagePreprocessor._enhance_text(gray)
            
            return original_resized, processed
            
        except Exception as e:
            logger.error(f"Error preprocessing image {image_path}: {str(e)}")
            raise
    
    @staticmethod
    def _enhance_text(gray_image):
        """
        Apply various image processing techniques to enhance text visibility.
        
        Args:
            gray_image: Grayscale image
            
        Returns:
            Enhanced image for OCR
        """
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
        
        # Apply adaptive threshold to get binary image
        binary = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Apply noise reduction
        denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
        
        # Apply morphological operations to improve text
        kernel = np.ones((1, 1), np.uint8)
        dilated = cv2.dilate(denoised, kernel, iterations=1)
        enhanced = cv2.erode(dilated, kernel, iterations=1)
        
        return enhanced
    
    @staticmethod
    def detect_text_regions(img):
        """
        Detect regions containing text in the image.
        
        Args:
            img: Processed image
            
        Returns:
            list: List of text regions in format [(x, y, w, h), ...]
        """
        # Ensure the image is grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
            
        # Apply morphological operations to highlight text blocks
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        dilate = cv2.dilate(gray, kernel, iterations=3)
        
        # Find contours
        cnts, _ = cv2.findContours(~dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter contours
        text_regions = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            # Filter out too small regions
            if w > 100 and h > 20:
                text_regions.append((x, y, w, h))
                
        return text_regions
    
    @staticmethod
    def prepare_for_tesseract(img):
        """
        Final preparation of the image specifically for Tesseract OCR.
        
        Args:
            img: Preprocessed image
            
        Returns:
            Image ready for Tesseract OCR
        """
        # Apply additional processing specifically for Tesseract
        # For technical content and numbers, we'll use a slightly different approach
        
        # Convert to grayscale if needed
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        
        # Apply bilateral filter to preserve edges while removing noise
        filtered = cv2.bilateralFilter(gray, 11, 17, 17)
        
        # Apply unsharp masking to enhance edges (good for text)
        gaussian = cv2.GaussianBlur(filtered, (0, 0), 3)
        unsharp = cv2.addWeighted(filtered, 1.5, gaussian, -0.5, 0)
        
        # Apply binary thresholding
        _, binary = cv2.threshold(unsharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return binary
