code = '''

# === FINAL: / renders home.html (tiles) instead of library ===
def _ias_home_final():
    from flask import render_template as _rt_h
    return _rt_h('home.html')
app.view_functions['index'] = _ias_home_final
print('[fix-home] / now renders home.html')
'''
with open('app.py', 'a', encoding='utf-8') as f:
    f.write(code)
print('done')