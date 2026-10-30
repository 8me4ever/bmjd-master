"""Adversarial checks for professional boundaries, authority and review policy."""
import copy
import unittest

import review_job_jds as review


class JDReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = review.read(review.RULES)
        cls.master = review.read(review.INPUTS[0])
        cls.jobs = {j['code']: j for j in cls.master['jobs']}

    def profile(self, name, function, series=None):
        return review.choose_profile({'code': 'ZZ005', 'name': name,
                                      'series_name': series or name,
                                      'function_name': function}, self.rules)[0]

    def test_financial_preservation_is_not_equipment_maintenance(self):
        self.assertEqual(self.profile('资产保全经理', '资产保全'), '催收保全')
        self.assertEqual(self.profile('诉讼保全担保专员', '担保业务'), '风险')
        self.assertEqual(self.profile('设备保全工程师', '设备保全'), '设备维修')

    def test_safety_object_controls_profile(self):
        self.assertEqual(self.profile('安全运营专家', '信息安全'), '信息安全')
        self.assertEqual(self.profile('高级安全带产品应用工程师', '设计研发'), '产品设计')
        self.assertEqual(self.profile('现场安全专员', 'EHS'), 'EHS')

    def test_commercial_title_overrides_technical_object(self):
        self.assertEqual(self.profile('硬件采购经理', '物流管理'), '采购')
        self.assertEqual(self.profile('媒介销售代表', '销售'), '销售')
        self.assertEqual(self.profile('餐饮销售经理', '销售'), '销售')
        self.assertEqual(self.profile('售前技术支持工程师', '销售'), '售前技术')
        self.assertEqual(self.profile('软件采购经理', '软件开发'), '采购')

    def test_machine_captain_is_not_a_driver(self):
        self.assertEqual(self.profile('双色机长', '生产'), '生产')
        self.assertEqual(self.profile('航空机长', '运输'), '飞行')
        self.assertEqual(self.profile('叉车司机', '生产技术'), '驾驶')

    def test_medical_titles_do_not_grant_people_management(self):
        for name in ['内科主任医师', '内科副主任医师', '药剂科主任药师', '药剂科主管药师']:
            job = {'name': name}
            self.assertNotEqual(review.role_mode(job), '管理', name)
        self.assertEqual(review.role_mode({'name': '内科主任'}), '管理')
        self.assertEqual(review.role_mode({'name': '护理部主任'}), '管理')

    def test_doctor_is_not_an_admission_guide(self):
        job = {'name': '内科住院医师'}
        texts = ['介绍体检流程并引导客户就诊。', '维护客户关系并建立服务档案。', '安排客户预约并提供咨询服务。']
        reasons = review.semantic_problems(job, texts, '临床医生', self.rules['profiles']['临床医生'])
        self.assertIn('医师名称与仅导诊或服务内容不匹配', reasons)

    def test_preserved_legacy_text_not_rewritten_for_low_keywords_alone(self):
        job = {'name': '业务流程专员'}
        texts = ['梳理跨部门协作中的交接节点，明确参与各方的信息传递与完成时限。',
                 '核实重复录入与等待环节的形成原因，提出缩短流转时间的具体办法。',
                 '与参与岗位确认改动后的办理步骤，记录实际使用反馈并形成书面说明。']
        self.assertFalse(review.semantic_problems(job, texts, '流程咨询', self.rules['profiles']['流程咨询']))

    def test_digital_and_physical_light_roles_are_separate(self):
        cg = self.jobs['CT205']; stage = self.jobs['AC435']
        self.assertEqual(review.choose_profile(cg, self.rules)[0], 'CG渲染')
        self.assertEqual(review.choose_profile(stage, self.rules)[0], '舞台灯光')
        cg_text = review.format_jd(review.render_new(cg, self.rules['profiles']['CG渲染']))
        stage_text = review.format_jd(review.render_new(stage, self.rules['profiles']['舞台灯光']))
        self.assertNotIn('舞台', cg_text)
        self.assertNotIn('渲染', stage_text)

    def test_av_lead_is_not_an_actor(self):
        self.assertEqual(review.choose_profile(self.jobs['AC205'], self.rules)[0], '影音技术')
        self.assertEqual(review.role_mode(self.jobs['AC205']), '管理')

    def test_structural_drawer_never_receives_software_tasks(self):
        job = self.jobs['DP045']
        profile = review.choose_profile(job, self.rules)[0]
        self.assertEqual(profile, '建筑结构')
        text = review.format_jd(review.render_new(job, self.rules['profiles'][profile]))
        self.assertIn('施工图', text)
        self.assertNotIn('代码', text)

    def test_teaching_specialties_stay_educational(self):
        self.assertEqual(self.profile('会计类课程讲师', '职业教育/培训辅导'), '教学')
        self.assertEqual(self.profile('教师测评经理', '教师发展'), '教育督导')
        self.assertEqual(self.profile('幼儿体育教师（小班）', '学前教育'), '幼教')
        self.assertEqual(self.profile('电教教师', '教务'), 'IT运维')

    def test_data_models_are_not_3d_art(self):
        self.assertEqual(self.profile('勘探开发数据建模工程师', '数据分析'), '数据分析')

    def test_all_new_drafts_have_4_or_5_items_and_label_invention(self):
        for job in self.master['jobs']:
            key, _ = review.choose_profile(job, self.rules)
            clauses = review.render_new(job, self.rules['profiles'][key])
            self.assertIn(len(clauses), {4, 5}, job['code'])
            self.assertEqual([c['number'] for c in clauses], list(range(1, len(clauses)+1)))
            self.assertEqual(len({c['text'] for c in clauses}), len(clauses))
            for c in clauses:
                self.assertEqual(c['basis_type'], '专业补写')
                self.assertFalse(c['source_refs'])
                self.assertNotIn('{subject}', c['text'])

    def test_assistant_keeps_support_boundary(self):
        job = self.jobs['LO306']; key, _ = review.choose_profile(job, self.rules)
        self.assertEqual(review.role_mode(job), '辅助或初级')
        clauses = review.render_new(job, self.rules['profiles'][key])
        self.assertTrue(all(c['text'].startswith('在指导下，') for c in clauses))
        self.assertFalse(any('统筹' in c['text'] for c in clauses))


if __name__ == '__main__':
    unittest.main()
