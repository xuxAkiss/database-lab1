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

BASE='http://127.0.0.1:8000'; RUN='qa_fill_'+uuid4().hex[:10]; PASSWORD=secrets.token_urlsafe(24)
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
        db.users.update_one({'_id':ObjectId(u['id'])},{'$set':{'test_run_id':RUN,'test_purpose':'filling integration'}})
        self.user={'_id':ObjectId(u['id'])};return u

a,b=Client(),Client();a.login('_a');b.login('_b')
print('START TEST_RUN',RUN,flush=True)

def create(label,repeat=False,questions=None):
    structure={'title':RUN+' '+label,'anonymous':True,'allow_repeat':repeat,'questions':questions or [{'id':'q','type':'text','title':'可选文字','required':False}]}
    s=a.call('/api/surveys',structure,201);sid=s['id'];v=a.call('/api/surveys/'+sid+'/publish',{'revision':1})
    db.surveys.update_one({'_id':ObjectId(sid)},{'$set':{'test_run_id':RUN}})
    return {'sid':sid,'token':s['share_path'].split('/')[-1],'vid':v['version_id'],'structure':structure}

def base(f):return '/api/fill/'+f['token']
def start(f,client=a,**extra):return client.call(base(f)+'/start',{'version_id':f['vid'],**extra})
def act(f,d,action,client=a,code=200,**kw):return client.call(base(f)+'/drafts/'+f['vid']+'/action',{'attempt_id':d['attempt_id'],'revision':d['revision'],'action':action,**kw},code)
def intent(d):return {'attempt_id':d['attempt_id'],'revision':d['revision'],'request_key':uuid4().hex}
def submit(f,p,client=a,code=200):return client.call(base(f)+'/drafts/'+f['vid']+'/submit',p,code)
def ready(f):return act(f,start(f),'finish')
def key(f):return {'survey_id':ObjectId(f['sid']),'version_id':ObjectId(f['vid']),'user_id':a.user['_id']}

options=[{'id':'A','label':'A'},{'id':'B','label':'B'}]
qs=[{'id':'s','type':'single','title':'是否参加','required':True,'options':options,'rules':[{'id':'r','selected':['A'],'targets':['t']}]},
    {'id':'m','type':'multiple','title':'选择两个活动','required':True,'options':options,'exact_choices':2},
    {'id':'t','type':'text','title':'建议','required':True,'min_length':2,'max_length':20},
    {'id':'n','type':'number','title':'人数','required':True,'minimum':1,'maximum':3,'integer_only':True}]
f=create('four types and history',True,qs);d=start(f)
Client().call(base(f),code=401)
b.call(base(f)+'/drafts/'+f['vid'],code=404)
b.call(base(f)+'/drafts/'+f['vid']+'/action',{'attempt_id':d['attempt_id'],'revision':1,'action':'finish'},409)
a.call(base(f)+'/drafts/'+f['vid']+'/action',{'attempt_id':d['attempt_id'],'revision':1,'action':'finish','visited':['s']},422)
d=act(f,d,'save',question_id='s',value='A');d=act(f,d,'next');assert d['current']=='t'
d=act(f,d,'save',question_id='t',value='中');assert a.call(base(f))['draft']['answers']['t']=='中'
act(f,d,'next',code=422)
d=act(f,d,'save',question_id='t',value=' 中\t文 ');d=act(f,d,'next');assert d['current']=='m'
act(f,d,'save',question_id='m',value=['A','A'],code=422)
d=act(f,d,'save',question_id='m',value=['B','A']);d=act(f,d,'next');assert d['current']=='n'
d=act(f,d,'save',question_id='n',value='-');act(f,d,'next',code=422)
d=act(f,d,'save',question_id='n',value='2');d=act(f,d,'next');assert d['ended']
p1=intent(d);r1=submit(f,p1);assert r1['sequence']==1
old=db.submissions.find_one({'_id':ObjectId(r1['submission_id'])})
d2=start(f,new_attempt=True,previous_attempt_id=d['attempt_id']);assert d2['answers']=={}
assert db.participations.find_one(key(f))['latest_submission_id']==old['_id']
act(f,d,'save',question_id='s',value='B',code=409)
for qid,value in [('s','B'),('m',['A','B']),('t','新版答案'),('n','3')]:
    assert d2['current']==qid;d2=act(f,d2,'save',question_id=qid,value=value);d2=act(f,d2,'next')
r2=submit(f,intent(d2));assert r2['sequence']==2
assert db.submissions.count_documents(key(f))==2 and db.submissions.find_one({'_id':old['_id']})==old
assert str(db.participations.find_one(key(f))['latest_submission_id'])==r2['submission_id']
assert submit(f,p1)==r1
submit(f,{**p1,'revision':p1['revision']+1},code=409)
print('PASS four input types, incomplete autosave/recovery, backend boundaries, privacy, two independent histories/latest reference, consumed-attempt rejection, idempotency')

