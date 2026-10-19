"""Create every model table in the current database (Supabase)."""
import os
from dotenv import load_dotenv
load_dotenv()

from app import app, db

print('DB URL:', app.config['SQLALCHEMY_DATABASE_URI'][:60] + '...')

with app.app_context():
    db.create_all()
    # List all tables now in DB
    from sqlalchemy import inspect as _insp
    insp = _insp(db.engine)
    tables = sorted(insp.get_table_names())
    print(f'\n✅ Tables now in DB: {len(tables)}')
    for t in tables:
        print('  -', t)