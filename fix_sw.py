path = 'static/sw.js'
with open(path, encoding='utf-8') as f:
    s = f.read()

# Add PDF.js to precache list
old = "  '/static/icon-192.png',\n  '/static/icon-512.png',\n];"
new = ("  '/static/icon-192.png',\n"
       "  '/static/icon-512.png',\n"
       "  '/static/pdfjs/pdf.min.js',\n"
       "  '/static/pdfjs/pdf.worker.min.js',\n"
       "];")

if 'pdfjs/pdf.min.js' in s:
    print('already precached')
else:
    s = s.replace(old, new)
    # Bump version so a new SW installs
    s = s.replace("const VERSION = 'ias-v6'", "const VERSION = 'ias-v7'")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(s)
    print('patched sw.js — version ias-v6 -> ias-v7, PDF.js added to precache')

# Verify
with open(path, encoding='utf-8') as f:
    s2 = f.read()
print('pdfjs in precache:', 'pdfjs/pdf.min.js' in s2)
print('version:', 'ias-v7' if 'ias-v7' in s2 else 'still v6')