f2=create('concurrent saves');d=start(f2)
with ThreadPoolExecutor(2) as pool:
    results=list(pool.map(lambda text:act(f2,d,'save',question_id='q',value=text,code=None),['one','two']))
assert sorted(s for s,_ in results)==[200,409]
print('PASS concurrent draft CAS: one save succeeds, one conflicts')

f3=create('no repeat concurrent');d=ready(f3)
with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:submit(f3,intent(d),code=None),range(2)))
assert sorted(s for s,_ in results)==[200,409]
assert db.submissions.count_documents(key(f3))==1
start_body={'version_id':f3['vid'],'new_attempt':True,'previous_attempt_id':d['attempt_id']}
a.call(base(f3)+'/start',start_body,409)
print('PASS no-repeat concurrent submissions: only one successful history')

f4=create('same key concurrent');d=ready(f4);p=intent(d)
with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:submit(f4,p),range(2)))
assert results[0]==results[1] and db.submissions.count_documents(key(f4))==1
print('PASS concurrent same-key requests return one identical result')

f5=create('transaction rollback');d=ready(f5);p=intent(d)
before_d=db.fill_drafts.find_one(key(f5));before_p=db.participations.find_one(key(f5));before_s=db.surveys.find_one({'_id':ObjectId(f5['sid'])})
original=Collection.insert_one
def fault(collection,*args,**kwargs):
    r=original(collection,*args,**kwargs)
    if collection.name=='submissions':raise RuntimeError('QA failure after actual submission insert')
    return r
with patch.object(Collection,'insert_one',fault):
    try:submit_attempt(store,f5['token'],f5['vid'],a.user,Submit(**p))
    except RuntimeError:pass
    else:raise AssertionError('Expected transaction fault')
assert db.submissions.count_documents(key(f5))==0
assert db.fill_drafts.find_one(key(f5))==before_d and db.participations.find_one(key(f5))==before_p and db.surveys.find_one({'_id':ObjectId(f5['sid'])})==before_s
submit(f5,p)
print('PASS actual MongoDB transaction failure rolls back history, participation, draft consumption and survey coordination')

f6=create('late save vs submission');d0=start(f6);d=act(f6,d0,'finish')
with ThreadPoolExecutor(2) as pool:
    late=pool.submit(act,f6,d0,'save',question_id='q',value='late',code=None)
    sent=pool.submit(submit,f6,intent(d))
    assert late.result()[0]==409;sent.result()
assert db.fill_drafts.find_one(key(f6))['status']=='submitted'
# Legal same-revision navigation and submission also cannot both succeed.
f7=create('navigation vs submission');d=ready(f7)
with ThreadPoolExecutor(2) as pool:
    nav=pool.submit(act,f7,d,'goto',target='q',code=None);send=pool.submit(submit,f7,intent(d),code=None)
    assert sorted([nav.result()[0],send.result()[0]])==[200,409]
print('PASS stale save cannot revive consumed draft; competing current-revision navigation/submission serialize')

