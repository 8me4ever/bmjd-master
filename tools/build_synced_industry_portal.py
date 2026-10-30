"""Build the approved master portal from the newly synchronized industry catalogs."""
import argparse
import base64
import gzip
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'BMJD行业同步页面_20261030'
MASTER=ROOT/'原版分类编码收口_20261030/主库.json'
MAPPING=MASTER.parent/'逐岗原版代码对照.json'
AUDIT=MASTER.parent/'独立核验报告.json'
SOURCE=ROOT/'semantic_portal'
ORIGINAL=ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
ISSUES=ROOT/'主库职能序列整合_20261030/JD边界问题.json'
INDUSTRY=ROOT/'行业子库同步_20261030'
VERSION='BMJD-INDUSTRY-PORTAL-20261030-01'
FIELDS=['id','code','name','level','series_id','series_name','series_prefix','aliases','industries','jd']
EVIDENCE=['original_systems','original_functions','original_specialties','original_codes','extension_of']

def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def project(j,r):
    return {**{k:j[k] for k in FIELDS},'function_id':j['function_group_id'],'function_name':j['function_group_name'],
      'direction_id':j['function_direction_id'],'direction_name':j['function_direction_name'],
      'source_function_name':j['function_name'],**{k:r[k] for k in EVIDENCE},'code_reason':r['reason']}


