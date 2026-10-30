import copy
import json
import unittest
from pathlib import Path
from complete_master_v2 import route,candidate,make_jd

ROOT=Path(__file__).resolve().parents[1]
POLICY=json.loads((ROOT/'主库v2_层级补全_20261030/补全规则.json').read_text())
RULES=json.loads((ROOT/'岗位JD匹配审查_20261029/JD审查与编写规则.json').read_text())
def fixtures(name,roles,function='研发',profile='技术研发'):
    s={'id':'SERIES','name':name,'function_name':function}
    js=[{'id':f'J{lv}','name':title,'level':lv,'jd_profile':profile,'series_id':'SERIES'} for lv,title in roles]
    return s,js


class CompletionPolicyTests(unittest.TestCase):
    def test_typical_function_assistant_name_follows_existing_ladder(self):
        s,j=fixtures('薪酬',[(3,'薪酬经理'),(4,'薪酬主管'),(5,'薪酬专员')],function='人力资源',profile='人力资源')
        before=copy.deepcopy(j);r=route(s,j,POLICY,set())
        self.assertEqual(candidate(r,6,POLICY)[0],'薪酬助理');self.assertEqual(j,before)

    def test_professional_missing_fifth_uses_own_title_not_generic_specialist(self):
        s,j=fixtures('逻辑验证',[(4,'高级逻辑验证工程师'),(6,'初级逻辑验证工程师')],profile='硬件研发')
        r=route(s,j,POLICY,set());self.assertEqual(candidate(r,5,POLICY)[0],'逻辑验证工程师');self.assertEqual(candidate(r,3,POLICY)[0],'资深逻辑验证工程师')

    def test_shifted_design_respects_existing_high_at_three_base_at_four(self):
        s,j=fixtures('规划',[(3,'高级规划设计师/规划设计经理'),(4,'规划设计师/规划设计主管')],function='规划设计',profile='工程设计')
        r=route(s,j,POLICY,set());self.assertEqual(candidate(r,5,POLICY)[0],'初级规划设计师');self.assertEqual(candidate(r,6,POLICY)[0],'助理规划设计师')

    def test_doctor_suffix_is_not_misread_and_no_sixth_grade_physician_is_invented(self):
        s,j=fixtures('内科主任医师',[(2,'内科主任医师'),(3,'内科副主任医师'),(4,'内科主治医师'),(5,'内科住院医师')],function='临床科室',profile='临床医生')
        self.assertIsNone(candidate(route(s,j,POLICY,set()),6,POLICY)[0])
        wrong=[{**j[0],'name':'内科副主任医师'}];self.assertEqual(route(s,wrong,POLICY,set())['type'],'medical_boundary')

    def test_pharmacist_professional_rank_not_manager_and_assistant_scope_bounded(self):
        s,j=fixtures('药剂科主管药师',[(4,'药剂科主管药师'),(5,'药剂师')],function='临床科室',profile='药师');r=route(s,j,POLICY,set())
        self.assertEqual(candidate(r,3,POLICY)[0],'药剂科副主任药师')
        name=candidate(r,6,POLICY)[0];text,clauses,_,mode,_=make_jd(name,6,r,j,POLICY,RULES)
        self.assertEqual(name,'药剂科药士');self.assertEqual(mode,'辅助或初级');self.assertEqual(len(clauses),4);self.assertIn('不独立承担处方审核',text)

    def test_fixed_ceo_and_known_jd_issue_and_paused_roles_not_propagated(self):
        for name,function,profile,issues in [('总经理','综合管理','经营管理',set()),('叉车','生产','生产',set()),('客服转接','客户服务','客服',{'J5'})]:
            s,j=fixtures(name,[(5,name)],function,profile);r=route(s,j,POLICY,issues)
            self.assertIsNone(candidate(r,3,POLICY)[0])

    def test_plain_worker_no_arbitrary_business_manager(self):
        s,j=fixtures('发泡',[(7,'发泡操作工')],function='生产',profile='生产');r=route(s,j,POLICY,set())
        self.assertIsNone(candidate(r,3,POLICY)[0]);self.assertEqual(candidate(r,4,POLICY)[0],'发泡作业主管');self.assertEqual(candidate(r,6,POLICY)[0],'熟练发泡操作工')

    def test_single_assistant_row_does_not_create_senior_assistant(self):
        s,j=fixtures('音响师',[(6,'音响师助理')],function='文艺活动',profile='音响录音');r=route(s,j,POLICY,set())
        self.assertEqual(candidate(r,4,POLICY)[0],'高级音响师')

    def test_driver_group_leader_is_not_reused_as_junior_driver_title(self):
        s,j=fixtures('一般车辆运输司机',[(5,'一般车辆运输司机班长')],function='物流',profile='驾驶')
        self.assertEqual(candidate(route(s,j,POLICY,set()),6,POLICY)[0],'熟练一般车辆运输司机')

    def test_cook_grade_modifier_inside_department_name_is_removed(self):
        s,j=fixtures('员工餐厅高级厨师',[(5,'员工餐厅高级厨师')],function='餐饮',profile='餐饮')
        r=route(s,j,POLICY,set())
        self.assertEqual(candidate(r,3,POLICY)[0],'员工餐厅行政总厨')
        self.assertEqual(candidate(r,6,POLICY)[0],'员工餐厅初级厨师')

    def test_new_jd_four_or_five_clauses_transparent_provenance(self):
        s,j=fixtures('组织发展',[(4,'组织发展主管'),(5,'组织发展专员')],function='人力资源',profile='组织发展');r=route(s,j,POLICY,set())
        for level in [3,6]:
            name=candidate(r,level,POLICY)[0];text,cs,profile,mode,ref=make_jd(name,level,r,j,POLICY,RULES)
            self.assertIn(len(cs),[4,5]);self.assertTrue(all(c['source_refs']==[] for c in cs));self.assertIn(ref,{'J4','J5'})
            if level==6:self.assertTrue(all('指导' in c['text'] for c in cs))


if __name__=='__main__':unittest.main()
