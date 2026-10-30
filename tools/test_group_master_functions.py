"""Regressions for family grouping without losing sparse professional directions."""
import unittest
from group_master_functions import classify,allocate_product

def fixture():
    jobs=[{'id':'p','function_name':'产品研发','code':'RJ005','series_id':'s1','source_ids':['a'],'level':5},
          {'id':'q','function_name':'产品运营','code':'PP015','series_id':'s2','source_ids':['b'],'level':5},
          {'id':'r','function_name':'生产管理','code':'PP055','series_id':'s3','source_ids':['c'],'level':5}]
    series=[{'id':j['series_id'],'function_id':j['function_name'],'function_name':j['function_name'],'name':j['function_name'],'prefix':j['code'][:4],'job_ids':[j['id']]} for j in jobs]
    return {'jobs':jobs,'series':series}

def policy():return {'groups':[{'name':'产品','source_functions':['产品研发','产品运营'],'reason':'用户指定产品PP'}], 'series_overrides':[], 'direction_labels':{},'retain_reasons':{}}

class GroupingTests(unittest.TestCase):
    def test_product_family_retains_distinct_professional_directions(self):
        result=classify(fixture(),policy());self.assertEqual(result['s1']['group_id'],result['s2']['group_id']);self.assertNotEqual(result['s1']['direction_id'],result['s2']['direction_id'])
    def test_sparse_nonproduct_not_absorbed_because_its_code_starts_pp(self):
        result=classify(fixture(),policy());self.assertEqual(result['s3']['group_name'],'生产管理')
    def test_product_override_allows_pp_for_previous_r_research(self):
        m=fixture();result=allocate_product(m,classify(m,policy()),[{'source_id':'a','原版BMJD':{'code':'PP015'}},{'source_id':'b','原版BMJD':{'code':'PP015'}},{'source_id':'c','原版BMJD':{'code':'PP055'}}]);self.assertTrue(result['s1'].startswith('PP'));self.assertEqual(result['s2'],'PP01');self.assertNotIn(result['s1'],{'PP01','PP05'})
    def test_boundary_override_splits_department_by_real_role(self):
        m=fixture();p=policy();p['series_overrides']=[{'series_id':'s1','group':'临床研究','direction_name':'受试者招募','reason':'临床试验招募而非HR'}];r=classify(m,p);self.assertEqual(r['s1']['group_name'],'临床研究');self.assertEqual(r['s1']['direction_name'],'受试者招募');self.assertEqual(r['s2']['group_name'],'产品')
    def test_duplicate_whole_function_rule_rejected(self):
        p=policy();p['groups'].append({'name':'研发','source_functions':['产品研发'],'reason':'错误重复'});self.assertRaises(ValueError,classify,fixture(),p)
    def test_unknown_override_rejected(self):
        p=policy();p['series_overrides']=[{'series_id':'missing','group':'产品'}];self.assertRaises(ValueError,classify,fixture(),p)

if __name__=='__main__':unittest.main()
