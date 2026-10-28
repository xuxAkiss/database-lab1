"""Embedded questionnaire structures and field-local validation (no runtime answering)."""
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from fastapi import HTTPException

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Option(Model):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    label: str = Field(min_length=1, max_length=200)

class Rule(Model):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    selected: list[str] = Field(default_factory=list, max_length=50)
    operator: Literal['eq', 'lt', 'lte', 'gt', 'gte'] | None = None
    value: float | None = Field(default=None, strict=True, allow_inf_nan=False)
    action: Literal['targets', 'end'] = 'targets'
    targets: list[str] = Field(default_factory=list, max_length=100)

class QuestionSource(Model):
    question_id: str = Field(pattern=r'^[0-9a-f]{24}$')
    version_id: str = Field(pattern=r'^[0-9a-f]{24}$')

class Question(Model):
    source: QuestionSource | None = None
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    type: Literal['single', 'multiple', 'text', 'number']
    title: str = Field(min_length=1, max_length=300)
    required: StrictBool = False
    options: list[Option] = Field(default_factory=list, max_length=50)
    min_choices: StrictInt | None = Field(default=None, ge=0, le=50)
    max_choices: StrictInt | None = Field(default=None, ge=0, le=50)
    exact_choices: StrictInt | None = Field(default=None, ge=0, le=50)
    min_length: StrictInt | None = Field(default=None, ge=0, le=10000)
    max_length: StrictInt | None = Field(default=None, ge=0, le=10000)
    minimum: float | None = Field(default=None, strict=True, allow_inf_nan=False)
    maximum: float | None = Field(default=None, strict=True, allow_inf_nan=False)
    integer_only: StrictBool = False
    rules: list[Rule] = Field(default_factory=list, max_length=50)

class Structure(Model):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    anonymous: StrictBool = False
    allow_repeat: StrictBool = False
    questions: list[Question] = Field(default_factory=list, max_length=100)


def invalid(path, message):
    raise HTTPException(422, {'code': 'invalid_structure', 'message': f'{path}: {message}',
                              'errors': [{'field': path, 'message': message}]})


def interval(rule):
    v = rule.value
    return {'eq': (v, True, v, True), 'lt': (-math.inf, False, v, False),
            'lte': (-math.inf, False, v, True), 'gt': (v, False, math.inf, False),
            'gte': (v, True, math.inf, False)}[rule.operator]


def overlap(a, b):
    lo, hi = max(a[0], b[0]), min(a[2], b[2])
    if lo < hi:
        return True
    return lo == hi and all((x[0] < lo or x[1]) and (x[2] > hi or x[3]) for x in (a, b))


