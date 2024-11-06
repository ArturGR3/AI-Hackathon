import os
from pdf2image import convert_from_path
import pytesseract
from PIL import Image

class PDFTextExtractor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        
    def convert_pdf_to_images(self):
        """Convert PDF pages to images"""
        try:
            # Convert PDF to list of images
            return convert_from_path(self.pdf_path)
        except Exception as e:
            print(f"Error converting PDF to images: {str(e)}")
            return []

    def extract_text_from_images(self, images):
        """Extract text from list of images using OCR"""
        extracted_text = []
        
        for i, image in enumerate(images):
            try:
                # Extract text from image using pytesseract
                text = pytesseract.image_to_string(image)
                extracted_text.append(text)
            except Exception as e:
                print(f"Error processing page {i + 1}: {str(e)}")
                
        return '\n'.join(extracted_text)

    def extract_text(self):
        """Main method to extract text from PDF"""
        # Convert PDF to images
        images = self.convert_pdf_to_images()
        if not images:
            return None
            
        # Extract text from images
        return self.extract_text_from_images(images)

def extract_text_from_pdf(path_to_pdf: str):
    # Example usage
    pdf_path = path_to_pdf
    
    extractor = PDFTextExtractor(pdf_path) # create extractor object
    extracted_text = extractor.extract_text() # extract text from pdf
        
    return extracted_text