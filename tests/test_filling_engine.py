"""Pure state-machine tests, separate from real MongoDB integration evidence."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from backend.survey_models import validate_structure
from backend.filling_engine import initial, transition, answer_error, all_errors


def make(n=7):
    return {'title':'QA engine','questions':[{'id':str(i),'type':'single','title':str(i),'required':False,'options':[{'id':'A','label':'A'},{'id':'B','label':'B'}],'rules':[]} for i in range(1,n+1)]}

def jump(s, q, targets=None, selected=None):
    s['questions'][q-1]['rules']=[{'id':'r','selected':selected or ['A'],'action':'end' if targets is None else 'targets','targets':[] if targets is None else [str(t) for t in targets]}]

def step(s,d,action,**kw):return transition(s,d,action,**kw)
def save(s,d,v):return step(s,d,'save',question_id=d['current'],value=v)
def route(s,values=None):
    s=validate_structure(s,True);d=initial(s);seen=[]
    while d['current']:
        seen.append(d['current']);d=save(s,d,(values or {}).get(d['current'],'A'));d=step(s,d,'next')
    return seen,d

class EngineTests(unittest.TestCase):
    def test_normal_optional_order(self):self.assertEqual(route(make())[0],list('1234567'))
    def test_single_target(self):
        s=make(6);jump(s,1,[5]);self.assertEqual(route(s)[0],list('152346'))
    def test_multitarget_continuous(self):
        s=make();jump(s,1,[5,3,5]);jump(s,3,[7]);self.assertEqual(route(s)[0],list('1375246'))
    def test_exact_multiple(self):
        s=make(5);s['questions'][0]['type']='multiple';jump(s,1,[5,3],['A','B'])
        self.assertEqual(route(s,{'1':['B','A']})[0],list('13524'))
        self.assertEqual(route(s,{'1':['A']})[0],list('12345'))
    def test_visited_not_requeued(self):
        s=make(3);jump(s,2,[1]);self.assertEqual(route(s)[0],list('123'))
    def test_chain_revoked_independent_source_kept(self):
        s=make(8);jump(s,1,[8]);jump(s,2,[4,8]);jump(s,4,[5,8]);s=validate_structure(s,True)
        d=initial(s);d=save(s,d,'B');d=step(s,d,'next') # 2
        d=save(s,d,'A');d=step(s,d,'next') # 4
        d=save(s,d,'A');d=step(s,d,'next') # 5; 8 is pending from 2 and 4
        d=step(s,d,'goto',target='1');d=save(s,d,'A') # independent root -> 8
        d=step(s,d,'goto',target='2');d=save(s,d,'B') # revoke 2 and descendant 4
        self.assertEqual(d['pending'],['8','3','6','7'])
        self.assertEqual([x['question_id'] for x in d['sources']],['1'])
        self.assertEqual(d['answers']['4'],'A');self.assertIn('5',d['visited'])
    def test_descendant_with_multiple_parents_survives_one_chain_revocation(self):
        raw=make(9);jump(raw,1,[8]);jump(raw,2,[4,8]);jump(raw,4,[5,8]);jump(raw,8,[7,9]);s=validate_structure(raw,True)
        d=step(s,save(s,initial(s),'B'),'next')
        d=step(s,save(s,d,'A'),'next')
        d=step(s,save(s,d,'A'),'next') # currently 5
        d=step(s,d,'goto',target='1');d=save(s,d,'A')
        d=step(s,d,'goto',target='5');d=step(s,d,'next') # 8, supported by 1, 2 and 4
        d=step(s,save(s,d,'A'),'next') # 7, with 9 pending
        d=step(s,d,'goto',target='2');d=save(s,d,'B')
        source8=next(x for x in d['sources'] if x['question_id']=='8')
        self.assertEqual(len(source8['parents']),1)
        self.assertEqual(d['pending'][0],'9')
        self.assertEqual({x['question_id'] for x in d['sources']},{'1','8'})

    def test_partial_change_revokes_then_new_answer_recalculates(self):
        s=make(5);jump(s,1,[5]);s=validate_structure(s,True);d=save(s,initial(s),'A');self.assertEqual(d['pending'][0],'5')
        d=save(s,d,'B');self.assertEqual(d['pending'],list('2345'))
        d=save(s,d,'A');self.assertEqual(d['pending'][0],'5')
    def test_restricted_and_free_navigation(self):
        s=validate_structure(make(),True);d=step(s,initial(s),'goto',target='7');self.assertEqual(d['current'],'7')
        raw=make();jump(raw,1,[5]);s=validate_structure(raw,True)
        with self.assertRaises(HTTPException):step(s,initial(s),'goto',target='7')
    def test_end_required_supplement(self):
        raw=make(3);jump(raw,1);raw['questions'][2]['required']=True;s=validate_structure(raw,True)
        d=step(s,save(s,initial(s),'A'),'next');self.assertTrue(d['ended'])
        self.assertEqual(all_errors(s,d)[0]['question_id'],'3')
        d=step(s,d,'goto',target='3');d=save(s,d,'B');d=step(s,d,'finish');self.assertEqual(all_errors(s,d),[])
    def test_no_client_forged_question_or_option(self):
        s=validate_structure(make(),True);d=initial(s)
        for qid,v in [('fake','A'),('1','fake')]:
            with self.assertRaises(HTTPException):step(s,d,'save',question_id=qid,value=v)
    def test_four_type_bounds(self):
        qs=[{'id':'s','title':'s','type':'single','required':True,'options':[{'id':'A','label':'A'},{'id':'B','label':'B'}]},
            {'id':'m','title':'m','type':'multiple','min_choices':2,'max_choices':2,'options':[{'id':'A','label':'A'},{'id':'B','label':'B'}]},
            {'id':'t','title':'t','type':'text','required':True,'min_length':2,'max_length':3},
            {'id':'n','title':'n','type':'number','minimum':1,'maximum':3,'integer_only':True}]
        s=validate_structure({'title':'bounds','questions':qs},True);q=s['questions']
        self.assertIsNotNone(answer_error(q[0],''));self.assertIsNotNone(answer_error(q[0],'fake'));self.assertIsNone(answer_error(q[0],'A'))
        self.assertIsNone(answer_error(q[1],[]));self.assertIsNotNone(answer_error(q[1],['A']));self.assertIsNotNone(answer_error(q[1],['A','A']));self.assertIsNone(answer_error(q[1],['B','A']))
        self.assertIsNone(answer_error(q[2],' 中\t文\u3000'));self.assertIsNotNone(answer_error(q[2],' \n'));self.assertIsNotNone(answer_error(q[2],'abcd'))
        for v in ['NaN','Infinity','-','1e9999','0','4','1.5',True]:self.assertIsNotNone(answer_error(q[3],v),v)
        for v in ['1','3','2e0','']:self.assertIsNone(answer_error(q[3],v),v)
    def test_incomplete_draft_saved_but_next_rejected(self):
        s=validate_structure({'title':'n','questions':[{'id':'n','type':'number','title':'n','required':True}]},True)
        d=save(s,initial(s),'-');self.assertEqual(d['answers']['n'],'-')
        with self.assertRaises(HTTPException):step(s,d,'next')

if __name__=='__main__':unittest.main(verbosity=2)
