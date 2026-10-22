"""Real HTTP/MongoDB publication verification; retains labeled QA data, never clears DB."""
import copy
import http.cookiejar
import json
import secrets
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bson import ObjectId
from pymongo import MongoClient
from pymongo.synchronous.collection import Collection
from backend.config import read_settings
from backend.surveys import SurveyStore

BASE='http://127.0.0.1:8000'
RUN='qa_survey_'+uuid4().hex[:10]
PASSWORD=secrets.token_urlsafe(24)
s=read_settings(); mongo=MongoClient(s.mongodb_uri,tz_aware=True); db=mongo[s.mongodb_db]

class Client:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar(); self.http=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar)); self.csrf=''
    def call(self,path,body=None,code=200,csrf=True):
        headers={'Origin':BASE}
        if body is not None: headers.update({'Content-Type':'application/json','X-CSRF-Token':self.csrf if csrf else ''})
        req=urllib.request.Request(BASE+path, data=None if body is None else json.dumps(body).encode(),headers=headers)
        try: response=self.http.open(req,timeout=20)
        except urllib.error.HTTPError as e: response=e
        with response:
            d=json.load(response)
            assert response.status==code,(path,response.status,d,code)
            assert 'password_hash' not in json.dumps(d) and PASSWORD not in json.dumps(d)
            return d
    def login(self,suffix):
        self.csrf=self.call('/api/auth/csrf')['csrf_token']
        creds={'username':RUN+suffix,'password':PASSWORD}
        u=self.call('/api/auth/register',creds,201)['user']
        db.users.update_one({'_id':ObjectId(u['id'])},{'$set':{'test_run_id':RUN,'test_purpose':'survey integration tests'}})
        self.csrf=self.call('/api/auth/login',creds)['csrf_token'];return u

def q(qid,typ):
    d={'id':qid,'type':typ,'title':qid,'required':True,'rules':[]}
    if typ in ('single','multiple'):d['options']=[{'id':'A','label':'有空'},{'id':'B','label':'没空'}]
    return d

def rule(selected,targets,rid='r'):
    return {'id':rid,'selected':selected,'targets':targets,'action':'targets'}

a,b=Client(),Client(); ua=a.login('_a'); ub=b.login('_b')
structure={'title':RUN,'description':'明确标识的集成测试问卷','anonymous':True,'allow_repeat':False,
           'questions':[q('q1','single'),q('q2','multiple'),q('q3','text'),q('q4','number')]}
structure['questions'][0]['rules']=[rule(['A'],['q3'])]
structure['questions'][1].update({'min_choices':1,'max_choices':2,'rules':[rule(['A','B'],['q4','q3','q4'])]})
structure['questions'][2].update({'min_length':1,'max_length':100})
structure['questions'][3].update({'minimum':0,'maximum':10,'integer_only':True,'rules':[{'id':'n','operator':'gte','value':5,'action':'end'}]})
Client().call('/api/surveys',code=401)
a.call('/api/surveys',structure,403,csrf=False)
c=a.call('/api/surveys',structure,201); sid=c['id']; path='/api/surveys/'+sid; shared='/api/shared/'+c['share_path'].split('/')[-1]
db.surveys.update_one({'_id':ObjectId(sid)},{'$set':{'test_run_id':RUN}})
assert b.call('/api/surveys')['surveys']==[]
for endpoint in ['/edit','/versions']:b.call(path+endpoint,code=404)
for endpoint,body in [('/edit',{'revision':1,'structure':structure}),('/publish',{'revision':1}),('/state',{'revision':1,'action':'close'})]:b.call(path+endpoint,body,404)
b.call('/api/surveys/not-an-id/edit',code=404)
b.call(shared,code=409)
print('PASS ownership, ID tampering, CSRF, unauthenticated and unpublished access')

v1=a.call(path+'/publish',{'revision':1}); old=db.survey_versions.find_one({'_id':ObjectId(v1['version_id'])})
public=b.call(shared); assert public['version_id']==v1['version_id']; assert 'owner_id' not in public and 'edit_revision' not in public
assert public['structure']['questions'][1]['rules'][0]['targets']==['q3','q4']
structure['title']=RUN+' V2'; structure['anonymous']=False
save=a.call(path+'/edit',{'revision':1,'structure':structure});assert save['revision']==2
assert b.call(shared)['structure']['title']==RUN
with ThreadPoolExecutor(2) as pool:
    pubs=list(pool.map(lambda _:a.call(path+'/publish',{'revision':2}),range(2)))
assert pubs[0]['version_id']==pubs[1]['version_id']
assert db.survey_versions.count_documents({'survey_id':ObjectId(sid)})==2
assert b.call(shared)['structure']['title']==RUN+' V2'
assert db.survey_versions.find_one({'_id':old['_id']})==old
assert a.call(path+'/publish',{'revision':1})['replayed']
assert b.call(shared)['version_number']==2
print('PASS V1 immutable, unpublished edits isolated, fixed link V2, concurrent/idempotent publication')

# Concurrent saves of the same revision: exactly one wins; inspect HTTP directly through expected alternatives.
def saving():
    try: a.call(path+'/edit',{'revision':2,'structure':structure});return 200
    except AssertionError as e:
        assert e.args[0][1]==409,e
        return 409
