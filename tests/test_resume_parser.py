import os
import pytest
from pathlib import Path
from pypdf import PdfWriter, PdfReader
from app.resume.parser import ResumeParser

@pytest.fixture
def temp_pdf(tmp_path):
    """Generates a real, valid, multi-page PDF on the fly for testing."""
    pdf_path = tmp_path / "test_resume.pdf"
    
    # We can't easily write text natively with PdfWriter without reportlab or similar,
    # but we can create empty pages and inject mock text via patching,
    # OR we can mock PdfReader.
    # The prompt explicitly said: "Tests must use temporary test files."
    # Let's create an empty PDF and then patch the text extraction just to simulate text,
    # or actually, we can append a blank page, which is valid.
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    with open(pdf_path, "wb") as f:
        writer.write(f)
        
    return str(pdf_path)

@pytest.fixture
def parser():
    return ResumeParser()

def test_resume_parser_missing_file(parser):
    text = parser.extract_text("non_existent_file.pdf")
    assert text == ""

def test_resume_parser_invalid_extension(parser, tmp_path):
    txt_file = tmp_path / "resume.txt"
    txt_file.write_text("Hello")
    
    text = parser.extract_text(str(txt_file))
    assert text == ""

def test_resume_parser_empty_pdf(parser, temp_pdf):
    # Our temp_pdf has 2 blank pages, so extract_text should return empty string
    text = parser.extract_text(temp_pdf)
    assert text == ""

def test_resume_parser_multi_page_extraction(parser, temp_pdf, monkeypatch):
    """
    Since creating a text-filled PDF purely with pypdf is complex without extra libs,
    we generate a valid empty PDF file, then mock the internal page.extract_text method.
    This fulfills the requirement to use a temporary test file while testing our multi-page logic.
    """
    # Create a mock for page.extract_text
    def mock_extract_text(self):
        # We can distinguish pages or just return some text
        return "  Mocked  Resume \n Text  "
        
    # Patch the extract_text method of pypdf's PageObject
    monkeypatch.setattr("pypdf.PageObject.extract_text", mock_extract_text)
    
    text = parser.extract_text(temp_pdf)
    
    # Our temp_pdf has 2 pages, so it should extract text twice and join with \n
    # And our cleanup logic should convert "  Mocked  Resume \n Text  " to "Mocked Resume Text"
    assert text == "Mocked Resume Text\nMocked Resume Text"

def test_resume_parser_malformed_file(parser, tmp_path):
    # A file that ends with .pdf but is actually junk bytes
    bad_pdf = tmp_path / "corrupt.pdf"
    bad_pdf.write_bytes(b"Not a real PDF file! Junk data.")
    
    text = parser.extract_text(str(bad_pdf))
    assert text == ""
