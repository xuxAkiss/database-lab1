"""Owner-only cross-survey statistics using original immutable publications/submissions."""
from collections import Counter
from decimal import Decimal, localcontext
from fastapi import APIRouter, Depends
from pydantic import Field, StrictInt
from backend.auth import require_user, require_mutating_user, fail, utcnow
from backend.surveys import get_store, oid
from backend.survey_models import Model
from backend.questions import definition
from backend.filling_engine import answer_error, WHITE

router = APIRouter(prefix='/api/question-statistics', tags=['question-statistics'])
MAX_SURVEYS = 200
MAX_VERSIONS = 1000
MAX_LATEST = 10000
MAX_TEXT_CHARS = 2000000

class Selection(Model):
    survey_id: str
    survey_version_id: str
    instance_id: str | None = None

class Query(Model):
    question_version_id: str
    selections: list[Selection] = Field(default_factory=list, max_length=MAX_SURVEYS)
    page: StrictInt = Field(default=1, ge=1, le=100000)
    page_size: StrictInt = Field(default=50, ge=1, le=100)


def bounded(cursor, limit, label):
    rows = list(cursor.limit(limit + 1))
    if len(rows) > limit:
        fail(413, 'statistics_limit', f'{label}超过本次统计上限 {limit}；未返回局部统计。')
    return rows


def source_matches(q, qid, vid=None):
    s = q.get('source') or {}
    return s.get('question_id') == qid and (vid is None or s.get('version_id') == vid)


def owned_scope(store, user, session):
    surveys = bounded(store.db.surveys.find({'owner_id': user['_id']}, session=session).sort('_id', 1), MAX_SURVEYS, '本人问卷数')
    versions = bounded(store.db.survey_versions.find({'survey_id': {'$in': [s['_id'] for s in surveys]}}, session=session).sort([('survey_id', 1), ('number', 1)]), MAX_VERSIONS, '本人发布版本数')
    return surveys, versions


def authorized_definition(store, user, qid, vid, versions, session):
    """Revoked library access never prevents reading one's already saved snapshot."""
    snapshots = [q for v in versions for q in v['structure']['questions'] if source_matches(q, qid, vid)]
    resource = store.db.questions.find_one({'_id': oid(qid), '$or': [{'owner_id': user['_id']}, {'shared_with': user['_id']}]}, session=session)
    # Also allow a saved edit's source, without making its answers eligible.
    if not snapshots:
        for e in store.db.survey_edits.find({'owner_id': user['_id'], 'structure.questions.source.question_id': qid}, session=session):
            snapshots.extend(q for q in e['structure']['questions'] if source_matches(q, qid, vid))
    if not resource and not snapshots:
        fail(404, 'not_found', '题目版本不存在或没有可用的本人快照。')
    v = store.db.question_versions.find_one({'_id': oid(vid), 'question_id': oid(qid)}, session=session)
    if not v and not snapshots:
        fail(404, 'not_found', '题目版本不存在。')
    content = v['definition'] if v else definition(snapshots[0])
    if any(definition(q) != content for q in snapshots):
        fail(409, 'snapshot_mismatch', '同一来源的快照内容不一致，停止统计，请检查数据。')
    return content, v['number'] if v else None


@router.get('/{qid}/scope')
def scope(qid: str, user=Depends(require_user), store=Depends(get_store)):
    oid(qid)
    def read(session):
        surveys, versions = owned_scope(store, user, session)
        known = {}
        rows = []
        for s in surveys:
            vs = []
            for v in versions:
                if v['survey_id'] != s['_id']: continue
                matches = [q for q in v['structure']['questions'] if source_matches(q, qid)]
                if not matches: continue
                instances = []
                for q in matches:
                    vid = q['source']['version_id']; known[vid] = q['title']
                    instances.append({'instance_id': q['id'], 'question_version_id': vid, 'title': q['title']})
                vs.append({'survey_version_id': str(v['_id']), 'number': v['number'], 'title': v['structure']['title'], 'instances': instances})
            if vs:
                rows.append({'survey_id': str(s['_id']), 'current_survey_version_id': str(s['currentVersionId']) if s['currentVersionId'] else None, 'versions': vs})
        for e in store.db.survey_edits.find({'owner_id': user['_id'], 'structure.questions.source.question_id': qid}, session=session):
            for q in e['structure']['questions']:
                if source_matches(q, qid): known[q['source']['version_id']] = q['title']
        resource = store.db.questions.find_one({'_id': oid(qid), '$or': [{'owner_id': user['_id']}, {'shared_with': user['_id']}]}, session=session)
        if resource:
            available = bounded(store.db.question_versions.find({'question_id': oid(qid)}, session=session), MAX_VERSIONS, '题目版本数')
            known.update({str(v['_id']): v['definition']['title'] for v in available})
        if not known and not resource: fail(404, 'not_found', '没有可访问的题目或本人快照。')
        items = []
        for vid, title in known.items():
            v = store.db.question_versions.find_one({'_id': oid(vid), 'question_id': oid(qid)}, session=session)
            items.append({'question_version_id': vid, 'number': v['number'] if v else None, 'title': title})
        return {'question_id': qid, 'question_versions': sorted(items, key=lambda v: (v['number'] or 0, v['question_version_id'])), 'surveys': rows,
                'scope_notice': '仅本人问卷；每卷默认当前发布，可选一个历史发布替代；同卷多个实例默认首个，可切换。'}
    return store.transaction(read)


