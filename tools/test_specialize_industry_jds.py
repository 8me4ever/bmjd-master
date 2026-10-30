"""Professional boundary and preservation regressions for industry-only JDs."""
import copy
import unittest

import specialize_industry_jds as s


class IndustryJDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=s.read(s.RULES)
        cls.parent_rules=s.read(s.ROOT/'岗位JD匹配审查_20261029/JD审查与编写规则.json')
        cls.jobs={j['code']:j for j in s.read(s.MASTER)['jobs']}

    def profile(self,code,industry,context='本行业岗位原始资料'):
        matches=s.match_profile(self.jobs[code],industry,self.rules['profiles'],context)
        return matches[0] if matches else None

    def test_common_functions_are_preserved_in_every_industry(self):
        protected=set(self.rules['protected_functions'])
        for j in self.jobs.values():
            if j['function_name'] in protected:
                for industry in j['industries']:
                    status,profile,_,_=s.decide(j,industry,self.rules,self.parent_rules,'行业专业资料')
                    self.assertEqual(status,'保留-通用职能')
                    self.assertIsNone(profile)

    def test_chip_engineer_gets_chip_tasks(self):
        p=self.profile('RB055','高科技')
        self.assertEqual(p['id'],'科技-芯片数字设计')
        self.assertGreaterEqual(len(s.professional_gaps(self.jobs['RB055'],p)),2)
        text=s.jd_text(s.render_specialized(self.jobs['RB055'],'高科技',p))
        self.assertIn('IP集成',text);self.assertIn('时序',text)

    def test_ai_product_manager_is_not_written_as_a_teacher(self):
        p=self.profile('CX003','教育')
        self.assertEqual(p['id'],'教育-AI产品')
        text=s.jd_text(s.render_specialized(self.jobs['CX003'],'教育',p))
        self.assertIn('产品需求',text)
        self.assertNotIn('指导学习者',text)

    def test_storyboard_is_not_a_model_asset(self):
        p=self.profile('AR003','传媒')
        self.assertEqual(p['id'],'传媒-分镜')
        text=s.jd_text(s.render_specialized(self.jobs['AR003'],'传媒',p))
        self.assertIn('镜头连接',text)
        self.assertNotIn('拓扑',text)

    def test_ic_layout_and_pcb_layout_remain_distinct(self):
        self.assertEqual(self.profile('RE224','高科技')['id'],'科技-IC版图')
        self.assertEqual(self.profile('RS094','高科技','高速PCB板布局和布线，SI及PI仿真')['id'],'科技-PCB信号')

    def test_ship_outfitting_is_not_hull_segment_production(self):
        p=self.profile('AW003','制造')
        self.assertEqual(p['id'],'制造-船舶舾装')
        text=s.jd_text(s.render_specialized(self.jobs['AW003'],'制造',p))
        self.assertIn('安装',text)
        self.assertNotIn('焊缝',text)

    def test_clinical_pharmacology_is_not_animal_testing(self):
        p=self.profile('RF043','医药')
        self.assertEqual(p['id'],'医药-临床药理')
        text=s.jd_text(s.render_specialized(self.jobs['RF043'],'医药',p))
        self.assertIn('药代动力学',text)
        self.assertNotIn('动物',text)

    def test_lab_animal_caretaker_does_not_design_dosing(self):
        p=self.profile('RF216','医药')
        self.assertEqual(p['id'],'医药-实验动物照护')
        text=s.jd_text(s.render_specialized(self.jobs['RF216'],'医药',p))
        self.assertIn('饲喂',text)
        self.assertNotIn('给药',text)

    def test_carbon_credit_project_does_not_become_capture_r_and_d(self):
        p=self.profile('PS005','能源化工','CDM项目设计文件PDD、基准线及监测计划')
        self.assertEqual(p['id'],'能源-减排项目')
        text=s.jd_text(s.render_specialized(self.jobs['PS005'],'能源化工',p))
        self.assertIn('额外性',text)
        self.assertNotIn('捕集',text)

    def test_no_borrowing_industry_direction_for_a_shared_code(self):
        job=self.jobs['RB055']
        self.assertIsNone(self.profile('RB055','物流'))

    def test_department_annotation_does_not_decide_profession(self):
        self.assertIsNone(self.profile('DP003','地产'))

    def test_exact_parent_provenance_and_local_sources_are_both_required(self):
        original=self.jobs['RB055'];modified=copy.deepcopy(original)
        modified['jd']='1、另一份专业原稿。'
        status,_,_,_=s.decide(modified,'高科技',self.rules,self.parent_rules,'芯片设计与验证')
        self.assertEqual(status,'保留-现稿非通用补写框架')
        status,_,_,_=s.decide(original,'高科技',self.rules,self.parent_rules,'芯片设计与验证',False)
        self.assertEqual(status,'保留-本行业专业方向依据不足')

    def test_new_writing_does_not_mutate_parent_job(self):
        job=copy.deepcopy(self.jobs['RF006']);before=copy.deepcopy(job)
        p=self.profile('RF006','医药')
        clauses=s.render_specialized(job,'医药',p)
        self.assertEqual(job,before)
        self.assertEqual(len(clauses),4)
        self.assertTrue(all(c['text'].startswith('在指导下，') for c in clauses))
        self.assertTrue(all(c['basis_type']=='专业补写' and not c['source_refs'] for c in clauses))

    def test_professional_titles_do_not_grant_manager_authority(self):
        job=self.jobs['DR033'];p=self.profile('DR033','医药')
        self.assertEqual(job['jd_role_mode'],'资深专业')
        text=s.jd_text(s.render_specialized(job,'医药',p))
        self.assertNotIn('人员分工',text)
        self.assertNotIn('审批',text)


if __name__=='__main__':unittest.main()
