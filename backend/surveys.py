"""Owner-only management and atomic immutable publication."""
import secrets
import pymongo
import threading
from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import Field, StrictInt, field_validator
from pymongo import ReturnDocument
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from backend.auth import fail, utcnow, require_user, require_mutating_user, get_auth_store
from backend.survey_models import Model, Structure, validate_structure

router = APIRouter(prefix='/api', tags=['surveys'])

class Save(Model):
    revision: StrictInt = Field(ge=1)
    structure: Structure

class Publish(Model):
    revision: StrictInt = Field(ge=1)

class State(Model):
    revision: StrictInt = Field(ge=1)
    action: str = Field(pattern=r'^(close|reopen|deadline)$')
    deadline: datetime | None = None

    @field_validator('deadline')
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('截止时间必须包含时区')
        return value


def oid(value):
    if not ObjectId.is_valid(value):
        fail(404, 'not_found', '问卷不存在或无权访问。')
    return ObjectId(value)


def summary(s):
    return {'id': str(s['_id']), 'share_path': '/s/' + s['share_token'],
            'currentVersionId': str(s['currentVersionId']) if s['currentVersionId'] else None,
            'version_number': s['version_number'], 'closed': s['closed'],
            'deadline': s['deadline'], 'state_revision': s['state_revision'], 'created_at': s['created_at']}


class SurveyStore:
    def __init__(self, db):
        self.db = db
        self.lock = threading.Lock()
        self.ready = False

    def ensure_indexes(self):
        if self.ready:
            return
        with self.lock:
            if not self.ready:
                self.db.surveys.create_index('share_token', unique=True)
                self.db.surveys.create_index([('owner_id', 1), ('created_at', -1)])
                # survey_edits._id equals the stable survey ID, inherently unique.
                self.db.survey_edits.create_index('owner_id')
                self.db.survey_versions.create_index([('survey_id', 1), ('edit_revision', 1)], unique=True)
                self.db.survey_versions.create_index([('survey_id', 1), ('number', 1)], unique=True)
                for name in ('fill_drafts', 'participations'):
                    self.db[name].create_index([('survey_id', 1), ('version_id', 1), ('user_id', 1)], unique=True)
                self.db.submissions.create_index([('version_id', 1), ('user_id', 1), ('sequence', 1)], unique=True)
                self.db.submissions.create_index([('version_id', 1), ('user_id', 1), ('request_key', 1)], unique=True)
                self.ready = True

    def owned(self, sid, user, session=None):
        s = self.db.surveys.find_one({'_id': oid(sid), 'owner_id': user['_id']}, session=session)
        if s is None:
            fail(404, 'not_found', '问卷不存在或无权访问。')
        return s

    def transaction(self, callback):
        with pymongo.timeout(10), self.db.client.start_session() as session:
            return session.with_transaction(callback, read_concern=ReadConcern('snapshot'),
                                            write_concern=WriteConcern('majority'), max_commit_time_ms=5000)

    def create(self, user, structure):
        data = validate_structure(structure)
        sid = ObjectId()
        s = {'_id': sid, 'owner_id': user['_id'], 'share_token': secrets.token_urlsafe(24),
             'currentVersionId': None, 'version_number': 0, 'closed': False, 'deadline': None,
             'state_revision': 1, 'created_at': utcnow()}
        e = {'_id': sid, 'owner_id': user['_id'], 'revision': 1, 'structure': data, 'updated_at': utcnow()}
        def create_tx(session):
            self.db.surveys.insert_one(s.copy(), session=session)
            self.db.survey_edits.insert_one(e.copy(), session=session)
        self.transaction(create_tx)
        return {**summary(s), 'revision': 1, 'structure': data}

    def publish(self, sid, user, revision):
        def publish_tx(session):
            s = self.owned(sid, user, session)
            old = self.db.survey_versions.find_one({'survey_id': s['_id'], 'edit_revision': revision}, session=session)
            if old:
                # A retry returns its historical publication, never rolls the pointer backwards.
                return {'version_id': str(old['_id']), 'number': old['number'], 'replayed': True,
                        'currentVersionId': str(s['currentVersionId'])}
            edit = self.db.survey_edits.find_one({'_id': s['_id'], 'revision': revision}, session=session)
            if not edit:
                fail(409, 'edit_conflict', '编辑稿已变化，请重新打开后检查再发布。')
            data = validate_structure(edit['structure'], publishing=True)
            # Write the edit as well as survey: concurrent save/state changes conflict and retry.
            self.db.survey_edits.update_one({'_id': s['_id'], 'revision': revision},
                                            {'$inc': {'publish_fence': 1}}, session=session)
            v = {'_id': ObjectId(), 'survey_id': s['_id'], 'edit_revision': revision,
                 'number': s['version_number'] + 1, 'structure': data, 'published_at': utcnow()}
            self.db.survey_versions.insert_one(v, session=session)
            self.db.surveys.update_one({'_id': s['_id']}, {'$set': {'currentVersionId': v['_id'],
                                       'version_number': v['number']}, '$inc': {'state_revision': 1}}, session=session)
            return {'version_id': str(v['_id']), 'number': v['number'], 'replayed': False,
                    'currentVersionId': str(v['_id'])}
        return self.transaction(publish_tx)


