"""Create/query the SQLite clinical imaging database."""
import argparse,csv,sqlite3
from pathlib import Path
SCHEMA='''CREATE TABLE IF NOT EXISTS patients (id INTEGER PRIMARY KEY, patient_no TEXT UNIQUE NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS measurements (id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id), segment TEXT NOT NULL, voxel_count INTEGER, volume_mm3 REAL, volume_cm3 REAL, surface_area_mm2 REAL, mesh_path TEXT, UNIQUE(patient_id,segment));'''
def init_db(db):
 c=sqlite3.connect(db); c.executescript(SCHEMA); c.commit(); return c
def import_csv(db,csv_path,mesh_dir):
 c=init_db(db); c.execute("INSERT OR IGNORE INTO patients(patient_no) VALUES (?)",("case-001",)); pid=c.execute("SELECT id FROM patients WHERE patient_no='case-001'").fetchone()[0]
 meshes={'skull':'Segmentation_skull.stl','left_orbit':'Segmentation_left_orbit.stl','right_orbit':'Segmentation_right_orbit.stl'}
 with open(csv_path,encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   c.execute('''INSERT OR REPLACE INTO measurements(patient_id,segment,voxel_count,volume_mm3,volume_cm3,surface_area_mm2,mesh_path) VALUES(?,?,?,?,?,?,?)''',(pid,r['segment'],int(r['voxel_count']),float(r['volume_lm_mm3']),float(r['volume_lm_cm3']),float(r['surface_area_mm2']),str(Path(mesh_dir)/meshes.get(r['segment'],''))))
 c.commit(); return c
def summary(db):
 c=sqlite3.connect(db); c.row_factory=sqlite3.Row; rows=c.execute('SELECT p.patient_no,m.* FROM patients p JOIN measurements m ON p.id=m.patient_id ORDER BY m.segment').fetchall(); return [dict(r) for r in rows]
if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--db',type=Path,default=Path('web/ct_measurements.sqlite')); ap.add_argument('--csv',type=Path,default=Path('V.txt')); ap.add_argument('--mesh-dir',type=Path,default=Path('.')); ap.add_argument('--query',action='store_true'); a=ap.parse_args(); import_csv(a.db,a.csv,a.mesh_dir); print(summary(a.db) if a.query else f'initialized {a.db}')
