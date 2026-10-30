"""Independent verification of industry-local JD revisions and frozen master files.

Reads actual child catalogs, original industry sources, comparison ledgers and
Excel/TSV exports; does not import the industry JD writer or trust its pass flags.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from audit_job_codes import audit_jobs,spreadsheet_rows

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'行业一级子库_20261029'
DIRECTORY=ROOT/'行业专业JD优化_20261029'
MASTER=ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
ALLOWED={'jd','jd_clauses','jd_version','industry_jd_revision'}
HEADER=['岗位ID','岗位代码','岗位名称','职能','职责系列','层级','所属子库','本轮处置','岗位JD']
CHANGE_HEADER=['行业','岗位ID','岗位代码','岗位名称','改写原因','主库JD（未修改）','本行业子库新JD','专业框架','本行业来源ID']


def read(path):return json.loads(path.read_text('utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def text_sha(text):return hashlib.sha256(text.encode()).hexdigest()


def verify_job(before,after,common_functions):
    errors=[]
    if any(after.get(k)!=v for k,v in before.items() if k not in ALLOWED) or set(after)-set(before)-{'industry_jd_revision'}:
        errors.append('non_jd_fields_changed')
    changed=before['jd']!=after['jd']
    if before['function_name'] in common_functions and before!=after:
        errors.append('common_function_modified')
    if not changed and before!=after:
        errors.append('unchanged_job_has_hidden_edits')
    if changed:
        clauses=after['jd_clauses']
        if len(clauses) not in {4,5} or [c['number'] for c in clauses]!=list(range(1,len(clauses)+1)):
            errors.append('invalid_clause_count_or_numbering')
        if after['jd']!='\n'.join(f"{c['number']}、{c['text']}" for c in clauses):errors.append('clause_body_mismatch')
        if len({c['text'] for c in clauses})!=len(clauses):errors.append('duplicate_clause')
        if any(c['basis_type']!='专业补写' or c['source_refs'] for c in clauses):errors.append('fabricated_direct_evidence')
        if before['jd_role_mode']=='辅助或初级' and not all(c['text'].startswith('在指导下，') for c in clauses):errors.append('assistant_scope_exceeded')
        revision=after.get('industry_jd_revision',{})
        if revision.get('parent_jd_sha256')!=text_sha(before['jd']):errors.append('wrong_parent_jd')
    return errors


def valid_context(context,industry,job,evidence,metadata,authorized):
    sid=context['source_id']
    if sid not in job['industry_membership']['source_ids'] or sid not in evidence['sources']:
        return False
    source=evidence['sources'][sid]
    if source['industry']!=industry or metadata[sid]['最新输入_修改版6']['sheet']!=industry:
        return False
    body=evidence['texts'][source['jd_sha256']]
    if sid in {'SRC-传媒-1045','SRC-地产-1510'}:
        body=authorized.get((job['code'],sid),'')
    quote_valid=bool(context['quote']) and context['quote'] in body if body else context['quote']==''
    return bool(quote_valid and context.get('source_text_is_empty')==(not bool(body))
                and context['context_sha256']==text_sha(body) and context['source_name']==source['source_name'])


def equal_table(expected,actual,key_columns=(0,)):
    if not actual or actual[0]!=expected[0] or len(actual)!=len(expected):return False
    def key(r):return tuple(r[n] for n in key_columns)
    by_id={key(r):r for r in expected[1:]}
    return len({key(r) for r in actual[1:]})==len(by_id) and all(by_id.get(key(r))==r for r in actual[1:])


def audit():
    rules=read(DIRECTORY/'行业专业化规则.json');profiles={p['id']:p for p in rules['profiles']}
    overview=read(DIRECTORY/'子库优化总览.json');generation=read(DIRECTORY/'核验报告.json')
    records=read(DIRECTORY/'逐岗行业JD审查台账.json');changes=read(DIRECTORY/'行业JD改写对照.json')
    master=read(MASTER);master_by_id={j['id']:j for j in master['jobs']}
    original_industry_audit=read(BASE/'独立核验报告.json')
    evidence=read(ROOT/'双线协作交接_20261029/JD原文证据.json')
    metadata={r['source_id']:r for r in read(ROOT/'全量名称代码统一_20261029/全量原表元数据.json')}
    authorized={}
    for task in read(ROOT/'双线协作交接_20261029/JD编写输入.json')['jobs']:
        for item in task['role_scoped_evidence']:authorized[(task['baseline_code'],item['parent_source_id'])]=item['text']
    industries=sorted(p.parent.name for p in BASE.glob('*/岗位主库.json'))
    checks={'11行业范围与上版子库相同':len(industries)==11 and sorted(p.parent.name for p in DIRECTORY.glob('*/岗位主库.json'))==industries,
            '主库字节指纹等于上版已交付审计':sha(MASTER)==original_industry_audit['sha256'][MASTER.relative_to(ROOT).as_posix()],
            '主库及上版子库全部保护文件未变':all((ROOT/p).is_file() and sha(ROOT/p)==value for p,value in generation['protected_input_sha256'].items()),
            '强制通用职能保护集合存在':{'人力资源','财务','行政','审计','销售','采购','商务','政府事务','法律合规'}<=set(rules['protected_functions']),
            '19018条台账无遗漏无重复':len(records)==len({(r['industry'],r['job_id']) for r in records})==19018,
            '改写对照恰等于台账的修改记录':changes==[r for r in records if r['changed']]}
    grouped={i:{r['job_id']:r for r in records if r['industry']==i} for i in industries}
    combined=DIRECTORY/'BMJD_11行业专业JD优化.xlsx';errors=[];context_errors=[];summary=[];actual_changed=[];identity_ids=set();identity_codes=set()
    protected_set=set(rules['protected_functions'])
    for industry in industries:
        old_path=BASE/industry/'岗位主库.json';path=DIRECTORY/industry/'岗位主库.json';child=read(path);old=read(old_path)
        old_jobs={j['id']:j for j in old['jobs']};jobs=child['jobs'];local=grouped[industry]
        basic,_=audit_jobs(jobs)
        checks[industry+'子库编码名称ID及层级有效']=all(basic.values())
        checks[industry+'岗位范围和顺序未改']=[j['id'] for j in jobs]==[j['id'] for j in old['jobs']] and set(local)==set(old_jobs)
        checks[industry+'来源职能系列及行业边界未改']=child['sources']==old['sources'] and child['functions']==old['functions'] and child['series']==old['series'] and child['industry']==industry
        checks[industry+'原子库版本及指纹准确']=child['parent_subcatalog_version']==old['version'] and child['parent_subcatalog_sha256']==sha(old_path)
        changed=0;retained=0;common=0;expected=[HEADER]
        local_job_errors=[];local_context_errors=[];local_profile_errors=[]
        for job in jobs:
            before=old_jobs[job['id']];r=local[job['id']];diff=before['jd']!=job['jd']
            issues=verify_job(before,job,protected_set)
            if issues:local_job_errors.append([job['code'],issues])
            if r['changed']!=diff or r['old_jd_sha256']!=text_sha(before['jd']) or r['new_jd_sha256']!=text_sha(job['jd']):
                local_job_errors.append([job['code'],'incorrect_change_record'])
            if r['code']!=job['code'] or r['name']!=job['name']:
                local_job_errors.append([job['code'],'ledger_identity_changed'])
            if r['function_name'] in protected_set:common+=1
            if {c['source_id'] for c in r['local_source_context']}!=set(before['industry_membership']['source_ids']):
                local_context_errors.append([job['code'],'local_sources_incomplete'])
            for context in r['local_source_context']:
                if not valid_context(context,industry,before,evidence,metadata,authorized):local_context_errors.append([job['code'],context['source_id']])
            if diff:
                changed+=1;actual_changed.append((industry,job['id']))
                if r.get('old_jd')!=before['jd'] or r.get('new_jd')!=job['jd']:local_job_errors.append([job['code'],'wrong_comparison_body'])
                profile=profiles.get(r['selected_profile'])
                title=before['name'].replace('（'+before['function_name']+'）','').replace('('+before['function_name']+')','')+'\n'+before['series_name']
                if not profile or industry not in profile['industries'] or (profile['functions'] and before['function_name'] not in profile['functions']) or not re.search(profile['title_pattern'],title,re.I):
                    local_profile_errors.append([job['code'],'wrong_professional_profile'])
                elif profile.get('exclude_pattern') and re.search(profile['exclude_pattern'],title,re.I):local_profile_errors.append([job['code'],'excluded_profession'])
                else:
                    if not all(any(term.casefold() in job['jd'].casefold() for term in d) for d in profile['professional_dimensions']):
                        local_profile_errors.append([job['code'],'professional_dimensions_not_in_new_body'])
                if before['jd_review_status']!='重写' or len(r['missing_professional_dimensions'])<2:
                    local_profile_errors.append([job['code'],'not_a_generic_parent_with_explicit_gaps'])
                rev=job.get('industry_jd_revision',{})
                if rev.get('industry')!=industry or rev.get('profile_id')!=r['selected_profile'] or rev.get('local_source_ids')!=before['industry_membership']['source_ids']:
                    local_profile_errors.append([job['code'],'wrong_industry_revision'])
                if master_by_id[job['id']]['jd']!=before['jd']:local_profile_errors.append([job['code'],'master_jd_changed'])
            else:retained+=1
            identity_ids.add(job['id']);identity_codes.add(job['code'])
            expected.append([job['id'],job['code'],job['name'],job['function_name'],job['series_name'],str(job['level']),industry,r['status'],job['jd']])
        errors+=local_job_errors+local_profile_errors;context_errors+=local_context_errors
        checks[industry+'仅允许JD字段变更且通用职能原样保留']=not local_job_errors
        checks[industry+'每个原文引文只来自本行业授权来源']=not local_context_errors
        checks[industry+'新专业方向条款及变更记录有效']=not local_profile_errors
        with (DIRECTORY/industry/'岗位名称代码及JD.tsv').open(encoding='utf-8-sig',newline='') as f:checks[industry+'TSV与实际JSON逐字段相同']=equal_table(expected,list(csv.reader(f,delimiter='\t')))
        checks[industry+'独立Excel与实际JSON逐字段相同']=equal_table(expected,spreadsheet_rows(DIRECTORY/industry/'岗位主库.xlsx','岗位主库'))
        checks[industry+'合并Excel与实际JSON逐字段相同']=equal_table(expected,spreadsheet_rows(combined,industry))
        expected_changes=[CHANGE_HEADER]+[[r['industry'],r['job_id'],r['code'],r['name'],r['reason'],r['old_jd'],r['new_jd'],r['selected_profile'],'、'.join(s['source_id'] for s in r['local_source_context'])] for r in local.values() if r['changed']]
        checks[industry+'Excel逐岗改写前后对照完整']=equal_table(expected_changes,spreadsheet_rows(DIRECTORY/industry/'岗位主库.xlsx','改写前后对照'),(0,1))
        declared=next(x for x in overview['industries'] if x['industry']==industry)
        checks[industry+'改写保留统计可以重算']=declared['jobs']==len(jobs) and declared['modified']==changed and declared['retained']==retained and child['summary']['industry_jd_modified']==changed
        summary.append({'industry':industry,'jobs':len(jobs),'modified':changed,'retained':retained,'common_preserved':common})
    expected_all=[CHANGE_HEADER]+[[r['industry'],r['job_id'],r['code'],r['name'],r['reason'],r['old_jd'],r['new_jd'],r['selected_profile'],'、'.join(s['source_id'] for s in r['local_source_context'])] for r in changes]
    checks['合并Excel全部改写前后对照完整']=equal_table(expected_all,spreadsheet_rows(combined,'改写前后对照'),(0,1))
    checks['全部9111主库身份与19018行业岗位完整']=len(identity_ids)==len(identity_codes)==9111 and sum(r['jobs'] for r in summary)==19018
    checks['全部新写条款计数与总览一致']=len(actual_changed)==overview['summary']['modified_industry_jobs']
    checks['全部通用职能保留数与总览一致']=sum(r['common_preserved'] for r in summary)==overview['summary']['protected_common_function_jobs']
    paths=[MASTER,DIRECTORY/'行业专业化规则.json',DIRECTORY/'子库优化总览.json',DIRECTORY/'逐岗行业JD审查台账.json',DIRECTORY/'行业JD改写对照.json',combined,Path(__file__)]+[DIRECTORY/i/n for i in industries for n in ['岗位主库.json','岗位名称代码及JD.tsv','岗位主库.xlsx']]
    return {'version':rules['version'],'reviewer':'Codex独立行业JD产物核验','all_passed':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),
            'summary':{'industries':len(industries),'reviewed_industry_jobs':len(records),'modified_industry_jobs':len(actual_changed),'retained_industry_jobs':len(records)-len(actual_changed),'master_jd_changes':0,'changed_names':0,'changed_codes':0},
            'industries':summary,'checks':checks,'errors':errors,'context_errors':context_errors,
            'sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in paths},
            'scope_note':'核验身份、主库隔离、来源、专业规则边界和实际导出；规则通过不等于机器证明全部专业语义。'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group();group.add_argument('--write',action='store_true');group.add_argument('--check',action='store_true');args=parser.parse_args()
    report=audit()
    if not report['all_passed']:
        print(json.dumps(report,ensure_ascii=False,indent=2));return 1
    data=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode();path=DIRECTORY/'独立核验报告.json'
    if args.write or args.check:
        if path.exists() and path.read_bytes()!=data:raise ValueError('独立报告存在不同内容，不覆盖。')
        if args.check and not path.exists():raise ValueError('缺少独立核验报告。')
        if args.write and not path.exists():path.write_bytes(data)
    print(json.dumps({**report['summary'],'all_passed':report['all_passed'],'checks':f"{report['passed']}/{report['total']}"},ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
