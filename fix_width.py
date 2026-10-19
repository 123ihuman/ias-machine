import re
path = 'templates/base.html'
with open(path, encoding='utf-8') as f:
    html = f.read()

# Remove the old 540px hard cap
html = re.sub(r'<style id="ias-mobile-force">.*?</style>', '', html, flags=re.DOTALL)

# New responsive layout: mobile on phone, roomy on laptop
css = '''
<style id="ias-responsive">
  @media (min-width: 768px) {
    html { background: #f7f5ee; }
    body { max-width: 900px !important; margin: 0 auto !important;
           background: #f7f5ee; }
    .container, .container-fluid { max-width: 900px !important; }
    .navbar { max-width: 900px; margin: 0 auto; }
    .navbar-collapse.show { max-width: 900px; margin: 0 auto; }
  }
  @media (max-width: 767px) {
    /* Mobile stays exactly as it is now */
  }
</style>
</head>
'''
if 'ias-responsive' not in html:
    html = html.replace('</head>', css, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print('540px cap removed:', 'ias-mobile-force' not in html)
print('responsive added:', 'ias-responsive' in html)