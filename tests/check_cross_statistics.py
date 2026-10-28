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

BASE='http://127.0.0.1:8000'; RUN='qa_cross_'+uuid4().hex[:10]; PASSWORD=secrets.token_urlsafe(24)
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


from backend.question_statistics import cross_statistics, Query
print('RUN',RUN,flush=True)
a,b=Client(),Client();ua=a.login('_a');ub=b.login('_b')
opts=[{'id':'yes','label':'Yes'},{'id':'no','label':'No'}]
defs=[{'id':'n','type':'number','title':RUN+' age','minimum':0,'maximum':1000}, {'id':'s','type':'single','title':'single','options':opts}, {'id':'m','type':'multiple','title':'multi','options':opts}, {'id':'t','type':'text','title':'text'}]
vs=[a.call('/api/questions',{'definition':q},201) for q in defs]
def instance(v,id):return {**v['definition'],'id':id,'rules':[],'source':{'question_id':v['question_id'],'version_id':v['_id']}}
qs=[instance(v,q['id']) for v,q in zip(vs,defs)]
def create(client,label,questions):
 s=client.call('/api/surveys',{'title':RUN+label,'anonymous':True,'allow_repeat':True,'questions':questions},201)
 s['root']='/api/surveys/'+s['id'];s['vid']=client.call(s['root']+'/publish',{'revision':1})['version_id'];s['revision']=1
 db.surveys.update_one({'_id':ObjectId(s['id'])},{'$set':{'test_run_id':RUN}});return s
A=create(a,' A',qs);B=create(a,' B',qs)
attempts={}
def fill(client,s,values,send=True):
 key=(str(client.user['_id']),s['id'],s['vid']);body={'version_id':s['vid']}
 if key in attempts:body.update(new_attempt=True,previous_attempt_id=attempts[key])
 fp='/api/fill/'+s['share_path'].split('/')[-1];d=client.call(fp+'/start',body)
 for qid,value in values.items():
  if d['current']!=qid:d=client.call(fp+'/drafts/'+s['vid']+'/action',{'attempt_id':d['attempt_id'],'revision':d['revision'],'action':'goto','target':qid})
  d=client.call(fp+'/drafts/'+s['vid']+'/action',{'attempt_id':d['attempt_id'],'revision':d['revision'],'action':'save','question_id':qid,'value':value})
 if send:
  d=client.call(fp+'/drafts/'+s['vid']+'/action',{'attempt_id':d['attempt_id'],'revision':d['revision'],'action':'finish'})
  client.call(fp+'/drafts/'+s['vid']+'/submit',{'attempt_id':d['attempt_id'],'revision':d['revision'],'request_key':uuid4().hex})
 attempts[key]=d['attempt_id'];return d

def query(v=vs[0],client=a,selections=None,**kw):return client.call('/api/question-statistics/'+v['question_id']+'/query',{'question_version_id':v['_id'],'selections':selections or [],**kw})
def choose(s,vid=None,instance_id=None):return {'survey_id':s['id'],'survey_version_id':vid or s['vid'],'instance_id':instance_id}
def publish(s,questions,client=a):
 e=client.call(s['root']+'/edit');e['structure']['questions']=questions
 r=client.call(s['root']+'/edit',{'revision':e['revision'],'structure':e['structure']});s['vid']=client.call(s['root']+'/publish',{'revision':r['revision']})['version_id'];return s['vid']
