"""Verify full, unpaginated result DOMs and the customer feature boundary."""
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
import time
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from threading import Thread
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'BMJD内外双版_20261030';MASTER=ROOT/'原版分类编码收口_20261030/主库.json';CHILDREN=ROOT/'行业子库同步_20261030'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def payload(p):return json.loads(gzip.decompress(base64.b64decode(re.search(r'<script id="portal-payload"[^>]*>(.*?)</script>',p.read_text('utf-8'),re.S)[1])))
def clauses(t):return [re.sub(r'^\s*\d+\s*[、.．)]\s*','',s).strip() for s in t.splitlines() if s.strip()]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--screenshots',type=Path,default=Path('/tmp/bmjd-audience'));args=parser.parse_args();args.screenshots.mkdir(exist_ok=True,parents=True)
    from playwright.sync_api import sync_playwright
    build=read(OUT/'构建核验.json');m=read(MASTER);master_by={j['id']:j for j in m['jobs']};mapping={r['job_id']:r for r in read(MASTER.parent/'逐岗原版代码对照.json')}
    overview=read(CHILDREN/'子库总览.json');children={r['industry']:read(CHILDREN/r['industry']/'岗位主库.json') for r in overview['industries']}
    checks={};errors=[];external=[];metrics={}
    def check(n,ok):assert ok,n;checks[n]=True;print('PASS '+n,flush=True)
    datasets={}
    for audience,r in build['profiles'].items():
        p=OUT/r['file'];data=payload(p);datasets[audience]=data
        check(audience+' 同版9111岗ID名称五位码及JD全量一致',len(data['jobs'])==9111 and all(all(j[k]==master_by[j['id']][k] for k in ['id','code','name','level','series_id','series_prefix','industries','jd']) for j in data['jobs']) and data['master_version']==m['version'])
        by={j['id']:j for j in data['jobs']}
        check(audience+' 全部19018行业归属及843行业JD与已同步子库一致',sum(len(c['jobs']) for c in children.values())==19018 and sum(len(v) for v in data['industryJD'].values())==843 and all({j['id'] for j in child['jobs']}=={j['id'] for j in data['jobs'] if industry in j['industries']} and all(data['industryJD'][industry].get(j['id'],by[j['id']]['jd'])==j['jd'] for j in child['jobs']) for industry,child in children.items()))
    check('客户载荷不包含原码审查来源和内部修订说明',all(not({'original_codes','original_functions','original_systems','original_specialties','extension_of','code_reason','source_ids'}&set(j)) for j in datasets['client']['jobs']) and 'jdIssues' not in datasets['client'])
    class Quiet(SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw):super().__init__(*a,directory=str(OUT),**kw)
        def log_message(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);Thread(target=server.serve_forever,daemon=True).start();origin=f'http://127.0.0.1:{server.server_port}/'
    try:
        with sync_playwright() as pw,tempfile.TemporaryDirectory(prefix='bmjd-audience-') as temp:
            browser=pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
            for audience,r in build['profiles'].items():
                data=datasets[audience];by={j['id']:j for j in data['jobs']};ctx=browser.new_context(viewport={'width':1440,'height':1040},accept_downloads=True);ctx.set_default_timeout(45000)
                if audience=='client':ctx.add_init_script("window.__storageReads=0;Object.defineProperty(window,'localStorage',{get(){window.__storageReads++;throw Error('Customer storage access');}})")
                else:ctx.add_init_script("localStorage.setItem('bmjd-customer-shortlist-v1',"+json.dumps(json.dumps([{'id':data['jobs'][0]['id'],'industry':''}]))+")")
                page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda req:external.append(req.url) if req.url.startswith(('http:','https:')) and not req.url.startswith(origin) else None)
                started=time.perf_counter();page.goto(origin+quote(r['file']));page.wait_for_function('window.BMJDPortal?.ready===true',timeout=120000);metrics[audience]={'desktop_initial_seconds':round(time.perf_counter()-started,3)}
                def state():return page.evaluate('window.BMJDPortal.getState()')
                def close():
                    if page.locator('#detail-panel').evaluate('(e)=>e.open'):page.locator('#close-detail').click()
                def query(text):
                    page.locator('#query').fill(text);page.wait_for_function('(q)=>window.BMJDPortal.getState().filter.query===q',arg=text,timeout=60000)
                def open_job(j):
                    page.locator('[data-job="'+j['id']+'"]').click();page.wait_for_function('document.getElementById("detail-panel").open')
                def detail(j,text):return page.locator('#detail-code').inner_text()==j['code'] and page.locator('#detail-name').inner_text()==j['name'] and page.locator('#jd-clauses li').all_text_contents()==clauses(text)
                check(audience+' 不存在上一页下一页加载更多或分页控件',page.locator('.pagination,#previous-page,#next-page,#page-label,[data-load-more]').count()==0 and state()['resultCount']==9111)
                check(audience+' 矩阵3077方向及9111岗位一次全部生成',page.locator('#matrix-body>tr').count()==3077 and page.locator('#matrix-body [data-job]').count()==9111)
                last=page.locator('#matrix-body [data-job]').last;j=by[last.get_attribute('data-job')];last.click();check(audience+' 矩阵末尾岗位可直接滚动打开完整JD',detail(j,j['jd']));close()
                page.locator('#view-list').click()
                check(audience+' 列表单页实际包含全部9111岗无截断',page.locator('#job-list [data-job]').count()==9111 and set(page.locator('#job-list [data-job]').evaluate_all('(es)=>es.map(e=>e.dataset.job)'))==set(by))
                last=page.locator('#job-list [data-job]').last;j=by[last.get_attribute('data-job')];last.click();check(audience+' 列表末尾岗位可直接滚动打开完整JD',detail(j,j['jd']));close()
                if audience=='client':
                    check('客户页面保留矩阵且无内部维护功能',page.locator('#nav-saved,#saved-screen,#compare-screen,#compare-detail,#save-job,#export-saved,#copy-code,#copy-jd,#code-basis,#maintenance-pending,[data-compare]').count()==0 and page.locator('#view-matrix').count()==1)
                    check('客户JS仅提供搜索矩阵与JD能力且不读取本地清单',page.evaluate('Object.keys(window.BMJDPortalCore).sort()')==sorted(['key','prepare','search','jdFor','clauses','levels','matrixRows']) and page.evaluate('window.__storageReads')==0)
                else:
                    check('内部保留对比导出清单编码依据并承接旧清单',page.locator('#compare-detail,#export-saved,#code-basis').count()==3 and state()['saved'][0]['id']==data['jobs'][0]['id'])
                    page.evaluate('(d)=>window.__audit=window.BMJDPortalCore.prepare(d)',data)
                for industry,child in children.items():
                    page.locator('#industry-filter').select_option(industry)
                    actual=page.locator('#job-list [data-job]').evaluate_all('(es)=>es.map(e=>e.dataset.job)')
                    check(audience+' '+industry+'全部匹配岗位在一页显示',state()['resultCount']==len(child['jobs']) and len(actual)==len(child['jobs']) and set(actual)=={j['id'] for j in child['jobs']})
                    special=next(j for j in child['jobs'] if j['jd']!=master_by[j['id']]['jd']);open_job(special)
                    check(audience+' '+industry+'当前代码和专业JD正确',detail(special,special['jd']))
                    if audience=='internal' and industry=='高科技':page.locator('#save-job').click()
                    close()
                    if audience=='internal':
                        text=page.evaluate('(industry)=>{const d=window.__audit;return BMJDPortalCore.csv(d,d.jobs.filter(j=>j.industries.includes(industry)).map(j=>({id:j.id,industry})));}',industry)
                        rows=list(csv.reader(io.StringIO(text.lstrip('\ufeff'))));lookup={j['id']:j for j in child['jobs']}
                        check('内部 '+industry+'全量导出16列当前身份JD及子库版本正确',len(rows)==len(child['jobs'])+1 and all(len(row)==16 and row[0]==lookup[row[10]]['code'] and row[1]==lookup[row[10]]['name'] and row[9]==lookup[row[10]]['jd'] and row[11]==m['version'] and row[15]==data['industry_version'] for row in rows[1:]))
                if audience=='internal':
                    page.locator('[data-compare]').nth(0).check();page.locator('[data-compare]').nth(1).check();page.locator('#start-compare').click();check('内部并排职责对比可用',page.locator('.comparison-column').count()==2);page.locator('#compare-back').click()
                    page.locator('#nav-saved').click()
                    with page.expect_download() as got:page.locator('#export-saved').click()
                    p=Path(temp)/got.value.suggested_filename;got.value.save_as(p);rows=list(csv.reader(io.StringIO(p.read_text('utf-8-sig'))))
                    check('内部清单实际下载包含通用与行业JD及版本',len(rows)==3 and len(rows[0])==16 and rows[1][11]==m['version'] and rows[2][15]==data['industry_version'])
                    page.locator('#nav-search').click()
                page.locator('#industry-filter').select_option('');query('zzzz-no-matching-bmjd');check(audience+' 空结果及重置状态正常',state()['resultCount']==0 and page.locator('#empty-results').is_visible())
                target=next(j for j in data['jobs'] if j['code'].startswith('RX'));query(target['code'].lower());open_job(target);check(audience+' 扩展五位码精确检索及通用JD正确',detail(target,target['jd']))
                if audience=='internal':
                    page.locator('#code-basis').evaluate('(e)=>e.open=true');check('内部原版分类代码依据完整保留',page.locator('#basis-codes').inner_text()=='、'.join(mapping[target['id']]['original_codes']))
                close();ctx.set_offline(True);query(data['jobs'][0]['code']);open_job(data['jobs'][0]);check(audience+' 断网后仍可查询及查看JD',detail(data['jobs'][0],data['jobs'][0]['jd']));close();ctx.set_offline(False)
                query('产品')
                if audience=='client':page.locator('#view-matrix').click()
                page.screenshot(path=str(args.screenshots/(audience+'-desktop.png')),full_page=True)
                check(audience+' 桌面无横向溢出',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                ctx.close()
                mobile=browser.new_context(viewport={'width':390,'height':844});mobile.set_default_timeout(45000);mp=mobile.new_page();mp.on('pageerror',lambda e:errors.append(str(e)));mp.goto(origin+quote(r['file']));mp.wait_for_function('window.BMJDPortal?.ready===true',timeout=120000)
                check(audience+' 手机默认列表也完整显示9111岗',mp.locator('#job-list [data-job]').count()==9111 and mp.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                mp.locator('#query').fill(target['code']);mp.wait_for_function('(q)=>BMJDPortal.getState().filter.query===q',arg=target['code']);mp.locator('[data-job="'+target['id']+'"]').click()
                check(audience+' 手机职责详情完整且无横向溢出',mp.locator('#detail-code').inner_text()==target['code'] and mp.locator('#jd-clauses li').all_text_contents()==clauses(target['jd']) and mp.locator('#detail-panel').evaluate('(e)=>e.scrollWidth<=e.clientWidth'))
                mp.screenshot(path=str(args.screenshots/(audience+'-mobile.png')),full_page=True);mobile.close()
            browser.close()
    finally:server.shutdown();server.server_close()
    check('无浏览器脚本错误和外部服务请求',not errors and not external)
    check('输入主库子库及冻结页面指纹保持',all(sha(ROOT/p)==h for p,h in build['input_sha256'].items()))
    result={'version':build['version'],'all_passed':True,'passed':len(checks),'checks':checks,'metrics':metrics,'errors':errors,'external_requests':external,
      'html_sha256':{a:sha(OUT/r['file']) for a,r in build['profiles'].items()},
      'scope':'Both complete 9111-job DOMs and final-row access; all 11 industry ranges and JDs; internal CSV/compare/saved lists; customer feature/data minimization; desktop/mobile/offline. Local HTTP used because managed Chromium blocks file URLs.'}
    (OUT/'浏览器核验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({'all_passed':True,'passed':len(checks),'metrics':metrics},ensure_ascii=False))


if __name__=='__main__':main()
