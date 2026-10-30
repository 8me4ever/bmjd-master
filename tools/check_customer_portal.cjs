/* Isolated local UI checks: no external services, no source catalog mutations. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),output=path.join(root,'BMJD客户查岗平台_20261030'),review=path.join(root,'.impeccable','review');
const {chromium}=require(process.env.BMJD_TEST_NODE_MODULES?path.join(process.env.BMJD_TEST_NODE_MODULES,'playwright'):'playwright');
const C=require(path.join(root,'customer_portal','portal-core.js'));
const read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8')),hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const report=read('BMJD客户查岗平台_20261030/构建核验.json'),parent=read('岗位JD匹配审查_20261029/岗位JD主库.json'),parentMap=new Map(parent.jobs.map(j=>[j.id,j]));
const specialized=read('行业专业JD优化_20261029/医药/岗位主库.json').jobs.find(j=>j.jd!==parentMap.get(j.id).jd);
const checks={},errors=[],external=[];let browser,server;
function check(name,ok){assert.ok(ok,name);checks[name]=true;console.log('PASS',name);}
async function ready(p){await p.waitForFunction(()=>window.BMJDPortal?.ready===true,null,{timeout:60000});}
async function state(p){return p.evaluate(()=>window.BMJDPortal.getState());}
async function query(p,text){await p.locator('#query').fill(text);await p.waitForFunction(v=>window.BMJDPortal.getState().filter.query===v,text);}
async function openMatch(p){await p.locator('.job-select[data-match="true"]').first().click();}
async function close(p){if(await p.locator('#detail-panel').evaluate(e=>e.open))await p.locator('#close-detail').click();}
async function main(){
 fs.mkdirSync(review,{recursive:true});
 server=http.createServer((req,res)=>{let name;try{name=decodeURIComponent(new URL(req.url,'http://localhost').pathname.slice(1));}catch(_){res.writeHead(400);res.end();return;}if(!['BMJD客户查岗平台.html','岗位新增工具.html'].includes(name)){res.writeHead(404);res.end();return;}res.writeHead(200,{'Content-Type':'text/html;charset=utf-8'});res.end(fs.readFileSync(path.join(output,name)));});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`,url=origin+'/'+encodeURIComponent('BMJD客户查岗平台.html');
 browser=await chromium.launch({headless:true,...(process.env.BMJD_TEST_BROWSER_PATH?{executablePath:process.env.BMJD_TEST_BROWSER_PATH}:{}),args:['--no-sandbox']});
 const observe=p=>{p.on('pageerror',e=>errors.push(String(e)));p.on('request',r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith(origin))external.push(r.url());});};
 const ctx=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true}),page=await ctx.newPage();observe(page);await page.goto(url);await ready(page);
 check('载入9111岗263职能11行业',(await page.locator('#coverage').innerText()).includes('9,111')&&(await page.locator('#coverage').innerText()).includes('263'));
 check('桌面默认七层横向矩阵、每页12方向',(await state(page)).view==='matrix'&&await page.locator('#matrix-head [data-level]').count()===7&&await page.locator('#matrix-body tr').count()===12);
 check('桌面页面无横向溢出',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await query(page,'HR963');check('精确代码只高亮目标且保留同系列相邻岗位',await page.locator('[data-match="true"]').count()===1&&await page.locator('.job-select').count()>1);
 await openMatch(page);check('点击打开准确岗位完整JD',(await page.locator('#detail-name').innerText()).includes('会务经理')&&await page.locator('#detail-panel').evaluate(e=>e.open));
 await page.keyboard.press('Escape');check('Esc关闭并恢复岗位焦点',!(await page.locator('#detail-panel').evaluate(e=>e.open))&&await page.locator('[data-match="true"]').evaluate(e=>e===document.activeElement));
 await page.locator('#reset-filters').click();await page.locator('#function-query').fill('仓储');await page.locator('[data-function]').filter({hasText:'仓储'}).last().click();await page.locator('#level-filter').selectOption('5');
 check('职能层级筛选仅高亮5级，保留邻级对照',await page.locator('[data-match="true"]').count()>0&&await page.locator('[data-match="true"]').evaluateAll(es=>es.every(e=>e.getAttribute('aria-label').includes('5级')))&&await page.locator('[data-match="false"]').count()>0);
 await page.locator('#reset-filters').click();await query(page,specialized.code);await page.locator('#industry-filter').selectOption('医药');
 const contextIds=await page.locator('.job-select').evaluateAll(es=>es.map(e=>e.dataset.job));check('行业筛选严格限制所有相邻岗位',contextIds.every(id=>parentMap.get(id).industries.includes('医药')));
 await openMatch(page);check('专业JD准确对应医药子库',JSON.stringify(await page.locator('#jd-clauses li').allTextContents())===JSON.stringify(C.clauses(specialized.jd)));
 await page.locator('#jd-scope').selectOption('');check('通用JD切换不混入行业稿',JSON.stringify(await page.locator('#jd-clauses li').allTextContents())===JSON.stringify(C.clauses(parentMap.get(specialized.id).jd)));
 await page.locator('#jd-scope').selectOption('医药');await page.locator('#save-job').click();await page.locator('#compare-detail').click();await close(page);
 check('清单与对比保留所选行业职责',(await state(page)).saved[0].industry==='医药'&&(await state(page)).compared[0].industry==='医药');
 await page.locator('#reset-filters').click();const choices=page.locator('[data-compare]:not(:checked)');await choices.nth(0).check();await choices.nth(0).check();check('允许对比三个岗位',(await state(page)).compared.length===3);await choices.nth(0).click();check('第四岗被限制且勾选状态恢复',(await state(page)).compared.length===3&&await page.locator('[data-compare]:checked').count()<=3);
 await page.locator('#start-compare').click();check('三岗完整职责并排呈现',await page.locator('.comparison-column').count()===3&&JSON.stringify(await page.locator('.comparison-column').first().locator('li').allTextContents())===JSON.stringify(C.clauses(specialized.jd)));
 await page.locator('#toast').waitFor({state:'hidden'});await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(review,'desktop-compare.png'),fullPage:true});await page.locator('#compare-back').click();await page.locator('#clear-compare').click();
 await page.reload();await ready(page);check('刷新恢复收藏',await page.locator('#saved-count').innerText()==='1');await page.locator('#nav-saved').click();
 const waitDownload=page.waitForEvent('download');await page.locator('#export-saved').click();const download=await waitDownload,csv=fs.readFileSync(await download.path(),'utf8');check('CSV含完整行业JD和版本',csv.includes(specialized.code)&&csv.includes('医药行业职责')&&C.clauses(specialized.jd).every(t=>csv.includes(t.replace(/"/g,'""'))));
 await page.locator('[data-open-saved]').click();check('收藏可返回准确岗位',await page.locator('#detail-code').innerText()===specialized.code);await close(page);await page.locator('#reset-filters').click();
 await query(page,'BMJD绝不存在的岗位XYZ');check('空结果可恢复',await page.locator('#empty-results').isVisible());await page.locator('#clear-empty').click();await query(page,'<img src=x onerror=alert(1)>');check('恶意输入仅按文字显示',await page.locator('img').count()===0&&await page.locator('#empty-results').isVisible());await page.locator('#clear-empty').click();
 await query(page,'备份恢复');const nameCount=(await state(page)).resultCount;await page.locator('#search-scope').selectOption('all');check('职责搜索需显式开启且扩大匹配范围',(await state(page)).resultCount>nameCount);await page.locator('#reset-filters').click();
 await page.locator('#matrix-scroll').evaluate(e=>e.scrollTop=500);const first=await page.locator('#matrix-body tr').first().getAttribute('data-series');await page.locator('#next-page').click();check('矩阵翻页恢复表顶和键盘焦点',(await state(page)).page===1&&await page.locator('#matrix-body tr').first().getAttribute('data-series')!==first&&await page.locator('#matrix-scroll').evaluate(e=>e.scrollTop===0)&&await page.locator('#results-title').evaluate(e=>e===document.activeElement));await page.locator('#previous-page').click();check('上一页恢复原职责方向',await page.locator('#matrix-body tr').first().getAttribute('data-series')===first);
 await page.locator('#query').blur();await page.keyboard.press('/');check('快捷键定位搜索',await page.locator('#query').evaluate(e=>e===document.activeElement));
 const popupWait=page.waitForEvent('popup');await page.locator('.maintenance').click();const popup=await popupWait;observe(popup);await popup.waitForFunction(()=>window.BMJDTool?.ready===true,null,{timeout:60000});check('独立新增工具正常且含9111岗',await popup.locator('#base-count').innerText()==='9,111');await popup.close();
 await ctx.setOffline(true);await query(page,'GM001');await openMatch(page);check('断网仍可查询完整岗位',await page.locator('#detail-code').innerText()==='GM001');await close(page);await ctx.setOffline(false);await page.locator('#reset-filters').click();
 await page.locator('#function-query').fill('财务');await page.locator('[data-function]').filter({hasText:'财务'}).last().click();await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(review,'desktop.png'),fullPage:true});
 const mobileCtx=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true}),mobile=await mobileCtx.newPage();observe(mobile);await mobile.goto(url);await ready(mobile);
 check('手机默认列表且页面无横向溢出',(await state(mobile)).view==='list'&&await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await mobile.locator('#toggle-filters').click();check('手机筛选可展开',await mobile.locator('#filter-controls').isVisible());await mobile.locator('#toggle-filters').click();await query(mobile,'配货');await mobile.evaluate(()=>scrollTo(0,0));await mobile.screenshot({path:path.join(review,'mobile.png'),fullPage:true});
 await mobile.locator('.job-select').first().click();check('手机详情使用原生全屏对话框',await mobile.locator('#detail-panel').evaluate(e=>e.open&&Math.abs(e.getBoundingClientRect().width-innerWidth)<2));await mobile.screenshot({path:path.join(review,'mobile-detail.png')});await mobile.locator('#detail-back').click();check('手机返回保留搜索',await mobile.locator('.results').isVisible()&&await mobile.locator('#query').inputValue()==='配货');
 await mobile.locator('#view-matrix').click();check('手机矩阵在容器内横向滑动',await mobile.locator('#matrix-scroll').evaluate(e=>e.scrollWidth>e.clientWidth)&&await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 const fallbackCtx=await browser.newContext();await fallbackCtx.addInitScript(()=>{Storage.prototype.setItem=function(){throw new Error('blocked');};});const fallback=await fallbackCtx.newPage();observe(fallback);await fallback.goto(url);await ready(fallback);await fallback.locator('.job-select').first().click();await fallback.locator('#save-job').click();await close(fallback);await fallback.locator('#nav-saved').click();check('禁用存储可保留会话清单并提示导出',(await fallback.locator('#storage-note').innerText()).includes('本次页面')&&await fallback.locator('#saved-count').innerText()==='1');await fallbackCtx.close();
 const fileCtx=await browser.newContext(),filePage=await fileCtx.newPage();await filePage.goto(pathToFileURL(path.join(output,'BMJD客户查岗平台.html')).href);await ready(filePage);await query(filePage,'GM001');await openMatch(filePage);check('本地HTML双击方式可直接查询',await filePage.locator('#detail-code').innerText()==='GM001');await fileCtx.close();
 check('无外部服务请求',external.length===0);check('浏览器无未处理异常',errors.length===0);check('父库与所有行业输入未改',Object.entries(report.input_sha256).every(([p,s])=>hash(path.join(root,p))===s));
 const result={version:report.version,all_passed:true,passed:Object.keys(checks).length,checks,errors,external_requests:external,file_url_check:{passed:true,scope:'Actual standalone HTML opened with Chrome file URL'},html_sha256:hash(path.join(output,'BMJD客户查岗平台.html')),scope:'Isolated Chrome: desktop1440, mobile390; matrix context, dialogs, comparison, offline, export, maintenance; original catalogs unchanged.'};
 fs.writeFileSync(path.join(output,'浏览器核验.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({all_passed:true,passed:result.passed,screenshots:review}));
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));});