def get_store(request: Request, auth=Depends(get_auth_store)):
    store = request.app.state.survey_store
    store.ensure_indexes()
    return store


@router.post('/surveys', status_code=201)
def create(body: Structure, user=Depends(require_mutating_user), store=Depends(get_store)):
    return store.create(user, body)


@router.get('/surveys')
def listing(user=Depends(require_user), store=Depends(get_store)):
    result = []
    for s in store.db.surveys.find({'owner_id': user['_id']}).sort('created_at', -1):
        edit = store.db.survey_edits.find_one({'_id': s['_id']}, {'structure.title': 1})
        result.append({**summary(s), 'title': edit['structure']['title'] if edit else '编辑稿暂不可用'})
    return {'surveys': result}


@router.get('/surveys/{sid}/edit')
def get_edit(sid: str, user=Depends(require_user), store=Depends(get_store)):
    s = store.owned(sid, user)
    e = store.db.survey_edits.find_one({'_id': s['_id']})
    return {**summary(s), 'revision': e['revision'], 'structure': e['structure']}


@router.post('/surveys/{sid}/edit')
def save(sid: str, body: Save, user=Depends(require_mutating_user), store=Depends(get_store)):
    s = store.owned(sid, user)
    data = validate_structure(body.structure)
    e = store.db.survey_edits.find_one_and_update({'_id': s['_id'], 'revision': body.revision},
           {'$set': {'structure': data, 'updated_at': utcnow()}, '$inc': {'revision': 1}}, return_document=ReturnDocument.AFTER)
    if not e:
        fail(409, 'edit_conflict', '其他窗口已保存，请先复制当前内容，再重新打开合并修改。')
    return {'revision': e['revision'], 'structure': e['structure']}


@router.post('/surveys/{sid}/publish')
def publish(sid: str, body: Publish, user=Depends(require_mutating_user), store=Depends(get_store)):
    return store.publish(sid, user, body.revision)


@router.post('/surveys/{sid}/state')
def state(sid: str, body: State, user=Depends(require_mutating_user), store=Depends(get_store)):
    def change(session):
        s = store.owned(sid, user, session)
        if s['state_revision'] != body.revision:
            fail(409, 'state_conflict', '运行状态已变化，请重新打开。')
        if body.action != 'deadline' and body.deadline is not None:
            fail(422, 'invalid_input', '仅设置截止操作可传入 deadline。')
        update = {}
        if body.action == 'deadline':
            update['deadline'] = body.deadline
        elif body.action == 'close':
            update['closed'] = True
        else:
            if s['currentVersionId'] is None:
                fail(409, 'unpublished', '请先发布问卷。')
            if s['deadline'] and utcnow() >= s['deadline']:
                fail(409, 'expired', '请先延长或清除截止时间，再重开。')
            update['closed'] = False
        changed = store.db.surveys.find_one_and_update({'_id': s['_id'], 'state_revision': body.revision},
                    {'$set': update, '$inc': {'state_revision': 1}}, session=session, return_document=ReturnDocument.AFTER)
        return summary(changed)
    return store.transaction(change)


@router.get('/surveys/{sid}/versions')
def versions(sid: str, user=Depends(require_user), store=Depends(get_store)):
    s = store.owned(sid, user)
    return {'versions': [{'id': str(v['_id']), 'number': v['number'], 'edit_revision': v['edit_revision'],
                         'published_at': v['published_at'], 'structure': v['structure']}
                        for v in store.db.survey_versions.find({'survey_id': s['_id']}).sort('number', -1)]}


@router.get('/shared/{token}')
def shared(token: str, user=Depends(require_user), store=Depends(get_store)):
    s = store.db.surveys.find_one({'share_token': token})
    if not s:
        fail(404, 'not_found', '链接不存在。')
    if not s['currentVersionId']:
        fail(409, 'unpublished', '问卷尚未发布。')
    if s['closed']:
        fail(409, 'closed', '问卷已关闭。')
    if s['deadline'] and utcnow() >= s['deadline']:
        fail(409, 'expired', '问卷已到截止时间。')
    v = store.db.survey_versions.find_one({'_id': s['currentVersionId'], 'survey_id': s['_id']})
    if not v:
        fail(503, 'version_unavailable', '发布结构暂不可用。')
    # Only filling-related structure and version association; no owner/edit/internal metadata.
    return {'survey_id': str(s['_id']), 'version_id': str(v['_id']), 'version_number': v['number'],
            'deadline': s['deadline'], 'structure': v['structure']}
