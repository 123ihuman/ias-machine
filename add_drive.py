code = '''

# ============ GOOGLE DRIVE BACKUP (laptop) ============
import os as _os_gd
import json as _json_gd
import io as _io_gd
import time as _time_gd
from datetime import datetime as _dt_gd

GDRIVE_FOLDER_ID = '1UaYQuQwznTc3A4mms0sjQ3L7B76tJAZQ'
GDRIVE_KEY = _os_gd.path.expanduser('~/ias_machine/config/gdrive_key.json')
if not _os_gd.path.exists(GDRIVE_KEY):
    GDRIVE_KEY = 'config/gdrive_key.json'
GDRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']

_gd_cache = {'svc': None, 'ts': 0}


def _gdrive_service():
    now = _time_gd.time()
    if _gd_cache['svc'] and (now - _gd_cache['ts']) < 600:
        return _gd_cache['svc']
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(GDRIVE_KEY, scopes=GDRIVE_SCOPES)
    svc = build('drive', 'v3', credentials=creds, cache_discovery=False)
    _gd_cache['svc'] = svc
    _gd_cache['ts'] = now
    return svc


BACKUP_TABLES = ['Book', 'Topper', 'TopperFullText', 'TopperParagraph', 'TopperDNA',
                 'InterviewQA', 'InterviewTranscript', 'NewsArticle',
                 'Question', 'Answer', 'CommonMistake', 'EthicsCase', 'EssayTopic',
                 'StudyNote', 'SyllabusNode', 'SelectionStat']


def _dump_tables(limit=5000):
    out = {}
    for tname in BACKUP_TABLES:
        cls = globals().get(tname)
        if cls is None:
            continue
        try:
            rows = cls.query.limit(limit).all()
            cols = [c.name for c in cls.__table__.columns]
            out[tname] = [{c: (str(getattr(r, c)) if getattr(r, c) is not None else None) for c in cols} for r in rows]
        except Exception as e:
            out[tname] = [{'__error': str(e)[:120]}]
    return out


@app.route('/backup/to-drive', methods=['GET', 'POST'])
def backup_to_drive():
    from flask import jsonify as _jf, request as _rq
    try:
        svc = _gdrive_service()
    except Exception as e:
        return _jf({'ok': False, 'error': 'auth: ' + str(e)[:250]}), 500
    try:
        data = _dump_tables()
    except Exception as e:
        return _jf({'ok': False, 'error': 'dump: ' + str(e)[:250]}), 500
    counts = {k: len(v) for k, v in data.items()}
    payload = {
        'generated_at': _dt_gd.utcnow().isoformat() + 'Z',
        'version': 'v1',
        'tables': counts,
        'data': data,
    }
    js = _json_gd.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    fname = 'ias_backup_' + _dt_gd.utcnow().strftime('%Y-%m-%d_%H%M') + '.json'
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(_io_gd.BytesIO(js), mimetype='application/json')
    try:
        created = svc.files().create(
            body={'name': fname, 'parents': [GDRIVE_FOLDER_ID]},
            media_body=media,
            fields='id,name,size,createdTime').execute()
    except Exception as e:
        return _jf({'ok': False, 'error': 'upload: ' + str(e)[:350]}), 500
    return _jf({'ok': True, 'file': created, 'size_bytes': len(js), 'tables': counts})


@app.route('/backup/list-drive')
def backup_list_drive():
    from flask import jsonify as _jf
    try:
        svc = _gdrive_service()
        q = "'" + GDRIVE_FOLDER_ID + "' in parents and trashed=false"
        res = svc.files().list(q=q, orderBy='createdTime desc', pageSize=100,
                               fields='files(id,name,size,createdTime)').execute()
        files = res.get('files', [])
        total = sum(int(f.get('size', 0) or 0) for f in files)
        return _jf({'ok': True, 'count': len(files), 'total_bytes': total, 'files': files[:30]})
    except Exception as e:
        return _jf({'ok': False, 'error': str(e)[:250], 'count': 0, 'total_bytes': 0, 'files': []})


@app.route('/backup/status')
def backup_status():
    from flask import jsonify as _jf
    return _jf({'folder_id': GDRIVE_FOLDER_ID, 'has_key': _os_gd.path.exists(GDRIVE_KEY)})


@app.route('/backup/drive')
def backup_drive_ui():
    from flask import render_template as _rt_gd
    return _rt_gd('backup_drive.html')


@app.route('/backup/delete/<file_id>', methods=['POST'])
def backup_delete(file_id):
    from flask import jsonify as _jf
    try:
        svc = _gdrive_service()
        svc.files().delete(fileId=file_id).execute()
        return _jf({'ok': True})
    except Exception as e:
        return _jf({'ok': False, 'error': str(e)[:250]}), 500


print('[gdrive-laptop] backup routes registered')
'''
with open('app.py', 'a', encoding='utf-8') as f:
    f.write(code)
print('appended drive code')