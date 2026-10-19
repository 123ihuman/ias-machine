code = '''

# === RAW SQL library_view (bypasses ORM stuck-transaction bug) ===
def _ias_library_view_raw():
    from flask import request as _rq, render_template as _rt
    from sqlalchemy import text as _t
    try:
        db.session.remove()
    except Exception:
        pass
    col = _rq.args.get('collection', '').strip().upper()
    year_f = _rq.args.get('year', '').strip()
    subj_f = _rq.args.get('subject', '').strip()
    with db.engine.connect() as conn:
        conn.execute(_t('ROLLBACK'))
        where = []
        params = {}
        if col:
            where.append('collection = :col')
            params['col'] = col
        if year_f:
            try:
                where.append('year = :yr')
                params['yr'] = int(year_f)
            except ValueError:
                pass
        if subj_f:
            where.append('subject = :subj')
            params['subj'] = subj_f
        wh = ('WHERE ' + ' AND '.join(where)) if where else ''
        sql = 'SELECT id,title,author,subject,topic,category,collection,year,sub_subject,ocr_status,filename,uploaded_at FROM book ' + wh + ' ORDER BY uploaded_at DESC LIMIT 500'
        rows = conn.execute(_t(sql), params).fetchall()
        counts_rows = conn.execute(_t('SELECT collection, COUNT(*) FROM book WHERE collection IS NOT NULL GROUP BY collection')).fetchall()
        total = conn.execute(_t('SELECT COUNT(*) FROM book')).fetchone()[0]
        years_rows = conn.execute(_t('SELECT DISTINCT year FROM book WHERE year IS NOT NULL ORDER BY year DESC')).fetchall()
        subj_rows = conn.execute(_t('SELECT DISTINCT subject FROM book WHERE subject IS NOT NULL ORDER BY subject')).fetchall()

    class _BK:
        def __init__(self, r):
            self.id = r[0]
            self.title = r[1]
            self.author = r[2]
            self.subject = r[3]
            self.topic = r[4]
            self.category = r[5]
            self.collection = r[6]
            self.year = r[7]
            self.sub_subject = r[8]
            self.ocr_status = r[9]
            self.filename = r[10]
            self.uploaded_at = r[11]

    books = [_BK(r) for r in rows]
    LIBCOLL = {
        'NCERT': {'label': 'NCERT', 'icon': 'NCERT'},
        'STANDARD': {'label': 'Standard', 'icon': 'Standard'},
        'PYQ': {'label': 'PYQ', 'icon': 'PYQ'},
        'UPSC': {'label': 'UPSC', 'icon': 'UPSC'},
        'BANKING': {'label': 'Banking', 'icon': 'Banking'},
        'SSC': {'label': 'SSC', 'icon': 'SSC'},
        'OTHER': {'label': 'Other', 'icon': 'Other'},
    }
    counts = {r[0]: r[1] for r in counts_rows if r[0]}
    years = [r[0] for r in years_rows if r[0]]
    subjects = [r[0] for r in subj_rows if r[0]]

    return _rt('index.html', books=books, collections=LIBCOLL,
               collection_counts=counts, total_count=total,
               years=years, subjects=subjects)

library_view = _ias_library_view_raw
print('[fix-libview] library_view replaced with raw SQL version')
'''

with open('app.py', 'a', encoding='utf-8') as f:
    f.write(code)
print('appended raw library_view')