def validate_structure(structure, publishing=False):
    s = Structure.model_validate(structure) if isinstance(structure, dict) else structure
    if not s.title.strip():
        invalid('title', '标题不能全为空白')
    if publishing and not s.questions:
        invalid('questions', '发布至少需要一道题')
    ids = [q.id for q in s.questions]
    if len(set(ids)) != len(ids):
        invalid('questions', '题目 ID 不可重复')
    order = {qid: n for n, qid in enumerate(ids)}
    graph = {qid: set() for qid in ids}
    for i, q in enumerate(s.questions):
        path = f'questions[{i}]({q.id})'
        if not q.title.strip():
            invalid(path + '.title', '题目不能为空白')
        opts = [o.id for o in q.options]
        if len(opts) != len(set(opts)) or any(not o.label.strip() for o in q.options):
            invalid(path + '.options', '选项 ID 必须唯一、文字不能为空白')
        if q.type in ('single', 'multiple'):
            if len(opts) < 2:
                invalid(path + '.options', '选择题至少需要两个选项')
        elif opts:
            invalid(path + '.options', '仅选择题可配置选项')
        groups = [('multiple', ['min_choices', 'max_choices', 'exact_choices']),
                  ('text', ['min_length', 'max_length']), ('number', ['minimum', 'maximum'])]
        for typ, fields in groups:
            for field in fields:
                value = getattr(q, field)
                if value is not None and q.type != typ:
                    invalid(path + '.' + field, '字段不适用于此题型')
                if isinstance(value, float) and not math.isfinite(value):
                    invalid(path + '.' + field, '必须是有限数值')
        if q.integer_only and q.type != 'number':
            invalid(path + '.integer_only', '仅数字题可要求整数')
        if q.type == 'multiple':
            if q.required and (q.exact_choices == 0 or q.max_choices == 0):
                invalid(path + '.required', '必答多选题必须允许至少一个选项')
            low = q.min_choices if q.min_choices is not None else 0
            high = q.max_choices if q.max_choices is not None else len(opts)
            if low > high or high > len(opts):
                invalid(path + '.max_choices', '必须满足 0 ≤ 最少 ≤ 最多 ≤ 选项数')
            if q.exact_choices is not None and (q.min_choices is not None or q.max_choices is not None):
                invalid(path + '.exact_choices', '恰好数量与最少/最多二选一')
            if q.exact_choices is not None and q.exact_choices > len(opts):
                invalid(path + '.exact_choices', '不能超过选项数')
        if q.type == 'text' and q.required and q.max_length == 0:
            invalid(path + '.max_length', '必答文本题必须允许非空内容')
        for low, high in [('min_length', 'max_length'), ('minimum', 'maximum')]:
            if getattr(q, low) is not None and getattr(q, high) is not None and getattr(q, low) > getattr(q, high):
                invalid(path + '.' + high, '上限不能小于下限')
        if q.type == 'number' and q.integer_only and q.minimum is not None and q.maximum is not None and math.ceil(q.minimum) > math.floor(q.maximum):
            invalid(path + '.minimum', '范围内没有可填写的整数')
        seen, ranges, ruleids = set(), [], set()
        for j, r in enumerate(q.rules):
            rp = path + f'.rules[{j}]'
            if r.id in ruleids:
                invalid(rp + '.id', '规则 ID 重复')
            ruleids.add(r.id)
            if q.type in ('single', 'multiple'):
                if r.operator is not None or r.value is not None:
                    invalid(rp, '选择题条件只能使用选项集合')
                if len(r.selected) != len(set(r.selected)) or not set(r.selected) <= set(opts):
                    invalid(rp + '.selected', '选项引用不存在或重复')
                if not r.selected or (q.type == 'single' and len(r.selected) != 1):
                    invalid(rp + '.selected', '单选条件恰好一个选项，多选条件至少一个选项')
                key = tuple(sorted(r.selected))
                if key in seen:
                    invalid(rp + '.selected', '同一条件不可重复配置')
                seen.add(key)
                if q.type == 'multiple':
                    low = q.exact_choices if q.exact_choices is not None else (q.min_choices or 0)
                    high = q.exact_choices if q.exact_choices is not None else (q.max_choices if q.max_choices is not None else len(opts))
                    if not low <= len(r.selected) <= high:
                        invalid(rp + '.selected', '条件集合不满足本题数量限制')
                r.selected = sorted(r.selected, key=opts.index)
            elif q.type == 'number':
                if r.selected or r.operator is None or r.value is None or not math.isfinite(r.value):
                    invalid(rp, '数字条件需要比较符与有限数值')
                current = interval(r)
                if any(overlap(current, prior) for prior in ranges):
                    invalid(rp, '数字条件重叠（按整个实数范围保守检查）')
                ranges.append(current)
            else:
                invalid(rp, '文本题本轮不支持跳转条件')
            if r.action == 'end':
                if r.targets:
                    invalid(rp + '.targets', '结束不能混合题目目标')
            else:
                if not r.targets or not set(r.targets) <= set(ids):
                    invalid(rp + '.targets', '目标不能为空或引用不存在')
                if q.id in r.targets:
                    invalid(rp + '.targets', '禁止跳转到自己')
                r.targets = sorted(set(r.targets), key=order.get)
                graph[q.id].update(r.targets)
    visiting, done = set(), set()
    def visit(qid):
        if qid in visiting:
            invalid(f'questions[{order[qid]}].rules', '跳转图包含循环')
        if qid in done:
            return
        visiting.add(qid)
        for target in graph[qid]:
            visit(target)
        visiting.remove(qid)
        done.add(qid)
    for qid in ids:
        visit(qid)
    result = s.model_dump()
    for q in result['questions']:
        if q.get('source') is None:
            q.pop('source', None)
    return result
