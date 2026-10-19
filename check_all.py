"""Check every GET route in the app. Reports working vs erroring."""
import sys, re, warnings
warnings.filterwarnings('ignore')

from app import app

# Collect all GET routes with no path params (can be tested with no args)
routes = []
for rule in app.url_map.iter_rules():
    if 'GET' not in rule.methods:
        continue
    if '<' in rule.rule:  # skip routes needing params
        continue
    if rule.rule.startswith('/static'):
        continue
    if rule.endpoint in ('static',):
        continue
    routes.append(rule.rule)

routes = sorted(set(routes))
print(f'Testing {len(routes)} GET routes (param-free only)\n')

ok, fail, skip = [], [], []

with app.test_client() as c:
    for path in routes:
        try:
            r = c.get(path, follow_redirects=False)
            code = r.status_code
            if code in (200, 302, 304, 201, 204):
                ok.append((path, code))
                print(f'  [{code}] OK   {path}')
            elif code in (404, 405):
                skip.append((path, code))
                print(f'  [{code}] SKIP {path}')
            else:
                body = r.get_data(as_text=True)
                # Extract last line if it's a traceback page
                last = ''
                m = re.search(r'(psycopg2\.[\w.]+|sqlalchemy\.[\w.]+|AttributeError|KeyError|TypeError|NameError)[^\n]{0,120}', body)
                if m:
                    last = m.group(0)[:120]
                fail.append((path, code, last))
                print(f'  [{code}] FAIL {path}  {last}')
        except Exception as e:
            fail.append((path, 0, str(e)[:120]))
            print(f'  [ERR] FAIL {path}  {str(e)[:120]}')

print('\n' + '=' * 60)
print(f'OK    : {len(ok)}')
print(f'SKIP  : {len(skip)}  (redirect/404, fine)')
print(f'FAIL  : {len(fail)}')
print('=' * 60)

if fail:
    print('\nFAILED ROUTES:')
    for path, code, msg in fail:
        print(f'  {path}   [{code}]  {msg}')