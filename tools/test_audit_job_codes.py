"""Adversarial checks for the independent audit, not the catalog generator."""
import unittest

import audit_job_codes as audit


def job(jid='J1', code='AA001', name='岗位一', level=1):
    return {'id': jid, 'code': code, 'name': name, 'level': level, 'function_name': '职能',
            'series_name': '系列', 'industries': ['行业'], 'decision': '保留', 'identity_contains_inference': False}


class IndependentCodeAuditTests(unittest.TestCase):
    def test_duplicate_code_with_different_names_is_rejected(self):
        checks, details = audit.audit_jobs([job(), job('J2', 'AA001', '岗位二')])
        self.assertFalse(checks['岗位代码全局唯一'])
        self.assertEqual(len(details['duplicate_codes']), 1)

    def test_full_width_and_invisible_characters_cannot_hide_code_collision(self):
        checks, _ = audit.audit_jobs([job(), job('J2', ' ＡＡ００１\u200b', '岗位二')])
        self.assertFalse(checks['代码无大小写全半角及隐形字符冲突'])
        self.assertFalse(checks['有效代码格式正确'])

    def test_one_identity_cannot_have_two_codes(self):
        checks, _ = audit.audit_jobs([job(), job('J1', 'AB001', '岗位二')])
        self.assertFalse(checks['岗位ID唯一'])

    def test_code_suffix_must_equal_level(self):
        checks, _ = audit.audit_jobs([job(level=2)])
        self.assertFalse(checks['代码末位与层级一致'])

    def test_display_grade_cannot_conflict_with_recorded_level(self):
        checks, _ = audit.audit_jobs([job(name='岗位（3级）')])
        self.assertFalse(checks['名称中明示职级与字段一致'])

    def test_valid_distinct_codes_pass_job_checks(self):
        checks, _ = audit.audit_jobs([job(), job('J2', 'AB001', '岗位二')])
        self.assertTrue(all(checks.values()))

    def test_repeated_export_row_cannot_hide_missing_job(self):
        jobs = [job(), job('J2', 'AB001', '岗位二')]
        first = ['J1', 'AA001', '岗位一', '职能', '系列', '1', '行业', '保留', '否']
        rows = [['header'], first, first]
        checks = audit.representations(jobs, rows, rows)
        self.assertFalse(checks['Excel岗位数与ID唯一性一致'])
        self.assertFalse(checks['TSV岗位数与ID唯一性一致'])
        self.assertFalse(checks['Excel与JSON逐字段一致'])

    def test_changed_export_code_is_detected(self):
        jobs = [job()]
        rows = [['header'], ['J1', 'AB001', '岗位一', '职能', '系列', '1', '行业', '保留', '否']]
        checks = audit.representations(jobs, rows, rows)
        self.assertFalse(checks['Excel与JSON逐字段一致'])


if __name__ == '__main__':
    unittest.main()
