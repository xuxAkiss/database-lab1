"""Independent immutable question versions; original survey store remains authoritative."""
from copy import deepcopy
from typing import Literal
from bson import ObjectId
from fastapi import APIRouter, Depends
from pydantic import Field, StrictInt
from pymongo import ReturnDocument
from backend.auth import require_user, require_mutating_user, utcnow, fail
from backend.surveys import get_store, oid
from backend.survey_models import Model, Question, validate_structure

router = APIRouter(prefix='/api', tags=['question-library'])

def definition(q):
    return {k: v for k,v in q.items() if k not in ('id','rules','source')}

def clean(body):
    q=body.model_dump() if isinstance(body, Question) else body
    if q.get('rules') or q.get('source'):
        fail(422,'instance_only','独立题目不接受问卷跳转或来源字段。')
    return definition(validate_structure({'title':'validation','questions':[q]})['questions'][0])

def indexes(store):
    db=store.db
    db.questions.create_index('owner_id')
    db.questions.create_index('shared_with')
    db.question_versions.create_index([('question_id',1),('number',1)],unique=True)
    db.question_banks.create_index('owner_id')
    for name in ('survey_edits','survey_versions'):
        db[name].create_index('structure.questions.source.question_id')

def accessible(store,qid,user,session=None,write=False,fence=False):
    query={'_id':oid(qid)}
    query.update({'owner_id':user['_id']} if write else {'$or':[{'owner_id':user['_id']},{'shared_with':user['_id']}]})
    q=(store.db.questions.find_one_and_update(query,{'$inc':{'access_fence':1}},session=session,return_document=ReturnDocument.AFTER)
       if fence else store.db.questions.find_one(query,session=session))
    if not q: fail(404,'not_found','题目不存在或无权访问。')
    return q

def version(store,qid,vid,session=None):
    v=store.db.question_versions.find_one({'_id':oid(vid),'question_id':oid(qid)},session=session)
    if not v: fail(404,'not_found','题目版本不存在。')
    return v

def public(v):
    # A shared question does not disclose its author's private legacy survey ID.
    v = {k:x for k,x in v.items() if k != 'legacy_origin'}
    return {k:(str(x) if isinstance(x,ObjectId) else x) for k,x in v.items()}

def verify_sources(store,data,user,prior=None,session=None):
    previous={q['id']:q for q in (prior or {}).get('questions',[])}
    for q in data['questions']:
        source=q.get('source')
        if not source: continue
        old=previous.get(q['id'])
        if old and old.get('source')==source and definition(old)==definition(q): continue
        accessible(store,source['question_id'],user,session,fence=True)
        v=version(store,source['question_id'],source['version_id'],session)
        if definition(q)!=v['definition']:
            fail(422,'source_mismatch','题目内容与固定版本不符；请先创建新版或明确解除来源。')

class New(Model):
    definition: Question
    derived_question_id: str | None = None
    derived_version_id: str | None = None

class Revision(Model):
    parent_version_id: str
    definition: Question | None = None
    restore_version_id: str | None = None

class Share(Model):
    username: str
    enabled: bool

class Bank(Model):
    name: str = Field(min_length=1,max_length=100)

class BankChange(Bank):
    revision: StrictInt = Field(ge=1)

class Member(Model):
    question_id: str
    present: bool
    revision: StrictInt = Field(ge=1)

@router.post('/questions',status_code=201)
def create(body:New,user=Depends(require_mutating_user),store=Depends(get_store)):
    indexes(store); content=clean(body.definition); qid=ObjectId(); vid=ObjectId()
    def tx(session):
        origin=None
        if body.derived_question_id or body.derived_version_id:
            if not body.derived_question_id or not body.derived_version_id: fail(422,'invalid_source','派生需同时指定题目及版本。')
            accessible(store,body.derived_question_id,user,session,fence=True)
            version(store,body.derived_question_id,body.derived_version_id,session)
            origin={'question_id':body.derived_question_id,'version_id':body.derived_version_id}
        store.db.questions.insert_one({'_id':qid,'owner_id':user['_id'],'shared_with':[], 'number':1,'created_at':utcnow()},session=session)
        v={'_id':vid,'question_id':qid,'number':1,'definition':content,'parent_version_id':None,'restore_version_id':None,'derived_from':origin,'created_at':utcnow()}
        store.db.question_versions.insert_one(v,session=session)
        return public(v)
    return store.transaction(tx)

