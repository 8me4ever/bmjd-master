"""Build the corrected-master review HTML, retaining prior catalogs and UI sources.

Industry JD texts are linked by stable job ID, never by historical codes. The
legacy add-job tool is deliberately not shipped or enabled in this review page.
"""
import argparse
import base64
import gzip
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'BMJD主库复核页面_20261030'
SRC=ROOT/'customer_portal'
MASTER=ROOT/'主库编码统一_20261030/主库.json'
PREVIOUS=ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
MAPPING=ROOT/'主库编码统一_20261030/新旧岗位代码映射.json'
INDUSTRY=ROOT/'行业专业JD优化_20261029'
VERSION='BMJD-MASTER-REVIEW-20261030-01'
FIELDS=['id','code','name','level','function_id','function_name','series_id','series_name','series_prefix','aliases','industries','jd']


def read(path):return json.loads(path.read_text('utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('页面源码接口已变更，需要复核替换位置：'+old[:75])
    return text.replace(old,new)


def build():
    master=read(MASTER);previous=read(PREVIOUS);mapping=read(MAPPING)
    old_by={j['id']:j for j in previous['jobs']};by_id={j['id']:j for j in master['jobs']};routes={r['job_id']:r for r in mapping}
    assert len(routes)==len(mapping)==len(by_id)==len(master['jobs'])==9111 and set(old_by)==set(by_id)==set(routes)
    for j in master['jobs']:
        old=old_by[j['id']];route=routes[j['id']]
        assert {k:v for k,v in j.items() if k not in {'code','series_prefix'}}=={k:v for k,v in old.items() if k not in {'code','series_prefix'}}
        assert route['previous_code']==old['code'] and route['current_code']==j['code'] and route['name']==j['name']
    jobs=[{k:j[k] for k in FIELDS} for j in master['jobs']]
    overview=read(INDUSTRY/'子库优化总览.json');overrides={};memberships=0
    inputs=[MASTER,PREVIOUS,MAPPING,INDUSTRY/'子库优化总览.json']
    for item in overview['industries']:
        name=item['industry'];path=INDUSTRY/name/'岗位主库.json';inputs.append(path);child=read(path);local={};memberships+=len(child['jobs'])
        assert {j['id'] for j in child['jobs']}=={j['id'] for j in master['jobs'] if name in j['industries']}
        for j in child['jobs']:
            current=by_id[j['id']];old=old_by[j['id']]
            assert all(j[k]==old[k] for k in ['code','name','level','function_id','series_id'])
            assert all(j[k]==current[k] for k in ['name','level','function_id','series_id'])
            if j['jd']!=old['jd']:local[j['id']]=j['jd']
        overrides[name]=local
    funcs=sorted({(j['function_id'],j['function_name']) for j in jobs},key=lambda x:x[1])
    series=[{k:s[k] for k in ['id','name','prefix','function_id']} for s in master['series']]
    payload={'version':VERSION,'master_version':master['version'],'industry_version':overview['version'],
      'review_mode':True,'industry_codes_migrated':False,'maintenance_enabled':False,
      'functions':[{'id':i,'name':n} for i,n in funcs],'series':series,
      'industries':[i['industry'] for i in overview['industries']],'jobs':jobs,'industryJD':overrides}
    html=(SRC/'template.html').read_text('utf-8')
    html=replace_once(html,'<title>BMJD · 岗位字典</title>','<title>BMJD · 主库编码复核版</title>')
    old_link=re.search(r'<a class="maintenance"[^>]*>.*?</a>',html,re.S)
    assert old_link
    html=replace_once(html,old_link[0],'<button class="maintenance" id="maintenance-pending" type="button" disabled title="新增工具尚未切换本次主库，确认后再同步">新增岗位 · 待同步</button>')
    notice='<p class="review-version" id="review-version">主库编码复核版 · 人力资源HR、财务FA、综合管理GM等已校正。行业职责沿用前版内容，新增工具待确认后同步。</p>'
    html=replace_once(html,'  <div id="loading"',f'  {notice}\n  <div id="loading"')
    html=replace_once(html,'<p>加入清单时保存所选职责版本。新增岗位在独立工具录入，导出后由主库维护者合并，不会自动更新此字典。</p>',
      '<p>本页供核对主库编码，使用BMJD-CODE-UNIFIED-20261030-01。行业JD沿用前版职责内容，岗位代码统一取本次主库。新增入口暂待同步。清单按岗位身份恢复，CSV附岗位ID及主库版本，便于回查。</p>')
    css=(SRC/'styles.css').read_text('utf-8')+'\n.review-version{padding:11px 15px;margin:-8px 0 22px;background:#edf2ff;border:1px solid #d3dff6;border-radius:7px;color:#415b87;font-size:12px;line-height:1.8;overflow-wrap:anywhere}.maintenance:disabled{opacity:.65;cursor:default;background:transparent}footer #version-label{overflow-wrap:anywhere}\n'
    core=(SRC/'portal-core.js').read_text('utf-8')
    core=replace_once(core,"'职责版本', '岗位JD']", "'职责版本', '岗位JD', '岗位ID', '主库版本']")
    core=replace_once(core,"v.label, v.text]);", "v.label, v.text, j.id, data.master_version]);")
    app=(SRC/'portal-app.js').read_text('utf-8')
    app=replace_once(app,"$('version-label').textContent='通用主库 + 行业专业职责 · 2026.10'", "$('version-label').textContent=data.master_version+' · 主库编码复核版'")
    for marker,content in [('/*__STYLES__*/',css),('/*__CORE__*/',core),('/*__APP__*/',app)]:
        assert '</script' not in content.lower();html=replace_once(html,marker,content)
    inputs.extend([SRC/name for name in ['template.html','styles.css','portal-core.js','portal-app.js']]+[Path(__file__)])
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    packed=bytearray(gzip.compress(raw,mtime=0));packed[9]=255  # platform-neutral gzip OS byte
    data=replace_once(html,'__PAYLOAD__',base64.b64encode(packed).decode()).encode('utf-8')
    checks={'9111岗名称代码ID唯一':len(jobs)==len({j['code'] for j in jobs})==len({j['name'] for j in jobs})==len({j['id'] for j in jobs})==9111,
      '当前代码与校正版主库全量一致':all(j['code']==by_id[j['id']]['code'] and j['series_prefix']==by_id[j['id']]['series_prefix'] for j in jobs),
      '263职能3077系列':len(funcs)==263 and len(series)==3077,
      '人资HR财务FA综合GM信息IT仓储LO':all(j['code'][:2]=={'人力资源':'HR','财务':'FA','综合管理':'GM','信息技术':'IT','仓储':'LO'}[j['function_name']] for j in jobs if j['function_name'] in {'人力资源','财务','综合管理','信息技术','仓储'}),
      '11行业19018归属不变':len(overrides)==11 and memberships==19018,
      '843条行业JD按岗位ID关联':sum(len(v) for v in overrides.values())==843 and len({i for v in overrides.values() for i in v})==832,
      '未输出行业旧代码或历史代码别名':all(set(j)==set(FIELDS) for j in jobs),
      '未启用旧版新增工具入口':b'id="maintenance-pending"' in data and 'href="岗位新增工具.html"' not in data.decode(),
      'CSV附岗位ID与主库版本':"'岗位ID', '主库版本'" in core,
      '主库版本在页面可见':"data.master_version+' · 主库编码复核版'" in app,
      '压缩内容平台无关':packed[9]==255 and gzip.decompress(packed)==raw}
    assert all(checks.values()),checks
    report={'version':VERSION,'master_version':master['version'],'industry_text_version':overview['version'],'industry_code_version_updated':False,'maintenance_updated':False,
      'jobs':len(jobs),'functions':len(funcs),'series':len(series),'industry_memberships':memberships,'specialized_jds':843,
      'all_passed':True,'checks':checks,'html_bytes':len(data),'html_sha256':hashlib.sha256(data).hexdigest(),
      'payload_sha256':hashlib.sha256(raw).hexdigest(),'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
      'scope':'只生成主库复核HTML；行业职责按稳定ID沿用文本，不生成/改写行业子库；不更新新增工具。'}
    return {'BMJD主库复核.html':data,'构建核验.json':(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8')},report


def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--write',action='store_true');group.add_argument('--check',action='store_true');args=parser.parse_args()
    files,report=build()
    if args.write:OUT.mkdir(exist_ok=True)
    for name,data in files.items():
        p=OUT/name
        if p.exists() and p.read_bytes()!=data:raise ValueError('已有不同文件，不覆盖：'+str(p))
        if args.check:assert p.read_bytes()==data,name
    if args.write:
        for name,data in files.items():
            p=OUT/name
            if not p.exists():p.write_bytes(data)
    print(json.dumps({k:report[k] for k in ['version','master_version','jobs','specialized_jds','all_passed','html_bytes']},ensure_ascii=False))

if __name__=='__main__':main()
