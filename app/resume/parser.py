import os
import logging
from pathlib import Path
import pypdf

logger = logging.getLogger(__name__)

class ResumeParser:
    """
    Deterministic local resume document parser.
    Extracts text from PDF files securely without AI.
    """
    
    def __init__(self, allowed_extensions=(".pdf",)):
        self.allowed_extensions = [ext.lower() for ext in allowed_extensions]
        
    def _is_safe_path(self, file_path: str) -> bool:
        """Basic validation to ensure the file path is a PDF."""
        path_obj = Path(file_path)
        
        if not path_obj.exists():
            logger.error(f"File not found: {file_path}")
            return False
            
        if not path_obj.is_file():
            logger.error(f"Path is not a file: {file_path}")
            return False
            
        if path_obj.suffix.lower() not in self.allowed_extensions:
            logger.error(f"Invalid file extension {path_obj.suffix}. Allowed: {self.allowed_extensions}")
            return False
            
        return True

    def extract_text(self, file_path: str) -> str:
        """
        Extracts plain text from all pages of the given PDF file.
        Returns empty string on failure.
        """
        if not self._is_safe_path(file_path):
            return ""
            
        extracted_text = []
        
        try:
            with open(file_path, "rb") as file:
                reader = pypdf.PdfReader(file)
                
                # Check for encryption or malformed headers before extracting
                if reader.is_encrypted:
                    logger.error(f"Cannot extract text from encrypted PDF: {file_path}")
                    return ""
                    
                for page_num, page in enumerate(reader.pages):
                    try:
                        text = page.extract_text()
                        if text:
                            # Basic cleanup: remove excessive whitespace and newlines
                            clean_text = " ".join(text.split())
                            extracted_text.append(clean_text)
                    except Exception as page_err:
                        # Continue trying other pages if one fails
                        logger.warning(f"Error extracting text from page {page_num} of {file_path}: {page_err}")
                        
        except Exception as e:
            logger.error(f"Fatal error parsing PDF {file_path}: {e}")
            return ""
            
        final_text = "\n".join(extracted_text).strip()
        
        if not final_text:
            logger.warning(f"No text could be extracted from {file_path}")
            
        return final_text
