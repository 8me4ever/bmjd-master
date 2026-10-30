"""Build the customer-facing offline catalog. Never change master or industry data."""
import argparse,base64,gzip,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'BMJD客户查岗平台_20261030'
SRC=ROOT/'customer_portal'
MASTER=ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
INDUSTRY=ROOT/'行业专业JD优化_20261029'
MAINTENANCE=ROOT/'BMJD持续补全工具_20261029/BMJD岗位持续补全.html'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build():
    master=read(MASTER);by_id={j['id']:j for j in master['jobs']};overview=read(INDUSTRY/'子库优化总览.json');industry_jd={};inputs=[MASTER,INDUSTRY/'子库优化总览.json',MAINTENANCE];memberships=0
    fields=['id','code','name','level','function_id','function_name','series_id','series_name','series_prefix','aliases','industries','jd']
    jobs=[{k:j[k] for k in fields} for j in master['jobs']]
    for item in overview['industries']:
        industry=item['industry'];p=INDUSTRY/industry/'岗位主库.json';inputs.append(p);sub=read(p);local={};memberships+=len(sub['jobs'])
        assert {j['id'] for j in sub['jobs']}=={j['id'] for j in master['jobs'] if industry in j['industries']}
        for j in sub['jobs']:
            parent=by_id[j['id']];assert all(j[k]==parent[k] for k in ['name','code','level','function_id','series_id'])
            if j['jd']!=parent['jd']:local[j['id']]=j['jd']
        industry_jd[industry]=local
    funcs=sorted({(j['function_id'],j['function_name']) for j in jobs},key=lambda x:x[1])
    series=[{k:s[k] for k in ['id','name','prefix','function_id']} for s in master['series']]
    payload={'version':'BMJD-CUSTOMER-20261030-01','master_version':master['version'],'industry_version':overview['version'],'functions':[dict(id=i,name=n) for i,n in funcs],'series':series,'industries':[i['industry'] for i in overview['industries']],'jobs':jobs,'industryJD':industry_jd}
    checks={'9111个只读岗位':len(jobs)==len(by_id)==9111,'263规范职能及3077系列':len(funcs)==263 and len(series)==3077,'11行业19018归属记录':len(industry_jd)==11 and memberships==19018,'843条行业专业JD覆盖':sum(len(v) for v in industry_jd.values())==843,'832个主岗位有行业专业版本':len({i for v in industry_jd.values() for i in v})==832,'客户数据不含原文证据与审议台账':all(set(j)==set(fields) for j in jobs)}
    html=(SRC/'template.html').read_text('utf-8')
    for marker,name in [('/*__STYLES__*/','styles.css'),('/*__CORE__*/','portal-core.js'),('/*__APP__*/','portal-app.js')]:
        p=SRC/name;inputs.append(p);content=p.read_text('utf-8');assert '</script' not in content.lower(),name;assert html.count(marker)==1;html=html.replace(marker,content)
    inputs.extend([SRC/'template.html',Path(__file__)])
    assert html.count('__PAYLOAD__')==1
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8');html=html.replace('__PAYLOAD__',base64.b64encode(gzip.compress(raw,mtime=0)).decode())
    checks['独立新增入口有效']='href="岗位新增工具.html"' in html
    checks['查询页没有审议或主库编辑控件']=not any(x in html for x in ['审议通过','待审议','审核决议','id="job-form"'])
    assert all(checks.values()),checks
    data=html.encode('utf-8');report={'version':payload['version'],'master_version':master['version'],'industry_version':overview['version'],'jobs':len(jobs),'functions':len(funcs),'industry_memberships':memberships,'specialized_jds':843,'all_passed':True,'checks':checks,'html_bytes':len(data),'html_sha256':hashlib.sha256(data).hexdigest(),'maintenance_sha256':sha(MAINTENANCE),'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs}}
    return {'BMJD客户查岗平台.html':data,'岗位新增工具.html':MAINTENANCE.read_bytes(),'构建核验.json':(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8')},report
def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group();g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');args=p.parse_args();files,report=build()
    if args.write:
        OUT.mkdir(exist_ok=True)
        for name,data in files.items():(OUT/name).write_bytes(data)
        guide=OUT/'使用说明.md'
        if guide.exists():
            with zipfile.ZipFile(OUT/'BMJD客户查岗平台_外发包.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
                names=[*files,'使用说明.md']
                if (OUT/'浏览器核验.json').exists():names.append('浏览器核验.json')
                for name in names:z.write(OUT/name,arcname=name)
    if args.check:
        for name,data in files.items():assert (OUT/name).read_bytes()==data,name
    assert all(sha(ROOT/n)==h for n,h in report['input_sha256'].items())
    print(json.dumps({'version':report['version'],'jobs':9111,'specialized_jds':843,'all_passed':True,'html_mb':round(report['html_bytes']/1048576,2)},ensure_ascii=False))
if __name__=='__main__':main()
