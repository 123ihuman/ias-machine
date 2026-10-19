import traceback, warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv
load_dotenv()

from app import app, db
from sqlalchemy import text

with app.test_client() as c:
    try:
        r = c.get('/reader/140')
        print('status:', r.status_code)
        if r.status_code != 200:
            body = r.get_data(as_text=True)
            # Find the traceback or error
            print('--- response (first 800 chars) ---')
            print(body[:800])
    except Exception as e:
        traceback.print_exc()

# Also verify the reader function is our raw-SQL one
print('\nbook_reader endpoint =', app.view_functions.get('book_reader'))