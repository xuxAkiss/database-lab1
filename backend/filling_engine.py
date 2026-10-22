"""Pure filling transitions. The server owns navigation and provenance, never the client."""
import copy
import math
import re
from fastapi import HTTPException

WHITE = frozenset('\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000')
NUMBER = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', re.ASCII)
PARTIAL_NUMBER = re.compile(r'[+-]?(?:\d*(?:\.\d*)?)(?:[eE][+-]?\d*)?', re.ASCII)

def error(code, message, status=422, errors=None):
    raise HTTPException(status, {'code': code, 'message': message, **({'errors': errors} if errors else {})})

def questions(structure):
    return {q['id']: q for q in structure['questions']}

def draft_value(q, value):
    """Accept unfinished/bounds-invalid input, but reject fake references and unsafe shapes."""
    typ = q['type']
    if value is None:
        return [] if typ == 'multiple' else ''
    if typ == 'multiple':
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            error('invalid_answer', '多选答案必须是选项 ID 列表。')
        opts = [o['id'] for o in q['options']]
        if len(value) != len(set(value)) or not set(value) <= set(opts):
            error('invalid_answer', '选项不存在或重复。')
        return sorted(value, key=opts.index)
    if not isinstance(value, str):
        error('invalid_answer', '单选、文本和数字输入须为字符串；数字保留未输入完成的原文。')
    if typ == 'single' and value and value not in {o['id'] for o in q['options']}:
        error('invalid_answer', '选项不存在。')
    if typ == 'text' and len(value) > 20000:
        error('invalid_answer', '草稿文本最多保存 20000 个字符。')
    if typ == 'number' and (len(value) > 128 or not PARTIAL_NUMBER.fullmatch(value)):
        error('invalid_answer', '数字只允许十进制/科学计数法输入（不接受 NaN/Infinity）。')
    return value

def answer_error(q, value):
    try:
        value = draft_value(q, value)
    except HTTPException as exc:
        return exc.detail['message']
    length = sum(c not in WHITE for c in value) if q['type'] == 'text' else len(value)
    if length == 0:
        return '此题必答。' if q['required'] else None
    if q['type'] == 'multiple':
        if q.get('exact_choices') is not None and length != q['exact_choices']:
            return f"必须恰好选择 {q['exact_choices']} 项。"
        if q.get('min_choices') is not None and length < q['min_choices']:
            return f"至少选择 {q['min_choices']} 项。"
        if q.get('max_choices') is not None and length > q['max_choices']:
            return f"最多选择 {q['max_choices']} 项。"
    if q['type'] == 'text':
        if q.get('min_length') is not None and length < q['min_length']:
            return f"去除空白后至少 {q['min_length']} 字。"
        if q.get('max_length') is not None and length > q['max_length']:
            return f"去除空白后最多 {q['max_length']} 字。"
    if q['type'] == 'number':
        if not NUMBER.fullmatch(value):
            return '请输入完整数字。'
        number = float(value)
        if not math.isfinite(number):
            return '数字必须是有限值。'
        if q.get('integer_only') and not number.is_integer():
            return '必须为整数。'
        if q.get('minimum') is not None and number < q['minimum']:
            return f"不得小于 {q['minimum']}。"
        if q.get('maximum') is not None and number > q['maximum']:
            return f"不得大于 {q['maximum']}。"
    return None

def all_errors(structure, state, required_only=False):
    return [{'question_id': q['id'], 'number': i+1, 'message': msg}
            for i, q in enumerate(structure['questions'])
            if (not required_only or q['required']) and (msg := answer_error(q, state['answers'].get(q['id'])))]

def recalculate(structure, state):
    visited = set(state['visited'])
    priority = []
    for source in sorted(state['sources'], key=lambda s: s['rank'], reverse=True):
        priority.extend(source['targets'])
    priority.extend(q['id'] for q in structure['questions'])
    state['pending'] = list(dict.fromkeys(q for q in priority if q not in visited))

