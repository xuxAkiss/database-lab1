"""Real HTTP and MongoDB tests. Only adds/later updates this run's labeled QA records."""
import copy
import http.cookiejar
import json
import secrets
import sys
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bson import ObjectId
from fastapi import HTTPException
from pymongo import MongoClient
from pymongo.synchronous.collection import Collection
from backend.config import read_settings
from backend.surveys import SurveyStore, State, state as change_state
from backend.filling import Submit, submit_attempt

BASE='http://127.0.0.1:8000'; RUN='qa_stats_'+uuid4().hex[:10]; PASSWORD=secrets.token_urlsafe(24)
settings=read_settings();mongo=MongoClient(settings.mongodb_uri,tz_aware=True);db=mongo[settings.mongodb_db]
store=SurveyStore(db);store.ensure_indexes()
class Client:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar();self.http=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar));self.csrf=''
    def call(self,path,body=None,code=200):
        headers={'Origin':BASE}
        if body is not None:headers.update({'Content-Type':'application/json','X-CSRF-Token':self.csrf})
        req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:r=self.http.open(req,timeout=20)
        except urllib.error.HTTPError as e:r=e
        with r:
            result=json.load(r)
            if code is not None:assert r.status==code,(path,r.status,result,code)
            return (r.status,result) if code is None else result
    def login(self,suffix):
        self.csrf=self.call('/api/auth/csrf')['csrf_token'];body={'username':RUN+suffix,'password':PASSWORD}
        u=self.call('/api/auth/register',body,201)['user'];self.csrf=self.call('/api/auth/login',body)['csrf_token']
        db.users.update_one({'_id':ObjectId(u['id'])},{'$set':{'test_run_id':RUN,'test_purpose':'statistics integration'}})
        self.user={'_id':ObjectId(u['id'])};return u


a,b=Client(),Client();a.login('_a');b.login('_b')
print('RUN',RUN,flush=True)
options=[{'id':'A','label':'A'},{'id':'B','label':'B'}]
qs=[{'id':'s','type':'single','title':'单选','options':options},
    {'id':'m','type':'multiple','title':'多选','options':options},
    {'id':'t','type':'text','title':'文字'}, {'id':'n','type':'number','title':'数字'}]
structure={'title':RUN,'anonymous':True,'allow_repeat':True,'questions':qs}
s=a.call('/api/surveys',structure,201);sid=s['id'];token=s['share_path'].split('/')[-1]
db.surveys.update_one({'_id':ObjectId(sid)},{'$set':{'test_run_id':RUN}})
root='/api/surveys/'+sid
a.call(root+'/statistics',code=409)
v=a.call(root+'/publish',{'revision':1});vid=v['version_id']

def stats():return a.call(root+'/statistics')
def fill(client,values,previous=None,send=True):
    body={'version_id':vid}
    if previous:body.update(new_attempt=True,previous_attempt_id=previous)
    d=client.call('/api/fill/'+token+'/start',body)
    for qid,value in values.items():
        def action(action,**kw):
            return client.call('/api/fill/'+token+'/drafts/'+vid+'/action',{'attempt_id':d['attempt_id'],'revision':d['revision'],'action':action,**kw})
        if d['current']!=qid:d=action('goto',target=qid)
        d=action('save',question_id=qid,value=value)
    if send:
        d=client.call('/api/fill/'+token+'/drafts/'+vid+'/action',{'attempt_id':d['attempt_id'],'revision':d['revision'],'action':'finish'})
        client.call('/api/fill/'+token+'/drafts/'+vid+'/submit',{'attempt_id':d['attempt_id'],'revision':d['revision'],'request_key':uuid4().hex})
    return d['attempt_id']

