code = '''

# === RAW SQL reader route (bypasses ORM stuck-session bug) ===
def _ias_reader_raw(book_id):
    from flask import render_template as _rt_r, abort as _abort
    from sqlalchemy import text as _t
    try:
        db.session.remove()
    except Exception:
        pass
    with db.engine.connect() as _conn:
        try:
            _conn.execute(_t('ROLLBACK'))
        except Exception:
            pass
        row = _conn.execute(
            _t('SELECT id, title, filename FROM book WHERE id = :i'),
            {'i': book_id}).fetchone()
    if not row:
        _abort(404)
    class _B:
        pass
    b = _B()
    b.id = row[0]
    b.title = row[1]
    b.filename = row[2]
    return _rt_r('reader.html', book=b)

try:
    app.view_functions['book_reader'] = _ias_reader_raw
    print('[fix-reader] book_reader -> raw SQL')
except Exception as _e:
    print('[fix-reader] error:', _e)
'''
with open('app.py', 'a', encoding='utf-8') as f:
    f.write(code)
print('appended fix_reader')