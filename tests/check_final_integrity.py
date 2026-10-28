"""Audit the preserved 022 database snapshot and original stage-one snapshot, read only."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pymongo import MongoClient
from bson import ObjectId
from bson.json_util import dumps
from backend.config import read_settings
s=read_settings();db=MongoClient(s.mongodb_uri)[s.mongodb_db]
for filename in ['docs/stage2-baseline.json','docs/stage2-final-data-baseline.json']:
 m=json.loads(Path(filename).read_text(encoding='utf-8'));m=m.get('documents',m);total=0
 for name,records in m.items():
  for id,expected in records.items():
   d=db[name].find_one({'_id':ObjectId(id)});assert d is not None,(name,id,'missing')
   assert hashlib.sha256(dumps(d,sort_keys=True).encode()).hexdigest()==expected,(name,id,'changed')
   total+=1
 print('PASS',filename,total,'original documents unchanged')
