import sqlite3

try:
    conn = sqlite3.connect("credit_dossier.db")
    c = conn.cursor()
    c.execute("ALTER TABLE deals ADD COLUMN theme_palette VARCHAR(256) DEFAULT '[\"#002060\", \"#800020\"]'")
    conn.commit()
    print("DB Altered successfully.")
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
