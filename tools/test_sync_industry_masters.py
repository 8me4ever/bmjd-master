import copy
import hashlib
import unittest
from sync_industry_masters import carry_forward


class IndustryCarryForwardTests(unittest.TestCase):
    def setUp(self):
        self.original={'id':'stable','name':'研发工程师','code':'OLD005','level':5,'function_id':'F','series_id':'S','source_ids':['SRC'],
          'jd':'1、通用研发职责。','jd_clauses':[{'number':1,'text':'通用研发职责。'}],'jd_version':'OLD'}
        self.parent={**copy.deepcopy(self.original),'code':'RX105','series_prefix':'RX10','jd_version':'OLD'}
        self.member={'industry':'制造','source_ids':['SRC']}
        self.old={**copy.deepcopy(self.original),'industry_membership':copy.deepcopy(self.member)}

    def test_specialized_jd_is_carried_by_id_with_new_master_code(self):
        self.old.update(jd='1、行业专业职责。',jd_clauses=[{'number':1,'text':'行业专业职责。'}],jd_version='SPECIAL',
          industry_jd_revision={'parent_jd_sha256':hashlib.sha256(self.parent['jd'].encode()).hexdigest()})
        parent=copy.deepcopy(self.parent);old=copy.deepcopy(self.old)
        result=carry_forward(self.parent,self.old,self.original,self.member)
        self.assertEqual(result['code'],'RX105');self.assertEqual(result['jd'],self.old['jd'])
        self.assertEqual(self.parent,parent);self.assertEqual(self.old,old)

    def test_general_jd_remains_parent_fields_and_new_code(self):
        result=carry_forward(self.parent,self.old,self.original,self.member)
        self.assertEqual({k:v for k,v in result.items() if k!='industry_membership'},self.parent)

    def test_old_code_cannot_attach_a_different_identity(self):
        for field,value in [('id','other'),('name','其他岗位'),('level',4),('series_id','OTHER')]:
            wrong={**self.old,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):carry_forward(self.parent,wrong,self.original,self.member)

    def test_changed_parent_jd_and_industry_sources_require_review(self):
        with self.assertRaises(ValueError):carry_forward({**self.parent,'jd':'changed'},self.old,self.original,self.member)
        with self.assertRaises(ValueError):carry_forward(self.parent,self.old,self.original,{**self.member,'source_ids':['OTHER']})

    def test_specialized_revision_requires_matching_parent_fingerprint(self):
        for revision in [None,{'parent_jd_sha256':'wrong'}]:
            wrong={**self.old,'jd':'专业稿','industry_jd_revision':revision}
            with self.subTest(revision=revision),self.assertRaises(ValueError):carry_forward(self.parent,wrong,self.original,self.member)


if __name__=='__main__':unittest.main()
