import sqlite3
try:
    conn = sqlite3.connect('/opt/pmpr-crm/data/pmpr_leads.db')
    conn.execute("ALTER TABLE developers ADD COLUMN notes TEXT DEFAULT '';")
    conn.commit()
    print("✅ SUCCESS: Notes column permanently added!")
except Exception as e:
    print(f"ℹ️ Status: {e}")
finally:
    conn.close()