@router.get('/questions')
def listing(user=Depends(require_user),store=Depends(get_store)):
    indexes(store); result=[]
    for q in store.db.questions.find({'$or':[{'owner_id':user['_id']},{'shared_with':user['_id']}]}):
        v=store.db.question_versions.find_one({'question_id':q['_id'],'number':q['number']})
        result.append({'id':str(q['_id']),'owned':q['owner_id']==user['_id'],'latest':public(v)})
    return {'questions':result}

@router.get('/questions/{qid}/versions')
def history(qid:str,user=Depends(require_user),store=Depends(get_store)):
    q=accessible(store,qid,user)
    return {'versions':[{**public(v), **({'legacy_origin':v['legacy_origin']} if q['owner_id']==user['_id'] and v.get('legacy_origin') else {})} for v in store.db.question_versions.find({'question_id':oid(qid)}).sort('number',1)]}

@router.post('/questions/{qid}/versions',status_code=201)
def revise(qid:str,body:Revision,user=Depends(require_mutating_user),store=Depends(get_store)):
    if (body.definition is None)==(body.restore_version_id is None): fail(422,'invalid_input','修改内容与恢复来源必须二选一。')
    content=clean(body.definition) if body.definition else None
    def tx(session):
        accessible(store,qid,user,session,write=True)
        version(store,qid,body.parent_version_id,session)
        data=content if content is not None else version(store,qid,body.restore_version_id,session)['definition']
        q=store.db.questions.find_one_and_update({'_id':oid(qid)}, {'$inc':{'number':1}},session=session,return_document=ReturnDocument.AFTER)
        v={'_id':ObjectId(),'question_id':q['_id'],'number':q['number'],'definition':data,'parent_version_id':body.parent_version_id,'restore_version_id':body.restore_version_id,'derived_from':None,'created_at':utcnow()}
        store.db.question_versions.insert_one(v,session=session); return public(v)
    return store.transaction(tx)

@router.post('/questions/{qid}/share')
def sharing(qid:str,body:Share,user=Depends(require_mutating_user),store=Depends(get_store)):
    accessible(store,qid,user,write=True)
    target=store.db.users.find_one({'username':body.username.strip().lower()})
    if not target: fail(404,'user_missing','指定的注册账号不存在。')
    store.db.questions.update_one({'_id':oid(qid),'owner_id':user['_id']},{'$addToSet' if body.enabled else '$pull':{'shared_with':target['_id']}})
    return {'shared':body.enabled}

@router.get('/questions/{qid}/shares')
def shares(qid:str,user=Depends(require_user),store=Depends(get_store)):
    q=accessible(store,qid,user,write=True)
    return {'usernames':[u['username'] for u in store.db.users.find({'_id':{'$in':q['shared_with']}})]}

@router.get('/questions/{qid}/usage')
def usage(qid:str,version_id:str|None=None,user=Depends(require_user),store=Depends(get_store)):
    accessible(store,qid,user)
    if version_id: version(store,qid,version_id)
    mine=[]; counts={'edit':0,'current':0,'historical':0}
    for name in ('survey_edits','survey_versions'):
        for doc in store.db[name].find({'structure.questions.source.question_id':qid}):
            sid=doc['_id'] if name=='survey_edits' else doc['survey_id']
            s=store.db.surveys.find_one({'_id':sid})
            if not s: continue
            kind='edit' if name=='survey_edits' else ('current' if s['currentVersionId']==doc['_id'] else 'historical')
            for q in doc['structure']['questions']:
                src=q.get('source') or {}
                if src.get('question_id')!=qid or (version_id and src.get('version_id')!=version_id): continue
                if s['owner_id']==user['_id']:
                    mine.append({'survey_id':str(sid),'title':doc['structure']['title'],'kind':kind,'instance_id':q['id'],'version_id':src['version_id'],'survey_version':doc.get('number'),'edit_revision':doc.get('revision')})
                else: counts[kind]+=1
    return {'own_references':mine,'other_reference_counts':counts}

