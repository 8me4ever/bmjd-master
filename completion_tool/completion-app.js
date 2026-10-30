(async function () {
  'use strict';
  const C=window.BMJDCompletion,$=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>Number(n).toLocaleString('en-US');
  let db=null,memory=null,state=null,base=null,policy=null,editingId=null,preview=null,toastTimer=null,channel=null,working=false;
  $('job-form').addEventListener('submit',event=>event.preventDefault());
  document.querySelector('main').inert=true;
  function toast(text,error=false) {
    clearTimeout(toastTimer);$('toast').textContent=text;$('toast').classList.toggle('error',error);$('toast').hidden=false;
    toastTimer=setTimeout(()=>$('toast').hidden=true,error?6500:4500);
  }
  function showError(error) {
    const message=error?.message||String(error);$('form-error').textContent=message;$('form-error').hidden=false;toast(message,true);
  }
  function openDatabase() {
    return new Promise((resolve,reject)=>{
      const request=indexedDB.open('bmjd-continuous-completion-v1',1);
      request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains('workspace'))request.result.createObjectStore('workspace');};
      request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
      request.onblocked=()=>reject(new Error('浏览器数据库暂不可用。'));
    });
  }
  function readStore(includeBase=false) {
    if(!db)return Promise.resolve({state:memory.state,...(includeBase?{base:memory.base}:{})});
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('workspace','readonly'),store=tx.objectStore('workspace'),s=store.get('state'),b=includeBase?store.get('base'):null;
      tx.oncomplete=()=>resolve({state:s.result,...(b?{base:b.result}:{})});tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
    });
  }
  function atomic(mutator) {
    if(!db) {
      try {const result=mutator(memory.state);memory.state=result.state;if(result.base)memory.base=result.base;return Promise.resolve(result);}catch(e){return Promise.reject(e);}
    }
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('workspace','readwrite'),store=tx.objectStore('workspace'),request=store.get('state');let result,failure;
      request.onsuccess=()=>{
        try {result=mutator(request.result);store.put(result.state,'state');if(result.base)store.put(result.base,'base');}
        catch(error){failure=error;tx.abort();}
      };
      tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(failure||tx.error);tx.onabort=()=>reject(failure||tx.error||new Error('保存未完成，原数据保持不变。'));
    });
  }
  async function sync() {
    const snapshot=await readStore(false);
    if(!snapshot.state)throw new Error('工作库不存在，请重新打开工具。');
    const changed=!state||state.baseToken!==snapshot.state.baseToken;
    state=snapshot.state;
    if(changed){const fresh=await readStore(true);state=fresh.state;base=fresh.base;}
    render();
  }
  function publish(){if(channel)channel.postMessage({revision:state.revision});}
  function findFunction(){const value=C.clean($('function-input').value);return state.functions.find(f=>f.name===value);}
  function formDraft(){return {functionId:findFunction()?.id,level:Number($('level-input').value),seriesId:$('series-select').value,seriesName:$('series-name').value,name:$('job-name').value,jd:$('job-jd').value,author:$('author').value,industries:[...$('industry-options').querySelectorAll('input:checked')].map(input=>input.value)};}
  function populateSeries(selected) {
    const f=findFunction(),options=f?C.allSeries(state).filter(s=>s.function_id===f.id).sort((a,b)=>a.prefix.localeCompare(b.prefix)):[];
    $('series-select').innerHTML='<option value="__new__">＋ 新建职责系列</option>'+options.map(s=>`<option value="${esc(s.id)}">${esc(s.name)} · ${s.prefix}</option>`).join('');
    if(selected&&options.some(s=>s.id===selected))$('series-select').value=selected;
    $('new-series-field').hidden=$('series-select').value!=='__new__';
  }
  function render() {
    if(!state)return;
    const functionValue=$('function-input').value,selected=$('series-select').value;
    $('function-options').innerHTML=[...state.functions].sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).map(f=>`<option value="${esc(f.name)}"></option>`).join('');
    $('function-input').value=functionValue;populateSeries(selected);
    const selectedIndustries=new Set([...$('industry-options').querySelectorAll('input:checked')].map(i=>i.value));
    $('industry-options').innerHTML=state.industries.map(i=>`<label class="industry-option"><input type="checkbox" value="${esc(i)}" ${selectedIndustries.has(i)?'checked':''}><span>${esc(i)}</span></label>`).join('');
    $('base-count').textContent=fmt(state.baseJobs.length);$('function-count').textContent=fmt(state.functions.length);
    $('active-count').textContent=fmt(state.records.filter(r=>r.status==='active').length);
    const known=C.occupied(state),current=new Set(state.baseJobs.map(j=>j.code));
    $('reserved-count').textContent=fmt([...known].filter(c=>!current.has(c)&&!state.records.some(r=>r.status==='active'&&r.job.code===c)).length);
    $('base-version').textContent=state.baseVersion+' · 离线可用';
    $('storage-status').textContent=db?'本机记录自动保存':'仅本次会话';
    $('storage-warning').hidden=!!db;
    renderRecords();renderPreview();renderNameCheck();renderReferences();updateJDCount();
  }
  function renderPreview() {
    const draft=formDraft(),isNew=draft.seriesId==='__new__';$('new-series-field').hidden=!isNew;
    let prefix=null,code=null,error=null;
    if(editingId) {
      const record=state.records.find(r=>r.job.id===editingId);
      if(!record||record.status!=='active'){resetForm();toast('该记录已在另一窗口更新，表单已退出编辑。',true);return;}
      code=record.job.code;prefix=record.job.series_prefix;preview={code,prefix};$('suggestion-label').textContent='原码保持';
      $('allocation-note').textContent='编辑仅更新本次新增的名称、适用行业和JD，岗位代码及系列保持。';
    } else {
      $('suggestion-label').textContent='可用建议码';
      try {
        if(isNew&&C.key(draft.seriesName)) {
          const duplicate=C.allSeries(state).find(s=>s.function_id===draft.functionId&&C.key(s.name)===C.key(draft.seriesName));
          if(duplicate)throw new Error('已有同名系列 '+duplicate.prefix+'，请选择已有职责系列。');
        }
        preview=C.allocate(state,draft);code=preview.code;prefix=preview.prefix;
        $('allocation-note').textContent=isNew?`将为本职能新建 ${prefix} 系列，已排除全库与历史占用；保存后正式登记。`:`${prefix} 系列的${draft.level}级位置可用；保存时会再次检查。`;
      } catch(e) {
        preview=null;error=e.message;
        const series=C.allSeries(state).find(s=>s.id===draft.seriesId);prefix=series?.prefix||null;
        $('allocation-note').textContent=error;
      }
    }
    $('suggested-code').textContent=code?code.slice(0,2)+' '+code.slice(2,4)+' '+code.slice(4):'— — — — —';
    $('suggested-code').dataset.code=code||'';$('suggested-code').classList.toggle('invalid',!code);
    $('slot-prefix').textContent=prefix||'尚未选择';$('save-job').disabled=working||!preview;
    const used=C.occupied(state),jobs=C.allJobs(state,true);
    $('series-slots').innerHTML=Array.from({length:7},(_,i)=>{
      const level=i+1,slot=prefix?prefix+level:null,job=jobs.find(j=>j.code===slot);
      const record=state.records.find(r=>r.job.code===slot),blocked=slot&&used.has(slot),candidate=slot===code;
      const label=!slot?'—':record?.status==='withdrawn'?'保留':blocked?(job?'占用':'历史'):'空闲';
      const cls=candidate?'candidate':blocked?(job&&record?.status!=='withdrawn'?'occupied':'history'):'';
      const title=job?job.name:slot?`${slot} · ${label}`:'请选择职能';
      return `<div class="slot ${cls}" title="${esc(title)}"><strong>${level}</strong><span>${label}</span></div>`;
    }).join('');
  }
  function renderNameCheck() {
    const matches=C.findNames(state,$('job-name').value,editingId);
    $('name-conflict').hidden=!matches.length;
    $('name-conflict').innerHTML=matches.length?'该名称已用于现有岗位或历史别名，请先核对：'+matches.slice(0,5).map(j=>`<button type="button" data-detail="${esc(j.id)}">${esc(j.code)} · ${esc(j.name)}</button>`).join(''):'';
  }
  function updateJDCount() {
    const count=$('job-jd').value.split(/\r?\n/).filter(t=>t.trim()).length;$('jd-count').textContent=count+' / 4—5条';
    $('jd-count').style.color=[4,5].includes(count)?'#4a9f85':'';
  }
  function renderReferences() {
    const raw=$('lookup').value.trim(),query=C.key(raw),f=findFunction();
    let jobs=C.allJobs(state);
    if(query)jobs=jobs.filter(j=>[j.code,j.name,...(j.aliases||[])].some(t=>C.key(t).includes(query)));
    else if(f)jobs=jobs.filter(j=>j.function_id===f.id);
    jobs.sort((a,b)=>a.code.localeCompare(b.code));
    $('reference-list').innerHTML=jobs.length?jobs.slice(0,8).map(j=>`<button class="reference-item" data-detail="${esc(j.id)}" type="button"><span class="reference-code">${esc(j.code)}</span><span><span class="reference-name">${esc(j.name)}</span><span class="reference-sub">${esc(j.function_name)} / ${esc(j.series_name)}</span></span></button>`).join(''):'<p class="reference-empty">没有匹配岗位。仍建议核对专业方向，避免仅换名称重复建岗。</p>';
  }
  function renderRecords() {
    const filter=$('record-filter').value,records=state.records.filter(r=>filter==='all'||r.status===filter);
    $('record-total').textContent=state.records.length;
    $('records-body').innerHTML=records.length?[...records].reverse().map(r=>{
      const j=r.job,label={active:'活动新增',withdrawn:'已撤回',integrated:'已并入基库'}[r.status];
      const actions=r.status==='active'?`<button class="table-action" data-edit="${esc(j.id)}">编辑</button><button class="table-action withdraw" data-status="withdrawn" data-id="${esc(j.id)}">撤回</button>`:r.status==='withdrawn'?`<button class="table-action" data-status="active" data-id="${esc(j.id)}">恢复原码</button>`:'';
      return `<tr><td><span class="reference-code">${esc(j.code)}</span></td><td><span class="job-label">${esc(j.name)}</span><span class="job-function">${esc(j.function_name)}</span></td><td>${esc(j.series_name)}</td><td>${esc(j.level)}级</td><td><span class="record-status ${r.status}">${label}</span></td><td><button class="table-action" data-detail="${esc(j.id)}">JD</button>${actions}</td></tr>`;
    }).join(''):'<tr><td colspan="6" class="empty">'+(state.records.length?'当前状态下没有记录。':'还没有新增岗位，从上方表单开始补全。')+'</td></tr>';
    $('export-csv').disabled=!state.records.some(r=>r.status==='active');
  }
  function resetForm() {
    editingId=null;$('editing-label').hidden=true;$('save-job').textContent='＋ 保存新增岗位';
    for(const id of ['function-input','series-select','level-input','author'])$(id).disabled=false;
    for(const id of ['job-name','job-jd','series-name'])$(id).value='';
    $('series-select').value='__new__';$('form-error').hidden=true;$('name-conflict').hidden=true;
    if(state){populateSeries();renderPreview();updateJDCount();}
  }
  async function submit(event) {
    event.preventDefault();if(working)return;
    const draft=formDraft(),oldSuggestion=preview?.code;working=true;$('form-error').hidden=true;$('save-job').disabled=true;
    try {
      const result=await atomic(current=>editingId?C.edit(current,editingId,draft):C.add(current,draft));
      const wasEditing=!!editingId;await sync();resetForm();publish();
      toast(wasEditing?`已保存 ${result.record.job.code} 的修改。`:`已登记 ${result.record.job.code} · ${result.record.job.name}`+(oldSuggestion&&oldSuggestion!==result.record.job.code?'；已按最新占用重新配码。':''));
    } catch(e){showError(e);}finally{working=false;renderPreview();}
  }
  function fullJob(id) {
    const r=state.records.find(r=>r.job.id===id&&r.status!=='integrated');
    return r?r.job:base.jobs.find(j=>j.id===id);
  }
  function showDetail(id) {
    const j=fullJob(id);if(!j)return;
    $('detail-code').textContent=j.code;$('detail-name').textContent=j.name;
    $('detail-meta').textContent=j.function_name+' / '+j.series_name+' · '+j.level+'级 · '+j.industries.join('、');
    $('detail-clauses').replaceChildren(...j.jd_clauses.map(c=>{const li=document.createElement('li');li.textContent=c.text;return li;}));
    if(!$('job-dialog').open)$('job-dialog').showModal();
  }
  function editRecord(id) {
    const record=state.records.find(r=>r.job.id===id&&r.status==='active');if(!record)return;
    const j=record.job;editingId=id;$('editing-label').hidden=false;$('save-job').textContent='保存本次修改';
    $('function-input').value=j.function_name;$('level-input').value=String(j.level);populateSeries(j.series_id);
    $('job-name').value=j.name;$('job-jd').value=j.jd;$('author').value=j.manual_entry?.author||'';
    for(const input of $('industry-options').querySelectorAll('input'))input.checked=j.industries.includes(input.value);
    for(const control of ['function-input','series-select','level-input','author'])$(control).disabled=true;
    $('form-error').hidden=true;renderPreview();renderNameCheck();updateJDCount();
    $('form-heading').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});$('job-name').focus({preventScroll:true});
  }
  function download(name,text,type) {
    const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
  }
  const dateStamp=()=>new Date().toISOString().replace(/[^0-9]/g,'').slice(0,14);
  async function exportFile(kind) {
    if(working)return;working=true;
    try {
      const snapshot=await readStore(true);state=snapshot.state;base=snapshot.base;
      if(kind==='full')download('BMJD_完整主库_'+dateStamp()+'.json',JSON.stringify(C.exportMaster(base,state),null,2),'application/json;charset=utf-8');
      else if(kind==='delta')download('BMJD_新增增量_'+dateStamp()+'.json',JSON.stringify(C.exportDelta(state),null,2),'application/json;charset=utf-8');
      else {const jobs=state.records.filter(r=>r.status==='active').map(r=>r.job);C.allJobs(state);if(!jobs.length)throw new Error('尚无活动新增岗位。');download('BMJD_新增岗位_'+dateStamp()+'.csv',C.csv(jobs),'text/csv;charset=utf-8');}
      toast('已生成下载文件，请妥善保存。');
    } catch(e){showError(e);}finally{working=false;renderPreview();}
  }
  async function importFile(file) {
    if(!file||working)return;working=true;$('load-message').textContent='正在检查并导入JSON，已有数据不会在冲突时被部分覆盖。';$('load-message').hidden=false;
    try {
      if(file.size>80*1024*1024)throw new Error('文件超过80MiB，请选择主库或本工具导出的增量JSON。');
      const data=JSON.parse((await file.text()).replace(/^\uFEFF/,''));
      let result;
      if(data.type==='increment')result=await atomic(current=>C.mergeDelta(current,data));
      else result=await atomic(current=>C.importMaster(current,data,policy));
      await sync();resetForm();publish();
      toast(data.type==='increment'?`合并完成：新增登记${result.added}条，已存在${result.skipped}条。`:`已导入${fmt(state.baseJobs.length)}岗主库，未并入的本机记录继续保留。`);
    } catch(e){showError(e);}finally{working=false;$('load-message').hidden=true;$('import-file').value='';renderPreview();}
  }
  function bindEvents() {
    $('job-form').addEventListener('submit',submit);
    $('function-input').addEventListener('input',()=>{populateSeries();renderPreview();renderReferences();});
    $('series-select').addEventListener('change',renderPreview);$('series-name').addEventListener('input',renderPreview);$('level-input').addEventListener('change',renderPreview);
    $('job-name').addEventListener('input',renderNameCheck);$('job-jd').addEventListener('input',updateJDCount);$('lookup').addEventListener('input',renderReferences);
    $('record-filter').addEventListener('change',renderRecords);$('reset-form').addEventListener('click',resetForm);
    $('select-industries').addEventListener('click',()=>{const inputs=[...$('industry-options').querySelectorAll('input')],all=inputs.every(i=>i.checked);for(const i of inputs)i.checked=!all;$('select-industries').textContent=all?'全选11行业':'取消全选';});
    $('help').addEventListener('click',()=>$('help-dialog').showModal());
    document.addEventListener('click',async event=>{
      const detail=event.target.closest('[data-detail]');if(detail){showDetail(detail.dataset.detail);return;}
      const edit=event.target.closest('[data-edit]');if(edit){editRecord(edit.dataset.edit);return;}
      const status=event.target.closest('[data-status]');
      if(status&&!working){working=true;try{const result=await atomic(current=>C.setStatus(current,status.dataset.id,status.dataset.status));await sync();publish();toast(result.record.status==='withdrawn'?`${result.record.job.code}已撤回，代码仍保留。`:`已恢复 ${result.record.job.code}。`);}catch(e){showError(e);}finally{working=false;renderPreview();}}
      if(event.target.closest('.close-dialog'))event.target.closest('dialog').close();
    });
    for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
    $('export-full').addEventListener('click',()=>exportFile('full'));$('export-delta').addEventListener('click',()=>exportFile('delta'));$('export-csv').addEventListener('click',()=>exportFile('csv'));
    $('import-json').addEventListener('click',()=>$('import-file').click());$('import-file').addEventListener('change',event=>importFile(event.target.files[0]));
    window.addEventListener('focus',()=>{if(!working)sync().catch(e=>toast(e.message,true));});
    if('BroadcastChannel' in window){channel=new BroadcastChannel('bmjd-completion-v1');channel.onmessage=()=>{sync().catch(e=>toast(e.message,true));};}
  }
  try {
    if(!('DecompressionStream' in window))throw new Error('浏览器不支持离线主库解压，请用最新版Chrome、Edge或Safari打开。');
    const packed=$('bmjd-payload').textContent.trim(),binary=atob(packed),bytes=new Uint8Array(binary.length);
    for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
    const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    const bundle=JSON.parse(await new Response(stream).text());policy=bundle.policy;
    C.validateMaster(bundle.master);
    try {db=await openDatabase();db.onversionchange=()=>db.close();}
    catch(error){db=null;}
    if(db) {
      const initial=await readStore(true);
      if(!initial.state){const first=C.makeState(bundle.master,policy);await atomic(current=>current?{state:current}:{state:first,base:bundle.master});}
      else {if(initial.state.schema!==C.SCHEMA)throw new Error('本机记录版本不兼容，请保留浏览器数据并联系维护者升级。');C.assertRegistry(initial.state);}
      const initialState=await readStore(true);state=initialState.state;base=initialState.base;C.validateMaster(base);
    } else {state=C.makeState(bundle.master,policy);base=bundle.master;memory={state,base};}
    bindEvents();render();$('load-message').hidden=true;document.querySelector('main').inert=false;
    window.BMJDTool={ready:true,getState:async()=>JSON.parse(JSON.stringify((await readStore(false)).state))};
  } catch(error) {
    $('load-message').textContent='载入失败：'+error.message;$('load-message').classList.add('warning');$('storage-status').textContent='未载入';
    window.BMJDTool={ready:false,error:error.message};
  }
})();
