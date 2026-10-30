(async function () {
  'use strict';
  const C=window.BMJDPortalCore,$=id=>document.getElementById(id),fmt=n=>n.toLocaleString('en-US');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let data,matches=[],selectedId='',scope='',timer;
  const filter={query:'',industry:'',functionId:'',directionId:'',level:'',searchScope:'name'};
  window.BMJDPortal={ready:false};
  function closeDetail(){if($('detail-panel').open)$('detail-panel').close();document.querySelector('[data-job="'+CSS.escape(selectedId)+'"]')?.focus({preventScroll:true});}
  function renderFunctions(){
    const counts=new Map();for(const j of data.jobs)if((!filter.industry||j.industries.includes(filter.industry))&&(!filter.level||j.level===Number(filter.level)))counts.set(j.function_id,(counts.get(j.function_id)||0)+1);
    const q=C.key($('function-query').value),available=data.functions.filter(f=>counts.has(f.id)||f.id===filter.functionId);
    $('function-total').textContent=available.length+'类';
    $('function-list').innerHTML=`<button class="function-button ${!filter.functionId?'active':''}" data-function=""><span>全部职能</span><span>${fmt([...counts.values()].reduce((a,b)=>a+b,0))}</span></button>`+available.filter(f=>!q||C.key(f.name+' '+data.directions.filter(d=>d.function_id===f.id).map(d=>d.name).join(' ')).includes(q)).map(f=>`<button class="function-button ${f.id===filter.functionId?'active':''}" data-function="${esc(f.id)}"><span>${esc(f.name)}</span><span>${fmt(counts.get(f.id)||0)}</span></button>`).join('');
  }
  function renderDirections(){
    const ids=new Set(data.jobs.filter(j=>(!filter.functionId||j.function_id===filter.functionId)&&(!filter.industry||j.industries.includes(filter.industry))).map(j=>j.direction_id));
    const ds=filter.functionId?data.directions.filter(d=>d.function_id===filter.functionId&&ids.has(d.id)):[];
    if(!ds.some(d=>d.id===filter.directionId))filter.directionId='';
    $('direction-filter').disabled=!filter.functionId;$('direction-filter').innerHTML=`<option value="">${filter.functionId?'全部专业方向':'先选择职能分类'}</option>`+ds.map(d=>`<option value="${esc(d.id)}">${esc(d.name)}</option>`).join('');$('direction-filter').value=filter.directionId;
  }
  function renderResults(){
    matches=C.search(data,filter);
    $('results-title').textContent=filter.functionId?data.functions.find(f=>f.id===filter.functionId).name+' · 岗位列表':'岗位列表';
    $('result-count').textContent=`全部显示 ${fmt(matches.length)} 个岗位${filter.industry?' · '+filter.industry:''}`;
    $('job-list').innerHTML=matches.map(j=>`<article class="job-row"><button class="job-select" data-job="${esc(j.id)}" aria-haspopup="dialog"><span class="row-top"><span class="row-code">${esc(j.code)}</span><span class="row-level">${j.level}级</span></span><strong class="row-name">${esc(j.name)}</strong><span class="row-sub">${esc(j.function_name)} · ${esc(j.direction_name)} · ${esc(j.series_name)}</span><span class="row-action">查看职责 ›</span></button></article>`).join('');
    $('empty-results').hidden=matches.length>0;renderFunctions();$('job-list').scrollTop=0;
  }
  function renderDetail(){
    const j=data.byId.get(selectedId);if(!j)return;
    $('detail-code').textContent=j.code;$('detail-name').textContent=j.name;$('detail-meta').textContent=j.function_name+' · '+j.direction_name;
    $('detail-series').textContent=j.series_name;$('detail-level').textContent=j.level+'级';$('detail-industries').innerHTML=j.industries.map(i=>`<span>${esc(i)}</span>`).join('');
    $('jd-scope').innerHTML='<option value="">通用岗位职责</option>'+j.industries.map(i=>`<option value="${esc(i)}">${esc(i)}行业职责</option>`).join('');$('jd-scope').value=scope;
    const v=C.jdFor(data,j,scope);$('scope-note').textContent=!scope?'通用岗位职责':v.specialized?scope+'行业岗位职责':scope+'行业沿用通用职责';
    $('jd-clauses').innerHTML=C.clauses(v.text).map(t=>`<li>${esc(t)}</li>`).join('');$('jd-notice').hidden=!data.jdNotices[j.id];$('jd-notice').textContent=data.jdNotices[j.id]||'';
  }
  function selectJob(id){selectedId=id;scope=filter.industry;renderDetail();$('detail-panel').showModal();$('detail-panel').scrollTop=0;$('detail-name').focus({preventScroll:true});}
  function reset(){clearTimeout(timer);closeDetail();Object.assign(filter,{query:'',industry:'',functionId:'',directionId:'',level:'',searchScope:'name'});$('query').value='';$('industry-filter').value='';$('level-filter').value='';$('search-scope').value='name';$('function-query').value='';renderDirections();renderResults();}
  try{
    $('retry-load').addEventListener('click',()=>location.reload());
    if(typeof DecompressionStream==='undefined')throw new Error('请使用较新的Chrome、Edge或Safari打开此文件。');
    await new Promise(resolve=>requestAnimationFrame(resolve));
    const bytes=Uint8Array.from(atob($('portal-payload').textContent.trim()),c=>c.charCodeAt(0));data=C.prepare(JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text()));
    $('coverage').textContent=fmt(data.jobs.length)+' 个标准岗位';$('industry-filter').innerHTML+=data.industries.map(i=>`<option>${esc(i)}</option>`).join('');
    $('query').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{closeDetail();filter.query=$('query').value;renderResults();},150);});
    for(const [id,k] of [['industry-filter','industry'],['level-filter','level'],['direction-filter','directionId'],['search-scope','searchScope']])$(id).addEventListener('change',()=>{closeDetail();filter[k]=$(id).value;if(k==='industry')renderDirections();renderResults();});
    $('function-query').addEventListener('input',renderFunctions);$('function-list').addEventListener('click',e=>{const b=e.target.closest('[data-function]');if(!b)return;closeDetail();filter.functionId=b.dataset.function;filter.directionId='';renderDirections();renderResults();});
    $('job-list').addEventListener('click',e=>{const b=e.target.closest('[data-job]');if(b)selectJob(b.dataset.job);});
    $('jd-scope').addEventListener('change',()=>{scope=$('jd-scope').value;renderDetail();});$('close-detail').addEventListener('click',closeDetail);$('detail-back').addEventListener('click',closeDetail);$('detail-panel').addEventListener('cancel',e=>{e.preventDefault();closeDetail();});
    $('reset-filters').addEventListener('click',reset);$('clear-empty').addEventListener('click',reset);$('brand-home').addEventListener('click',e=>{e.preventDefault();reset();});
    $('toggle-filters').addEventListener('click',()=>{$('toggle-filters').setAttribute('aria-expanded',String($('filter-controls').classList.toggle('open')));});
    document.addEventListener('keydown',e=>{if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName)&&!$('detail-panel').open){e.preventDefault();$('query').focus();}});
    renderDirections();renderResults();$('loading').hidden=true;$('workspace').hidden=false;
    window.BMJDPortal={ready:true,getState:()=>({selectedId,scope,resultCount:matches.length,view:'list',filter:{...filter}})};
  }catch(error){$('loading').hidden=true;$('load-error').hidden=false;$('error-message').textContent=error?.message||'请重新下载完整文件后打开。';}
})();
