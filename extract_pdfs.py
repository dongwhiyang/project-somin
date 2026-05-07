import os
from pathlib import Path
import fitz  # PyMuPDF
import easyocr
import olefile
import win32com.client
import numpy as np

source_dir = Path('source_pdfs')
target_dir = Path('anchor_data')

# Ensure target directory exists
target_dir.mkdir(parents=True, exist_ok=True)

# Define supported extensions
supported_extensions = {'.pdf', '.hwp', '.doc', '.docx', '.png', '.jpg', '.jpeg'}

# Recursively get all files with supported extensions
all_files = [f for f in source_dir.rglob('*') if f.suffix.lower() in supported_extensions]
total_files = len(all_files)

print(f"Total supported files found: {total_files}")

# Initialize EasyOCR reader (this will download models on first run if not present)
# Using ['ko', 'en'] for Korean and English
reader = None 
def get_ocr_reader():
    global reader
    if reader is None:
        print("Initializing OCR model (might take a while on first run)...")
        reader = easyocr.Reader(['ko', 'en'], gpu=False)
    return reader

# Initialize Word application
word_app = None
def get_word_app():
    global word_app
    if word_app is None:
        word_app = win32com.client.Dispatch("Word.Application")
        word_app.Visible = False
    return word_app

def extract_text(file_path):
    ext = file_path.suffix.lower()
    text = ""
    
    if ext == '.pdf':
        doc = fitz.open(file_path)
        for page in doc:
            page_text = page.get_text()
            if len(page_text.strip()) < 50:
                # Likely an image page, use OCR
                pix = page.get_pixmap()
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                # Convert to RGB if needed (easyocr expects RGB images)
                if pix.n == 4: # RGBA
                    import cv2
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                elif pix.n == 1: # Grayscale
                    import cv2
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                    
                ocr_reader = get_ocr_reader()
                result = ocr_reader.readtext(img, detail=0)
                page_text = "\n".join(result)
            text += page_text + "\n"
            
    elif ext in ['.doc', '.docx']:
        app = get_word_app()
        try:
            # Need absolute path for Word COM
            abs_path = str(file_path.resolve())
            doc = app.Documents.Open(abs_path, ReadOnly=True)
            text = doc.Content.Text
            doc.Close(False)
        except Exception as e:
            text = f"Word extraction error: {e}"
            
    elif ext == '.hwp':
        try:
            f = olefile.OleFileIO(file_path)
            dirs = f.listdir()
            if ["PrvText"] in dirs:
                stream = f.openstream("PrvText").read()
                text = stream.decode('utf-16le', errors='ignore')
            else:
                text = "Could not extract text from HWP (No PrvText stream found)."
        except Exception as e:
            text = f"HWP extraction error: {e}"
            
    elif ext in ['.png', '.jpg', '.jpeg']:
        ocr_reader = get_ocr_reader()
        result = ocr_reader.readtext(str(file_path), detail=0)
        text = "\n".join(result)
        
    return text

# Main extraction loop
try:
    for i, file_path in enumerate(all_files, 1):
        txt_filename = file_path.stem + '.txt'
        txt_path = target_dir / txt_filename
        
        try:
            extracted_text = extract_text(file_path)
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            print(f"[{i}/{total_files}] Successfully extracted: {file_path.name}")
        except Exception as e:
            print(f"[{i}/{total_files}] Error extracting {file_path.name}: {e}")

finally:
    # Cleanup Word application if it was initialized
    if word_app is not None:
        try:
            word_app.Quit()
        except:
            pass

print("Extraction completed!")
