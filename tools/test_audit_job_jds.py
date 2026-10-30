import unittest
from audit_job_jds import HEADER, compare_export, validate_retained


class IndependentJDAuditTests(unittest.TestCase):
    def test_repeated_export_row_cannot_hide_missing_job(self):
        a = ['A', 'AA005', '核保员', '核保', '核保', '5', '匹配保留', '匹配', '1、审核投保资料。']
        b = ['B', 'AA015', '寿险核保员', '核保', '寿险核保', '5', '重写', '错配', '1、评估承保风险。']
        self.assertFalse(compare_export([HEADER, a, b], [HEADER, a, a]))

    def test_modified_export_jd_is_detected(self):
        row = ['A', 'AA005', '核保员', '核保', '核保', '5', '重写', '错配', '1、审核投保资料。']
        changed = row[:-1] + ['1、开展销售工作。']
        self.assertFalse(compare_export([HEADER, row], [HEADER, changed]))

    def test_foreign_source_cannot_support_a_retained_clause(self):
        job = {'source_ids': ['OWN'], 'jd_clauses': [{'basis_type': '原文提炼', 'source_refs': [{'source_id': 'OTHER', 'quote': '真实句子'}]}]}
        self.assertIn('foreign_or_unquoted_source', validate_retained(job, {'OTHER': '真实句子'}))

    def test_parent_text_outside_authorized_role_is_rejected(self):
        job = {'source_ids': ['PARENT'], 'jd_clauses': [{'basis_type': '原文提炼', 'source_refs': [{'source_id': 'PARENT', 'quote': '舞台布光'}]}]}
        self.assertIn('foreign_or_unquoted_source', validate_retained(job, {'PARENT': '调整三维渲染参数'}))

    def test_unquoted_inference_cannot_be_labelled_retained(self):
        job = {'source_ids': ['OWN'], 'jd_clauses': [{'basis_type': '专业补写', 'source_refs': []}]}
        self.assertIn('missing_direct_evidence', validate_retained(job, {'OWN': '实际原文'}))


if __name__ == '__main__':
    unittest.main()