print('EXPECTED C01 no answers: count=0, average=null, rows=[]',flush=True)
r=query();assert r['answered_count']==0 and r['average'] is None and r['rows']==[]
print('PASS C01 empty numeric result')
print('EXPECTED C02 A alpha:10 then 0, A beta:4, B alpha:8 => [0,4,8], count=3, avg=4, frequencies 1 each',flush=True)
fill(a,A,{'n':'10','s':'no','m':['yes'],'t':'old'})
fill(a,A,{'n':'0','s':'yes','m':['yes','no'],'t':'new'})
fill(b,A,{'n':'4','s':'no','m':['no'],'t':'beta'})
fill(a,B,{'n':'8','s':'yes','m':['yes'],'t':'gamma'})
r=query();assert (r['answered_count'],r['average'],r['empty_count'],r['included_survey_count'])==(3,4,0,2)
assert r['rows']==[{'value':0.0,'count':1},{'value':4.0,'count':1},{'value':8.0,'count':1}]
print('ACTUAL C02',json.dumps(r,ensure_ascii=False));print('PASS C02 latest whole submission, zero valid, cross-survey account NOT deduplicated')
print('EXPECTED C03 single counts yes=2 no=1; multi yes=2 no=2; text beta,gamma,new')
assert [o['count'] for o in query(vs[1])['options']]==[2,1]
assert [o['count'] for o in query(vs[2])['options']]==[2,2]
assert query(vs[3])['rows']==['beta','gamma','new']
p1=query(page_size=1);p2=query(page_size=1,page=2);assert p1['average']==p2['average']==4 and p1['rows_total']==3 and p2['rows']==[{'value':4.0,'count':1}]
print('PASS C03 all four types and pagination retains full totals')
print('EXPECTED C04 latest A alpha blank => [4,8], avg=6, empty=1; draft 99 ignored')
fill(a,A,{'n':'','s':'','m':[],'t':''});r=query();assert (r['answered_count'],r['average'],r['empty_count'])==(2,6,1)
fill(a,A,{'n':'99'},send=False);r2=query();assert r2['rows']==r['rows'] and r2['average']==6
print('PASS C04 latest blank no backfill, drafts excluded')
oldA=A['vid'];publish(A,qs);fill(a,A,{'n':'100'})
print('EXPECTED C05 default [100,8] avg54; A historical replaces current => [4,8] avg6')
assert query()['average']==54
history=query(selections=[choose(A,oldA)]);assert history['average']==6 and next(i for i in history['included'] if i['survey_id']==A['id'])['survey_version_id']==oldA
print('PASS C05 current/history publication replacement')
v2=a.call('/api/questions/'+vs[0]['question_id']+'/versions',{'parent_version_id':vs[0]['_id'],'definition':{**defs[0],'title':'age V2'}},201)
publish(A,[instance(v2,'n'),*qs[1:]]);fill(a,A,{'n':'20'})
assert query()['average']==8 and query(v2)['average']==20
restored=a.call('/api/questions/'+vs[0]['question_id']+'/versions',{'parent_version_id':v2['_id'],'restore_version_id':vs[0]['_id']},201);assert query(restored)['answered_count']==0
same=a.call('/api/questions',{'definition':defs[0]},201);der=a.call('/api/questions',{'definition':defs[0],'derived_question_id':vs[0]['question_id'],'derived_version_id':vs[0]['_id']},201)
C=create(a,' same name',[instance(same,'n')]);D=create(a,' derived',[instance(der,'n')]);L=create(a,' legacy',[defs[0]])
fill(a,C,{'n':'888'});fill(a,D,{'n':'999'});fill(a,L,{'n':'555'});assert query()['average']==8
assert any(x['survey_id']==L['id'] and x['reason']=='no_reliable_source' for x in query()['excluded'])
print('PASS C06 question versions/restoration/same-name/derivation/unknown legacy separated')
publish(B,[qs[0],instance(vs[0],'n2')]);fill(a,B,{'n':'2','n2':'6'})
r=query();assert r['average']==2 and r['answered_count']==1 and r['included'][0]['available_instance_ids']==['n','n2']
assert query(selections=[choose(B,instance_id='n2')])['average']==6
path='/api/question-statistics/'+vs[0]['question_id']
a.call(path+'/query',{'question_version_id':vs[0]['_id'],'selections':[choose(B),choose(B)]},422)
a.call(path+'/query',{'question_version_id':vs[0]['_id'],'selections':[choose(B,instance_id='fake')]},422)
print('PASS C07 duplicate instances explicitly selected, never double counted')
a.call('/api/questions/'+vs[0]['question_id']+'/share',{'username':ub['username'],'enabled':True})
secret=create(b,' PRIVATE',[qs[0]]);fill(b,secret,{'n':'777'})
assert query()['average']==2 and query(client=b)['average']==777
for client,s in [(a,secret),(b,B)]:client.call(path+'/query',{'question_version_id':vs[0]['_id'],'selections':[choose(s)]},404)
a.call(path+'/query',{'question_version_id':vs[0]['_id'],'selections':[choose(B,secret['vid'])]},404)
a.call('/api/questions/'+vs[0]['question_id']+'/share',{'username':ub['username'],'enabled':False})
b.call('/api/questions/'+vs[0]['question_id']+'/versions',code=404)
assert query(client=b)['average']==777 and b.call(path+'/scope')['question_versions']
assert 'PRIVATE' not in json.dumps(query()) and secret['id'] not in json.dumps(query())
b.call('/api/question-statistics/'+v2['question_id']+'/query',{'question_version_id':v2['_id']},404)
Client().call(path+'/scope',code=401)
forbidden={'user_id','owner_id','username','session','session_id','submission_id','attempt_id','sequence','request_key','answers','_id'}
def safe(value):
 if isinstance(value,dict):
  assert not forbidden.intersection(value)
  for x in value.values():safe(x)
 elif isinstance(value,list):
  for x in value:safe(x)
