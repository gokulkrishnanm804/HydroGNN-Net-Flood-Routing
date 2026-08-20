"""
Issue #4 Fix — DB Migration
Adds `source` column (VARCHAR 50, default 'observed') to:
  - weather table
  - river_levels table

Run from project root:
  python migrate_add_source_column.py
"""
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app.backend.services.db.connection import initialize_database, get_db_url

import sqlite3

def run_migration():
    db_url = get_db_url()
    if not db_url.startswith("sqlite:///"):
        print("ERROR: This migration script only supports SQLite. For PostgreSQL, run:")
        print("  ALTER TABLE weather ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'observed';")
        print("  ALTER TABLE river_levels ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'observed';")
        sys.exit(1)

    db_path = db_url.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        print("Start the backend first to create the DB, then run this migration.")
        sys.exit(1)

    print(f"Connecting to SQLite database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check and add `source` to `weather`
    cursor.execute("PRAGMA table_info(weather)")
    weather_cols = [row[1] for row in cursor.fetchall()]
    if "source" not in weather_cols:
        cursor.execute("ALTER TABLE weather ADD COLUMN source VARCHAR(50) DEFAULT 'observed'")
        # Back-fill existing rows based on matching rainfall source
        cursor.execute("""
            UPDATE weather
            SET source = (
                SELECT r.source FROM rainfall r
                WHERE r.station_id = weather.station_id AND r.ts = weather.ts
                LIMIT 1
            )
            WHERE source IS NULL OR source = 'observed'
        """)
        print(f"  [weather] Added 'source' column and back-filled {cursor.rowcount} rows.")
    else:
        print("  [weather] 'source' column already exists — skipping.")

    # Check and add `source` to `river_levels`
    cursor.execute("PRAGMA table_info(river_levels)")
    rl_cols = [row[1] for row in cursor.fetchall()]
    if "source" not in rl_cols:
        cursor.execute("ALTER TABLE river_levels ADD COLUMN source VARCHAR(50) DEFAULT 'observed'")
        # Back-fill: mark as 'open_meteo' if there is a matching open-meteo rainfall at same ts
        cursor.execute("""
            UPDATE river_levels
            SET source = (
                SELECT r.source FROM rainfall r
                WHERE r.station_id = river_levels.station_id AND r.ts = river_levels.ts
                LIMIT 1
            )
            WHERE source IS NULL OR source = 'observed'
        """)
        print(f"  [river_levels] Added 'source' column and back-filled {cursor.rowcount} rows.")
    else:
        print("  [river_levels] 'source' column already exists — skipping.")

    conn.commit()
    conn.close()
    print("\nMigration complete.")

if __name__ == "__main__":
    run_migration()
