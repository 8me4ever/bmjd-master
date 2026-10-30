"""Read-only data and isolated Chromium checks for the corrected-master HTML."""
import argparse
import base64
import csv
import gzip
import hashlib
import io
import json
import re
import shutil
import tempfile
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'BMJD主库复核页面_20261030'
MASTER=ROOT/'主库编码统一_20261030/主库.json'
FIELDS=['id','code','name','level','function_id','function_name','series_id','series_name','series_prefix','aliases','industries','jd']


def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clauses(text):return [re.sub(r'^\s*\d+\s*[、.．)]\s*','',s).strip() for s in text.splitlines() if s.strip()]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--screenshots',type=Path,default=Path('/tmp/bmjd-master-review-screenshots'));args=parser.parse_args()
    from playwright.sync_api import sync_playwright
    checks={};errors=[];external=[]
    def check(name,ok):
        assert ok,name
        checks[name]=True;print('PASS '+name,flush=True)
    path=OUT/'BMJD主库复核.html';report=read(OUT/'构建核验.json');master=read(MASTER);by_id={j['id']:j for j in master['jobs']}
    packed=re.search(r'<script id="portal-payload"[^>]*>(.*?)</script>',path.read_text(),re.S)[1]
    payload=json.loads(gzip.decompress(base64.b64decode(packed)))
    check('HTML内置9111岗与校正版主库全部展示字段一致',payload['jobs']==[{k:j[k] for k in FIELDS} for j in master['jobs']])
    check('内置代码名称ID唯一',len(payload['jobs'])==len({j['code'] for j in payload['jobs']})==len({j['name'] for j in payload['jobs']})==len({j['id'] for j in payload['jobs']})==9111)
    check('内置3077系列使用新前缀',payload['series']==[{k:s[k] for k in ['id','name','prefix','function_id']} for s in master['series']])
    expected={'人力资源':'HR','财务':'FA','综合管理':'GM','行政':'OA','信息技术':'IT','市场':'MK','销售':'MS','销售管理':'SA','法律合规':'LE','质量管理':'QA','EHS':'SE','物流管理':'LO','物流':'LO','仓储':'LO','运输':'LO','进出口事务':'LO'}
    check('16类基础职能全部使用校正码段',all(j['code'][:2]==expected[j['function_name']] for j in payload['jobs'] if j['function_name'] in expected))
    count=0;med=None;special_industry=''
    for name,local in payload['industryJD'].items():
        child=read(ROOT/'行业专业JD优化_20261029'/name/'岗位主库.json');local_by={j['id']:j for j in child['jobs']}
        for jid,text in local.items():
            assert text==local_by[jid]['jd'] and name in by_id[jid]['industries'];count+=1
            if med is None and by_id[jid]['code']!=local_by[jid]['code']:med=by_id[jid];special_industry=name
    check('843条专业JD按ID准确关联且行业适用',count==843 and med is not None)
    med_jd=payload['industryJD'][special_industry][med['id']]
    hr=next(j for j in master['jobs'] if j['function_name']=='人力资源' and j['series_prefix']=='HR00' and j['level']==5)
    warehouse=next(j for j in master['jobs'] if j['function_name']=='仓储' and j['level']==5)
    it=next(j for j in master['jobs'] if j['function_name']=='信息技术' and j['level']==5)
    reassigned=read(ROOT/'主库编码统一_20261030/跨版本代码身份变更.json')[0]
    class Quiet(SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw):super().__init__(*a,directory=str(OUT),**kw)
        def log_message(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}/'+quote(path.name)
    args.screenshots.mkdir(parents=True,exist_ok=True)
    file_check={'passed':False,'scope':'Managed system Chromium file-URL policy; no bypass attempted.'}
    try:
        with tempfile.TemporaryDirectory(prefix='bmjd-review-') as temp,sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            seed=json.dumps([{'id':hr['id'],'industry':''},{'id':med['id'],'industry':special_industry}],ensure_ascii=False)
            context.add_init_script('if(!localStorage.getItem("bmjd-customer-shortlist-v1")) localStorage.setItem("bmjd-customer-shortlist-v1",'+json.dumps(seed)+');')
            def observe(page):
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) and not r.url.startswith(f'http://127.0.0.1:{server.server_port}/') else None)
            def ready(page):page.wait_for_function('window.BMJDPortal?.ready===true',timeout=60000)
            def state(page):return page.evaluate('window.BMJDPortal.getState()')
            def query(page,text):
                page.locator('#query').fill(text)
                page.wait_for_function('(q)=>window.BMJDPortal.getState().filter.query===q',arg=text)
            def close(page):
                if page.locator('#detail-panel').evaluate('(e)=>e.open'):page.locator('#close-detail').click()
            def open_job(page,j,industry=''):
                close(page)
                page.locator('#reset-filters').click();query(page,j['code'])
                if industry:page.locator('#industry-filter').select_option(industry)
                page.locator('[data-job="'+j['id']+'"]').click()
                page.wait_for_function('document.getElementById("detail-panel").open')
            page=context.new_page();observe(page);page.goto(url);ready(page)
            check('页面载入9111岗并显示本次主库版本','9,111' in page.locator('#coverage').inner_text() and master['version'] in page.locator('#version-label').inner_text())
            check('桌面保留七层矩阵和12方向分页',state(page)['view']=='matrix' and page.locator('#matrix-head [data-level]').count()==7 and page.locator('#matrix-body tr').count()==12)
            check('待同步新增工具入口禁用',page.locator('#maintenance-pending').is_disabled() and page.locator('a[href="岗位新增工具.html"]').count()==0)
            page.locator('#nav-saved').click()
            check('旧清单按ID恢复显示新代码',state(page)['saved'][0]['id']==hr['id'] and hr['code'] in page.locator('#saved-list').inner_text() and med['code'] in page.locator('#saved-list').inner_text())
            with page.expect_download() as d:page.locator('#export-saved').click()
            file=Path(temp)/d.value.suggested_filename;d.value.save_as(file)
            rows=list(csv.reader(io.StringIO(file.read_text('utf-8-sig'))))
            check('CSV含新代码岗位ID主库版本及准确行业JD',rows[0][-2:]==['岗位ID','主库版本'] and rows[1][0]==hr['code'] and rows[1][-2:]==[hr['id'],master['version']] and rows[2][0]==med['code'] and rows[2][7]==med_jd)
            page.locator('#nav-search').click()
            open_job(page,hr)
            check('HR005详情与主库名称JD完全一致',page.locator('#detail-code').inner_text()==hr['code'] and page.locator('#detail-name').inner_text()==hr['name'] and page.locator('#jd-clauses li').all_text_contents()==clauses(hr['jd']))
            family=page.locator('#matrix-body tr').filter(has=page.locator('[data-job="'+hr['id']+'"]'))
            check('人资系列相邻岗位全部显示HR代码',all(code.startswith('HR') for code in family.locator('.row-code').all_text_contents()))
            page.evaluate('Object.defineProperty(navigator,"clipboard",{value:{writeText:async(value)=>window.__reviewCopied=value},configurable:true})')
            page.locator('#copy-code').click()
            check('复制岗位代码采用校正版',page.evaluate('window.__reviewCopied')==hr['code'])
            page.locator('#compare-detail').click();close(page)
            page.locator('#reset-filters').click();query(page,'AI003')
            check('已停用的人资旧AI代码不再误匹配',state(page)['resultCount']==0)
            open_job(page,it)
            check('信息技术详情已更新为IT',page.locator('#detail-code').inner_text().startswith('IT') and page.locator('#detail-name').inner_text()==it['name'])
            close(page);open_job(page,warehouse)
            check('仓储详情已更新为LO',page.locator('#detail-code').inner_text().startswith('LO') and page.locator('#detail-name').inner_text()==warehouse['name'])
            close(page);open_job(page,med,special_industry)
            check('专业JD按ID挂到新代码而非旧码',page.locator('#detail-code').inner_text()==med['code'] and page.locator('#jd-clauses li').all_text_contents()==clauses(med_jd))
            page.locator('#jd-scope').select_option('')
            check('通用JD切换保留同一新代码',page.locator('#detail-code').inner_text()==med['code'] and page.locator('#jd-clauses li').all_text_contents()==clauses(med['jd']))
            page.locator('#jd-scope').select_option(special_industry);page.locator('#compare-detail').click();close(page)
            page.locator('#start-compare').click()
            check('两岗完整JD对比均使用新代码',page.locator('.comparison-column').count()==2 and page.locator('.comparison-column .row-code').all_text_contents()==[hr['code'],med['code']] and page.locator('.comparison-column').nth(1).locator('li').all_text_contents()==clauses(med_jd))
            page.locator('#compare-back').click()
            open_job(page,by_id[reassigned['current_job_id']])
            check('跨版本同码显示本版正确岗位身份',page.locator('#detail-name').inner_text()==by_id[reassigned['current_job_id']]['name'] and state(page)['selectedId']!=reassigned['previous_job_id'])
            close(page);page.locator('#reset-filters').click()
            hr_function=next(f for f in payload['functions'] if f['name']=='人力资源')
            page.locator('#function-query').fill('人力资源');page.locator('[data-function="'+hr_function['id']+'"]').click()
            check('职能筛选显示60个人资岗位和HR系列',state(page)['resultCount']==60 and all(t.startswith('HR') for t in page.locator('#matrix-body .direction-cell small').all_text_contents()))
            page.locator('#function-query').fill('');page.locator('#reset-filters').click()
            page.locator('#industry-filter').select_option(special_industry);query(page,med['code'])
            ids=page.locator('.job-select').evaluate_all('(es)=>es.map(e=>e.dataset.job)')
            check('行业矩阵相邻岗位不越界',all(special_industry in by_id[i]['industries'] for i in ids))
            page.locator('#reset-filters').click();page.evaluate('document.activeElement?.blur()');page.screenshot(path=str(args.screenshots/'桌面主库复核.png'),full_page=True)
            check('桌面无页面横向溢出',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            context.set_offline(True);open_job(page,hr)
            check('断网后仍可查询新主库并阅读完整JD',page.locator('#detail-code').inner_text()==hr['code'] and page.locator('#jd-clauses li').count()==len(clauses(hr['jd'])))
            close(page);context.set_offline(False)
            mobile=browser.new_context(viewport={'width':390,'height':844});mp=mobile.new_page();observe(mp);mp.goto(url);ready(mp)
            check('手机默认列表且无页面横向溢出',state(mp)['view']=='list' and mp.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            query(mp,hr['code']);mp.locator('[data-job="'+hr['id']+'"]').click()
            check('手机详情显示新代码和准确名称',mp.locator('#detail-code').inner_text()==hr['code'] and mp.locator('#detail-name').inner_text()==hr['name'])
            mp.screenshot(path=str(args.screenshots/'手机主库复核.png'),full_page=True)
            mobile.close()
            file_context=browser.new_context();fp=file_context.new_page()
            try:
                fp.goto(path.resolve().as_uri(),timeout=15000);ready(fp)
                file_check={'passed':True,'scope':'Actual standalone HTML file URL opened in isolated system Chromium.'}
            except Exception as error:
                file_check['reason']=str(error).splitlines()[0][:220]
            file_context.close()
            check('无外部资源请求',not external);check('浏览器无未处理脚本异常',not errors)
            browser.close()
    finally:server.shutdown();server.server_close()
    check('主库及全部行业和UI源码指纹未改变',all(sha(ROOT/name)==digest for name,digest in report['input_sha256'].items()))
    result={'version':report['version'],'master_version':master['version'],'all_passed':all(checks.values()),'passed':len(checks),'checks':checks,'html_sha256':sha(path),'errors':errors,'external_requests':external,'file_url_check':file_check,
      'scope':'Full embedded payload vs corrected master; isolated Chromium desktop1440/mobile390, loopback load, offline queries, ID-based legacy JD/shortlist binding, CSV version metadata; no catalog writes.'}
    (OUT/'浏览器核验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['all_passed','passed','master_version','file_url_check']},ensure_ascii=False))

if __name__=='__main__':main()
