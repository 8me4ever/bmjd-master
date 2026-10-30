"""Check code uniqueness, source conservation, metadata-only reading and tracing."""
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import name_code_master as phase


class MetadataReaderTests(unittest.TestCase):
    def test_jd_column_is_ignored_even_if_its_shared_string_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.xlsx'
            ns = phase.NS['m']
            with ZipFile(path, 'w') as archive:
                archive.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="教育" r:id="rId1"/></sheets></workbook>')
                archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
                archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="B1" t="inlineStr"><is><t>标准岗位代码</t></is></c><c r="C1" t="inlineStr"><is><t>标准职位名称</t></is></c></row><row r="2"><c r="B2" t="inlineStr"><is><t>EO005</t></is></c><c r="C2" t="inlineStr"><is><t>教务专员</t></is></c><c r="H2" t="s"><v>999999</v></c></row></sheetData></worksheet>')
            rows = phase.metadata_rows(path, '教育')
            self.assertEqual(rows[2][1:3], ['EO005', '教务专员'])
            self.assertEqual(len(rows[2]), 7)

    def test_work_version_cannot_be_overwritten_or_partially_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'existing.json').write_text('user work', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '禁止覆盖'):
                phase.save({'new.json': {}, 'existing.json': {}}, directory=root)
            self.assertFalse((root / 'new.json').exists())
            self.assertEqual((root / 'existing.json').read_text('utf-8'), 'user work')


class NameCodeMasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = phase.read(phase.OUT / '名称代码主库.json')
        cls.jobs = cls.master['jobs']
        cls.series = cls.master['series']
        cls.sources = phase.read(phase.OUT / '来源去向映射.json')
        cls.baseline = phase.read(phase.ROOT / phase.BASE)['sources']
        cls.mapping = {m['old_code']: m for m in phase.read(phase.OUT / '基线名称代码映射.json')}
        cls.by_code = {j['code']: j for j in cls.jobs}

    def validate(self, jobs=None, sources=None):
        phase.validate_master(jobs or self.jobs, self.series, sources or self.sources, self.baseline, {})

    def test_duplicate_current_code_rejected(self):
        jobs = list(self.jobs)
        jobs[0] = dict(jobs[0], code=jobs[1]['code'])
        with self.assertRaisesRegex(ValueError, '不唯一'):
            self.validate(jobs=jobs)

    def test_level_and_code_mismatch_rejected(self):
        jobs = list(self.jobs)
        jobs[0] = dict(jobs[0], level=7 if jobs[0]['level'] != 7 else 6)
        with self.assertRaisesRegex(ValueError, '层级不一致'):
            self.validate(jobs=jobs)

    def test_ordinary_source_cannot_have_two_targets(self):
        sources = list(self.sources)
        index = next(i for i, s in enumerate(sources) if s['target_job_ids'] and not s['authorization'])
        sources[index] = dict(sources[index], target_job_ids=[self.jobs[0]['id'], self.jobs[1]['id']])
        with self.assertRaises(ValueError):
            self.validate(sources=sources)

    def test_paused_sources_cannot_be_reactivated(self):
        sources = list(self.sources)
        index = next(i for i, s in enumerate(sources) if s['state'] == '用户暂缓')
        sources[index] = dict(sources[index], target_job_ids=[self.jobs[0]['id']])
        with self.assertRaises(ValueError):
            self.validate(sources=sources)

    def test_original_source_name_cannot_be_rewritten(self):
        sources = list(self.sources)
        sources[0] = dict(sources[0], original_name='换成另一个原名')
        with self.assertRaisesRegex(ValueError, '原始来源被改写'):
            self.validate(sources=sources)

    def test_authorized_stage_cg_allocation_is_protected(self):
        sources = list(self.sources)
        index = next(i for i, s in enumerate(sources) if s['authorization'])
        sources[index] = dict(sources[index], authorization=[])
        with self.assertRaisesRegex(ValueError, '授权拆分变化'):
            self.validate(sources=sources)

    def test_jd_fields_rejected_in_name_code_master(self):
        jobs = list(self.jobs)
        jobs[0] = dict(jobs[0], standard_jd='不得混入本阶段')
        with self.assertRaisesRegex(ValueError, 'JD字段'):
            self.validate(jobs=jobs)

    def test_boiler_split_and_retired_identity_tracing(self):
        self.assertEqual(self.by_code['BC173']['name'], '高级锅炉工程师')
        self.assertEqual(self.by_code['BC176']['source_ids'], ['SRC-地产-1726'])
        self.assertEqual(self.mapping['BC006']['new_codes'], ['BC176'])
        self.assertNotEqual(self.by_code['BC006']['id'], self.mapping['BC006']['baseline_job_id'])
        self.assertEqual(set(self.by_code['BC006']['source_ids']), {'SRC-制造-1661', 'SRC-能源化工-1872', 'SRC-地产-1736'})
        self.assertIn('继续推定', self.by_code['BC006']['name_code_review_status'])

    def test_warehouse_supervisor_and_keeper_not_same_grade(self):
        self.assertEqual(self.by_code['AX014']['name'], '仓储主管')
        self.assertEqual(self.by_code['AX086']['name'], '库管组长')
        self.assertEqual((self.by_code['AX014']['level'], self.by_code['AX086']['level']), (4, 6))
        self.assertEqual(set(self.mapping['AX014']['new_codes']), {'AX014', 'AX086'})

    def test_customs_levels_are_separated(self):
        self.assertEqual(self.by_code['LO095']['name'], '报关专员')
        self.assertEqual(set(self.by_code['LO096']['source_ids']), {'SRC-地产-1075', 'SRC-物流-0193'})
        self.assertEqual(self.by_code['LO096']['level'], 6)

    def test_shared_lighting_source_does_not_cross_identity_successors(self):
        self.assertEqual(self.mapping['AC435']['new_codes'], ['AC435'])
        self.assertEqual(self.mapping['CT205']['new_codes'], ['CT205'])
        self.assertEqual(self.mapping['AC435']['source_destinations']['SRC-传媒-1045'], ['AC435'])
        self.assertEqual(self.mapping['CT205']['source_destinations']['SRC-传媒-1045'], ['CT205'])

    def test_teacher_inference_is_marked_and_prior_codes_traced(self):
        for old, current in [('VE146', 'VE644'), ('VE067', 'VE645'), ('EO076', 'VE646')]:
            self.assertEqual(self.mapping[old]['new_codes'], [current])
            self.assertIn('继续推定', self.by_code[current]['name_code_review_status'])


if __name__ == '__main__':
    unittest.main()