@router.post('/question-banks',status_code=201)
def bank_create(body:Bank,user=Depends(require_mutating_user),store=Depends(get_store)):
    indexes(store)
    if not body.name.strip(): fail(422,'invalid_input','题库名称不能为空。')
    d={'owner_id':user['_id'],'name':body.name,'question_ids':[],'revision':1}
    result=store.db.question_banks.insert_one(d);return {'id':str(result.inserted_id),'revision':1}

@router.get('/question-banks')
def banks(user=Depends(require_user),store=Depends(get_store)):
    return {'banks':[{'id':str(b['_id']),'name':b['name'],'question_ids':b['question_ids'],'revision':b['revision']} for b in store.db.question_banks.find({'owner_id':user['_id']})]}

def change_bank(store,bid,user,rev,update,session=None):
    b=store.db.question_banks.find_one({'_id':oid(bid),'owner_id':user['_id']},session=session)
    if not b: fail(404,'not_found','题库不存在。')
    result=store.db.question_banks.update_one({'_id':b['_id'],'revision':rev},{**update,'$inc':{'revision':1}},session=session)
    if not result.modified_count: fail(409,'bank_conflict','题库已修改，请刷新。')
    return {'revision':rev+1}

@router.post('/question-banks/{bid}/rename')
def rename(bid:str,body:BankChange,user=Depends(require_mutating_user),store=Depends(get_store)):
    if not body.name.strip(): fail(422,'invalid_input','名称不能为空。')
    return change_bank(store,bid,user,body.revision,{'$set':{'name':body.name}})

@router.post('/question-banks/{bid}/members')
def member(bid:str,body:Member,user=Depends(require_mutating_user),store=Depends(get_store)):
    def tx(session):
        if body.present: accessible(store,body.question_id,user,session,fence=True)
        return change_bank(store,bid,user,body.revision,{'$addToSet' if body.present else '$pull':{'question_ids':body.question_id}},session)
    return store.transaction(tx)
class Export(Model):
    revision: StrictInt = Field(ge=1)

@router.post('/surveys/{sid}/questions/{instance_id}/export',status_code=201)
def export_legacy(sid:str,instance_id:str,body:Export,user=Depends(require_mutating_user),store=Depends(get_store)):
    """Idempotent explicit association of a saved legacy edit; never touches publications."""
    indexes(store)
    def tx(session):
        store.owned(sid,user,session)
        edit=store.db.survey_edits.find_one({'_id':oid(sid)},session=session)
        q=next((q for q in edit['structure']['questions'] if q['id']==instance_id),None)
        if not q: fail(404,'not_found','编辑稿题目不存在。')
        if q.get('source'):
            # Retry only the exact export performed on this edit revision.
            v=version(store,q['source']['question_id'],q['source']['version_id'],session)
            if v.get('legacy_origin')=={'survey_id':sid,'edit_revision':body.revision,'instance_id':instance_id}:
                return {'source':q['source'],'revision':edit['revision'],'replayed':True}
            fail(409,'already_linked','该题已有来源，请使用版本或派生功能。')
        if edit['revision']!=body.revision: fail(409,'edit_conflict','编辑稿已变化，请刷新。')
        normalized=validate_structure(edit['structure'])
        q=next(q for q in normalized['questions'] if q['id']==instance_id)
        qid,vid=ObjectId(),ObjectId()
        store.db.questions.insert_one({'_id':qid,'owner_id':user['_id'],'shared_with':[],'number':1,'created_at':utcnow()},session=session)
        store.db.question_versions.insert_one({'_id':vid,'question_id':qid,'number':1,'definition':definition(q),'parent_version_id':None,'restore_version_id':None,'derived_from':None,'legacy_origin':{'survey_id':sid,'edit_revision':body.revision,'instance_id':instance_id},'created_at':utcnow()},session=session)
        q['source']={'question_id':str(qid),'version_id':str(vid)}
        store.db.survey_edits.update_one({'_id':oid(sid),'revision':body.revision},{'$set':{'structure':normalized,'updated_at':utcnow()},'$inc':{'revision':1}},session=session)
        return {'source':q['source'],'revision':body.revision+1,'replayed':False}
    return store.transaction(tx)
