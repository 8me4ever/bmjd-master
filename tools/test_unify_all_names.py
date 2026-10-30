"""Regressions for the complete name/code catalog and metadata-only boundaries."""
import unittest

import unify_all_names as task


class MetadataRulesTests(unittest.TestCase):
    def metadata(self, specialty='结构设计', function='研发'):
        return {'原版BMJD': {'function': function}, '最新输入_修改版6': {'specialty': specialty}}

    def current(self, function='软件开发', prefix='RB13'):
        return {'function_name': function, 'series_prefix': prefix}

    def test_programming_languages_keep_identity_symbols(self):
        cpp = task.clean('高级程序员（C++）')
        csharp = task.clean('高级程序员（C#）')
        self.assertEqual(cpp, '高级C++开发工程师')
        self.assertEqual(csharp, '高级C#开发工程师')
        self.assertNotEqual(task.key(cpp), task.key(csharp))

    def test_unicode_radicals_and_whitespace_are_normalized(self):
        self.assertEqual(task.clean('高级Android framework ⼯程师\n'), '高级Androidframework工程师')

    def test_structure_design_is_not_software(self):
        function, _ = task.route_function('高级结构设计工程师', self.metadata(), self.current())
        self.assertEqual(function, '设计研发')

    def test_store_accounting_is_not_human_resources(self):
        function, _ = task.route_function('门店会计', self.metadata('门店', '门店'), self.current('人力资源', 'AI04'))
        self.assertEqual(function, '财务')

    def test_ui_design_and_ui_programming_are_distinct(self):
        design, _ = task.route_function('高级UI设计师', self.metadata('UI设计'), self.current('美工', 'AD11'))
        development, _ = task.route_function('高级UI开发工程师', self.metadata('UI开发'), self.current('美工', 'AD11'))
        self.assertEqual((design, development), ('美工', '软件开发'))

    def test_generic_testing_does_not_connect_different_objects(self):
        software, assumed_soft = task.test_scope_title('高级测试工程师', self.metadata('测试'), self.current('测试', 'TE02'))
        product, assumed_product = task.test_scope_title('高级测试工程师', self.metadata('测试'), self.current('信息技术', 'AK02'))
        self.assertEqual((software, product), ('高级软件测试工程师', '高级产品测试工程师'))
        self.assertTrue(assumed_soft and assumed_product)
        self.assertNotEqual(task.key(software), task.key(product))

    def test_explicit_testing_specialty_is_evidence_not_family_guess(self):
        title, inferred = task.test_scope_title('测试经理', self.metadata('设备测试'), self.current('设备测试', 'A000'))
        self.assertEqual(title, '设备测试经理')
        self.assertFalse(inferred)

    def test_jd_content_cannot_change_metadata_routing(self):
        current = self.current('软件开发', 'RB13')
        before = task.route_function('初级研发工程师', self.metadata('通用研发'), current)
        current['standard_jd'] = '与岗位名称相反的旧错贴文本'
        self.assertEqual(before, task.route_function('初级研发工程师', self.metadata('通用研发'), current))
        self.assertEqual(before[0], '研发')

    def test_name_qualification_uses_recorded_grades_not_new_seniority(self):
        groups = [{'title': '库管', 'code': 'AX136', 'level': 6, 'function': '仓储', 'source_ids': ['S1'], 'aliases': [], 'locked': False},
                  {'title': '库管', 'code': 'AX137', 'level': 7, 'function': '仓储', 'source_ids': ['S2'], 'aliases': [], 'locked': False}]
        records = task.qualify_cross_level_names(groups)
        self.assertEqual([g['title'] for g in groups], ['库管（6级）', '库管（7级）'])
        self.assertEqual([g['level'] for g in groups], [6, 7])
        self.assertEqual(len(records), 1)

    def test_name_qualification_cannot_hide_same_grade_duplicates(self):
        groups = [{'title': '同名主管', 'level': 4}, {'title': '同名主管', 'level': 4}]
        with self.assertRaisesRegex(ValueError, '同级同名必须先解决'):
            task.qualify_cross_level_names(groups)


class FullCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = task.prior.read(task.OUT / '名称代码主库.json')
        cls.jobs = cls.master['jobs']
        cls.by_id = {j['id']: j for j in cls.jobs}
        cls.sources = task.prior.read(task.OUT / '来源去向映射.json')
        cls.by_source = {s['source_id']: s for s in cls.sources}
        cls.baseline = task.prior.read(task.ROOT / task.prior.BASE)
        cls.previous = task.prior.read(task.PREVIOUS)
        cls.previous_mappings = task.prior.read(task.OUT / '前版ID名称代码映射.json')
        cls.prev_by_code = {m['previous_code']: m for m in cls.previous_mappings}
        cls.baseline_mappings = task.prior.read(task.OUT / '基线ID名称代码映射.json')
        cls.inferences = task.prior.read(task.OUT / '基线推定岗位处置.json')
        cls.rules = task.prior.read(task.OUT / '统一规则.json')

    def validate(self, sources=None, mappings=None, inferences=None):
        task.validate(self.jobs, self.master['series'], sources or self.sources, self.baseline, self.previous,
                      self.previous_mappings, mappings or self.baseline_mappings, inferences or self.inferences, self.rules)

    def targets_for_original_name(self, name):
        ids = {jid for source in self.sources if source['original_name'] == name for jid in source['target_job_ids']}
        self.assertTrue(ids, '测试样本未找到: ' + name)
        return [self.by_id[j] for j in ids]

    def test_all_inferred_baseline_ids_have_a_real_disposition(self):
        expected = {j['id'] for j in self.baseline['jobs'] if j['inferred_identity']}
        self.assertEqual({r['baseline_job_id'] for r in self.inferences}, expected)
        self.assertEqual(len(expected), 3092)
        self.assertTrue(all(r['target_job_ids'] and r['actions'] and r['current_inference_retained'] for r in self.inferences))
        self.assertEqual(self.master['summary']['unprocessed_baseline_inference_jobs'], 0)

    def test_duplicate_source_cannot_hide_missing_source(self):
        sources = list(self.sources)
        sources[-1] = sources[0]
        with self.assertRaisesRegex(ValueError, '来源ID重复|来源总账集合'):
            self.validate(sources=sources)

    def test_duplicate_baseline_mapping_cannot_hide_missing_identity(self):
        mappings = list(self.baseline_mappings)
        mappings[-1] = mappings[0]
        with self.assertRaisesRegex(ValueError, '基线ID映射集合'):
            self.validate(mappings=mappings)

    def test_inference_ledger_cannot_silently_clear_assumptions(self):
        inferences = list(self.inferences)
        inferences[0] = dict(inferences[0], current_inference_retained=False)
        with self.assertRaisesRegex(ValueError, '无依据取消'):
            self.validate(inferences=inferences)

    def test_current_codes_and_standard_names_are_unique_per_level(self):
        self.assertEqual(len(self.jobs), len({j['code'] for j in self.jobs}))
        self.assertEqual(len(self.jobs), len({(task.key(j['name']), j['level']) for j in self.jobs}))
        self.assertEqual(len(self.jobs), len({task.key(j['name']) for j in self.jobs}))
        self.assertTrue(all(int(j['code'][-1]) == j['level'] for j in self.jobs))

    def test_store_accounting_is_separated_from_hr(self):
        self.assertTrue(all(j['function_name'] == '财务' for j in self.targets_for_original_name('门店会计')))
        self.assertTrue(all(j['function_name'] == '财务' for j in self.targets_for_original_name('门店财务主管')))

    def test_nutrition_and_pharmacy_are_not_marketing_roles(self):
        self.assertTrue(all(j['function_name'] == '临床科室' for j in self.targets_for_original_name('初级营养师')))
        self.assertTrue(all(j['function_name'] == '医技科室' for j in self.targets_for_original_name('驻店药师')))

    def test_physical_structure_design_is_not_software(self):
        candidates = self.targets_for_original_name('高级结构设计/工艺设计工程师')
        self.assertTrue(all(j['function_name'] != '软件开发' for j in candidates))
        self.assertTrue(all(j['function_name'] == '软件开发' for j in self.targets_for_original_name('软件开发工程师')))

    def test_life_and_property_claims_are_different_jobs(self):
        life = {j['id'] for j in self.targets_for_original_name('寿险理赔经理')}
        property_claims = {j['id'] for j in self.targets_for_original_name('财险理赔经理')}
        self.assertFalse(life & property_claims)

    def test_generic_architecture_and_algorithm_forks_are_merged(self):
        self.assertEqual(self.prev_by_code['RS714']['target_job_ids'], self.prev_by_code['RI854']['target_job_ids'])
        self.assertEqual(self.prev_by_code['RD394']['target_job_ids'], self.prev_by_code['RI984']['target_job_ids'])

    def test_investment_and_generic_project_duplicates_are_merged(self):
        for level in range(3, 7):
            self.assertEqual(self.prev_by_code[f'FA07{level}']['target_job_ids'], self.prev_by_code[f'IO07{level}']['target_job_ids'])
        self.assertEqual(self.prev_by_code['PC035']['target_job_ids'], self.prev_by_code['PC085']['target_job_ids'])

    def test_customs_foreman_is_not_automatically_promoted(self):
        self.assertTrue(all(j['level'] == 5 for j in self.targets_for_original_name('报关组长')))
        self.assertTrue(all(j['level'] == 4 for j in self.targets_for_original_name('报关主管')))

    def test_shared_stage_cg_sources_do_not_cross_identity_mappings(self):
        for code in ('AC435', 'CT205'):
            self.assertEqual(self.prev_by_code[code]['current_codes'], [code])
        self.assertEqual(len(self.by_source['SRC-传媒-1045']['target_job_ids']), 2)
        self.assertEqual(self.by_source['SRC-传媒-1045']['authorization'],
                         next(s for s in self.baseline['sources'] if s['source_id'] == 'SRC-传媒-1045')['allocations'])

    def test_confirmed_ladder_does_not_force_ordinary_sibling_to_recode(self):
        self.assertEqual(self.prev_by_code['LO305']['current_codes'], ['LO305'])
        self.assertEqual(self.prev_by_code['CT204']['current_codes'], ['CT204'])

    def test_paused_sources_remain_unassigned(self):
        paused = [s for s in self.sources if s['state'] == '用户暂缓']
        self.assertEqual(len(paused), 23)
        self.assertTrue(all(not s['target_job_ids'] for s in paused))

    def test_revision_changes_are_traced_and_do_not_drop_sources(self):
        differences = task.prior.read(task.OUT / '原表版本差异.json')
        self.assertEqual(sum(d['type'] == '原版到修改版名称修订' for d in differences), 43)
        self.assertEqual(sum(d['type'] == '空白规范化' for d in differences), 66)
        self.assertEqual(len(self.by_source), 19249)

    def test_this_catalog_contains_no_jd_fields(self):
        self.assertTrue(all(not any('jd' in k.casefold() for k in j) for j in self.jobs))
        self.assertFalse(self.master['summary']['jd_matching_started'])


if __name__ == '__main__':
    unittest.main()
