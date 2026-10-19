"""IAS Machine — Bulk OCR of all pending books.
Reads from local SQLite. OCRs pages. Saves to page table.
"""
import os, sys, time, sqlite3
try:
    import pypdfium2 as pdfium
except ImportError:
    print('pip install pypdfium2'); sys.exit(1)
try:
    import pytesseract
except ImportError:
    print('pip install pytesseract'); sys.exit(1)

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

DB = r'C:\Users\divy0\ias_machine\instance\ias_machine_v2.db'
UPLOADS = r'C:\Users\divy0\ias_machine\uploads'
LANG = 'hin+eng'
DPI = 200
CFG = '--oem 3 --psm 6'


def find_pdf(book):
    fn = book['filename'] or ''
    if fn.startswith('b2://'):
        return None  # not local — skip
    p = os.path.join(UPLOADS, fn)
    if os.path.exists(p):
        return p
    # try matching by title
    for f in os.listdir(UPLOADS):
        if not f.lower().endswith('.pdf'): continue
        if (book['title'] or '')[:20].lower() in f.lower():
            return os.path.join(UPLOADS, f)
    return None


def ocr_page(img):
    return pytesseract.image_to_string(img, lang=LANG, config=CFG)


def process_book(book, db):
    bid = book['id']
    title = (book['title'] or '')[:60]
    pdf_path = find_pdf(book)
    if not pdf_path:
        print(f'  [SKIP {bid}] {title} — no local PDF')
        return 0, 0
    print(f'  [OCR {bid}] {title} — {os.path.basename(pdf_path)}')
    try:
        pdf = pdfium.PdfDocument(pdf_path)
    except Exception as e:
        print(f'    FAILED open: {e}')
        return 0, 0

    total = len(pdf)
    print(f'    {total} pages')
    # clear old pages for this book
    db.execute('DELETE FROM page WHERE book_id=?', (bid,))
    db.commit()

    saved = 0
    t0 = time.time()
    for i in range(total):
        try:
            page = pdf[i]
            bmp = page.render(scale=DPI/72)
            img = bmp.to_pil().convert('L')
            text = ocr_page(img)
            db.execute(
                'INSERT INTO page (book_id, page_number, text) VALUES (?, ?, ?)',
                (bid, i+1, text))
            saved += 1
            if (i+1) % 5 == 0 or i == 0:
                el = time.time() - t0
                eta = el / (i+1) * (total - i - 1)
                print(f'    {i+1}/{total} — {el:.0f}s elapsed, ETA {eta:.0f}s')
        except Exception as e:
            print(f'    page {i+1} err: {e}')
    pdf.close()
    db.execute(
        "UPDATE book SET ocr_status='complete' WHERE id=?", (bid,))
    db.commit()
    return saved, total


def main():
    if not os.path.exists(DB):
        print(f'DB not found: {DB}'); sys.exit(1)
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    # Ensure page table exists
    db.execute('''CREATE TABLE IF NOT EXISTS page (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER,
        page_number INTEGER,
        text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    db.commit()

    rows = db.execute(
        "SELECT id, title, filename, ocr_status FROM book "
        "WHERE ocr_status IS NULL OR ocr_status != 'complete'").fetchall()
    print(f'Pending: {len(rows)} books')
    if not rows:
        print('Nothing to do.'); return

    done_pages = 0
    for idx, b in enumerate(rows, 1):
        print(f'[{idx}/{len(rows)}]')
        try:
            saved, total = process_book(b, db)
            done_pages += saved
        except KeyboardInterrupt:
            print('\nStopped. Progress saved.')
            break
        except Exception as e:
            print(f'  book {b["id"]} crashed: {e}')
            continue

    print(f'\nDONE — {done_pages} pages OCR\'d across {len(rows)} books')


if __name__ == '__main__':
    main()