# Deterministic real transactions: hold the first transaction AFTER its actual DB write.
def controlled_order(first_kind, other_kind):
    fixture=create(first_kind+' then '+other_kind);d=ready(fixture);p=intent(d)
    edit=a.call('/api/surveys/'+fixture['sid']+'/edit')
    edited=copy.deepcopy(edit['structure']);edited['title']+=' next'
    a.call('/api/surveys/'+fixture['sid']+'/edit',{'revision':edit['revision'],'structure':edited})
    revision=edit['revision']+1
    acquired=threading.Event();release=threading.Event();second_started=threading.Event();second_read=threading.Event()
    def run(kind):
        if kind=='submit':return submit_attempt(store,fixture['token'],fixture['vid'],a.user,Submit(**p))
        if kind=='publish':return store.publish(fixture['sid'],a.user,revision)
        s=db.surveys.find_one({'_id':ObjectId(fixture['sid'])})
        return change_state(fixture['sid'],State(revision=s['state_revision'],action='close'),a.user,store)
    method={'submit':'insert_one','publish':'update_one','close':'find_one_and_update'}[first_kind]
    orig=getattr(Collection,method)
    def gate(collection,*args,**kwargs):
        result=orig(collection,*args,**kwargs)
        hit=(first_kind=='submit' and collection.name=='submissions') or (first_kind=='publish' and collection.name=='surveys' and 'currentVersionId' in args[1].get('$set',{})) or (first_kind=='close' and collection.name=='surveys' and args[1].get('$set',{}).get('closed') is True)
        if hit and threading.current_thread().name.endswith('_0') and not acquired.is_set():
            acquired.set();assert release.wait(5),'test gate timed out'
        return result
    read_original=Collection.find_one
    def observe_read(collection,*args,**kwargs):
        result=read_original(collection,*args,**kwargs)
        if collection.name=='surveys' and kwargs.get('session') is not None and threading.current_thread().name.endswith('_1') and not second_read.is_set():
            assert result['currentVersionId']==ObjectId(fixture['vid']) and not result['closed']
            second_read.set()
        return result
    def second():
        second_started.set()
        try:return (200,run(other_kind))
        except HTTPException as e:return (e.status_code,e.detail)
    with patch.object(Collection,method,gate),patch.object(Collection,'find_one',observe_read),ThreadPoolExecutor(2,thread_name_prefix='ordered') as pool:
        first=pool.submit(run,first_kind)
        assert acquired.wait(5),'first transaction did not acquire tested write'
        other=pool.submit(second);assert second_started.wait(2)
        assert second_read.wait(3),'second transaction did not read the old survey snapshot while first held its write'
        release.set();first_result=first.result(timeout=15);other_code,other_result=other.result(timeout=15)
    if first_kind=='submit':
        assert other_code==200 and db.submissions.count_documents(key(fixture))==1
        # Already successful old-version submission can be retried after switch/close.
        replay=submit(fixture,p)
        assert all(replay[k]==first_result[k] for k in ('submission_id','version_id','sequence'))
        assert datetime.fromisoformat(replay['submitted_at'])==first_result['submitted_at']
    else:
        assert other_code==409 and db.submissions.count_documents(key(fixture))==0
        assert db.fill_drafts.find_one(key(fixture))['status']=='active'
    if 'publish' in (first_kind,other_kind):
        prior=a.call(base(fixture)+'/drafts/'+fixture['vid']);assert prior['draft']['read_only']
        current=a.call(base(fixture));assert current['version_id']!=fixture['vid'] and current['draft'] is None and current['submission_count']==0
        a.call(base(fixture)+'/start',{'version_id':current['version_id']})
        assert a.call(base(fixture))['draft']['answers']=={}
    print('PASS controlled real transaction order (second transaction observed stale snapshot):',first_kind,'before',other_kind)

for first,second in [('submit','publish'),('publish','submit'),('submit','close'),('close','submit')]:controlled_order(first,second)

f8=create('deadline reopen');d=ready(f8);s=a.call('/api/surveys/'+f8['sid']+'/edit')
a.call('/api/surveys/'+f8['sid']+'/state',{'revision':s['state_revision'],'action':'deadline','deadline':(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat()})
submit(f8,intent(d),code=409);assert a.call(base(f8))['draft']['read_only']
s=a.call('/api/surveys/'+f8['sid']+'/edit');a.call('/api/surveys/'+f8['sid']+'/state',{'revision':s['state_revision'],'action':'deadline','deadline':None})
assert a.call(base(f8))['draft']['attempt_id']==d['attempt_id'];submit(f8,intent(d))
print('PASS expired submission rejected; same-version deadline recovery preserves original draft')

endqs=[{'id':'s','type':'single','title':'结束条件','required':True,'options':options,'rules':[{'id':'end','selected':['A'],'action':'end','targets':[]}]},
       {'id':'t','type':'text','title':'未访必答','required':True,'min_length':2},
       {'id':'optional','type':'text','title':'未访可选'}]
endf=create('end required supplement',False,endqs);endd=start(endf)
endd=act(endf,endd,'save',question_id='s',value='A');endd=act(endf,endd,'next')
assert endd['ended'] and endd['visited']==['s']
submit(endf,intent(endd),code=422)
act(endf,endd,'goto',target='optional',code=409)
endd=act(endf,endd,'goto',target='t');endd=act(endf,endd,'save',question_id='t',value='补答')
endd=act(endf,endd,'finish');submit(endf,intent(endd))
print('PASS real end-action submission validation and restricted required-question supplement')
closef=create('close same-version recovery');closedraft=start(closef)
closedraft=act(closef,closedraft,'save',question_id='q',value='保留内容')
state_before=a.call('/api/surveys/'+closef['sid']+'/edit')
closed=a.call('/api/surveys/'+closef['sid']+'/state',{'revision':state_before['state_revision'],'action':'close'})
act(closef,closedraft,'save',question_id='q',value='不应存入',code=409)
assert a.call(base(closef))['draft']['answers']['q']=='保留内容'
a.call('/api/surveys/'+closef['sid']+'/state',{'revision':closed['state_revision'],'action':'reopen'})
recovered=a.call(base(closef))['draft'];assert not recovered['read_only'] and recovered['attempt_id']==closedraft['attempt_id'] and recovered['revision']==closedraft['revision']
print('PASS close pauses saves; same-version reopen restores the exact original draft')

browser=create('BROWSER filling fixture',True,qs)
print('TEST_RUN',RUN)
print('BROWSER_SHARE', '/s/'+browser['token'])
a.call('/api/health/live');a.call('/api/health/database');b.call('/api/auth/me')
mongo.close()
