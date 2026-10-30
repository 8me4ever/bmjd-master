"""Specialize demonstrably generic JDs only in new industry subcatalog versions.

Never writes the global master or the original 11 subcatalogs. Exact parent
template provenance, explicit professional identity and local industry evidence
are required; lexical gaps alone do not trigger rewriting.
"""
import argparse
import collections
import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path

from review_job_jds import render_new as render_parent, subject

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'行业一级子库_20261029'
DIRECTORY = ROOT/'行业专业JD优化_20261029'
MASTER = ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
RULES = DIRECTORY/'行业专业化规则.json'
INDUSTRIES = ('传媒','制造','医药','地产','教育','消费品','物流','综合服务','能源化工','金融','高科技')
HEADER = ['岗位ID','岗位代码','岗位名称','职能','职责系列','层级','所属子库','本轮处置','岗位JD']
JD_FIELDS = {'jd','jd_clauses','jd_version','industry_jd_revision'}


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def encode(data):
    return (json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()


def jd_text(clauses):
    return '\n'.join(f"{c['number']}、{c['text']}" for c in clauses)


def is_parent_template(job, parent_rules):
    return (job['jd_review_status']=='重写' and
            job['jd']==jd_text(render_parent(job,parent_rules['profiles'][job['jd_profile']])))


def professional_gaps(job,profile):
    # Remove the title/series echo first. A title mentioning "芯片" does not
    # demonstrate that the body covers logic verification or timing closure.
    body=job['jd']
    for label in sorted({job['name'],job['series_name'],subject(job)},key=len,reverse=True):
        if label:body=body.replace(label,'')
    return [dimension for dimension in profile['professional_dimensions']
            if not any(term.casefold() in body.casefold() for term in dimension)]


def match_profile(job,industry,profiles,local_context):
    name=job['name'].replace('（'+job['function_name']+'）','').replace('('+job['function_name']+')','')
    title=name+'\n'+job['series_name']
    candidates=[]
    for profile in profiles:
        if industry not in profile['industries']:
            continue
        if profile['functions'] and job['function_name'] not in profile['functions']:
            continue
        if not re.search(profile['title_pattern'],title,re.I):
            continue
        if profile.get('exclude_pattern') and re.search(profile['exclude_pattern'],title,re.I):
            continue
        if profile.get('local_context_any') and not any(term in local_context for term in profile['local_context_any']):
            continue
        candidates.append(profile)
    return candidates


def render_specialized(job,industry,profile):
    texts=[t.format(subject=subject(job)) for t in profile['clauses']]
    mode=job['jd_role_mode']
    if mode=='辅助或初级':
        texts=['在指导下，'+t for t in texts]
    elif mode=='管理':
        texts.append(f"组织{subject(job)}专业任务分工与成果复核，协调关键接口，跟进质量问题和改进措施。")
    elif mode=='资深专业':
        texts.append(f"复核{subject(job)}的关键专业判断，分析复杂问题并指导验证与改进。")
    return [{'number':n,'text':text,'basis_type':'专业补写','source_refs':[],
             'basis_note':f"仅用于{industry}子库；依据当前岗位名称及行业专业职责框架补写。本行业来源为方向上下文，不冒充新条款逐字证据。"}
            for n,text in enumerate(texts,1)]


def decide(job,industry,rules,parent_rules,local_context,has_local_evidence=True):
    if job['function_name'] in rules['protected_functions']:
        return '保留-通用职能',None,[],[]
    candidates=match_profile(job,industry,rules['profiles'],local_context)
    if not candidates:
        return '保留-无明确专业化改写依据',None,[],[]
    profile=candidates[0]
    gaps=professional_gaps(job,profile)
    if not has_local_evidence:
        return '保留-本行业专业方向依据不足',profile,gaps,candidates
    if not is_parent_template(job,parent_rules):
        return '保留-现稿非通用补写框架',profile,gaps,candidates
    if len(gaps)<2:
        return '保留-已覆盖关键专业维度',profile,gaps,candidates
    return '改写-补充行业专业职责',profile,gaps,candidates


def table_rows(child,ledger):
    decisions={r['job_id']:r for r in ledger}
    return [HEADER]+[[j['id'],j['code'],j['name'],j['function_name'],j['series_name'],str(j['level']),
                     child['industry'],decisions[j['id']]['status'],j['jd']] for j in child['jobs']]


def tsv(rows):
    stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter='\t',lineterminator='\n');writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')


