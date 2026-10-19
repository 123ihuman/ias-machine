import re

path = 'app.py'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

# Find every @app.route(...) line and track its rule string
route_re = re.compile(r"""@app\.route\(\s*['"]([^'"]+)['"]""")
rule_lines = {}          # rule -> first line index
dupe_lines = []          # line indices to comment out (the decorator + following def)

for i, ln in enumerate(lines):
    m = route_re.search(ln)
    if not m:
        continue
    rule = m.group(1)
    if rule in rule_lines:
        # This is a duplicate — comment decorator + the def line right after
        dupe_lines.append(i)
        # comment the def line too (next line that starts with 'def ')
        for j in range(i+1, min(i+4, len(lines))):
            if lines[j].lstrip().startswith('def '):
                dupe_lines.append(j)
                break
    else:
        rule_lines[rule] = i

print(f'Unique routes: {len(rule_lines)}')
print(f'Duplicate route lines to disable: {len(dupe_lines)}')

for i in sorted(dupe_lines, reverse=True):
    if not lines[i].lstrip().startswith('#'):
        lines[i] = '# DISABLED-DUP: ' + lines[i]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done. Now run: C:\\Users\\divy0\\AppData\\Local\\Programs\\Python\\Python311\\python.exe app.py')