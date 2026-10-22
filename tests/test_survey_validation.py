"""Pure validation boundaries; does not access MongoDB."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from pydantic import ValidationError
from backend.survey_models import validate_structure

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.s={'title':'测试','questions':[{'id':'m','title':'多选','type':'multiple','options':[{'id':'a','label':'A'},{'id':'b','label':'B'}], 'rules':[{'id':'r','selected':['b','a'],'targets':['n','t','n']}]},{'id':'t','title':'文字','type':'text'},{'id':'n','title':'数字','type':'number'}]}
    def rejects(self):
        with self.assertRaises((HTTPException,ValidationError)):validate_structure(self.s,True)
    def test_exact_set_and_targets(self):
        d=validate_structure(self.s,True);r=d['questions'][0]['rules'][0]
        self.assertEqual(r['selected'],['a','b']);self.assertEqual(r['targets'],['t','n'])
    def test_reorder_keeps_identity_and_reorders_targets(self):
        self.s['questions'][1:]=reversed(self.s['questions'][1:]);r=validate_structure(self.s)['questions'][0]['rules'][0]
        self.assertEqual(r['targets'],['n','t'])
    def test_exact_excludes_range(self):
        self.s['questions'][0].update(exact_choices=2,min_choices=1);self.rejects()
    def test_impossible_match_size(self):
        self.s['questions'][0]['max_choices']=1;self.rejects()
    def test_min_max(self):
        self.s['questions'][1].update(min_length=10,max_length=2);self.rejects()
    def test_required_zero(self):
        self.s['questions'][1].update(required=True,max_length=0);self.rejects()
    def test_no_integer_in_range(self):
        self.s['questions'][2].update(minimum=1.1,maximum=1.9,integer_only=True);self.rejects()
    def test_nonfinite(self):
        self.s['questions'][2]['minimum']=float('inf');self.rejects()
    def test_bool_not_number(self):
        self.s['questions'][2]['minimum']=True;self.rejects()
    def test_touching_numeric_ranges(self):
        self.s['questions'][2]['rules']=[{'id':'r1','operator':'lt','value':5,'action':'end'},{'id':'r2','operator':'gte','value':5,'action':'end'}]
        validate_structure(self.s,True)
        self.s['questions'][2]['rules'][0]['operator']='lte';self.rejects()
    def test_blank_title(self):
        self.s['title']='  ';self.rejects()
    def test_empty_draft_not_publishable(self):
        self.s['questions']=[];validate_structure(self.s);self.rejects()
    def test_unique_ids(self):
        self.s['questions'][1]['id']='m';self.rejects()
    def test_wrong_type_constraint(self):
        self.s['questions'][1]['minimum']=0;self.rejects()

if __name__=='__main__':unittest.main(verbosity=2)
