code = '''

# === OAuth-based Drive service (replaces service account) ===
import os as _os_oauth
import json as _json_oauth

OAUTH_TOKEN  = _os_oauth.path.expanduser('~/ias_machine/config/oauth_token.json')
if not _os_oauth.path.exists(OAUTH_TOKEN):
    OAUTH_TOKEN = 'config/oauth_token.json'

def _gdrive_service_oauth():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import time as _t
    if not _os_oauth.path.exists(OAUTH_TOKEN):
        raise RuntimeError('OAuth token missing — run oauth_setup.py first')
    creds = Credentials.from_authorized_user_file(OAUTH_TOKEN, SCOPES)
    if not creds.valid or (creds.expired and creds.refresh_token):
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        with open(OAUTH_TOKEN, 'w') as f:
            f.write(creds.to_json())
    return build('drive', 'v3', credentials=creds, cache_discovery=False)

# Replace the service-account path
_gd_cache['svc'] = None
_gd_cache['ts'] = 0
_gdrive_service = _gdrive_service_oauth
print('[gdrive-oauth] Drive now uses OAuth user credentials')
'''
with open('app.py', 'a', encoding='utf-8') as f:
    f.write(code)
print('appended oauth override')