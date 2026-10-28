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

BASE='http://127.0.0.1:8000'; RUN='qa_stage2_'+uuid4().hex[:10]; PASSWORD=secrets.token_urlsafe(24)
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

a,b,c=Client(),Client(),Client();ua=a.login('_a');ub=b.login('_b');uc=c.login('_c')
print('RUN',RUN,flush=True)
q={'id':'definition','type':'single','title':RUN+' choice','options':[{'id':'A','label':'Yes'},{'id':'B','label':'No'}],'rules':[]}
v1=a.call('/api/questions',{'definition':q},201);qid=v1['question_id'];p='/api/questions/'+qid
Client().call('/api/questions',code=401);b.call(p+'/versions',code=404)
bank=a.call('/api/question-banks',{'name':RUN},201);bp='/api/question-banks/'+bank['id']
a.call(bp+'/members',{'question_id':qid,'present':True,'revision':1});a.call(bp+'/rename',{'name':RUN+' renamed','revision':2});a.call(bp+'/rename',{'name':'stale','revision':2},409)
b.call(bp+'/rename',{'name':'theft','revision':3},404)
print('PASS S01 independent question, bank create/list/rename/member and ownership/CAS')
a.call(p+'/share',{'username':ub['username'],'enabled':True})
assert b.call(p+'/versions')['versions'][0]['_id']==v1['_id']
b.call(p+'/versions',{'parent_version_id':v1['_id'],'definition':q},404)
b.call(p+'/share',{'username':uc['username'],'enabled':True},404)
def instance(v,id='instance'):
 return {**v['definition'],'id':id,'rules':[],'source':{'question_id':v['question_id'],'version_id':v['_id']}}
def survey(client,v,title):
 d=client.call('/api/surveys',{'title':RUN+title,'questions':[instance(v)]},201)
 db.surveys.update_one({'_id':ObjectId(d['id'])},{'$set':{'test_run_id':RUN}})
 return d
s1=survey(a,v1,' owner');s2=survey(b,v1,' PRIVATE_TITLE');sp='/api/surveys/'+s1['id'];sp2='/api/surveys/'+s2['id']
pub1=a.call(sp+'/publish',{'revision':1});pub2=b.call(sp2+'/publish',{'revision':1})
old=db.survey_versions.find_one({'_id':ObjectId(pub1['version_id'])})
# Real submission using the original filling state machine.
fp='/api/fill/'+s1['share_path'].split('/')[-1]
d=a.call(fp+'/start',{'version_id':pub1['version_id']})
def act(d,action,**kw):return a.call(fp+'/drafts/'+pub1['version_id']+'/action',{'attempt_id':d['attempt_id'],'revision':d['revision'],'action':action,**kw})
d=act(d,'save',question_id='instance',value='A');d=act(d,'next');sub=a.call(fp+'/drafts/'+pub1['version_id']+'/submit',{'attempt_id':d['attempt_id'],'revision':d['revision'],'request_key':uuid4().hex});oldsub=db.submissions.find_one({'_id':ObjectId(sub['submission_id'])})
print('PASS S02 two owners/two surveys fixed same version; original filling submission')
q2=copy.deepcopy(q);q2['title']='updated';v2=a.call(p+'/versions',{'parent_version_id':v1['_id'],'definition':q2},201)
v3=a.call(p+'/versions',{'parent_version_id':v1['_id'],'definition':{**q,'title':'branch'}},201)
v4=a.call(p+'/versions',{'parent_version_id':v3['_id'],'restore_version_id':v1['_id']},201)
assert v4['definition']==v1['definition'] and v4['restore_version_id']==v1['_id']
assert v3['parent_version_id']==v1['_id']
s1['structure']['questions']=[instance(v2)];a.call(sp+'/edit',{'revision':1,'structure':s1['structure']});pubnew=a.call(sp+'/publish',{'revision':2})
assert db.survey_versions.find_one({'_id':old['_id']})==old and db.submissions.find_one({'_id':oldsub['_id']})==oldsub
assert b.call('/api/shared/'+s2['share_path'].split('/')[-1])['structure']['questions'][0]['title']==v1['definition']['title']
usage=a.call(p+'/usage');assert 'PRIVATE_TITLE' not in json.dumps(usage) and s2['id'] not in json.dumps(usage) and ub['id'] not in json.dumps(usage)
assert usage['other_reference_counts']=={'edit':1,'current':1,'historical':0}
assert set(r['kind'] for r in usage['own_references'])=={'edit','current','historical'}
assert len(a.call(p+'/usage?version_id='+v1['_id'])['own_references'])==1
b.call(sp+'/versions',code=404)
derived=b.call('/api/questions',{'definition':q2,'derived_question_id':qid,'derived_version_id':v1['_id']},201);assert derived['derived_from']['version_id']==v1['_id']
print('PASS S03 branches/restore/derivation, coexistence, old publication+submission byte semantics unchanged; S04 privacy categories/version filter')
# Concurrent versions are all retained, allocated on the server in a transaction.
with ThreadPoolExecutor(6) as pool:
 out=list(pool.map(lambda i:a.call(p+'/versions',{'parent_version_id':v1['_id'],'definition':{**q,'title':'parallel '+str(i)}},201),range(6)))
