"""Owner-only, version-pinned statistics from successful immutable submissions."""
from decimal import Decimal, localcontext
from fastapi import APIRouter, Depends
from backend.auth import require_user, fail
from backend.surveys import get_store, oid
from backend.filling_engine import answer_error, WHITE

router = APIRouter(prefix='/api/surveys', tags=['statistics'])


def question_statistics(q, latest):
    values = [a.get(q['id']) for a in latest]
    values = [v for v in values if v is not None and v != "" and v != [] and not (q["type"] == "text" and all(c in WHITE for c in v)) and not answer_error(q, v)]
    result = {'question_id': q['id'], 'title': q['title'], 'type': q['type'],
              'answered_count': len(values)}
    if q['type'] in ('single', 'multiple'):
        result['options'] = [{'id': o['id'], 'label': o['label'],
            'count': sum(v == o['id'] if q['type'] == 'single' else o['id'] in v for v in values)}
            for o in q['options']]
    elif q['type'] == 'text':
        # Independently sort each question: no respondent ordering or row identifiers.
        result['values'] = sorted(values)
    else:
        numbers = sorted(float(v) for v in values)
        result['values'] = numbers
        result['valid_count'] = len(numbers)
        with localcontext() as context:
            context.prec = 40
            result['average'] = float(sum((Decimal(str(v)) for v in numbers), Decimal(0)) / len(numbers)) if numbers else None
    return result


def statistics(store, sid, user, version_id=None, question_id=None):
    def read(session):
        survey = store.owned(sid, user, session)
        vid = oid(version_id) if version_id else survey['currentVersionId']
        if vid is None:
            fail(409, 'unpublished', '问卷尚未发布，暂无统计。')
        version = store.db.survey_versions.find_one({'_id': vid, 'survey_id': survey['_id']}, session=session)
        if not version:
            fail(404, 'not_found', '版本不存在或无权访问。')
        questions = version['structure']['questions']
        if question_id is not None:
            questions = [q for q in questions if q['id'] == question_id]
            if not questions:
                fail(404, 'not_found', '题目不存在。')
        # One snapshot fixes survey pointer, immutable structure, total and latest rows.
        data = list(store.db.submissions.aggregate([
            {'$match': {'survey_id': survey['_id'], 'version_id': vid}},
            {'$facet': {
                'total': [{'$count': 'count'}],
                'latest': [{'$sort': {'user_id': 1, 'sequence': -1}},
                           {'$group': {'_id': '$user_id', 'answers': {'$first': '$answers'}}},
                           {'$project': {'_id': 0, 'answers': 1}}]
            }}
        ], session=session, maxTimeMS=5000))[0]
        latest = [row['answers'] for row in data['latest']]
        return {'survey_id': sid, 'version_id': str(vid), 'version_number': version['number'],
                'title': version['structure']['title'], 'anonymous': version['structure']['anonymous'],
                'submission_count': data['total'][0]['count'] if data['total'] else 0,
                'participant_count': len(latest),
                'questions': [question_statistics(q, latest) for q in questions]}
    return store.transaction(read)


@router.get('/{sid}/statistics')
def whole(sid: str, user=Depends(require_user), store=Depends(get_store)):
    return statistics(store, sid, user)


@router.get('/{sid}/versions/{version_id}/statistics/questions/{question_id}')
def single(sid: str, version_id: str, question_id: str,
           user=Depends(require_user), store=Depends(get_store)):
    return statistics(store, sid, user, version_id, question_id)
