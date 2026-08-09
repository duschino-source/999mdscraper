import sqlite3
import json

conn = sqlite3.connect('scraper.db')
cursor = conn.cursor()
cursor.execute('SELECT title, price, currency, price_dropped, date_added FROM items LIMIT 5')
rows = cursor.fetchall()
with open('verify_db.json', 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=4)
