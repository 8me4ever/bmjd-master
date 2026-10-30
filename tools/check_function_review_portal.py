"""Check grouped data projection and real filtering/export in isolated Chromium."""
import argparse,base64,csv,gzip,hashlib,io,json,re,shutil,tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from threading import Thread
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'主库职能序列整合_20261030'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clauses(s):return [re.sub(r'^\s*\d+\s*[、.．)]\s*','',r).strip() for r in s.splitlines() if r.strip()]
def main():
    p=argparse.ArgumentParser();p.add_argument('--screenshots',type=Path,default=Path('/tmp/bmjd-function-review'));args=p.parse_args()
    from playwright.sync_api import sync_playwright
    checks={};errors=[];external=[]
    def check(n,ok):assert ok,n;checks[n]=True;print('PASS '+n,flush=True)
    path=OUT/'主库查岗.html';build=read(OUT/'页面构建核验.json');m=read(OUT/'主库.json');by={j['id']:j for j in m['jobs']}
    html=path.read_text();data=json.loads(gzip.decompress(base64.b64decode(re.search(r'<script id="portal-payload"[^>]*>(.*?)</script>',html,re.S)[1])))
    expected=[]
    for j in m['jobs']:
        expected.append({**{k:j[k] for k in ['id','code','name','level','series_id','series_name','series_prefix','aliases','industries','jd']},'function_id':j['function_group_id'],'function_name':j['function_group_name'],'direction_id':j['function_direction_id'],'direction_name':j['function_direction_name'],'source_function_name':j['function_name']})
    check('全9111岗展示字段与新主库分层投影一致',data['jobs']==expected)
    check('95主序列270方向与主库字典对应',len(data['functions'])==95 and len(data['directions'])==270 and {g['id'] for g in data['functions']}=={g['id'] for g in m['function_groups']})
    check('产品108岗统一PP且标准名称代码唯一',sum(j['function_name']=='产品' for j in data['jobs'])==108 and all(j['code'].startswith('PP') for j in data['jobs'] if j['function_name']=='产品') and len({j['code'] for j in data['jobs']})==len({j['name'] for j in data['jobs']})==9111)
    product=next(g for g in m['function_groups'] if g['name']=='产品');recruit=next(g for g in m['function_groups'] if g['name']=='临床研究');hr=next(g for g in m['function_groups'] if g['name']=='人力资源与人才服务')
    dev=next(d for d in m['function_directions'] if d['group_name']=='产品' and d['source_function_name']=='产品研发')
    ops=next(d for d in m['function_directions'] if d['group_name']=='产品' and d['source_function_name']=='产品运营')
    job=next(j for j in m['jobs'] if j['function_direction_id']==dev['id'] and j['level']==5)
    med=None;sector='';count=0
    for name,jds in data['industryJD'].items():
        child={j['id']:j for j in read(ROOT/'行业专业JD优化_20261029'/name/'岗位主库.json')['jobs']}
        for jid,text in jds.items():
            assert text==child[jid]['jd'] and name in by[jid]['industries'];count+=1
            if med is None and by[jid]['code']!=child[jid]['code']:med=by[jid];sector=name
    check('843条行业JD仍按岗位ID准确关联',count==843 and med is not None)
    class Quiet(SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw):super().__init__(*a,directory=str(OUT),**kw)
        def log_message(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);Thread(target=server.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{server.server_port}/'+quote(path.name)
    args.screenshots.mkdir(parents=True,exist_ok=True);filecheck={'passed':False,'scope':'Managed Chromium file-URL policy; no bypass.'}
    try:
        with tempfile.TemporaryDirectory(prefix='bmjd-families-') as temp,sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
            ctx=browser.new_context(viewport={'width':1440,'height':1040},accept_downloads=True)
            seed=json.dumps([{'id':job['id'],'industry':''}],ensure_ascii=False)
            ctx.add_init_script('if(!localStorage.getItem("bmjd-customer-shortlist-v1"))localStorage.setItem("bmjd-customer-shortlist-v1",'+json.dumps(seed)+')')
            def observe(page):
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) and not r.url.startswith(f'http://127.0.0.1:{server.server_port}/') else None)
            def ready(page):page.wait_for_function('window.BMJDPortal?.ready===true',timeout=60000)
            def state(page):return page.evaluate('window.BMJDPortal.getState()')
            def query(page,text):
                page.locator('#query').fill(text);page.wait_for_function('(q)=>window.BMJDPortal.getState().filter.query===q',arg=text)
            def close(page):
                if page.locator('#detail-panel').evaluate('(e)=>e.open'):page.locator('#close-detail').click()
            def group(page,g):
                close(page);page.locator('#reset-filters').click();page.locator('#function-query').fill(g['name']);page.locator('[data-function="'+g['id']+'"]').click();page.locator('#function-query').fill('')
            def open_job(page,j,industry=''):
                close(page);page.locator('#reset-filters').click();query(page,j['code'])
                if industry:page.locator('#industry-filter').select_option(industry)
                page.locator('[data-job="'+j['id']+'"]').click();page.wait_for_function('document.getElementById("detail-panel").open')
            page=ctx.new_page();observe(page);page.goto(url);ready(page)
            check('页面显示95主序列270专业方向并保留七层矩阵','95 个主序列' in page.locator('#coverage').inner_text() and '270 个专业方向' in page.locator('#coverage').inner_text() and page.locator('#matrix-head [data-level]').count()==7)
            check('页面主库版本正确且新增入口仍禁用',m['version'] in page.locator('#version-label').inner_text() and page.locator('#maintenance-pending').is_disabled())
            group(page,product)
            check('产品主序列108岗无生产计划混入',state(page)['resultCount']==108 and all(c.startswith('PP') for c in page.locator('#matrix-body .row-code').all_text_contents()))
            check('产品主序列仅显示11个相关专业方向',page.locator('#direction-filter option').count()==12)
            page.locator('#direction-filter').select_option(dev['id'])
            check('产品研发10岗可独立筛选且仍为PP',state(page)['resultCount']==10 and state(page)['filter']['directionId']==dev['id'] and all(c.startswith('PP') for c in page.locator('#matrix-body .row-code').all_text_contents()))
            page.locator('#direction-filter').select_option(ops['id'])
            check('切换产品运营38岗不串研发方向',state(page)['resultCount']==38 and all(t=='产品运营' for t in page.locator('#matrix-body .direction-cell>span').all_text_contents()))
            page.locator('#direction-filter').select_option('');page.locator('#function-query').fill('产品项目部')
            check('原部门名仍可定位产品父序列',page.locator('[data-function="'+product['id']+'"]').count()==1)
            page.locator('#function-query').fill('');page.locator('#reset-filters').click();open_job(page,job)
            check('产品新码详情保留原岗位名和完整JD',page.locator('#detail-code').inner_text()==job['code'] and page.locator('#detail-name').inner_text()==job['name'] and page.locator('#jd-clauses li').all_text_contents()==clauses(job['jd']))
            check('详情同时显示产品主序列及研发专业方向','产品 · 产品研发'==page.locator('#detail-meta').inner_text())
            page.locator('#compare-detail').click();close(page);open_job(page,med,sector)
            check('分层后行业专业JD仍挂在准确岗位新代码',page.locator('#jd-clauses li').all_text_contents()==clauses(data['industryJD'][sector][med['id']]) and page.locator('#detail-code').inner_text()==med['code'])
            page.locator('#compare-detail').click();close(page);page.locator('#start-compare').click()
            check('岗位对比同时保留主序列专业方向及完整JD',page.locator('.comparison-column').count()==2 and '产品研发' in page.locator('.comparison-column').first.inner_text() and page.locator('.comparison-column').first.locator('li').count()==len(clauses(job['jd'])))
            page.locator('#compare-back').click();page.locator('#nav-saved').click()
            check('旧清单按岗位ID恢复为新PP编码',job['code'] in page.locator('#saved-list').inner_text() and state(page)['saved'][0]['id']==job['id'])
            with page.expect_download() as d:page.locator('#export-saved').click()
            p=Path(temp)/d.value.suggested_filename;d.value.save_as(p);rows=list(csv.reader(io.StringIO(p.read_text('utf-8-sig'))))
            check('CSV包含主序列专业方向新码ID和本版版本',rows[0][2]=='主职能序列' and rows[0][-3:]==['专业方向','岗位ID','主库版本'] and rows[1][0]==job['code'] and rows[1][2]=='产品' and rows[1][-3:]==[job['function_direction_name'],job['id'],m['version']])
            page.locator('#nav-search').click();group(page,recruit)
            check('受试者招募留在临床研究15岗入口',state(page)['resultCount']==15)
            group(page,hr)
            check('人资65岗入口不吸入临床招募',state(page)['resultCount']==65)
            issue=next(iter(data['jdIssues']));open_job(page,by[issue])
            check('已知JD错配在详情明确提示并保留原稿',page.locator('#jd-review-note').is_visible() and '本轮保留现稿' in page.locator('#jd-review-note').inner_text() and page.locator('#jd-clauses li').all_text_contents()==clauses(by[issue]['jd']))
            close(page);group(page,product);page.locator('#direction-filter').select_option(dev['id']);page.locator('#industry-filter').select_option('地产')
            ids=page.locator('.job-select').evaluate_all('(es)=>es.map(e=>e.dataset.job)')
            check('主序列专业方向和行业共同筛选不越界',all('地产' in by[i]['industries'] and by[i]['function_group_name']=='产品' for i in ids))
            page.locator('#industry-filter').select_option('');group(page,product);page.locator('#function-query').fill('');page.evaluate('document.activeElement?.blur()')
            page.screenshot(path=str(args.screenshots/'产品主序列.png'),full_page=True)
            check('桌面无页面横向溢出',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            ctx.set_offline(True);open_job(page,job)
            check('断网仍可检索新产品代码和完整JD',page.locator('#detail-code').inner_text()==job['code'] and page.locator('#jd-clauses li').count()>0)
            ctx.set_offline(False)
            mobile=browser.new_context(viewport={'width':390,'height':844});mp=mobile.new_page();observe(mp);mp.goto(url);ready(mp)
            check('手机默认列表且无页面横向溢出',state(mp)['view']=='list' and mp.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            query(mp,job['code']);mp.locator('[data-job="'+job['id']+'"]').click()
            check('手机详情展示产品主序列研发方向与新PP码',mp.locator('#detail-code').inner_text()==job['code'] and mp.locator('#detail-meta').inner_text()=='产品 · 产品研发')
            mp.screenshot(path=str(args.screenshots/'手机产品岗位.png'),full_page=True);mobile.close()
            fc=browser.new_context();fp=fc.new_page()
            try:fp.goto(path.resolve().as_uri(),timeout=10000);ready(fp);filecheck={'passed':True,'scope':'Actual file URL opened.'}
            except Exception as e:filecheck['reason']=str(e).splitlines()[0][:220]
            fc.close();check('无外部服务请求',not external);check('无未处理浏览器脚本异常',not errors);browser.close()
    finally:server.shutdown();server.server_close()
    check('构建输入与主库行业来源指纹保持',all(sha(ROOT/n)==h for n,h in build['input_sha256'].items()))
    result={'version':build['version'],'all_passed':True,'passed':len(checks),'checks':checks,'html_sha256':sha(path),'errors':errors,'external_requests':external,'file_url_check':filecheck,
      'scope':'Full 9111-row display projection; isolated Chromium desktop1440/mobile390; group/direction/industry filtering, PP codes, IDs, JD versions, shortlist, CSV, offline; no catalog writes.'}
    (OUT/'页面浏览器核验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'all_passed':True,'passed':len(checks),'file_url_check':filecheck},ensure_ascii=False))
if __name__=='__main__':main()
