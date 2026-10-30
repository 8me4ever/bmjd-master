"""Build separate internal and customer portals with all results on one page."""
import argparse
import base64
import copy
import gzip
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'audience_portal';OUT=ROOT/'BMJD内外双版_20261030'
BASE=ROOT/'BMJD行业同步页面_20261030';MASTER=ROOT/'原版分类编码收口_20261030/主库.json';CHILDREN=ROOT/'行业子库同步_20261030'
PUBLIC_FIELDS=['id','code','name','level','function_id','function_name','direction_id','direction_name','series_id','series_name','series_prefix','aliases','industries','jd']
PROFILES={'internal':('BMJD内部使用版.html','BMJD-INTERNAL-20261030-01'),'client':('BMJD客户查询版.html','BMJD-CLIENT-20261030-01')}
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encoded(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()


def load_source():
    p=BASE/'BMJD主库与行业子库.html';report=read(BASE/'页面构建核验.json');browser=read(BASE/'页面浏览器核验.json')
    assert report['all_passed'] and browser['all_passed'] and sha(p)==report['html_sha256']==browser['html_sha256']
    for name,h in report['input_sha256'].items():assert sha(ROOT/name)==h,name
    data=json.loads(gzip.decompress(base64.b64decode(re.search(r'<script id="portal-payload"[^>]*>(.*?)</script>',p.read_text(),re.S)[1])))
    m=read(MASTER);by={j['id']:j for j in data['jobs']};overview=read(CHILDREN/'子库总览.json')
    assert data['master_version']==m['version'] and data['industry_version']==overview['version'] and data['industry_codes_migrated']
    assert len(m['jobs'])==len(by)==9111
    for j in m['jobs']:
        assert all(by[j['id']][k]==j[k] for k in ['id','code','name','level','series_id','series_prefix','series_name','aliases','industries','jd'])
    inputs=[p,BASE/'页面构建核验.json',BASE/'页面浏览器核验.json',MASTER,CHILDREN/'子库总览.json',CHILDREN/'独立核验报告.json']
    for r in overview['industries']:
        p=CHILDREN/r['industry']/'岗位主库.json';inputs.append(p);child=read(p)
        assert {j['id'] for j in child['jobs']}=={j['id'] for j in data['jobs'] if r['industry'] in j['industries']}
        for j in child['jobs']:
            q=by[j['id']]
            assert all(q[k]==j[k] for k in ['id','code','name','level','series_id'])
            assert data['industryJD'][r['industry']].get(j['id'],q['jd'])==j['jd']
    return data,inputs


def build():
    base,inputs=load_source();files={};profiles={}
    for audience,(filename,version) in PROFILES.items():
        if audience=='internal':
            data=copy.deepcopy(base);data.update(version=version,audience=audience,pagination=False)
        else:
            data={'version':version,'master_version':base['master_version'],'industry_version':base['industry_version'],
              'audience':audience,'pagination':False,'industries':base['industries'],
              'functions':[{'id':f['id'],'name':f['name']} for f in base['functions']],
              'directions':base['directions'],'jobs':[{k:j[k] for k in PUBLIC_FIELDS} for j in base['jobs']],
              'industryJD':base['industryJD'],'jdNotices':{i:'该岗位职责待复核，请结合实际工作确认。' for i in base['jdIssues']}}
        template=SOURCE/(audience+'-template.html');inputs.append(template);html=template.read_text()
        if audience=='internal':
            assert html.count('__REVIEW_NOTICE__')==1
            html=html.replace('__REVIEW_NOTICE__','内部使用 · 主库及11行业子库已同步；全部结果在本页显示。支持职责对比、清单导出及原版编码依据查看。')
        for marker,suffix in [('/*__STYLES__*/','styles.css'),('/*__CORE__*/','core.js'),('/*__APP__*/','app.js')]:
            p=SOURCE/(audience+'-'+suffix);inputs.append(p);source=p.read_text()
            assert html.count(marker)==1 and '</script' not in source.lower();html=html.replace(marker,source)
        raw=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode();compressed=bytearray(gzip.compress(raw,mtime=0));compressed[9]=255
        assert html.count('__PAYLOAD__')==1
        html=html.replace('__PAYLOAD__',base64.b64encode(compressed).decode()).encode();files[filename]=html
        checks={'全部9111岗位名码层级JD及行业版本一致':len(data['jobs'])==9111 and all(all(j[k]==base['jobs'][i][k] for k in PUBLIC_FIELDS) for i,j in enumerate(data['jobs'])) and data['industryJD']==base['industryJD'],
          '没有分页控件或分页截取代码':not any(t in html.decode() for t in ['previous-page','next-page','page-label','slice(page','turnPage(','Math.ceil(total/size)']),
          '完整五位码及名称唯一':len({j['code'] for j in data['jobs']})==len({j['name'] for j in data['jobs']})==9111,
          '行业专业JD843条保持':sum(len(v) for v in data['industryJD'].values())==843,
          '单文件没有外部资源依赖':not re.search(r'(?:src|href)="https?://',html.decode())}
        if audience=='client':
            checks['客户岗位数据无内部原码及审查依据']=all(set(j)==set(PUBLIC_FIELDS) for j in data['jobs']) and 'jdIssues' not in data
            checks['客户无对比清单导出复制新增及存储逻辑']=not any(t in html.decode() for t in ['id="compare','id="nav-saved"','id="save-job"','id="export','id="copy','id="code-basis"','maintenance-pending','localStorage','navigator.clipboard','function csv(','function matrixRows('])
        else:checks['内部保留对比清单导出及原码依据']=all(t in html.decode() for t in ['id="compare-detail"','id="save-job"','id="export-saved"','id="code-basis"'])
        assert all(checks.values()),checks
        profiles[audience]={'file':filename,'version':version,'all_passed':True,'checks':checks,'jobs':9111,'pagination':False,
          'html_sha256':hashlib.sha256(html).hexdigest(),'payload_sha256':hashlib.sha256(raw).hexdigest(),'payload_fields':sorted(data)}
    inputs.append(Path(__file__))
    report={'version':'BMJD-AUDIENCE-RELEASE-20261030-01','master_version':base['master_version'],'industry_version':base['industry_version'],
      'all_passed':True,'profiles':profiles,'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
      'scope':'仅新增内部/客户两个单页HTML，确认主库及11子库不改。客户只含查找及JD查看所需功能和数据。'}
    files['构建核验.json']=encoded(report)
    return files,report


def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');a=p.parse_args();files,r=build();OUT.mkdir(exist_ok=True)
    for n,b in files.items():
        path=OUT/n
        if path.exists():assert path.read_bytes()==b,'不覆盖已有不同版本：'+n
        elif a.check:raise ValueError('缺少文件：'+n)
        else:path.write_bytes(b)
    print(json.dumps({'all_passed':True,'versions':{a:p['version'] for a,p in r['profiles'].items()},'jobs':9111,'pagination':False},ensure_ascii=False))


if __name__=='__main__':main()
