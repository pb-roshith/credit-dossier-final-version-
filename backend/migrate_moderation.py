"""Quick migration to add moderation columns to sections table."""
import sqlite3

conn = sqlite3.connect("credit_dossier.db")
cursor = conn.cursor()

# Check existing columns
cursor.execute("PRAGMA table_info(sections)")
cols = {row[1] for row in cursor.fetchall()}
print(f"Existing columns: {sorted(cols)}")

added = []
if "moderation_status" not in cols:
    cursor.execute("ALTER TABLE sections ADD COLUMN moderation_status VARCHAR(16)")
    added.append("moderation_status")

if "moderation_details" not in cols:
    cursor.execute("ALTER TABLE sections ADD COLUMN moderation_details TEXT")
    added.append("moderation_details")

conn.commit()
conn.close()
print(f"Added columns: {added if added else 'none needed'}")