def build():
    rules=read(RULES);master=read(MASTER);parent_rules=read(ROOT/'岗位JD匹配审查_20261029/JD审查与编写规则.json')
    evidence_path=ROOT/'双线协作交接_20261029/JD原文证据.json'
    metadata_path=ROOT/'全量名称代码统一_20261029/全量原表元数据.json'
    handoff_path=ROOT/'双线协作交接_20261029/JD编写输入.json'
    evidence=read(evidence_path);metadata={r['source_id']:r for r in read(metadata_path)}
    scoped={}
    for task in read(handoff_path)['jobs']:
        if task['role_scoped_evidence']:
            for item in task['role_scoped_evidence']:
                scoped[(task['baseline_code'],item['parent_source_id'])]=item['text']
    parent_hash=sha(MASTER)
    # Pin the actual previously delivered files, not just their logical contents.
    manifest=read(ROOT/'项目文件清单.json')
    protected_paths=[MASTER]+sorted(BASE.rglob('*'))
    protected_paths=[p for p in protected_paths if p.is_file()]
    protected={p.relative_to(ROOT).as_posix():sha(p) for p in protected_paths}
    assert all(manifest['files'][name]['sha256']==value for name,value in protected.items()),'上版交付文件指纹发生变化，请先核查。'
    files={};all_records=[];summaries=[];checks={};master_by_id={j['id']:j for j in master['jobs']}
    for industry in INDUSTRIES:
        input_path=BASE/industry/'岗位主库.json';old_child=read(input_path);child=copy.deepcopy(old_child);records=[]
        source_records={r['source_id']:r for r in old_child['sources']}
        for old_job,new_job in zip(old_child['jobs'],child['jobs']):
            assert old_job['jd']==master_by_id[old_job['id']]['jd']
            contexts=[];context_parts=[]
            for sid in old_job['industry_membership']['source_ids']:
                source=evidence['sources'][sid]
                assert source['industry']==industry and source_records[sid]['state']!='用户暂缓'
                text=evidence['texts'][source['jd_sha256']]
                authorized=False
                if sid in {'SRC-传媒-1045','SRC-地产-1510'}:
                    text=scoped[(old_job['code'],sid)]
                    authorized=True
                original_meta=metadata[sid]['最新输入_修改版6']
                assert original_meta['sheet']==industry
                context_parts.append(source['source_name']+' '+original_meta['specialty']+' '+text)
                contexts.append({'source_id':sid,'source_name':source['source_name'],
                                 'file':original_meta['file'],'sheet':industry,'row':original_meta['row'],
                                 'specialty':original_meta['specialty'],'quote':text[:240],
                                 'source_text_is_empty':not bool(text),
                                 'role_scoped':authorized,'context_sha256':text_sha(text)})
            local_context='\n'.join(context_parts)
            status,profile,gaps,candidates=decide(old_job,industry,rules,parent_rules,local_context,bool(contexts))
            changed=status.startswith('改写')
            reason=profile['gap_note'] if changed else {
                '保留-通用职能':'通用职能不因行业标签而改写。',
                '保留-无明确专业化改写依据':'未发现足够明确的行业专门职责缺口，不作无依据改写。',
                '保留-本行业专业方向依据不足':'缺少本行业可核验的专业方向来源，保留原稿。',
                '保留-现稿非通用补写框架':'现稿为原文支持的保留稿，不仅凭词语覆盖低改写。',
                '保留-已覆盖关键专业维度':'现有职责已体现框架要求的主要专业维度，保留原稿。'}[status]
            if changed:
                clauses=render_specialized(old_job,industry,profile)
                new_job['jd_clauses']=clauses;new_job['jd']=jd_text(clauses);new_job['jd_version']=rules['version']
                new_job['industry_jd_revision']={'industry':industry,'version':rules['version'],'profile_id':profile['id'],
                                                'reason':reason,'parent_jd_sha256':text_sha(old_job['jd']),
                                                'local_source_ids':old_job['industry_membership']['source_ids']}
            records.append({'industry':industry,'job_id':old_job['id'],'code':old_job['code'],'name':old_job['name'],
                            'function_name':old_job['function_name'],'series_id':old_job['series_id'],'series_name':old_job['series_name'],
                            'status':status,'changed':changed,'reason':reason,'parent_profile':old_job['jd_profile'],
                            'selected_profile':profile['id'] if profile else None,'candidate_profiles':[r['id'] for r in candidates],
                            'parent_template_verified':is_parent_template(old_job,parent_rules),
                            'missing_professional_dimensions':gaps,'local_source_context':contexts,
                            'old_jd_sha256':text_sha(old_job['jd']),'new_jd_sha256':text_sha(new_job['jd']),
                            **({'old_jd':old_job['jd'],'new_jd':new_job['jd']} if changed else {})})
        count=sum(r['changed'] for r in records)
        child['version']=rules['version'];child['parent_subcatalog_version']=old_child['version']
        child['parent_subcatalog_path']=input_path.relative_to(ROOT).as_posix();child['parent_subcatalog_sha256']=sha(input_path)
        child['jd_policy']='本行业内仅为明确专业性缺口改写JD；通用职能、身份和全部主库文件保持不变。'
        child['summary']=dict(old_child['summary'],industry_jd_modified=count,industry_jd_retained=len(records)-count)
        summaries.append({'industry':industry,'jobs':len(records),'modified':count,'retained':len(records)-count,
                          'decision_counts':dict(collections.Counter(r['status'] for r in records)),
                          'path':f'{industry}/岗位主库.json'})
        all_records+=records
        checks[industry+'岗位范围与顺序保持']= [j['id'] for j in child['jobs']]==[j['id'] for j in old_child['jobs']]
        checks[industry+'所有非JD原字段保持不变']=all(all(j[k]==v for k,v in old.items() if k not in JD_FIELDS) and set(j)-set(old)<= {'industry_jd_revision'} for old,j in zip(old_child['jobs'],child['jobs']))
        checks[industry+'所有保留岗完整原样不变']=all(j==old for old,j,r in zip(old_child['jobs'],child['jobs'],records) if not r['changed'])
        checks[industry+'每个修改岗新JD4或5条']=all(len(j['jd_clauses']) in {4,5} and j['jd']!=old['jd'] for old,j,r in zip(old_child['jobs'],child['jobs'],records) if r['changed'])
        checks[industry+'通用职能未改写']=all(not r['changed'] for r in records if r['function_name'] in rules['protected_functions'])
        checks[industry+'每个修改有专业框架本地来源及缺口']=all(r['selected_profile'] and r['local_source_context'] and r['parent_template_verified'] and len(r['missing_professional_dimensions'])>=2 for r in records if r['changed'])
        checks[industry+'新条款补写不伪造原文']=all(c['basis_type']=='专业补写' and not c['source_refs'] for j,r in zip(child['jobs'],records) if r['changed'] for c in j['jd_clauses'])
        files[f'{industry}/岗位主库.json']=encode(child)
        files[f'{industry}/岗位名称代码及JD.tsv']=tsv(table_rows(child,records))
    changed_records=[r for r in all_records if r['changed']]
    checks['11行业19018条全部有审查处置']=len(summaries)==11 and len(all_records)==19018 and len({(r['industry'],r['job_id']) for r in all_records})==19018
    checks['共用岗位未改名改码且全局9111身份保持']=len({r['job_id'] for r in all_records})==9111 and len({r['code'] for r in all_records})==9111
    checks['主库及旧子库40文件字节指纹保持']=all(sha(ROOT/p)==value for p,value in protected.items())
    inputs=[MASTER,RULES,evidence_path,metadata_path,handoff_path,ROOT/'岗位JD匹配审查_20261029/JD审查与编写规则.json',ROOT/'tools/review_job_jds.py',Path(__file__)]+[BASE/i/'岗位主库.json' for i in INDUSTRIES]
    summary={'industries':11,'reviewed_industry_jobs':len(all_records),'modified_industry_jobs':len(changed_records),
             'modified_unique_master_ids':len({r['job_id'] for r in changed_records}),'retained_industry_jobs':len(all_records)-len(changed_records),
             'protected_common_function_jobs':sum(r['status']=='保留-通用职能' for r in all_records),
             'unique_master_jobs':9111,'changed_names':0,'changed_codes':0,'master_jd_changes':0,'previous_subcatalog_changes':0}
    report={'version':rules['version'],'method':'全量审查处置、明确专业身份与本行业来源核对、通用框架精确验证、专业维度审查和重点内容自审；不宣称逐句人工阅读全库。',
            'all_passed':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),'summary':summary,'industries':summaries,
            'checks':checks,'protected_input_sha256':protected,'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs}}
    files['子库优化总览.json']=encode({'version':rules['version'],'global_master_version':master['version'],'global_master_sha256':parent_hash,'summary':summary,'industries':summaries})
    files['逐岗行业JD审查台账.json']=encode(all_records)
    files['行业JD改写对照.json']=encode(changed_records)
    files['核验报告.json']=encode(report)
    return files,report


def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group()
    group.add_argument('--write',action='store_true');group.add_argument('--check',action='store_true');args=parser.parse_args()
    files,report=build()
    if not report['all_passed']:
        print(json.dumps(report,ensure_ascii=False,indent=2));return 1
    if args.write or args.check:
        for name,data in files.items():
            p=DIRECTORY/name
            if p.exists() and p.read_bytes()!=data:raise ValueError('已有不同内容，不覆盖：'+name)
            if args.check and not p.exists():raise ValueError('缺少输出：'+name)
        if args.write:
            for name,data in files.items():
                p=DIRECTORY/name
                if not p.exists():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    print(json.dumps({**report['summary'],'all_passed':report['all_passed'],'checks':f"{report['passed']}/{report['total']}"},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
