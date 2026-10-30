"""Regression cases for original-letter restoration and minimum necessary moves."""
import unittest
from unify_master_codes import CORE,facts,minimum_assignment,options_for


def row(sid,old,blocks,reasonable=False,size=1,pinned=False,candidates=(),research=False):
    return {'series_id':sid,'previous_prefix':old,'extension_blocks':list(blocks),'previous_reasonable':reasonable,'job_count':size,
            'pinned':pinned,'research_policy':research,'original_candidates':[{'prefix':p} for p in candidates]}


class CodeCorrectionTests(unittest.TestCase):
    def test_two_functions_can_share_letters_without_sharing_series(self):
        rows=[row('HR','AI00',['HR'],candidates=['HR00']),row('EVENT','HR96',['HR'],True,pinned=True)]
        selected=minimum_assignment(rows,set())
        self.assertEqual(selected,{'HR':'HR00','EVENT':'HR96'})

    def test_keeps_valid_codes_and_uses_another_serial_on_original_conflict(self):
        rows=[row('A','FA00',['FA'],True,pinned=True),row('B','AB00',['FA'],candidates=['FA00'])]
        selected=minimum_assignment(rows,{'FA00'})
        self.assertEqual(selected['A'],'FA00');self.assertNotEqual(selected['B'],'FA00');self.assertTrue(selected['B'].startswith('FA'))

    def test_scans_other_supported_blocks_when_first_is_full(self):
        rows=[row(str(i),'AA'+f'{i:02}',['AA'],True,pinned=True) for i in range(100)]
        rows.append(row('NEW','ZZ00',['AA','BB']))
        self.assertTrue(minimum_assignment(rows,set())['NEW'].startswith('BB'))

    def test_minimizes_changed_jobs_before_restoring_an_extra_original_prefix(self):
        rows=[row('A','IT00',['IT'],True,size=7,candidates=['IT01']),row('B','AB00',['IT'],size=2,candidates=['IT00'])]
        selected=minimum_assignment(rows,set())
        self.assertEqual(selected['A'],'IT00');self.assertNotEqual(selected['B'],'IT00')

    def test_no_unrelated_function_blocks_added_as_fallback(self):
        r=row('S','ZZ00',['LO']);r['allowed_existing_blocks']=['LO','IT']
        self.assertTrue(all(p.startswith('LO') for p in options_for(r,set())))

    def test_research_extensions_exclude_reserved_nonresearch_blocks(self):
        selected=minimum_assignment([row('R','AB00',['RD'],research=True)],set())['R']
        self.assertTrue(selected.startswith('R'));self.assertNotIn(selected[:2],{'RA','RC','RM','RP'})

    def test_pinned_code_cannot_be_reallocated(self):
        r=row('PIN','HR96',['ME'],True,pinned=True,candidates=['ME00'])
        self.assertEqual(options_for(r,set()),{'HR96':1})

    def test_basic_function_policy_is_explicit(self):
        self.assertEqual({k:CORE[k] for k in ['人力资源','财务','综合管理','信息技术','行政','仓储']},{'人力资源':'HR','财务':'FA','综合管理':'GM','信息技术':'IT','行政':'OA','仓储':'LO'})

    def test_core_it_does_not_inherit_unrelated_source_block(self):
        master={'jobs':[{'id':'J','code':'AK005','name':'信息专员','aliases':[],'function_name':'信息技术','source_ids':['SRC'],'level':5}],
                'series':[{'id':'S','prefix':'AK00','function_id':'F','function_name':'信息技术','name':'信息','job_ids':['J']}]}
        meta=[{'source_id':'SRC','原版BMJD':{'code':'CS005','function':'旧分类','name':'信息专员'}}]
        r=facts(master,meta,[{'name':'信息技术','original_systems':['信息管理']}])[0]
        self.assertEqual(r['extension_blocks'],['IT']);self.assertFalse(r['previous_reasonable']);self.assertEqual(r['original_candidates'],[])


if __name__=='__main__':unittest.main()
