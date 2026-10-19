"""IAS Machine — OCR a single PDF. Supports Hindi + English."""
import sys, os, time
try:
    import pypdfium2 as pdfium
except ImportError:
    print('ERROR: pip install pypdfium2'); sys.exit(1)
try:
    import pytesseract
except ImportError:
    print('ERROR: pip install pytesseract'); sys.exit(1)

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def ocr_pdf(path, dpi=200, max_pages=None, lang='hin+eng'):
    print(f'Opening {path}')
    print(f'Language: {lang}')
    pdf = pdfium.PdfDocument(path)
    total = len(pdf)
    if max_pages:
        total = min(total, max_pages)
    out_pages = []
    t0 = time.time()
    cfg = '--oem 3 --psm 6'  # assume uniform block of text
    for i in range(total):
        try:
            page = pdf[i]
            bitmap = page.render(scale=dpi/72)
            img = bitmap.to_pil().convert('L')
            text = pytesseract.image_to_string(img, lang=lang, config=cfg)
            out_pages.append(text.strip())
            elapsed = time.time() - t0
            print(f'  Page {i+1}/{total} — {len(text)} chars — {elapsed:.1f}s total')
        except Exception as e:
            print(f'  Page {i+1} FAILED: {e}')
            out_pages.append('')
    pdf.close()
    return '\n\n---PAGE---\n\n'.join(out_pages)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python ocr_one.py <path-to-pdf> [max_pages] [lang]')
        print('  lang: hin+eng (default) | eng | hin')
        sys.exit(1)
    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f'Not found: {pdf_path}'); sys.exit(1)
    max_p = int(sys.argv[2]) if len(sys.argv) > 2 else None
    lang = sys.argv[3] if len(sys.argv) > 3 else 'hin+eng'
    text = ocr_pdf(pdf_path, max_pages=max_p, lang=lang)
    out_path = os.path.splitext(pdf_path)[0] + '.ocr.txt'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'\nSaved: {out_path}')
    print(f'Total chars: {len(text)}')
    print(f'\n--- First 400 chars ---\n{text[:400]}')