safe(query());safe(query(client=b))
bad=copy.deepcopy(qs[0]);bad['title']='forged';a.call('/api/surveys',{'title':RUN+' forged','questions':[bad]},422)
print('PASS C08 ownership, forged publication/source rejection, share is NOT stats grant, revoked own snapshots, anonymous key audit')
for action,extra in [('close',{}),('deadline',{'deadline':'2020-01-01T00:00:00Z'})]:
 e=a.call(B['root']+'/edit');a.call(B['root']+'/state',{'revision':e['state_revision'],'action':action,**extra})
assert query()['average']==2
print('PASS C09 closed and expired still included')
# Real concurrent publication while a snapshot read is between structure and answers.
e=a.call(B['root']+'/edit');a.call(B['root']+'/state',{'revision':e['state_revision'],'action':'deadline','deadline':None})
e=a.call(B['root']+'/edit');a.call(B['root']+'/state',{'revision':e['state_revision'],'action':'reopen'})
original=Collection.aggregate;triggered=[]
def racing(collection,*args,**kwargs):
 if collection.name=='submissions' and not triggered:
  triggered.append(True);publish(B,[qs[0]]);fill(a,B,{'n':'9'})
 return original(collection,*args,**kwargs)
with patch.object(Collection,'aggregate',racing):
 pinned=cross_statistics(store,a.user,vs[0]['question_id'],Query(question_version_id=vs[0]['_id']))
assert triggered and pinned['average']==2 and query()['average']==9
print('PASS C10 real concurrent publish+submit between reads: snapshot avg2, next HTTP query avg9')
from fastapi import HTTPException
with patch('backend.question_statistics.MAX_LATEST',0):
 try:cross_statistics(store,a.user,vs[0]['question_id'],Query(question_version_id=vs[0]['_id']))
 except HTTPException as e:assert e.status_code==413
 else:raise AssertionError('must reject incomplete totals')
print('PASS C11 explicit limit rejects entire result, no partial totals')
Path('.local/cross-test-fixture.json').write_text(json.dumps({'run':RUN,'question_id':vs[0]['question_id'],'question_version_id':vs[0]['_id'],'surveys':[A['id'],B['id']]}),encoding='utf-8')
print('PASS ALL CROSS TESTS',RUN)
