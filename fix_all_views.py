code = '''

# === GLOBAL SAFE-VIEW WRAPPER ===
# Catches InFailedSqlTransaction on ANY endpoint, nukes the session,
# and retries once. Fixes Book Zone, Toppers, Quiz, Mock, etc.
def _ias_safe_view(orig_fn):
    import functools
    @functools.wraps(orig_fn)
    def _wrap(*a, **kw):
        try:
            return orig_fn(*a, **kw)
        except Exception as _e1:
            msg = str(_e1)
            if 'InFailedSqlTransaction' in msg or 'current transaction is aborted' in msg or 'PendingRollback' in msg:
                print('[SAFE] retry on', getattr(orig_fn, '__name__', '?'), '-', msg[:120])
                try: db.session.rollback()
                except Exception: pass
                try: db.session.remove()
                except Exception: pass
                try: db.engine.dispose()
                except Exception: pass
                try:
                    return orig_fn(*a, **kw)
                except Exception as _e2:
                    import traceback as _tb
                    _tb.print_exc()
                    return str(_e2)[:500], 500
            raise
    return _wrap

_skip_endpoints = {'static', 'service_worker_root'}
for _ep, _fn in list(app.view_functions.items()):
    if _ep in _skip_endpoints:
        continue
    try:
        app.view_functions[_ep] = _ias_safe_view(_fn)
    except Exception:
        pass
print('[fix-views] wrapped', len(app.view_functions), 'endpoints with safe-retry')
'''

with open('app.py', 'a', encoding='utf-8') as f:
    f.write(code)
print('appended')