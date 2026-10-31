import argparse, csv, sqlite3
from pathlib import Path

SCHEMA='''PRAGMA foreign_keys=ON; CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY,patient_no TEXT UNIQUE NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS measurements(id INTEGER PRIMARY KEY,patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,skull_volume REAL,left_orbit_volume REAL,right_orbit_volume REAL,asymmetry_ratio REAL,skull_mesh TEXT,left_orbit_mesh TEXT,right_orbit_mesh TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);'''
def init_db(path):
    c=sqlite3.connect(path); c.executescript(SCHEMA); return c
def import_baseline(c,csv_path,root):
    vals={}
    with open(csv_path,encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            seg=r.get('segment','').lower(); v=float(r.get('volume_lm_cm3') or r.get('volume_cs_cm3') or 0)
            if seg=='skull': vals['skull_volume']=v
            elif seg=='left_orbit': vals['left_orbit_volume']=v
            elif seg=='right_orbit': vals['right_orbit_volume']=v
    l=vals.get('left_orbit_volume',0); rr=vals.get('right_orbit_volume',0); vals['asymmetry_ratio']=abs(l-rr)/max(l+rr,1e-9)
    c.execute("INSERT INTO patients(patient_no) VALUES('case-001') ON CONFLICT(patient_no) DO NOTHING"); pid=c.execute("SELECT id FROM patients WHERE patient_no='case-001'").fetchone()[0]
    c.execute('INSERT INTO measurements(patient_id,skull_volume,left_orbit_volume,right_orbit_volume,asymmetry_ratio,skull_mesh,left_orbit_mesh,right_orbit_mesh) VALUES(?,?,?,?,?,?,?,?)',(pid,vals.get('skull_volume'),l,rr,vals['asymmetry_ratio'],str(Path(root)/'Segmentation_skull.stl'),str(Path(root)/'Segmentation_left_orbit.stl'),str(Path(root)/'Segmentation_right_orbit.stl'))); c.commit()
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--csv',default='V.txt'); ap.add_argument('--db',default='ct_data.db'); a=ap.parse_args(); c=init_db(a.db); import_baseline(c,a.csv,Path(a.csv).resolve().parent); print(c.execute('SELECT * FROM measurements').fetchall()); c.close()
