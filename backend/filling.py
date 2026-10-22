"""Version-scoped private drafts and append-only, idempotent submissions."""
import hashlib
import json
from typing import Any, Literal
from bson import ObjectId
from fastapi import APIRouter, Depends
from pydantic import Field, StrictBool, StrictInt
from pymongo import ReturnDocument
from backend.auth import require_user, require_mutating_user, utcnow, fail
from backend.surveys import get_store, oid
from backend.survey_models import Model
from backend.filling_engine import initial, transition, all_errors, error

router = APIRouter(prefix='/api/fill', tags=['filling'])

class Start(Model):
    version_id: str
    new_attempt: StrictBool = False
    previous_attempt_id: str | None = None

class Action(Model):
    attempt_id: str
    revision: StrictInt = Field(ge=1)
    action: Literal['save', 'next', 'goto', 'finish']
    question_id: str | None = None
    value: Any = None
    target: str | None = None

class Submit(Model):
    attempt_id: str
    revision: StrictInt = Field(ge=1)
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{16,80}$')


def by_token(store, token, session=None):
    survey = store.db.surveys.find_one({'share_token': token}, session=session)
    if not survey:
        fail(404, 'not_found', '链接不存在。')
    return survey


def writable_reason(s, vid):
    if s['currentVersionId'] != vid:
        return 'version_changed', '此草稿属于旧版本，只能查看；填写新版请重新开始。'
    if s['closed']:
        return 'closed', '问卷已关闭，草稿保留，重开后可继续。'
    if s['deadline'] and utcnow() >= s['deadline']:
        return 'expired', '问卷已到截止时间，草稿保留。'
    return None


def coordinate(store, token, vid, session):
    # A REAL write on the exact survey document also written by publish/close.
    # A stale snapshot cannot pass: write conflict forces transaction retry and recheck.
    survey = store.db.surveys.find_one_and_update({'share_token': token}, {'$inc': {'fill_fence': 1}},
                                                 session=session, return_document=ReturnDocument.AFTER)
    if not survey:
        fail(404, 'not_found', '链接不存在。')
    reason = writable_reason(survey, vid)
    if reason:
        fail(409, *reason)
    return survey


def scope(survey, vid, user):
    return {'survey_id': survey['_id'], 'version_id': vid, 'user_id': user['_id']}


def version(store, survey, vid, session=None):
    v = store.db.survey_versions.find_one({'_id': vid, 'survey_id': survey['_id']}, session=session)
    if not v:
        fail(404, 'not_found', '版本不存在。')
    return v


def draft_public(d, structure, reason=None):
    state = d['state']
    return {'attempt_id': str(d['attempt_id']), 'version_id': str(d['version_id']), 'revision': d['revision'],
            'status': d['status'], 'read_only': bool(reason) or d['status'] != 'active',
            'reason': reason[1] if reason else ('此轮已提交。' if d['status'] != 'active' else None),
            'answers': state['answers'], 'current': state['current'], 'visited': state['visited'],
            'pending': state['pending'], 'ended': state['ended'], 'errors': all_errors(structure, state),
            'updated_at': d['updated_at']}


def submission_public(d):
    return {'submission_id': str(d['_id']), 'version_id': str(d['version_id']),
            'sequence': d['sequence'], 'submitted_at': d['submitted_at']}


@router.get('/{token}')
def context(token: str, user=Depends(require_user), store=Depends(get_store)):
    survey = by_token(store, token)
    if not survey['currentVersionId']:
        fail(409, 'unpublished', '问卷尚未发布。')
    v = version(store, survey, survey['currentVersionId'])
    key = scope(survey, v['_id'], user)
    d = store.db.fill_drafts.find_one(key)
    p = store.db.participations.find_one(key)
    reason = writable_reason(survey, v['_id'])
    old = []
    for prior in store.db.fill_drafts.find({'survey_id': survey['_id'], 'user_id': user['_id'], 'version_id': {'$ne': v['_id']}}):
        old.append({'version_id': str(prior['version_id']), 'status': prior['status'], 'updated_at': prior['updated_at']})
    return {'survey_id': str(survey['_id']), 'version_id': str(v['_id']), 'version_number': v['number'],
            'structure': v['structure'], 'read_only': bool(reason), 'reason': reason[1] if reason else None,
            'draft': draft_public(d, v['structure'], reason) if d else None, 'old_drafts': old,
            'submission_count': p['submission_count'] if p else 0,
            'latest_submission_id': str(p['latest_submission_id']) if p and p['latest_submission_id'] else None}


@router.get('/{token}/drafts/{vid}')
def read_draft(token: str, vid: str, user=Depends(require_user), store=Depends(get_store)):
    survey = by_token(store, token); version_id = oid(vid)
    d = store.db.fill_drafts.find_one(scope(survey, version_id, user))
    if not d:
        fail(404, 'not_found', '没有此账号的草稿。')
    v = version(store, survey, version_id)
    return {'structure': v['structure'], 'version_number': v['number'],
            'draft': draft_public(d, v['structure'], writable_reason(survey, version_id))}


