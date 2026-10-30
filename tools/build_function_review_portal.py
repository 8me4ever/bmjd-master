"""Build a standalone grouped-master browser with direction-aware filtering."""
import argparse,base64,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'主库职能序列整合_20261030'
MASTER=OUT/'主库.json'
SRC=ROOT/'function_portal'
ORIGINAL=ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
INDUSTRY=ROOT/'行业专业JD优化_20261029'
VERSION='BMJD-FUNCTION-PORTAL-20261030-01'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def project(j):
    return {**{k:j[k] for k in ['id','code','name','level','series_id','series_name','series_prefix','aliases','industries','jd']},
      'function_id':j['function_group_id'],'function_name':j['function_group_name'],
      'direction_id':j['function_direction_id'],'direction_name':j['function_direction_name'],'source_function_name':j['function_name']}
def build():
    m=read(MASTER);old=read(ORIGINAL);oldby={j['id']:j for j in old['jobs']};by={j['id']:j for j in m['jobs']};overview=read(INDUSTRY/'子库优化总览.json')
    inputs=[MASTER,ORIGINAL,INDUSTRY/'子库优化总览.json',OUT/'JD边界问题.json'];local_jd={};members=0
    for r in overview['industries']:
        industry=r['industry'];p=INDUSTRY/industry/'岗位主库.json';inputs.append(p);child=read(p);local={};members+=len(child['jobs'])
        assert {j['id'] for j in child['jobs']}=={j['id'] for j in m['jobs'] if industry in j['industries']}
        for j in child['jobs']:
            original=oldby[j['id']];current=by[j['id']]
            assert all(j[k]==original[k] for k in ['code','name','level','function_id','series_id'])
            assert all(j[k]==current[k] for k in ['name','level','function_id','series_id']) and current['jd']==original['jd']
            if j['jd']!=original['jd']:local[j['id']]=j['jd']
        local_jd[industry]=local
    payload={'version':VERSION,'master_version':m['version'],'industry_version':overview['version'],'maintenance_enabled':False,
      'functions':[{'id':g['id'],'name':g['name'],'aliases':g['source_functions']} for g in m['function_groups']],
      'directions':[{'id':d['id'],'name':d['name'],'function_id':d['group_id']} for d in m['function_directions']],
      'series':[{'id':s['id'],'name':s['name'],'prefix':s['prefix'],'function_id':s['function_group_id'],'direction_id':s['function_direction_id'],'direction_name':s['function_direction_name']} for s in m['series']],
      'industries':[r['industry'] for r in overview['industries']],'jobs':[project(j) for j in m['jobs']],'industryJD':local_jd,
      'jdIssues':{r['job_id']:r['issue']+' 本轮保留现稿，已在审查表单列待修订。' for r in read(OUT/'JD边界问题.json')}}
    html=(SRC/'template.html').read_text('utf-8');count=len(m['function_groups'])
    notice=f'{count}个主序列 · 专业方向保留；产品108岗已统一PP。非产品代码、所有岗位名称和JD保持原样；新增工具待同步。'
    assert html.count('__REVIEW_NOTICE__')==1;html=html.replace('__REVIEW_NOTICE__',notice)
    for marker,name in [('/*__STYLES__*/','styles.css'),('/*__CORE__*/','portal-core.js'),('/*__APP__*/','portal-app.js')]:
        p=SRC/name;inputs.append(p);s=p.read_text('utf-8');assert '</script' not in s.lower() and html.count(marker)==1;html=html.replace(marker,s)
    inputs.extend([SRC/'template.html',Path(__file__)])
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode();packed=bytearray(gzip.compress(raw,mtime=0));packed[9]=255
    assert html.count('__PAYLOAD__')==1;data=html.replace('__PAYLOAD__',base64.b64encode(packed).decode()).encode()
    checks={'全9111岗位正确投影主序列及专业方向':len(payload['jobs'])==9111 and payload['jobs']==[project(j) for j in m['jobs']],
      '95主序列270专业方向3077系列':len(payload['functions'])==95 and len(payload['directions'])==270 and len(payload['series'])==3077,
      '产品108岗全部PP':sum(j['function_name']=='产品' for j in payload['jobs'])==108 and all(j['code'].startswith('PP') for j in payload['jobs'] if j['function_name']=='产品'),
      '11行业19018归属与843专业JD准确':members==19018 and len(local_jd)==11 and sum(len(v) for v in local_jd.values())==843,
      '3个既有JD问题在详情明确提示':len(payload['jdIssues'])==3 and 'jd-review-note' in html,
      '新增入口禁用且未引入旧配码工具':'id="maintenance-pending"' in html and 'href="岗位新增工具.html"' not in html,
      '主序列专业方向独立筛选':'id="direction-filter"' in html and 'filter.directionId' in html,
      'CSV附主序列专业方向ID版本':"'主职能序列'" in html and "'专业方向', '岗位ID', '主库版本'" in html}
    assert all(checks.values()),checks
    report={'version':VERSION,'master_version':m['version'],'all_passed':True,'checks':checks,'jobs':9111,'function_groups':95,'professional_directions':270,'specialized_jds':843,
      'html_sha256':hashlib.sha256(data).hexdigest(),'payload_sha256':hashlib.sha256(raw).hexdigest(),'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
      'scope':'独立复核页；旧行业专业职责按岗位ID关联，不回写行业或新增工具；原UI源码及旧页面不覆盖。'}
    return {'主库查岗.html':data,'页面构建核验.json':(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()},report

def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');a=p.parse_args();files,r=build()
    for name,data in files.items():
        path=OUT/name
        if path.exists() and path.read_bytes()!=data:raise ValueError('不覆盖已有不同版本：'+str(path))
        if a.check:assert path.read_bytes()==data,name
    if a.write:
        for name,data in files.items():
            path=OUT/name
            if not path.exists():path.write_bytes(data)
    print(json.dumps({k:r[k] for k in ['version','all_passed','jobs','function_groups','professional_directions']},ensure_ascii=False))
if __name__=='__main__':main()
