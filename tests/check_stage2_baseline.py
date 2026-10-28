"""Read-only old-document integrity audit; compares only IDs captured before stage two."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bson import ObjectId
from bson.json_util import dumps
from pymongo import MongoClient
from backend.config import read_settings
s=read_settings();db=MongoClient(s.mongodb_uri)[s.mongodb_db]
baseline=json.loads(Path('docs/stage2-baseline.json').read_text(encoding='utf-8'))
failed=[]
for name,records in baseline['documents'].items():
 for id,expected in records.items():
  doc=db[name].find_one({'_id':ObjectId(id)})
  if doc is None or hashlib.sha256(dumps(doc,sort_keys=True).encode()).hexdigest()!=expected:failed.append((name,id))
 print(name,len(records),'original records checked')
assert not failed,failed
print('PASS all original non-session records retained and hashes unchanged')
