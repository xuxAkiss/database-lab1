import json, hashlib, subprocess
from pathlib import Path
from pymongo import MongoClient
from bson.json_util import dumps
from backend.config import read_settings
s=read_settings(); db=MongoClient(s.mongodb_uri)[s.mongodb_db]
manifest={name:{str(d['_id']):hashlib.sha256(dumps(d,sort_keys=True).encode()).hexdigest() for d in db[name].find()} for name in db.list_collection_names() if name not in ('sessions',)}
p=Path('docs/stage2-baseline.json')
if p.exists(): raise SystemExit('Baseline already exists; refusing overwrite')
p.write_text(json.dumps({'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'status':subprocess.check_output(['git','status','--porcelain'],text=True),'documents':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
print({k:len(v) for k,v in manifest.items()})