def revoke(state, question_id):
    """Remove the old source and descendants only when ALL support is gone."""
    removed = {s['id'] for s in state['sources'] if s['question_id'] == question_id}
    while True:
        extra = {s['id'] for s in state['sources'] if not s['root'] and s['parents'] and set(s['parents']) <= removed}
        if extra <= removed:
            break
        removed |= extra
    state['sources'] = [s for s in state['sources'] if s['id'] not in removed]
    for source in state['sources']:
        source['parents'] = [p for p in source['parents'] if p not in removed]
    for context in state['contexts'].values():
        context['parents'] = [p for p in context['parents'] if p not in removed]

def enter(state, qid, explicit=False):
    if qid not in state['visited']:
        state['visited'].append(qid)
        parents = [s['id'] for s in state['sources'] if qid in s['targets']]
        state['contexts'][qid] = {'root': explicit or not parents, 'parents': [] if explicit else parents}
    elif explicit:
        # A changed/reconfirmed answer after explicit return can create an independent source.
        state['contexts'][qid] = {'root': True, 'parents': []}
    state['current'] = qid
    state['ended'] = False

def initial(structure):
    state = {'answers': {}, 'current': None, 'visited': [], 'pending': [], 'sources': [],
             'contexts': {}, 'clock': 0, 'ended': False}
    enter(state, structure['questions'][0]['id'])
    recalculate(structure, state)
    return state

def match(q, value):
    if not value:
        return None
    for rule in q['rules']:
        if q['type'] == 'single':
            hit = rule['selected'] == [value]
        elif q['type'] == 'multiple':
            hit = set(rule['selected']) == set(value)
        elif q['type'] == 'number':
            n, v = float(value), rule['value']
            hit = {'eq': n == v, 'lt': n < v, 'lte': n <= v, 'gt': n > v, 'gte': n >= v}[rule['operator']]
        else:
            hit = False
        if hit:
            return rule
    return None

def activate(q, state):
    old = next((s for s in state['sources'] if s['question_id'] == q['id']), None)
    if old:
        return old['end']
    rule = match(q, state['answers'].get(q['id']))
    if rule is None:
        return False
    state['clock'] += 1
    context = state['contexts'][q['id']]
    live = {s['id'] for s in state['sources']}
    parents = [p for p in context['parents'] if p in live]
    state['sources'].append({'id': f"source_{state['clock']}", 'question_id': q['id'],
                             'parents': parents, 'root': context['root'] or not parents,
                             'targets': rule['targets'], 'end': rule['action'] == 'end', 'rank': state['clock']})
    return rule['action'] == 'end'

def can_finish(structure, state):
    return not state['pending'] or any(s['end'] for s in state['sources']) or not any(q['rules'] for q in structure['questions'])

def transition(structure, original, action, question_id=None, value=None, target=None):
    state = copy.deepcopy(original)
    qs = questions(structure)
    if action == 'save':
        if question_id != state['current'] or question_id not in qs:
            error('invalid_navigation', '只能保存当前题，请通过合法导航返回改答。', 409)
        val = draft_value(qs[question_id], value)
        if state['answers'].get(question_id) != val:
            revoke(state, question_id)
            state['answers'][question_id] = val
            if answer_error(qs[question_id], val) is None:
                activate(qs[question_id], state)
    elif action == 'next':
        q = qs.get(state['current'])
        if not q:
            error('invalid_navigation', '当前已在结束检查页。', 409)
        msg = answer_error(q, state['answers'].get(q['id']))
        if msg:
            error('answer_validation', msg, errors=[{'question_id': q['id'], 'message': msg}])
        ended = activate(q, state)
        recalculate(structure, state)
        if ended or not state['pending']:
            state['current'] = None
            state['ended'] = True
        else:
            enter(state, state['pending'][0])
    elif action == 'goto':
        missing = {e['question_id'] for e in all_errors(structure, state, required_only=True)}
        free = not any(q['rules'] for q in structure['questions'])
        supplement = (state['ended'] or any(s['end'] for s in state['sources'])) and target in missing
        if target not in qs or not (target in state['visited'] or free or supplement):
            error('invalid_navigation', '不能任意进入尚未安排的题目。', 409)
        enter(state, target, explicit=True)
    elif action == 'finish':
        if not can_finish(structure, state):
            error('invalid_navigation', '请按待答顺序继续，尚未到达结束入口。', 409)
        state['ended'], state['current'] = True, None
    else:
        error('invalid_action', '不支持的操作。')
    recalculate(structure, state)
    return state
