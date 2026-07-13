import sqlite3

try:
    conn = sqlite3.connect("credit_dossier.db")
    c = conn.cursor()
    c.execute("ALTER TABLE deals ADD COLUMN library_sync_status VARCHAR(32) NOT NULL DEFAULT 'not_started'")
    conn.commit()
    print("Column added successfully.")
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
