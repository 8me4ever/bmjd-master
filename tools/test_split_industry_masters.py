import copy
import unittest
from split_industry_masters import partition
from audit_industry_masters import same_table, verify_child


def fixture():
    shared = {'id': 'SHARED', 'code': 'GM001', 'name': '总经理(集团)', 'industries': ['制造', '高科技'],
              'source_ids': ['SRC-A', 'SRC-B'], 'jd': '1、统筹经营工作。', 'jd_clauses': [{'number': 1, 'text': '统筹经营工作。'}]}
    special = {'id': 'SPECIAL', 'code': 'RD005', 'name': '研发工程师', 'industries': ['高科技'],
               'source_ids': ['SRC-C'], 'jd': '1、开展研发。', 'jd_clauses': [{'number': 1, 'text': '开展研发。'}]}
    routes = [{'source_id': 'SRC-A', 'industry': '制造', 'state': '全库统一收录', 'target_job_ids': ['SHARED']},
              {'source_id': 'SRC-B', 'industry': '高科技', 'state': '全库统一收录', 'target_job_ids': ['SHARED']},
              {'source_id': 'SRC-C', 'industry': '高科技', 'state': '全库统一收录', 'target_job_ids': ['SPECIAL']},
              {'source_id': 'PAUSED', 'industry': '制造', 'state': '用户暂缓', 'target_job_ids': []}]
    return [shared, special], routes


class IndustryPartitionTests(unittest.TestCase):
    def test_shared_job_keeps_one_identity_and_code_in_both_children(self):
        jobs, routes = fixture()
        before = copy.deepcopy(jobs)
        children = partition(jobs, routes)
        a = children['制造'][0]; b = children['高科技'][0]
        self.assertEqual((a['id'], a['code'], a['name'], a['jd']), (b['id'], b['code'], b['name'], b['jd']))
        self.assertEqual(a['industry_membership']['source_ids'], ['SRC-A'])
        self.assertEqual(b['industry_membership']['source_ids'], ['SRC-B'])
        for k, v in jobs[0].items():
            self.assertEqual(a[k], v)
        self.assertEqual(jobs, before)

    def test_industry_specific_job_is_not_broadcast_to_other_industries(self):
        jobs, routes = fixture()
        children = partition(jobs, routes)
        self.assertEqual([j['id'] for j in children['制造']], ['SHARED'])
        self.assertEqual([j['id'] for j in children['高科技']], ['SHARED', 'SPECIAL'])

    def test_paused_source_is_not_reactivated(self):
        jobs, routes = fixture()
        routes[-1]['target_job_ids'] = ['SHARED']
        with self.assertRaisesRegex(ValueError, '暂缓'):
            partition(jobs, routes)

    def test_changed_industry_label_is_not_silently_trusted(self):
        jobs, routes = fixture()
        jobs[0]['industries'] = ['制造']
        with self.assertRaisesRegex(ValueError, '行业标签'):
            partition(jobs, routes)

    def test_duplicate_code_with_different_id_is_rejected(self):
        jobs, routes = fixture()
        jobs[1]['code'] = jobs[0]['code']
        with self.assertRaisesRegex(ValueError, '不唯一'):
            partition(jobs, routes)

    def test_misrouted_source_is_detected(self):
        jobs, routes = fixture()
        routes[0]['target_job_ids'] = ['SPECIAL']
        with self.assertRaises(ValueError):
            partition(jobs, routes)

    def test_unknown_industry_is_not_invented(self):
        jobs, routes = fixture()
        routes[0]['industry'] = '新建行业'
        with self.assertRaisesRegex(ValueError, '以外'):
            partition(jobs, routes)

    def test_multiple_original_rows_in_one_industry_only_make_one_job(self):
        jobs, routes = fixture()
        jobs[0]['source_ids'].append('SRC-A2')
        routes.append(dict(routes[0], source_id='SRC-A2'))
        child = partition(jobs, routes)['制造']
        self.assertEqual(len(child), 1)
        self.assertEqual(child[0]['industry_membership']['source_ids'], ['SRC-A', 'SRC-A2'])

    def test_duplicate_source_id_is_rejected(self):
        jobs, routes = fixture()
        routes.append(dict(routes[0]))
        with self.assertRaisesRegex(ValueError, '来源ID重复'):
            partition(jobs, routes)

    def test_independent_audit_rejects_renamed_child_job(self):
        jobs, routes = fixture()
        child_jobs = partition(jobs, routes)['制造']
        child_jobs[0]['name'] = '行业专属总经理'
        child = {'jobs': child_jobs, 'industry': '制造', 'tier': 1,
                 'sources': [r for r in routes if r['industry'] == '制造'], 'functions': [], 'series': []}
        checks, _ = verify_child(jobs, child, {'SHARED'}, child['sources'], '制造')
        self.assertFalse(checks['制造：岗位全部原字段与主库逐值相同'])

    def test_independent_audit_rejects_changed_jd_without_code_change(self):
        jobs, routes = fixture()
        child_jobs = partition(jobs, routes)['制造']
        child_jobs[0]['jd'] = '1、擅自改写本行业职责。'
        child = {'jobs': child_jobs, 'industry': '制造', 'tier': 1,
                 'sources': [r for r in routes if r['industry'] == '制造'], 'functions': [], 'series': []}
        checks, _ = verify_child(jobs, child, {'SHARED'}, child['sources'], '制造')
        self.assertFalse(checks['制造：岗位全部原字段与主库逐值相同'])

    def test_independent_audit_rejects_foreign_industry_anchor(self):
        jobs, routes = fixture()
        child_jobs = partition(jobs, routes)['制造']
        child_jobs[0]['industry_membership']['source_ids'] = ['SRC-B']
        child = {'jobs': child_jobs, 'industry': '制造', 'tier': 1,
                 'sources': [r for r in routes if r['industry'] == '制造'], 'functions': [], 'series': []}
        checks, _ = verify_child(jobs, child, {'SHARED'}, child['sources'], '制造')
        self.assertFalse(checks['制造：本地来源未串行业且全量指向该岗位'])

    def test_duplicate_export_row_cannot_hide_a_missing_job(self):
        expected = [['id', 'code'], ['A', 'AA005'], ['B', 'BB005']]
        self.assertFalse(same_table(expected, [['id', 'code'], ['A', 'AA005'], ['A', 'AA005']]))


if __name__ == '__main__':
    unittest.main()