@router.post('/{token}/start')
def start(token: str, body: Start, user=Depends(require_mutating_user), store=Depends(get_store)):
    def tx(session):
        vid = oid(body.version_id)
        survey = coordinate(store, token, vid, session)
        v = version(store, survey, vid, session); key = scope(survey, vid, user)
        d = store.db.fill_drafts.find_one(key, session=session)
        if d and d['status'] == 'active':
            if body.new_attempt and str(d.get('previous_attempt_id')) != body.previous_attempt_id:
                fail(409, 'attempt_conflict', '已有新的填写，请刷新恢复，不能用旧请求重开。')
            return draft_public(d, v['structure'])
        p = store.db.participations.find_one(key, session=session)
        count = p['submission_count'] if p else 0
        if count and not v['structure']['allow_repeat']:
            fail(409, 'already_submitted', '此版本不允许重复填写，已经成功提交。')
        if count and (not body.new_attempt or not d or str(d['attempt_id']) != body.previous_attempt_id):
            fail(409, 'explicit_restart_required', '请明确开始下一次空白填写。')
        if not count and body.new_attempt:
            fail(409, 'attempt_conflict', '尚未提交过，请开始首次填写。')
        if p is None:
            store.db.participations.insert_one({**key, 'submission_count': 0, 'latest_submission_id': None}, session=session)
        fresh = {**key, 'attempt_id': ObjectId(), 'previous_attempt_id': d['attempt_id'] if d else None,
                 'revision': 1, 'status': 'active', 'state': initial(v['structure']), 'updated_at': utcnow()}
        if d:
            fresh['_id'] = d['_id']; store.db.fill_drafts.replace_one({'_id': d['_id']}, fresh, session=session)
        else:
            store.db.fill_drafts.insert_one(fresh, session=session)
        return draft_public(fresh, v['structure'])
    return store.transaction(tx)


def active_draft(store, key, attempt_id, revision, session):
    d = store.db.fill_drafts.find_one(key, session=session)
    if not d or d['status'] != 'active' or str(d['attempt_id']) != attempt_id:
        fail(409, 'attempt_consumed', '此次填写已结束或已被新一轮替代，请刷新；旧请求不能恢复草稿。')
    if d['revision'] != revision:
        fail(409, 'draft_conflict', '草稿已被其他窗口或请求更新，请保留当前输入并刷新后核对。')
    return d


@router.post('/{token}/drafts/{vid}/action')
def act(token: str, vid: str, body: Action, user=Depends(require_mutating_user), store=Depends(get_store)):
    fields = body.model_fields_set
    if body.action == 'save':
        if not {'value', 'question_id'} <= fields or 'target' in fields:
            fail(422, 'invalid_action', '保存需要当前题目及输入，不可传导航目标。')
    elif 'value' in fields or 'question_id' in fields or (body.action != 'goto' and 'target' in fields):
        fail(422, 'invalid_action', '导航不能夹带答案；请先保存。')
    def tx(session):
        version_id = oid(vid)
        survey = coordinate(store, token, version_id, session)
        v = version(store, survey, version_id, session)
        d = active_draft(store, scope(survey, version_id, user), body.attempt_id, body.revision, session)
        d['state'] = transition(v['structure'], d['state'], body.action, body.question_id, body.value, body.target)
        d['revision'] += 1; d['updated_at'] = utcnow()
        store.db.fill_drafts.replace_one({'_id': d['_id'], 'revision': body.revision, 'attempt_id': d['attempt_id'], 'status': 'active'}, d, session=session)
        return draft_public(d, v['structure'])
    return store.transaction(tx)


def submit_attempt(store, token, vid, user, body):
    version_id = oid(vid)
    fingerprint = hashlib.sha256(json.dumps({'attempt_id': body.attempt_id, 'revision': body.revision}, sort_keys=True).encode()).hexdigest()
    def tx(session):
        survey = by_token(store, token, session)
        key = scope(survey, version_id, user)
        prior = store.db.submissions.find_one({**key, 'request_key': body.request_key}, session=session)
        if prior:
            if prior['request_hash'] != fingerprint:
                fail(409, 'idempotency_conflict', '同一提交键不能用于不同的填写或修订。')
            return submission_public(prior)  # even after close, switch, or a newer attempt
        survey = coordinate(store, token, version_id, session)
        # Decision point: after obtaining survey write coordination, on this server's UTC clock.
        checked_at = utcnow()
        if survey['deadline'] and checked_at >= survey['deadline']:
            fail(409, 'expired', '已到截止时间，不能提交。')
        v = version(store, survey, version_id, session)
        d = active_draft(store, key, body.attempt_id, body.revision, session)
        if not d['state']['ended']:
            fail(409, 'not_at_end', '请先进入结束检查页。')
        errors = all_errors(v['structure'], d['state'])
        if errors:
            error('answer_validation', '还有题目需要补答或修正。', errors=errors)
        p = store.db.participations.find_one(key, session=session)
        if p['submission_count'] and not v['structure']['allow_repeat']:
            fail(409, 'already_submitted', '此版本仅允许提交一次。')
        record = {**key, 'attempt_id': d['attempt_id'], 'draft_revision': body.revision,
                  'request_key': body.request_key, 'request_hash': fingerprint,
                  'sequence': p['submission_count'] + 1, 'answers': d['state']['answers'],
                  'submitted_at': checked_at.replace(microsecond=(checked_at.microsecond // 1000) * 1000)}
        store.db.submissions.insert_one(record, session=session)
        store.db.participations.update_one({'_id': p['_id']}, {'$inc': {'submission_count': 1},
                     '$set': {'latest_submission_id': record['_id']}}, session=session)
        store.db.fill_drafts.update_one({'_id': d['_id'], 'attempt_id': d['attempt_id'], 'revision': body.revision, 'status': 'active'},
                       {'$set': {'status': 'submitted', 'updated_at': checked_at}, '$inc': {'revision': 1}}, session=session)
        return submission_public(record)
    return store.transaction(tx)


@router.post('/{token}/drafts/{vid}/submit')
def submit(token: str, vid: str, body: Submit, user=Depends(require_mutating_user), store=Depends(get_store)):
    return submit_attempt(store, token, vid, user, body)
