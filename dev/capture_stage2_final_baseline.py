import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pymongo import MongoClient
from bson.json_util import dumps
from backend.config import read_settings
s=read_settings();db=MongoClient(s.mongodb_uri)[s.mongodb_db]
p=Path('docs/stage2-final-data-baseline.json')
if p.exists():raise SystemExit('Refuse overwrite')
m={n:{str(d['_id']):hashlib.sha256(dumps(d,sort_keys=True).encode()).hexdigest() for d in db[n].find()} for n in db.list_collection_names() if n!='sessions'}
p.write_text(json.dumps(m,indent=2),encoding='utf-8');print({n:len(v) for n,v in m.items()})
