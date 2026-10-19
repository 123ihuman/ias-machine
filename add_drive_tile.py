import re
path = 'templates/home.html'
with open(path, encoding='utf-8') as f:
    html = f.read()

tile = '''
<a href="/backup/drive" style="display:block;margin:8px auto;max-width:680px;padding:20px;background:linear-gradient(135deg,#f39c12,#e67e22);color:#fff;text-decoration:none;border-radius:18px;text-align:center;font-family:Georgia,serif;box-shadow:0 6px 18px rgba(0,0,0,0.18);">
  <div style="font-size:22px;font-weight:700;letter-spacing:1px;margin-bottom:6px;">💾 GOOGLE DRIVE BACKUP</div>
  <div style="font-size:13px;opacity:0.9;">Save all data to Drive · 15 GB free</div>
  <div style="margin-top:10px;font-size:12px;opacity:0.75;">Backup now →</div>
</a>
'''

if '/backup/drive' in html:
    print('already present')
else:
    # Insert before {% endblock %}
    html = html.replace('{% endblock %}', tile + '\n{% endblock %}', 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print('tile added')

# Verify
with open(path, encoding='utf-8') as f:
    print('has Drive tile:', '/backup/drive' in f.read())