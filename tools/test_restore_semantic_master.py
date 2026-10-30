import unittest
from restore_semantic_master import fresh_extensions,inventory,matching,options


def row(sid,old,originals,blocks,size=1,pinned=False):
    js=[{'id':sid+str(n),'level':n+1,'code':old+str(n+1)} for n in range(size)]
    return {'series':{'id':sid,'prefix':old},'jobs':js,'allowed_blocks':blocks,'pinned':pinned,
      'originals':{j['id']:{p+str(j['level']) for p in originals} for j in js}}


class OriginalClassCodeTests(unittest.TestCase):
    def test_protected_exception_is_not_fabricated_as_original_evidence(self):
        master={'jobs':[{'id':'J','code':'AC435','level':5,'source_ids':['SRC'],'function_group_name':'文艺活动'}],
          'series':[{'id':'S','prefix':'AC43','function_name':'文艺活动','job_ids':['J']}]}
        metadata=[{'source_id':'SRC','原版BMJD':{'code':'CT205','function':'文艺活动','system':'演艺','specialty':'灯光'}}]
        _,rows=inventory(master,metadata)
        self.assertEqual(rows[0]['own_blocks'],['CT'])
        self.assertEqual(rows[0]['allowed_blocks'],['AC','CT'])

    def test_original_retention_precedes_fewer_changes_to_wrong_working_version(self):
        a=row('A','ZZ00',['HR00'],['HR']);b=row('B','HR00',['HR01'],['HR'])
        result=matching(options([a,b],{}))
        self.assertEqual(result,['HR00','HR01'])

    def test_101_series_keep_five_characters_by_authorized_family_extension(self):
        rows=[row(str(n),'ZZ'+f'{n%100:02}',['PD00'],['PD']) for n in range(101)]
        result=matching(options(rows,{'PD':'PB'}))
        self.assertEqual(len(set(result)),101)
        self.assertEqual(sum(p.startswith('PB') for p in result),1)
        self.assertTrue(all(len(p+'1')==5 and p[:2] in {'PD','PB'} for p in result))

    def test_extension_cannot_be_borrowed_from_other_original_class(self):
        choices=options([row('A','ZZ00',['PE00'],['PE'])],{'PD':'PB','PE':'PG','RD':'RX'})[0]
        self.assertEqual({p[:2] for p in choices},{'PE','PG'})

    def test_extension_keeps_original_numeric_suffix_before_arbitrary_working_suffix(self):
        rows=[row(str(n),'PD'+f'{n:02}',['PD'+f'{n:02}'],['PD'],pinned=True) for n in range(100)]
        rows.append(row('NEW','PB00',['PD04'],['PD']))
        result=matching(options(rows,{'PD':'PB'}))
        self.assertEqual(result[-1],'PB04')

    def test_new_prefixes_never_reuse_current_or_historical_blocks(self):
        used={'PA','PB','PC','PD','PE','PF','PG','PH','PI','RA','RB','RC','RD'}
        result=fresh_extensions(used)
        self.assertFalse(set(result.values())&used)
        self.assertEqual(len(set(result.values())),3)
        self.assertTrue(all(a[0]==b[0] for a,b in result.items()))

    def test_same_letter_does_not_displace_protected_identity(self):
        rows=[row('HR','AI00',['HR96'],['HR']),row('EVENT','HR96',['HR96'],['HR'],pinned=True)]
        result=matching(options(rows,{}))
        self.assertEqual(result[1],'HR96');self.assertNotEqual(result[0],'HR96')

    def test_original_code_collision_is_resolved_without_mixing_letters(self):
        result=matching(options([row('A','ZZ00',['FA00'],['FA']),row('B','ZY00',['FA00'],['FA'])],{}))
        self.assertEqual(len(set(result)),2)
        self.assertTrue(all(p.startswith('FA') for p in result))


if __name__=='__main__':unittest.main()
