"""Idempotently validate/apply stage-two validators and indexes. Never touches old documents."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pymongo import MongoClient
from backend.config import read_settings, ROOT
from backend.surveys import SurveyStore
from backend.questions import indexes
s=read_settings();db=MongoClient(s.mongodb_uri)[s.mongodb_db]
schemas=json.loads((ROOT/'docs/stage2-mongodb-schema.json').read_text(encoding='utf-8'))
for name,schema in schemas.items():
 validator={'$jsonSchema':schema}
 if name in db.list_collection_names():
  invalid=db[name].count_documents({'$nor':[validator]})
  if invalid:raise SystemExit(f'{name}: {invalid} invalid documents; aborted, no destructive repair')
  db.command({'collMod':name,'validator':validator,'validationLevel':'strict','validationAction':'error'})
 else:db.create_collection(name,validator=validator,validationLevel='strict',validationAction='error')
 print('VALIDATED',name,db[name].count_documents({}))
indexes(SurveyStore(db))
print('PASS additive schema/index installation; no legacy collection validator changed')
