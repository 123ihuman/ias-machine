import re
path = 'templates/base.html'
with open(path, encoding='utf-8') as f:
    html = f.read()

# 1) Remove all navbar-expand-* classes (forces hamburger at every width)
html = re.sub(r'\s*navbar-expand(-\w+)?', '', html)

# 2) Inject force-hamburger CSS right before </head>
css = '''
<style id="ias-mobile-nav-v2">
  /* Force hamburger behavior at every screen size */
  .navbar-toggler { display: block !important; margin-left: auto; }
  .navbar-collapse { display: none !important; }
  .navbar-collapse.show { display: block !important; }
  .navbar-nav { display: block !important; width: 100% !important; }
  .navbar-nav .nav-item { width: 100% !important; }
  .navbar-nav .nav-link { padding: 14px 18px !important;
                          border-bottom: 1px solid #30363d !important;
                          font-size: 15px !important; }
  .navbar-collapse.show { max-height: 75vh; overflow-y: auto;
                          background: #161b22; border-radius: 0 0 12px 12px; }
  .navbar .container, .navbar .container-fluid,
  .navbar > div { max-width: 100% !important; }
  /* Hide the desktop feature row completely on wide screens */
  @media (min-width: 992px) {
    .navbar-collapse:not(.show) { display: none !important; }
  }
</style>
</head>
'''
if 'ias-mobile-nav-v2' not in html:
    html = html.replace('</head>', css, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print('navbar-expand remaining:', html.count('navbar-expand'))
print('mobile-nav-v2 present:', 'ias-mobile-nav-v2' in html)
print('navbar-toggler present:', html.count('navbar-toggler'))