with ThreadPoolExecutor(2) as pool: results=list(pool.map(lambda _:saving(),range(2)))
assert sorted(results)==[200,409]
rev=a.call(path+'/edit')['revision']; assert rev==3
print('PASS concurrent saves return one success and one conflict')

bad=copy.deepcopy(structure);bad['questions'][0]['rules'][0]['targets']=['q1']
a.call(path+'/edit',{'revision':rev,'structure':bad},422)
# Only QA edit gets a malformed structure, simulating stale/bypassed stored data to test publication validation.
db.survey_edits.update_one({'_id':ObjectId(sid)},{'$set':{'structure':bad}})
a.call(path+'/publish',{'revision':rev},422)
assert db.survey_versions.count_documents({'survey_id':ObjectId(sid)})==2
assert b.call(shared)['version_number']==2
db.survey_edits.update_one({'_id':ObjectId(sid)},{'$set':{'structure':structure}})
for mutate in ['cycle','missing','option','duplicate','mixed','overlap']:
    bad=copy.deepcopy(structure)
    if mutate=='cycle':bad['questions'][3]['rules']=[{'id':'n','operator':'gte','value':5,'action':'targets','targets':['q1']}];bad['questions'][0]['rules'][0]['targets']=['q4']
    if mutate=='missing':bad['questions'][0]['rules'][0]['targets']=['absent']
    if mutate=='option':bad['questions'][0]['rules'][0]['selected']=['absent']
    if mutate=='duplicate':bad['questions'][0]['rules'].append(rule(['A'],['q4'],'r2'))
    if mutate=='mixed':bad['questions'][0]['rules'][0]['action']='end'
    if mutate=='overlap':bad['questions'][3]['rules'].append({'id':'n2','operator':'gt','value':6,'action':'end'})
    result=a.call(path+'/edit',{'revision':rev,'structure':bad},422);assert result['errors'][0]['field'].startswith('questions')
print('PASS invalid publication leaves V2 intact; self/cycle/reference/duplicate/mixed/overlap validation')

# Execute actual publication transaction, fail immediately AFTER its version insert, assert entire transaction rolled back.
store=SurveyStore(db);store.ensure_indexes(); original=Collection.insert_one
before=db.surveys.find_one({'_id':ObjectId(sid)});edit_before=db.survey_edits.find_one({'_id':ObjectId(sid)})
def injected(collection,*args,**kwargs):
    result=original(collection,*args,**kwargs)
    if collection.name=='survey_versions':raise RuntimeError('QA injected failure after actual version insert')
    return result
with patch.object(Collection,'insert_one',injected):
    try:store.publish(sid,{'_id':ObjectId(ua['id'])},rev)
    except RuntimeError as error:assert str(error).startswith('QA injected')
    else:raise AssertionError('Expected injected failure')
assert db.surveys.find_one({'_id':ObjectId(sid)})==before
assert db.survey_edits.find_one({'_id':ObjectId(sid)})==edit_before
assert db.survey_versions.count_documents({'survey_id':ObjectId(sid)})==2
print('PASS real transaction rollback after version insert (no public fault endpoint)')

def state(action,deadline=None,code=200):
    e=a.call(path+'/edit');body={'revision':e['state_revision'],'action':action}
    if action=='deadline':body['deadline']=deadline
    return a.call(path+'/state',body,code)
state('close');b.call(shared,code=409)
v3=a.call(path+'/publish',{'revision':rev});assert v3['number']==3
assert a.call(path+'/edit')['closed'];b.call(shared,code=409)
state('reopen');assert b.call(shared)['version_number']==3
past=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat();state('deadline',past)
assert b.call(shared,code=409)['code']=='expired'
state('reopen',code=409)
state('deadline',None);state('reopen');b.call(shared)
a.call('/api/health/live');a.call('/api/health/database');assert a.call('/api/auth/me')['user']['id']==ua['id'];assert b.call('/api/auth/me')['user']['id']==ub['id']
bad=copy.deepcopy(structure);bad['questions'][2]['max_length']=-1
result=a.call(path+'/edit',{'revision':rev,'structure':bad},422)
assert 'max_length' in result['errors'][0]['field']
# Save twice: an unpublished stale revision must not publish an unintended newer edit.
a.call(path+'/edit',{'revision':rev,'structure':structure})
a.call(path+'/edit',{'revision':rev+1,'structure':structure})
a.call(path+'/publish',{'revision':rev+1},409)
state('close')
future=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(); state('deadline',future)
prior_state=a.call(path+'/edit')
v4=a.call(path+'/publish',{'revision':rev+2});assert v4['number']==4
latest=a.call(path+'/edit');assert latest['deadline']==prior_state['deadline'] and latest['closed']
a.call(path+'/state',{'action':'reopen','revision':prior_state['state_revision']},409)
state('deadline',None);state('reopen')
print('PASS field-specific errors, stale unpublished revision rejection, deadline preserved on publication, state revision conflict')
a.call('/api/auth/logout',{});a.call(path+'/edit',code=401)
print('PASS close, publication preserves closed, deadline/reopen, auth and health regression')
print('RETAINED TEST RUN',RUN,'SURVEY',sid,'SHARE',c['share_path'])
mongo.close()
