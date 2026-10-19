path = 'app.py'
with open(path, encoding='utf-8') as f:
    s = f.read()

# Find the SQLALCHEMY_DATABASE_URI line
import re
m = re.search(r"^(.*SQLALCHEMY_DATABASE_URI.*)$", s, flags=re.MULTILINE)
if not m:
    print('URI line not found — abort')
else:
    end = m.end()
    if 'SQLALCHEMY_ENGINE_OPTIONS' in s:
        print('engine options already present')
    else:
        patch = (
            '\nfrom sqlalchemy.pool import NullPool as _NP'
            "\napp.config['SQLALCHEMY_ENGINE_OPTIONS'] = "
            "{'pool_pre_ping': True, 'pool_recycle': 60, 'poolclass': _NP}"
        )
        s = s[:end] + patch + s[end:]
        with open(path, 'w', encoding='utf-8') as f:
            f.write(s)
        print('engine options added')

# Verify
with open(path, encoding='utf-8') as f:
    s2 = f.read()
print('NullPool present:', 'NullPool' in s2)
print('ENGINE_OPTIONS present:', 'SQLALCHEMY_ENGINE_OPTIONS' in s2)