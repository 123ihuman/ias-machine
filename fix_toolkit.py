import re
path = 'app.py'
with open(path, encoding='utf-8') as f:
    s = f.read()

pattern = r"@app\.route\('/toolkit'\)"
matches = list(re.finditer(pattern, s))
print(f'Found {len(matches)} occurrences of /toolkit route')

if len(matches) < 2:
    print('Only one — nothing to fix')
else:
    for m in reversed(matches[1:]):
        line_start = s.rfind('\n', 0, m.start()) + 1
        s = s[:line_start] + '# DISABLED-DUP: ' + s[line_start:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(s)
    print(f'Commented {len(matches) - 1} duplicate(s). Now run: python app.py')