def build():
    m=read(MASTER);old=read(ORIGINAL);by={j['id']:j for j in m['jobs']};oldby={j['id']:j for j in old['jobs']}
    mappings=read(MAPPING);routes={r['job_id']:r for r in mappings};audit=read(AUDIT)
    assert audit['all_passed'] and audit['version']==m['version']
    assert audit['sha256'][MASTER.relative_to(ROOT).as_posix()]==sha(MASTER)
    assert audit['sha256'][MAPPING.relative_to(ROOT).as_posix()]==sha(MAPPING)
    assert len(mappings)==len(routes)==len(by)==9111
    for j in m['jobs']:
        r=routes[j['id']]
        assert (j['code'],j['name'],j['level'])==(r['current_code'],r['name'],r['level'])
        assert re.fullmatch(r'[A-Z]{2}[0-9]{2}[1-7]',j['code'])
    overview=read(INDUSTRY/'子库总览.json');industry_audit=read(INDUSTRY/'独立核验报告.json');local_jd={};members=0;catalogs=[]
    assert industry_audit['all_passed'] and overview['approved_master'] and overview['parent_version']==m['version'] and overview['parent_master_sha256']==sha(MASTER)
    inputs=[MASTER,MAPPING,AUDIT,ORIGINAL,ISSUES,INDUSTRY/'子库总览.json',INDUSTRY/'独立核验报告.json',INDUSTRY/'主库确认记录.json']
    for r in overview['industries']:
        industry=r['industry'];p=INDUSTRY/industry/'岗位主库.json';inputs.append(p);child=read(p);local={}
        members+=len(child['jobs']);catalogs.append({'industry':industry,'version':child['version'],'parent_version':child['parent_version'],'jobs':len(child['jobs']),'sha256':sha(p)})
        assert child['version']==overview['version'] and child['parent_version']==m['version'] and child['parent_master_sha256']==sha(MASTER)
        assert {j['id'] for j in child['jobs']}=={j['id'] for j in m['jobs'] if industry in j['industries']}
        for j in child['jobs']:
            origin=oldby[j['id']];current=by[j['id']]
            assert all(j[k]==current[k] for k in ['id','code','name','level','function_id','series_id','series_prefix','function_group_id','function_direction_id','source_ids'])
            assert all(j[k]==current[k] for k in ['name','level','function_id','series_id']) and current['jd']==origin['jd']
            if j['jd']!=origin['jd']:local[j['id']]=j['jd']
        local_jd[industry]=local
    payload={'version':VERSION,'master_version':m['version'],'industry_version':overview['version'],
      'maintenance_enabled':False,'industry_codes_migrated':True,'approved_master':True,'review_mode':False,'industry_catalogs':catalogs,
      'functions':[{'id':g['id'],'name':g['name'],'aliases':g['source_functions']} for g in m['function_groups']],
      'directions':[{'id':d['id'],'name':d['name'],'function_id':d['group_id']} for d in m['function_directions']],
      'series':[{'id':s['id'],'name':s['name'],'prefix':s['prefix'],'function_id':s['function_group_id'],
        'direction_id':s['function_direction_id'],'direction_name':s['function_direction_name']} for s in m['series']],
      'industries':[r['industry'] for r in overview['industries']],
      'jobs':[project(j,routes[j['id']]) for j in m['jobs']],'industryJD':local_jd,
      'jdIssues':{r['job_id']:r['issue']+' 本轮保留现稿，已在审查表单列待修订。' for r in read(ISSUES)}}
    html=(SOURCE/'template.html').read_text().replace('BMJD · 主库汇总预览版','BMJD · 主库与11行业子库').replace('分类与代码确认后再同步新增工具','新增工具尚未迁移到确认主库').replace('新增工具仍待分类确认后同步','新增工具尚未迁移')
    notice='11个行业子库已同步确认主库 · 岗位名称、五位代码和层级统一；行业专业JD分别保留。左侧分类用于浏览，原版分类与代码依据可在岗位详情查看。'
    assert html.count('__REVIEW_NOTICE__')==1;html=html.replace('__REVIEW_NOTICE__',notice)
    for marker,name in [('/*__STYLES__*/','styles.css'),('/*__CORE__*/','portal-core.js'),('/*__APP__*/','portal-app.js')]:
        p=SOURCE/name;inputs.append(p);s=p.read_text()
        if name=='portal-app.js':s=s.replace("data.master_version+' · 主库汇总预览版'","data.master_version+' · '+data.industry_version")
        if name=='portal-core.js':
            assert s.count("'扩展自']]")==1 and s.count("j.extension_of || '']);")==1
            s=s.replace("'扩展自']]","'扩展自', '子库版本']]").replace("j.extension_of || '']);","j.extension_of || '', r.industry ? data.industry_version : '']);")
        assert '</script' not in s.lower() and html.count(marker)==1;html=html.replace(marker,s)
    inputs.extend([SOURCE/'template.html',Path(__file__)])
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode();packed=bytearray(gzip.compress(raw,mtime=0));packed[9]=255
    assert html.count('__PAYLOAD__')==1;html=html.replace('__PAYLOAD__',base64.b64encode(packed).decode()).encode()
    checks={'全部9111岗位来自最新主库':payload['jobs']==[project(j,routes[j['id']]) for j in m['jobs']],
      '名称代码ID唯一且严格五位':len(by)==len({j['code'] for j in m['jobs']})==len({j['name'] for j in m['jobs']})==9111,
      '95浏览分类270方向3077原系列':len(payload['functions'])==95 and len(payload['directions'])==270 and len(payload['series'])==3077,
      'PB_PG_RX扩展全部334岗使用当前码':sum(j['code'][:2] in {'PB','PG','RX'} for j in payload['jobs'])==334,
      '产品108岗全部PP':sum(j['function_name']=='产品' for j in payload['jobs'])==108 and all(j['code'].startswith('PP') for j in payload['jobs'] if j['function_name']=='产品'),
      '原分类原码及扩展依据逐岗可回查':all(all(j[k]==routes[j['id']][k] for k in EVIDENCE) for j in payload['jobs']) and b'id="code-basis"' in html,
      '11新子库名称代码层级与主库一致且843专业JD保留':members==19018 and len(local_jd)==11 and sum(len(v) for v in local_jd.values())==843 and payload['industry_codes_migrated'],
      '11子库版本及主库父版本完全一致':len(catalogs)==11 and all(c['version']==overview['version'] and c['parent_version']==m['version'] for c in catalogs),
      '3个既有JD问题继续提示':len(payload['jdIssues'])==3 and b'id="jd-review-note"' in html,
      '旧新增工具仍禁用':b'id="maintenance-pending"' in html and 'href="岗位新增工具.html"' not in html.decode(),
      '无外部数据文件依赖':not re.search(r'(?:src|href)="https?://',html.decode()),
      '平台无关压缩可还原':packed[9]==255 and gzip.decompress(packed)==raw}
    assert all(checks.values()),checks
    report={'version':VERSION,'master_version':m['version'],'all_passed':True,'checks':checks,
      'jobs':9111,'function_groups':95,'professional_directions':270,'specialized_jds':843,
      'html_sha256':hashlib.sha256(html).hexdigest(),'payload_sha256':hashlib.sha256(raw).hexdigest(),
      'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
      'industry_version':overview['version'],'industry_codes_migrated':True,'scope':'HTML直接读取新11行业子库；确认主库、岗位名码及JD不修改，旧版本与新增工具不覆盖。'}
    return {'BMJD主库与行业子库.html':html,'页面构建核验.json':(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()},report


def main():
    parser=argparse.ArgumentParser(description=__doc__);g=parser.add_mutually_exclusive_group(required=True);g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');args=parser.parse_args()
    files,report=build();OUT.mkdir(exist_ok=True)
    for name,data in files.items():
        p=OUT/name
        if p.exists():assert p.read_bytes()==data,'不覆盖已有不同版本：'+name
        elif args.check:raise ValueError('缺少文件：'+name)
        elif args.write:p.write_bytes(data)
    print(json.dumps({'all_passed':True,'version':report['version'],'master_version':report['master_version'],'jobs':9111},ensure_ascii=False))


if __name__=='__main__':main()