def cross_statistics(store, user, qid, body):
    oid(qid); oid(body.question_version_id)
    ids = [s.survey_id for s in body.selections]
    if len(ids) != len(set(ids)): fail(422, 'duplicate_survey', '每份问卷只能选择一个发布版本和实例。')
    def read(session):
        surveys, versions = owned_scope(store, user, session)
        owned = {str(s['_id']): s for s in surveys}
        by_id = {str(v['_id']): v for v in versions}
        overrides = {}
        for selection in body.selections:
            oid(selection.survey_id); oid(selection.survey_version_id)
            v = by_id.get(selection.survey_version_id)
            if selection.survey_id not in owned or not v or str(v['survey_id']) != selection.survey_id:
                fail(404, 'not_found', '问卷或发布版本不存在或无权访问。')
            overrides[selection.survey_id] = selection
        content, number = authorized_definition(store, user, qid, body.question_version_id, versions, session)
        included, excluded, values = [], [], []
        latest_count = empty_count = invalid_count = chars = 0
        # Each read, including pointers, structures and latest rows, is in ONE snapshot transaction.
        for sid, s in owned.items():
            override = overrides.get(sid)
            vid = override.survey_version_id if override else str(s['currentVersionId']) if s['currentVersionId'] else None
            v = by_id.get(vid)
            if not v:
                excluded.append({'survey_id': sid, 'reason': 'unpublished'}); continue
            matches = [q for q in v['structure']['questions'] if source_matches(q, qid, body.question_version_id)]
            if not matches:
                if override and override.instance_id: fail(422, 'instance_mismatch', '所选实例不属于指定题目版本。')
                reason = 'no_reliable_source' if any(not q.get('source') for q in v['structure']['questions']) else 'no_matching_question_version'
                excluded.append({'survey_id': sid, 'survey_version_id': vid, 'reason': reason}); continue
            q = next((q for q in matches if q['id'] == override.instance_id), None) if override and override.instance_id else matches[0]
            if q is None: fail(422, 'instance_mismatch', '所选实例不属于指定题目版本。')
            if definition(q) != content: fail(409, 'snapshot_mismatch', '题目来源与快照不一致，停止统计。')
            remaining = MAX_LATEST - latest_count
            data = list(store.db.submissions.aggregate([
                {'$match': {'survey_id': s['_id'], 'version_id': v['_id']}},
                {'$sort': {'user_id': 1, 'sequence': -1}},
                {'$group': {'_id': '$user_id', 'answers': {'$first': '$answers'}}},
                {'$project': {'_id': 0, 'answers': 1}}, {'$limit': remaining + 1}
            ], session=session, maxTimeMS=5000))
            if len(data) > remaining: fail(413, 'statistics_limit', '最新整份答卷数超过 10000，未返回局部统计。')
            valid_here = empty_here = invalid_here = 0
            for row in data:
                value = row['answers'].get(q['id'])
                blank = value is None or value == '' or value == [] or (q['type'] == 'text' and isinstance(value, str) and all(c in WHITE for c in value))
                if blank: empty_here += 1
                elif answer_error(q, value): invalid_here += 1
                else:
                    values.append(value); valid_here += 1
                    if isinstance(value, str): chars += len(value)
            if chars > MAX_TEXT_CHARS: fail(413, 'statistics_limit', '有效内容超过 2000000 字符，未返回局部统计。')
            latest_count += len(data); empty_count += empty_here; invalid_count += invalid_here
            included.append({'survey_id': sid, 'survey_title': v['structure']['title'], 'survey_version_id': vid, 'survey_version_number': v['number'],
                'selection': 'explicit' if override else 'current', 'instance_id': q['id'], 'available_instance_ids': [x['id'] for x in matches],
                'instance_notice': '同卷仅选一个实例；默认问卷顺序首个。' if len(matches) > 1 else '',
                'latest_submission_count': len(data), 'answered_count': valid_here, 'empty_count': empty_here, 'invalid_count': invalid_here})
        result = {'question_id': qid, 'question_version_id': body.question_version_id, 'question_version_number': number,
            'title': content['title'], 'type': content['type'], 'included_survey_count': len(included), 'included': included, 'excluded': excluded,
            'latest_submission_count': latest_count, 'answered_count': len(values), 'empty_count': empty_count, 'invalid_count': invalid_count,
            'computed_at': utcnow(), 'scope': '仅本人问卷；每卷选定发布版每账号最新整份成功提交；跨卷不去重；每卷一个题实例；空白不回填。',
            'page': body.page, 'page_size': body.page_size, 'limits': {'surveys': MAX_SURVEYS, 'publications': MAX_VERSIONS, 'latest_submissions': MAX_LATEST, 'text_characters': MAX_TEXT_CHARS}}
        if content['type'] in ('single', 'multiple'):
            result['proportion_denominator'] = len(values)
            result['options'] = [{'id': o['id'], 'label': o['label'], 'count': sum(value == o['id'] if content['type'] == 'single' else o['id'] in value for value in values)} for o in content['options']]
            rows = []
        elif content['type'] == 'number':
            numbers = [Decimal(str(value)) for value in values]
            with localcontext() as ctx:
                ctx.prec = 40
                result['average'] = float(sum(numbers, Decimal(0)) / len(numbers)) if numbers else None
            rows = [{'value': float(value), 'count': count} for value, count in sorted(Counter(numbers).items())]
            result['distribution_total'] = len(rows)
        else:
            rows = sorted(values)
        result['rows_total'] = len(rows)
        result['page_count'] = max(1, (len(rows) + body.page_size - 1) // body.page_size)
        result['rows'] = rows[(body.page - 1) * body.page_size:body.page * body.page_size]
        return result
    return store.transaction(read)


@router.post('/{qid}/query')
def query(qid: str, body: Query, user=Depends(require_mutating_user), store=Depends(get_store)):
    # Read-only POST carries structured selection; uses existing CSRF protection.
    return cross_statistics(store, user, qid, body)
