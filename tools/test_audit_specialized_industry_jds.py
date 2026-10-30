import copy
import unittest

from audit_specialized_industry_jds import text_sha,valid_context,verify_job


def job(function='研发'):
    return {'id':'JOB','code':'RD005','name':'研发工程师','function_name':function,'jd':'1、原职责。',
            'jd_clauses':[{'number':1,'text':'原职责。','basis_type':'原文提炼','source_refs':[]}],
            'jd_role_mode':'专业执行','jd_version':'PARENT',
            'industry_membership':{'industry':'高科技','source_ids':['OWN']}}


def changed(before):
    result=copy.deepcopy(before)
    result['jd_clauses']=[{'number':n,'text':f'第{n}项专业职责。','basis_type':'专业补写','source_refs':[]} for n in range(1,5)]
    result['jd']='\n'.join(f"{c['number']}、{c['text']}" for c in result['jd_clauses'])
    result['jd_version']='CHILD'
    result['industry_jd_revision']={'parent_jd_sha256':text_sha(before['jd'])}
    return result


class IndustryJDIsolationTests(unittest.TestCase):
    def test_only_jd_fields_may_change(self):
        before=job();after=changed(before);after['code']='RD015'
        self.assertIn('non_jd_fields_changed',verify_job(before,after,set()))

    def test_common_function_cannot_be_rewritten(self):
        before=job('人力资源');after=changed(before)
        self.assertIn('common_function_modified',verify_job(before,after,{'人力资源'}))

    def test_unchanged_body_cannot_hide_clause_or_metadata_edits(self):
        before=job();after=copy.deepcopy(before);after['jd_clauses'][0]['text']='偷偷修改条款。'
        self.assertIn('unchanged_job_has_hidden_edits',verify_job(before,after,set()))

    def test_professional_invention_cannot_claim_direct_evidence(self):
        before=job();after=changed(before);after['jd_clauses'][0]['source_refs']=[{'source_id':'OWN','quote':'旧原文'}]
        self.assertIn('fabricated_direct_evidence',verify_job(before,after,set()))

    def test_foreign_industry_source_is_rejected(self):
        before=job();evidence={'sources':{'OWN':{'industry':'金融','source_name':'研发工程师','jd_sha256':'HASH'}},'texts':{'HASH':'真实原文'}}
        metadata={'OWN':{'最新输入_修改版6':{'sheet':'金融'}}}
        context={'source_id':'OWN','source_name':'研发工程师','quote':'真实原文','context_sha256':text_sha('真实原文'),'source_text_is_empty':False}
        self.assertFalse(valid_context(context,'高科技',before,evidence,metadata,{}))

    def test_empty_original_jd_is_recorded_without_inventing_a_quote(self):
        before=job();evidence={'sources':{'OWN':{'industry':'高科技','source_name':'研发工程师','jd_sha256':'EMPTY'}},'texts':{'EMPTY':''}}
        metadata={'OWN':{'最新输入_修改版6':{'sheet':'高科技'}}}
        context={'source_id':'OWN','source_name':'研发工程师','quote':'','context_sha256':text_sha(''),'source_text_is_empty':True}
        self.assertTrue(valid_context(context,'高科技',before,evidence,metadata,{}))
        context['quote']='编造的原文'
        self.assertFalse(valid_context(context,'高科技',before,evidence,metadata,{}))

    def test_shared_lighting_source_obeys_authorized_role(self):
        before=job();before['code']='CT205';before['industry_membership']['source_ids']=['SRC-传媒-1045']
        sid='SRC-传媒-1045';body='舞台布光；三维渲染。';authorized={(before['code'],sid):'三维渲染。'}
        evidence={'sources':{sid:{'industry':'传媒','source_name':'灯光师','jd_sha256':'FULL'}},'texts':{'FULL':body}}
        metadata={sid:{'最新输入_修改版6':{'sheet':'传媒'}}}
        context={'source_id':sid,'source_name':'灯光师','quote':'舞台布光','context_sha256':text_sha('三维渲染。'),'source_text_is_empty':False}
        self.assertFalse(valid_context(context,'传媒',before,evidence,metadata,authorized))

    def test_valid_child_jd_change_is_accepted(self):
        before=job();self.assertEqual(verify_job(before,changed(before),set()),[])


if __name__=='__main__':unittest.main()
