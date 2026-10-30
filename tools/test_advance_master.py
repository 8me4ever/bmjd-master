"""Safety regressions for receipt handling; no frozen files are modified."""
import copy
import tempfile
import unittest
from pathlib import Path

import advance_master as receiver


class ReceiptSafetyTests(unittest.TestCase):
    def setUp(self):
        self.task = {'job_id': 'J1', 'baseline_code': 'AC435', 'source_ids': ['mixed', 'independent'],
                     'role_scoped_evidence': [{'parent_source_id': 'mixed', 'original_clauses': ['1、舞台灯光设计。']}]}
        self.evidence = {'sources': {'mixed': {'jd_sha256': 'mix'}, 'independent': {'jd_sha256': 'solo'}},
                         'texts': {'mix': '1、舞台灯光设计。2、三维渲染。', 'solo': '1、设备日常维护。'}}

    def clause(self, sid, quote):
        return [{'number': 1, 'text': '工作条款', 'basis_type': '原文提炼',
                 'source_refs': [{'source_id': sid, 'quote': quote}], 'basis_note': '有原文'}]

    def test_mixed_source_cannot_quote_other_role(self):
        with self.assertRaisesRegex(ValueError, '授权条款'):
            receiver.validate_clauses(self.clause('mixed', '三维渲染'), self.task, self.evidence, [])

    def test_independent_source_does_not_inherit_mixed_source_scope(self):
        receiver.validate_clauses(self.clause('independent', '设备日常维护'), self.task, self.evidence, [])

    def test_unassigned_source_rejected(self):
        with self.assertRaisesRegex(ValueError, '不属于本岗'):
            receiver.validate_clauses(self.clause('other', '设备日常维护'), self.task, self.evidence, [])

    def test_fabricated_quote_rejected(self):
        with self.assertRaisesRegex(ValueError, '原文子串'):
            receiver.validate_clauses(self.clause('mixed', '原文没有的话'), self.task, self.evidence, [])

    def test_whitespace_repair_preserves_actual_literal_and_audit(self):
        self.evidence['texts']['solo'] = '1、设备日常维护 。'
        clauses = self.clause('independent', '设备日常维护。')
        repairs = []
        receiver.validate_clauses(clauses, self.task, self.evidence, repairs)
        self.assertEqual(clauses[0]['source_refs'][0]['quote'], '设备日常维护 。')
        self.assertEqual(repairs[0]['before'], '设备日常维护。')
        self.assertEqual(repairs[0]['after'], '设备日常维护 。')

    def test_punctuation_change_is_not_silently_treated_as_literal_quote(self):
        with self.assertRaises(ValueError):
            receiver.literal_quote('设备,维护', '设备，维护')

    def test_supplement_cannot_claim_original_source(self):
        clauses = self.clause('independent', '设备日常维护')
        clauses[0]['basis_type'] = '专业补写'
        with self.assertRaisesRegex(ValueError, '补写或推定'):
            receiver.validate_clauses(clauses, self.task, self.evidence, [])

    def test_retained_status_does_not_allow_substantive_edits(self):
        self.assertEqual(receiver.formatting_key('1、2、供应商管理，核对。'), receiver.formatting_key('1、供应商管理,核对。'))
        self.assertNotEqual(receiver.formatting_key('1、供应商管理。'), receiver.formatting_key('1、仓库管理。'))

    def test_existing_version_conflict_preflights_entire_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'local user work\n'
            (root / 'existing.json').write_bytes(original)
            with self.assertRaisesRegex(ValueError, '禁止覆盖'):
                receiver.save_outputs({'new.json': {}, 'existing.json': {}}, directory=root)
            self.assertFalse((root / 'new.json').exists())
            self.assertEqual((root / 'existing.json').read_bytes(), original)

    def test_output_rerun_is_idempotent_and_check_requires_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, '缺少输出'):
                receiver.save_outputs({'one.json': {'result': 1}}, check=True, directory=root)
            receiver.save_outputs({'one.json': {'result': 1}}, directory=root)
            before = (root / 'one.json').stat().st_mtime_ns
            receiver.save_outputs({'one.json': {'result': 1}}, directory=root)
            receiver.save_outputs({'one.json': {'result': 1}}, check=True, directory=root)
            self.assertEqual((root / 'one.json').stat().st_mtime_ns, before)


class FullSubmissionSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = receiver.load(receiver.ROOT / '全库统一完成_20261029/统一主库.json')
        cls.inputs = receiver.load(receiver.ROOT / '双线协作交接_20261029/JD编写输入.json')
        cls.submission = receiver.load(receiver.ROOT / 'JD编写_20261029/out/JD回传_常规岗.json')
        cls.schema = receiver.load(receiver.ROOT / '双线协作交接_20261029/JD回传格式.schema.json')

    def mutated_submission(self):
        submission = dict(self.submission)
        submission['jobs'] = list(self.submission['jobs'])
        submission['jobs'][0] = copy.deepcopy(submission['jobs'][0])
        return submission

    def validate(self, submission, master=None):
        receiver.validate_submission(master or self.master, self.inputs, submission, self.schema)

    def test_duplicate_id_rejected(self):
        submission = self.mutated_submission()
        submission['jobs'].append(submission['jobs'][0])
        with self.assertRaisesRegex(ValueError, '重复job_id'):
            self.validate(submission)

    def test_changed_identity_anchor_rejected(self):
        submission = self.mutated_submission()
        submission['jobs'][0]['baseline_identity_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '基线指纹失配'):
            self.validate(submission)

    def test_missing_regular_job_rejected(self):
        submission = self.mutated_submission()
        submission['jobs'].pop()
        with self.assertRaisesRegex(ValueError, '覆盖不完整'):
            self.validate(submission)

    def test_current_jd_conflict_rejected(self):
        master = dict(self.master)
        master['jobs'] = list(self.master['jobs'])
        master['jobs'][0] = dict(master['jobs'][0], standard_jd='另一个作者已修改')
        with self.assertRaisesRegex(ValueError, '禁止静默覆盖'):
            self.validate(self.submission, master)


if __name__ == '__main__':
    unittest.main()