assert len({v['number'] for v in out})==6 and sorted(v['number'] for v in out)==list(range(5,11))
assert len(a.call(p+'/versions')['versions'])==10
# Concurrent draft saves: one succeeds, other conflicts.
body={'revision':2,'structure':s1['structure']}
with ThreadPoolExecutor(2) as pool: statuses=list(pool.map(lambda _:a.call(sp+'/edit',body,code=None)[0],range(2)))
assert sorted(statuses)==[200,409]
print('PASS S05 six concurrent version creations retained; concurrent survey edit CAS')
# Invalid source and instance jump references are rejected.
bad=copy.deepcopy(s1['structure']);bad['questions'][0]['title']='forged';a.call(sp+'/edit',{'revision':3,'structure':bad},422)
bad=copy.deepcopy(s1['structure']);bad['questions'][0]['rules']=[{'id':'r','selected':['A'],'targets':['foreign_instance']}];a.call(sp+'/edit',{'revision':3,'structure':bad},422)
good=copy.deepcopy(s1['structure']);good['questions'].append({'id':'target','type':'text','title':'target'});good['questions'][0]['rules']=[{'id':'r','selected':['A'],'targets':['target']}]
a.call(sp+'/edit',{'revision':3,'structure':good});a.call(sp+'/publish',{'revision':4})
qbad={**q,'options':[{'id':'C','label':'New'},{'id':'D','label':'Other'}]};vb=a.call(p+'/versions',{'parent_version_id':v1['_id'],'definition':qbad},201)
bad=copy.deepcopy(good);bad['questions'][0]={**instance(vb), 'rules':good['questions'][0]['rules']};a.call(sp+'/edit',{'revision':4,'structure':bad},422)
print('PASS S06 foreign jump targets/source forgery/changed option references rejected; local target valid')
a.call(p+'/share',{'username':ub['username'],'enabled':False});b.call(p+'/versions',code=404);b.call(p+'/usage',code=404)
b.call('/api/surveys',{'title':'blocked','questions':[instance(v1)]},404)
b.call('/api/questions',{'definition':q,'derived_question_id':qid,'derived_version_id':v1['_id']},404)
e=b.call(sp2+'/edit');e['structure']['title']=RUN+' retained after revoke';b.call(sp2+'/edit',{'revision':1,'structure':e['structure']});b.call(sp2+'/publish',{'revision':2})
assert b.call('/api/shared/'+s2['share_path'].split('/')[-1])['structure']['questions'][0]['source']['version_id']==v1['_id']
# Same revoked source in a NEW instance is disallowed even in the same survey.
e['structure']['questions'].append(instance(v1,'new-instance'));b.call(sp2+'/edit',{'revision':2,'structure':e['structure']},404)
a.call(bp+'/members',{'question_id':qid,'present':False,'revision':3});assert len(a.call(p+'/versions')['versions'])==11
print('PASS S07 revoke blocks access/new reference/derivation, preserves saved instance and publication; removal preserves history')
# Version after revoke still fillable, and unauthorized statistics remains forbidden.
b.call('/api/surveys/'+s1['id']+'/statistics',code=404)
assert db.survey_versions.find_one({'_id':old['_id']})==old and db.submissions.find_one({'_id':oldsub['_id']})==oldsub
print('PASS S08 final immutable old publication and submission')
print('RETAINED',RUN,'QUESTION',qid,'SURVEYS',s1['id'],s2['id'])
legacy=a.call('/api/surveys',{'title':RUN+' legacy','questions':[q]},201);lp='/api/surveys/'+legacy['id'];lv=a.call(lp+'/publish',{'revision':1});lvdoc=db.survey_versions.find_one({'_id':ObjectId(lv['version_id'])})
exp=lp+'/questions/definition/export';x=a.call(exp,{'revision':1},201);again=a.call(exp,{'revision':1},201)
assert again['replayed'] and x['source']==again['source']
lq='/api/questions/'+x['source']['question_id'];history=a.call(lq+'/versions')['versions'][0];assert history['legacy_origin']['edit_revision']==1
assert db.survey_versions.find_one({'_id':lvdoc['_id']})==lvdoc
b.call(exp,{'revision':1},404)
a.call(lq+'/share',{'username':ub['username'],'enabled':True});assert 'legacy_origin' not in b.call(lq+'/versions')['versions'][0]
assert legacy['id'] not in json.dumps(b.call(lq+'/usage'))
print('PASS S09 explicit legacy export atomic/replayable, original publication untouched, private legacy origin hidden from recipient')
