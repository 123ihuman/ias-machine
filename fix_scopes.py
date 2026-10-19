code = '''

# === Fix: define SCOPES for OAuth function ===
SCOPES = ['https://www.googleapis.com/auth/drive']
print('[fix-scopes] SCOPES defined')
'''
with open('app.py', 'a', encoding='utf-8') as f:
    f.write(code)
print('appended')