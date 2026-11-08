"""Add sample data for demonstration.  Usage:  python seed.py

Adds demo vessels, maintenance records and movement history so every tab has content.
Safe to re-run: existing vessels are skipped, and maintenance/movements are only added once.
"""
from app import run_query, init_db, UNIQUE_ERROR

# ship_id, name, type, registered, status, berth
SHIPS = [
    ("SH1001", "Ocean Star", "Cargo Ship", "2022-03-14", "In Service", None),
    ("SH1002", "Bay Queen", "Passenger Ship", "2021-07-02", "Docked", "B-04"),
    ("SH1003", "Vizag Pride", "Container Ship", "2023-01-20", "Under Maintenance", "D-07"),
    ("SH1004", "Coral Trader", "Tanker", "2020-11-08", "Ready", "B-09"),
    ("SH1005", "INS Sagar", "Naval Ship", "2019-05-25", "Docked", "N-02"),
    ("SH1006", "Blue Horizon", "Cargo Ship", "2018-09-30", "Inactive", None),
    ("SH1007", "Godavari", "Tanker", "2024-02-11", "Under Maintenance", "D-03"),
    ("SH1008", "Sea Falcon", "Other", "2023-08-17", "Ready", "B-12"),
]
# ship_id, description, start, end, status
MAINTENANCE = [
    ("SH1003", "Hull repainting and anti-fouling treatment", "2026-10-20", None, "In Progress"),
    ("SH1007", "Main engine overhaul - waiting for spare parts", "2026-10-10", "2026-11-20", "Delayed"),
    ("SH1004", "Annual safety and class inspection", "2026-11-25", "2026-11-27", "Scheduled"),
    ("SH1005", "Radar and navigation system upgrade", "2026-09-01", "2026-09-18", "Completed"),
]
# ship_id, type, date, berth, notes
MOVEMENTS = [
    ("SH1001", "Arrival", "2026-10-02", "B-01", "Cargo offloading"),
    ("SH1001", "Departure", "2026-10-09", "B-01", "Sailed for Chennai"),
    ("SH1002", "Arrival", "2026-10-28", "B-04", "Passenger terminal"),
    ("SH1005", "Arrival", "2026-10-15", "N-02", "Routine port call"),
    ("SH1004", "Departure", "2026-09-22", "B-09", None),
]

init_db()
ids = {}
added = 0
for s in SHIPS:
    try:
        run_query(
            """INSERT INTO ships (ship_id, ship_name, ship_type, registration_date, status, berth_number)
               VALUES (%s, %s, %s, %s, %s, %s)""", s, fetch=None)
        added += 1
    except UNIQUE_ERROR:
        pass
for r in run_query("SELECT id, ship_id FROM ships"):
    ids[r["ship_id"]] = r["id"]

if run_query("SELECT COUNT(*) AS n FROM maintenance", fetch="one")["n"] == 0:
    for sid, desc, start, end, status in MAINTENANCE:
        if sid in ids:
            run_query("""INSERT INTO maintenance (ship_pk, description, start_date, end_date, status)
                         VALUES (%s, %s, %s, %s, %s)""", (ids[sid], desc, start, end, status), fetch=None)
if run_query("SELECT COUNT(*) AS n FROM movements", fetch="one")["n"] == 0:
    for sid, mtype, d, berth, notes in MOVEMENTS:
        if sid in ids:
            run_query("""INSERT INTO movements (ship_pk, movement_type, movement_date, berth_number, notes)
                         VALUES (%s, %s, %s, %s, %s)""", (ids[sid], mtype, d, berth, notes), fetch=None)
print(f"Added {added} sample vessels (plus maintenance and movement history on a fresh database).")
