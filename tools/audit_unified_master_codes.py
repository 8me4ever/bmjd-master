"""Independent stdlib audit of the corrected master, evidence, mappings and exports.

Does not import the allocation builder or trust its pass flags. No child/HTML writes.
"""
import argparse
import collections
import csv
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from audit_job_codes import audit_jobs

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'主库编码统一_20261030'
BASE=ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
META=ROOT/'全量名称代码统一_20261029/全量原表元数据.json'
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
CORE={'人力资源':'HR','财务':'FA','综合管理':'GM','行政':'OA','信息技术':'IT','市场':'MK','销售':'MS','销售管理':'SA','法律合规':'LE','质量管理':'QA','EHS':'SE','物流管理':'LO','物流':'LO','仓储':'LO','运输':'LO','进出口事务':'LO'}
STRICT_R={'研发','软件开发','设计研发','产品研发','药品研发'}
PROTECTED={'GM001','HR963','DP203','DP204','DP205','DP206','AC435','CT205'}
RESERVED_R={'RA','RC','RM','RP'}

def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return ''.join(c for c in unicodedata.normalize('NFKC',s) if not c.isspace() and unicodedata.category(c)!='Cf').casefold()
def canon(s):return unicodedata.normalize('NFKC',s).strip().upper()

def xlsx(path):
    result={}
    with ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(t.text or '' for t in r.findall('.//s:t',NS)) for r in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',NS):
            rid=sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id');target=rels[rid]
            path=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            rows=[]
            for row in ET.fromstring(z.read(path)).findall('s:sheetData/s:row',NS):
                cells={}
                for c in row.findall('s:c',NS):
                    if c.find('s:f',NS) is not None:raise ValueError('Excel不应含公式岗位字段。')
                    col=re.match('[A-Z]+',c.get('r'))[0];n=0
                    for char in col:n=n*26+ord(char)-64
                    if c.get('t')=='inlineStr':value=''.join(t.text or '' for t in c.findall('.//s:t',NS))
                    else:
                        v=c.find('s:v',NS);value=v.text if v is not None else ''
                        if c.get('t')=='s':value=strings[int(value)]
                    cells[n-1]=value or ''
                rows.append([cells.get(i,'') for i in range(max(cells,default=-1)+1)])
            result[sheet.get('name')]=rows
    return result