empty=stats();assert (empty['submission_count'],empty['participant_count'])==(0,0)
assert all(q['answered_count']==0 for q in empty['questions']);assert empty['questions'][3]['average'] is None
print('PASS no submissions: all zero, numeric average null')
fill(a,{'s':'B','m':['B'],'t':'old version','n':'999'})
a.call(root+'/edit',{'revision':1,'structure':structure});vid=a.call(root+'/publish',{'revision':2})['version_id']
assert stats()['submission_count']==0
first=fill(a,{'s':'B','m':['B'],'t':'superseded','n':'88'})
fill(b,{'s':'A','m':['B'],'t':'beta','n':'4'})
latest=fill(a,{'s':'','m':['A','B'],'t':'','n':'0'},first)
r=stats();assert (r['submission_count'],r['participant_count'])==(3,2)
sq,mq,tq,nq=r['questions']
assert sq['answered_count']==1 and [o['count'] for o in sq['options']]==[1,0]
assert mq['answered_count']==2 and [o['count'] for o in mq['options']]==[1,2]
assert tq['values']==['beta'] and tq['answered_count']==1
assert nq['values']==[0.0,4.0] and nq['valid_count']==2 and nq['average']==2.0
print('EXPECTED total=3 participants=2 single=[1,0]/1 multi=[1,2]/2 text=[beta] numbers=[0,4] avg=2')
print('ACTUAL',json.dumps(r,ensure_ascii=False))
fill(a,{'s':'B','n':'100'},latest,send=False);assert stats()==r
print('PASS pending draft unchanged; old-version 999 and superseded 88 excluded; latest blanks do not backfill')
for q in qs:
    one=a.call(root+'/versions/'+vid+'/statistics/questions/'+q['id']);assert one['questions']==[next(x for x in r['questions'] if x['question_id']==q['id'])]
b.call(root+'/statistics',code=404);b.call(root+'/versions/'+vid+'/statistics/questions/n',code=404)
Client().call(root+'/statistics',code=401)
other=b.call('/api/surveys',structure,201);ov=b.call('/api/surveys/'+other['id']+'/publish',{'revision':1})['version_id']
db.surveys.update_one({'_id':ObjectId(other['id'])},{'$set':{'test_run_id':RUN}})
a.call(root+'/versions/'+ov+'/statistics/questions/n',code=404)
a.call('/api/surveys/'+other['id']+'/statistics',code=404)
a.call(root+'/versions/'+vid+'/statistics/questions/fake',code=404)
forbidden={'user_id','owner_id','username','session','session_id','participations','latest_submission_id','submission_id','request_key','attempt_id','sequence','submitted_at','_id'}
def safe(value):
    if isinstance(value,dict):
        assert not forbidden.intersection(value)
        for v in value.values():safe(v)
    elif isinstance(value,list):
        for v in value:safe(v)
safe(r)
print('PASS whole/single equivalence, anonymous response key audit, two-account ownership and tampered survey/version/question IDs')
e=a.call(root+'/edit');a.call(root+'/state',{'revision':e['state_revision'],'action':'close'});assert stats()==r
e=a.call(root+'/edit');a.call(root+'/state',{'revision':e['state_revision'],'action':'deadline','deadline':'2020-01-01T00:00:00Z'});assert stats()==r
print('PASS closed/expired statistics remain readable')
# New version: blank is excluded, numeric zero is a valid answer.
e=a.call(root+'/edit');a.call(root+'/state',{'revision':e['state_revision'],'action':'deadline','deadline':None})
e=a.call(root+'/edit');a.call(root+'/state',{'revision':e['state_revision'],'action':'reopen'})
a.call(root+'/edit',{'revision':2,'structure':structure});vid=a.call(root+'/publish',{'revision':3})['version_id']
fill(a,{'n':'0'});fill(b,{'n':''})
r3=stats();assert r3['submission_count']==2 and r3['participant_count']==2 and r3['questions'][3]['valid_count']==1 and r3['questions'][3]['average']==0
print('PASS V3 numeric zero plus blank => valid_count=1 average=0; V2 records excluded')
pinned=a.call(root+'/versions/'+r['version_id']+'/statistics/questions/n')
assert pinned['questions']==[nq] and pinned['submission_count']==3
print('PASS pinned V2 single-question remains V2 after current pointer moves to V3')
print('PASS health',a.call('/api/health/live')['status'],a.call('/api/health/database')['status'])
print('SURVEY',sid,'SHARE',s['share_path'])
mongo.close()