def build_report():
    old=read(BASE);new=read(DIR/'主库.json');metadata=read(META)
    src={r['source_id']:{**r['原版BMJD'],'code':canon(r['原版BMJD']['code'])} for r in metadata}
    raw=collections.defaultdict(set)
    for s in src.values():raw[s['function']].add(s['code'][:2])
    dictionary=read(ROOT/'全库统一完成_20261029/规范职能字典.json');systems={f['name']:f.get('original_systems',[]) for f in dictionary}
    old_by={j['id']:j for j in old['jobs']};by={j['id']:j for j in new['jobs']}
    series={s['id']:s for s in new['series']};old_series={s['id']:s for s in old['series']}
    mappings=read(DIR/'新旧岗位代码映射.json');ledger=read(DIR/'系列编码核查台账.json');functions=read(DIR/'职能代码核查.json')
    checks,code_errors=audit_jobs(new['jobs']);errors=[]
    checks['9111岗ID集合及顺序保持']=len(by)==9111 and list(by)==list(old_by)
    checks['所有非编码岗位字段逐值保持']=all({k:v for k,v in j.items() if k not in {'code','series_prefix'}}=={k:v for k,v in old_by[i].items() if k not in {'code','series_prefix'}} for i,j in by.items())
    checks['父库版本及待确认状态明确']=new['parent_version']==old['version'] and new['code_review']['status']=='VERIFIED_PENDING_USER_CONFIRMATION' and not new['code_review']['subcatalogs_updated'] and not new['code_review']['html_updated']
    checks['263职能保持不变']=len({j['function_id'] for j in new['jobs']})==263 and {j['function_id'] for j in new['jobs']}=={j['function_id'] for j in old['jobs']}
    checks['3077系列ID及前四位唯一']=len(series)==len({s['prefix'] for s in new['series']})==3077 and set(series)==set(old_series)
    checks['系列除prefix外字段保持']=all({k:v for k,v in s.items() if k!='prefix'}=={k:v for k,v in old_series[i].items() if k!='prefix'} for i,s in series.items())
    checks['岗位与系列职能层级一致']=all(j['series_id'] in series and j['series_prefix']==j['code'][:4]==series[j['series_id']]['prefix'] and j['function_id']==series[j['series_id']]['function_id'] and j['id'] in series[j['series_id']]['job_ids'] for j in by.values())
    checks['人力资源60岗全部HR']=len([j for j in by.values() if j['function_name']=='人力资源'])==60 and all(j['code'].startswith('HR') for j in by.values() if j['function_name']=='人力资源')
    checks['财务109岗及综合60岗原码不动']=all(sum(j['function_name']==f for j in by.values())==count and all(j['code']==old_by[j['id']]['code'] and j['code'].startswith(CORE[f]) for j in by.values() if j['function_name']==f) for f,count in [('财务',109),('综合管理',60)])
    checks['指定保护代码保持原身份']=all(by[j['id']]['code']==j['code'] for j in old['jobs'] if j['code'] in PROTECTED)
    checks['原HR963不会挤出人资HR']=next(j['function_name'] for j in by.values() if j['code']=='HR963')=='会展'
    checks['全部基础职能码段正确']=all(j['code'][:2]==CORE[j['function_name']] for j in by.values() if j['function_name'] in CORE)
    checks['全量岗位映射无遗漏无重复']=len(mappings)==len({r['job_id'] for r in mappings})==9111 and {r['job_id'] for r in mappings}==set(by)
    checks['新旧映射与实际主库逐项一致']=all(r['name']==by[r['job_id']]['name'] and r['previous_code']==old_by[r['job_id']]['code'] and r['current_code']==by[r['job_id']]['code'] and r['changed']==(r['previous_code']!=r['current_code']) and r['source_ids']==by[r['job_id']]['source_ids'] for r in mappings)
    checks['全量3077系列台账覆盖']=len(ledger)==len({r['series_id'] for r in ledger})==3077 and {r['series_id'] for r in ledger}==set(series)
    evidence_errors=[];reasonable={};historical=set()
    history=['全库统一完成_20261029/统一主库.json','主库推定整理_20261029/统一主库.json','岗位名称代码统一_20261029/名称代码主库.json','全量名称代码统一_20261029/名称代码主库.json']
    for path in [BASE,*[ROOT/p for p in history]]:historical.update(j['code'][:4] for j in read(path)['jobs'])
    for r in metadata:
        for version in ['原版BMJD','最新输入_修改版6']:
            c=canon(r[version]['code'])
            if re.fullmatch('[A-Z]{2}[0-9]{2}',c[:4]):historical.add(c[:4])
    historical_extensions=0
    for row in ledger:
        s=series[row['series_id']];previous=old_series[s['id']];jobs=[by[i] for i in s['job_ids']];f=s['function_name'];p=s['prefix']
        sids=sorted({sid for j in jobs for sid in j['source_ids']});own={src[sid]['code'][:2] for sid in sids}
        legacy=previous['prefix'].startswith('R') and previous['prefix'][:2] not in RESERVED_R and (any('研发' in x for x in systems.get(f,[])) or f=='畜牧饲料')
        research=f in STRICT_R or legacy
        allowed={CORE[f]} if f in CORE else own|raw[f]
        blocks={CORE[f]} if f in CORE else own
        if research:blocks={b for b in blocks if b.startswith('R') and b not in RESERVED_R}
        pinned=any(old_by[j['id']]['code'] in PROTECTED for j in jobs) or f in CORE and previous['prefix'].startswith(CORE[f])
        old_reasonable=pinned or previous['prefix'][:2] in allowed or research and previous['prefix'].startswith('R') and previous['prefix'][:2] not in RESERVED_R
        reasonable[s['id']]=old_reasonable
        originals={src[sid]['code'][:4] for sid in sids if src[sid]['code'][:2] in blocks}
        permitted=(p==previous['prefix'] and old_reasonable) or not pinned and (p[:2] in blocks or research and p.startswith('R') and p[:2] not in RESERVED_R)
        valid=(permitted and row['current_prefix']==p and row['previous_prefix']==previous['prefix'] and row['source_ids']==sids and row['extension_blocks']==sorted(blocks) and row['previous_reasonable']==old_reasonable and row['research_policy']==research and row['pinned']==pinned)
        if not valid:evidence_errors.append({'series_id':s['id'],'prefix':p,'function':f})
        historical_extensions+=int(p!=previous['prefix'] and p in historical and p not in originals)
    checks['每系列字母段按原始来源独立复核']=not evidence_errors
    checks['研发R规则不占非研发RA_RC_RM_RP']=all(not row['research_policy'] or not row['changed'] or row['current_prefix'].startswith('R') and row['current_prefix'][:2] not in RESERVED_R for row in ledger)
    checks['历史码段必要扩展无隐瞒']=historical_extensions==sum(r['historical_prefix_extension'] for r in ledger)
    checks['263职能统计与实际岗位一致']=len(functions)==len({r['function_name'] for r in functions})==263 and all(r['current_blocks']==dict(collections.Counter(j['code'][:2] for j in by.values() if j['function_name']==r['function_name'])) and r['previous_blocks']==dict(collections.Counter(j['code'][:2] for j in old_by.values() if j['function_name']==r['function_name'])) for r in functions)
    prior_by_code={j['code']:j for j in old['jobs']}
    expected_reuse={(j['code'],prior_by_code[j['code']]['id'],j['id']) for j in by.values() if j['code'] in prior_by_code and prior_by_code[j['code']]['id']!=j['id']}
    reuse=read(DIR/'跨版本代码身份变更.json')
    checks['跨版本代码身份变更逐条披露']=len(reuse)==len(expected_reuse) and {(r['code'],r['previous_job_id'],r['current_job_id']) for r in reuse}==expected_reuse
    m_by_id={r['job_id']:r for r in mappings}
    header=['岗位ID','岗位代码','岗位名称','职能','职责系列','层级','适用行业','岗位JD','旧代码','本轮处置']
    rows=[header]+[[j['id'],j['code'],j['name'],j['function_name'],j['series_name'],str(j['level']),'、'.join(j['industries']),j['jd'],old_by[j['id']]['code'],m_by_id[j['id']]['decision']] for j in new['jobs']]
    with (DIR/'岗位名称代码及JD.tsv').open('r',encoding='utf-8-sig',newline='') as f:tsv=list(csv.reader(f,delimiter='\t'))
    checks['TSV与主库9111岗全部字段一致']=tsv==rows
    excel=xlsx(DIR/'主库名称代码及JD.xlsx')
    checks['Excel主表与主库全部字段一致']=excel['岗位名称代码及JD']==rows
    changes=[['岗位ID','岗位名称','职能','职责系列','层级','旧代码','新代码','处理依据']]+[[r['job_id'],r['name'],r['function_name'],r['series_name'],str(r['level']),r['previous_code'],r['current_code'],r['decision']] for r in mappings if r['changed']]
    checks['Excel改动页与映射一致']=excel['新旧码改动对照']==changes
    checks['Excel跨版本身份变化页完整']=len(excel['跨版本同码身份变化'])==len(reuse)+1 and {tuple(r[:5]) for r in excel['跨版本同码身份变化'][1:]}=={(r['code'],r['previous_job_id'],r['previous_name'],r['current_job_id'],r['current_name']) for r in reuse}
    checks['Excel五类工作表齐全']=set(excel)=={'岗位名称代码及JD','新旧码改动对照','职能代码核对','跨版本同码身份变化','使用说明'}
    report=read(DIR/'核验报告.json');changed=sum(j['code']!=old_by[i]['code'] for i,j in by.items())
    checks['构建统计与实际改动一致']=report['summary']['changed_jobs']==changed and report['summary']['retained_jobs']==9111-changed and report['summary']['cross_version_code_reassignments']==len(reuse) and report['summary']['historical_prefix_extensions']==historical_extensions and report['summary']['unresolved_series']==0
    checks['输入指纹保持']=all(sha(ROOT/p)==h for p,h in report['input_sha256'].items())
    manifest=read(ROOT/'项目文件清单.json')
    protected={p:v['sha256'] for p,v in manifest['files'].items() if p.startswith(('岗位JD匹配审查_20261029/','行业一级子库_20261029/','行业专业JD优化_20261029/','BMJD客户查岗平台_20261030/','BMJD持续补全工具_20261029/','completion_tool/','customer_portal/'))}
    checks['旧主库子库和HTML工具未修改']=bool(protected) and all(sha(ROOT/p)==h for p,h in protected.items())
    files=[p for p in DIR.iterdir() if p.suffix in {'.json','.xlsx','.tsv'} and p.name!='独立核验报告.json']
    result={'version':new['version'],'reviewer':'Codex独立产物与原版证据核验','all_passed':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),
      'summary':{'jobs':len(by),'unique_codes':len({j['code'] for j in by.values()}),'changed_jobs':changed,'retained_jobs':9111-changed,'cross_version_code_reassignments':len(reuse),'historical_prefix_extensions':historical_extensions,'unresolved_series':len(evidence_errors),'subcatalogs_updated':False,'html_updated':False},
      'checks':checks,'code_errors':code_errors,'evidence_errors':evidence_errors,'sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)},'protected_sha256':protected,
      'scope':'结构、全量原表字母段依据、映射与导出核验；不是对全部岗位专业身份的新一轮语义审定。旧码必须附版本或ID。'}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--write',action='store_true');p.add_argument('--check',action='store_true');args=p.parse_args()
    report=build_report();assert report['all_passed'],[k for k,v in report['checks'].items() if not v]
    data=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode();path=DIR/'独立核验报告.json'
    if args.write:
        if path.exists() and path.read_bytes()!=data:raise ValueError('已有不同核验报告，不覆盖。')
        path.write_bytes(data)
    if args.check:assert path.read_bytes()==data,'独立报告与重算不同。'
    print(json.dumps({k:report[k] for k in ['all_passed','passed','total','summary']},ensure_ascii=False))

if __name__=='__main__':main()
