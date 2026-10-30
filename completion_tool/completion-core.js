/* BMJD allocation and append-only catalog logic. No DOM or storage dependency. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BMJDCompletion = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const SCHEMA = 'BMJD-COMPLETION-1';
  const CODE = /^[A-Z]{2}[0-9]{2}[1-7]$/;
  const PREFIX = /^[A-Z]{2}[0-9]{2}$/;
  const clone = value => JSON.parse(JSON.stringify(value));
  const key = text => String(text || '').normalize('NFKC').replace(/[\s\p{Cf}]/gu, '').toLowerCase();
  const clean = text => String(text || '').normalize('NFKC').replace(/\p{Cf}/gu, '').trim().replace(/\s+/g, ' ');
  const unique = values => [...new Set(values)];
  function need(ok, message) { if (!ok) throw new Error(message); }
  function identifier(prefix) {
    const c = typeof globalThis !== 'undefined' && globalThis.crypto;
    need(c && c.randomUUID, '浏览器不支持安全生成岗位ID，请使用最新版Chrome、Edge或Safari。');
    return prefix + c.randomUUID().replace(/-/g, '').slice(0, 14).toUpperCase();
  }
  function parseJD(text) {
    need(typeof text === 'string' && text.length <= 6000, 'JD请控制在6000字以内。');
    const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    need(lines.length === 4 || lines.length === 5, '请输入4或5条独立职责，每条占一行。');
    let numbered = 0;
    const clauses = lines.map((line, i) => {
      const match = line.match(/^(?:[（(]([0-9]+)[）)]|([0-9]+)[、.．)）])\s*(.*)$/u);
      if (match) {
        numbered++;
        need(Number(match[1] || match[2]) === i + 1, 'JD编号需要从1开始连续排列。');
        line = match[3].trim();
      }
      need(line.length >= 5, '每条职责至少填写5个字，请写清行动和工作对象。');
      return /[。！？.!?]$/.test(line) ? line : line + '。';
    });
    need(numbered === 0 || numbered === clauses.length, 'JD请全部编号，或全部不编号，不要混用。');
    need(new Set(clauses.map(key)).size === clauses.length, 'JD存在重复条款，请合并后填写。');
    return clauses;
  }
  const jdText = clauses => clauses.map((t, i) => `${i + 1}、${t}`).join('\n');
  function slim(job) {
    return Object.fromEntries(['id','code','name','function_id','function_name','series_id','series_name','series_prefix','level','aliases','industries'].map(k => [k, job[k] === undefined ? (k === 'aliases' ? [] : null) : clone(job[k])]));
  }
  function validateMaster(master) {
    need(master && Array.isArray(master.jobs) && master.jobs.length, '请选择包含jobs数组的完整BMJD主库JSON。');
    need(!master.industry && master.tier !== 1, '这是行业子库，请导入全局主库；行业专业JD不用于替换主库。');
    need(Array.isArray(master.series) && master.series.length, '完整主库需要包含series职责系列。');
    const ids = new Set(), codes = new Set(), names = new Set(), series = new Map(), prefixes = new Set();
    const functionNames = new Map();
    for (const s of master.series) {
      need(s && typeof s.id === 'string' && PREFIX.test(s.prefix) && typeof s.name === 'string' && s.name.trim(), '职责系列数据不完整。');
      need(!series.has(s.id) && !prefixes.has(s.prefix), '主库职责系列ID或前4位代码重复。');
      need(typeof s.function_id === 'string' && typeof s.function_name === 'string' && Array.isArray(s.job_ids), '职责系列职能或岗位索引不完整。');
      series.set(s.id, s); prefixes.add(s.prefix);
    }
    const members = new Map([...series.keys()].map(id => [id, []]));
    for (const j of master.jobs) {
      need(j && typeof j.id === 'string' && /^[A-Za-z0-9_-]{3,90}$/.test(j.id), '岗位ID格式无效。');
      need(CODE.test(j.code) && Number.isInteger(j.level) && Number(j.code.slice(-1)) === j.level, '岗位代码或层级无效：' + j.code);
      need(typeof j.name === 'string' && key(j.name), '岗位名称不能为空。');
      need(!ids.has(j.id) && !codes.has(j.code) && !names.has(key(j.name)), '主库存在重复岗位ID、代码或标准名称：' + j.name);
      const s = series.get(j.series_id);
      need(s && s.prefix === j.code.slice(0,4) && s.prefix === j.series_prefix && s.name === j.series_name && s.function_id === j.function_id && s.function_name === j.function_name, '岗位与职能、系列不一致：' + j.code);
      need(typeof j.jd === 'string' && j.jd.trim() && Array.isArray(j.jd_clauses) && j.jd_clauses.length, '缺少完整JD或条款：' + j.code);
      need(j.jd_clauses.every((c,i) => c.number === i+1 && typeof c.text === 'string' && c.text.trim()) && j.jd === j.jd_clauses.map(c => `${c.number}、${c.text}`).join('\n'), 'JD正文和条款不一致：' + j.code);
      need(Array.isArray(j.industries) && j.industries.length && new Set(j.industries).size === j.industries.length && j.industries.every(i => typeof i === 'string'), '适用行业无效：' + j.code);
      need(!j.aliases || (Array.isArray(j.aliases) && j.aliases.every(x => typeof x === 'string')), '历史名称格式无效。');
      need(!functionNames.has(j.function_id) || functionNames.get(j.function_id) === j.function_name, '同一职能ID对应多个名称。');
      functionNames.set(j.function_id, j.function_name);
      ids.add(j.id); codes.add(j.code); names.add(key(j.name)); members.get(s.id).push(j.id);
    }
    for (const s of master.series) {
      const actual = members.get(s.id);
      need(actual.length && new Set(s.job_ids).size === s.job_ids.length && actual.length === s.job_ids.length && s.job_ids.every(id => actual.includes(id)), '职责系列岗位索引不一致：' + s.prefix);
    }
    return true;
  }
  function makeState(master, policy) {
    validateMaster(master);
    need(master.jobs.every(j => j.industries.every(i => policy.industries.includes(i))), '导入包含原BMJD 11行业之外的标签。');
    const registry = master.completion_registry || {};
    const state = {
      schema: SCHEMA, revision: 0, baseToken: identifier('BASE-'), baseVersion: master.version || '导入主库',
      baseJobs: master.jobs.map(slim), baseSeries: clone(master.series),
      functions: [...new Map(master.jobs.map(j => [j.function_id, {id:j.function_id,name:j.function_name}])).values()],
      industries: unique([...policy.industries,...master.jobs.flatMap(j => j.industries)]),
      researchFunctions: clone(policy.research_function_ids), reservedR: clone(policy.reserved_nonresearch_r_prefixes),
      knownCodes: unique([...policy.reserved_codes,...(registry.known_codes || []),...master.jobs.map(j => j.code)]),
      knownPrefixes: unique([...policy.reserved_prefixes,...(registry.known_prefixes || []),...master.series.map(s => s.prefix)]),
      blockOwners: clone(policy.block_owners), newSeries: [], records: [], auditLog: clone(registry.audit_log || [])
    };
    for (const s of state.baseSeries) claimBlock(state,s.prefix.slice(0,2),s.function_id);
    for (const code of state.knownCodes) need(CODE.test(code), '历史代码登记无效。');
    for (const prefix of state.knownPrefixes) need(PREFIX.test(prefix), '历史系列登记无效。');
    if (master.completion_registry) {
      need(registry.schema === SCHEMA && Array.isArray(registry.records) && Array.isArray(registry.new_series), '补全登记格式不正确。');
      const base = new Map(master.jobs.map(j => [j.id,j]));
      for (const r of registry.records) {
        need(r && r.job && ['active','withdrawn','integrated'].includes(r.status), '补全记录无效。');
        need(CODE.test(r.job.code), '补全登记代码无效。');
        const original = base.get(r.job.id);
        if (original) {
          need(sameIdentity(original,r.job), '补全登记与主库身份冲突。');
          state.records.push({...clone(r),status:'integrated'});
        } else {
          need(r.status === 'withdrawn', '完整主库缺少已登记的活动新增岗位。');
          state.records.push(clone(r));
        }
      }
      state.newSeries = clone(registry.new_series);
      for (const s of state.newSeries) claimBlock(state,s.prefix.slice(0,2),s.function_id);
    }
    assertRegistry(state);
    return state;
  }
  function sameIdentity(a,b) {
    return ['id','code','name','function_id','function_name','series_id','series_name','series_prefix','level'].every(k => a[k] === b[k]);
  }
  function claimBlock(state,block,fid) {
    state.blockOwners[block] = unique([...(state.blockOwners[block] || []),fid]);
  }
  function allSeries(state) {
    return [...new Map([...state.baseSeries,...state.newSeries].map(s => [s.id,s])).values()];
  }
  function allJobs(state,includeWithdrawn=false) {
    return [...new Map([...state.baseJobs,...state.records.filter(r => includeWithdrawn || r.status === 'active').map(r => r.job)].map(j => [j.id,j])).values()];
  }
  function occupied(state) {
    return new Set([...state.knownCodes,...state.baseJobs.map(j => j.code),...state.records.map(r => r.job.code)]);
  }
  function findNames(state,name,excludeId) {
    const k = key(name);
    if (!k) return [];
    return allJobs(state,true).filter(j => j.id !== excludeId && (key(j.name) === k || (j.aliases || []).some(a => key(a) === k)));
  }
  function allocate(state,draft) {
    const f = state.functions.find(x => x.id === draft.functionId);
    need(f,'请选择已载入主库中的规范职能。');
    const level = Number(draft.level);
    need(Number.isInteger(level) && level >= 1 && level <= 7,'请选择1—7级岗位层级。');
    const used = occupied(state);
    if (draft.seriesId && draft.seriesId !== '__new__') {
      const s = allSeries(state).find(x => x.id === draft.seriesId);
      need(s && s.function_id === f.id,'职责系列必须属于当前职能。');
      const code = s.prefix + level;
      if (used.has(code)) {
        const job = allJobs(state,true).find(j => j.code === code);
        throw new Error(job ? `${code}已被“${job.name}”占用或保留，请选择其他层级。` : `${code}为历史保留代码，不能复用。`);
      }
      return {code,prefix:s.prefix,series:s,newSeries:false};
    }
    const prefixes = new Set([...state.knownPrefixes,...allSeries(state).map(s => s.prefix),...[...used].map(c => c.slice(0,4))]);
    const blocks = new Set([...prefixes].map(p => p.slice(0,2)));
    const research = state.researchFunctions.includes(f.id);
    const choices = Object.keys(state.blockOwners).filter(b => state.blockOwners[b].length === 1 && state.blockOwners[b][0] === f.id && (!research || (b[0] === 'R' && !state.reservedR.includes(b)))).sort();
    for (const block of choices) {
      for (let n=0;n<100;n++) {
        const prefix = block + String(n).padStart(2,'0');
        if (!prefixes.has(prefix)) return {code:prefix+level,prefix,series:null,newSeries:true};
      }
    }
    for (const first of (research ? 'R' : 'ABCDEFGHIJKLMNOPQSTUVWXYZ')) {
      for (const second of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ') {
        const block=first+second;
        if (blocks.has(block) || Object.hasOwn(state.blockOwners,block) || (research && state.reservedR.includes(block))) continue;
        const prefix=block+'00';
        return {code:prefix+level,prefix,series:null,newSeries:true};
      }
    }
    throw new Error('当前编码规则下没有可用系列，请调整编码容量后再录入。');
  }
  function validateFields(state,draft,excludeId) {
    const name=clean(draft.name);
    need(name && name.length <= 120,'请填写岗位名称，最多120字。');
    need(!findNames(state,name,excludeId).length,'岗位名称与现有名称或历史别名重复，请先查看已有岗位。');
    const clauses=parseJD(draft.jd);
    const industries=unique(draft.industries || []);
    need(industries.length && industries.every(i => state.industries.includes(i)),'请至少选择一个已知适用行业。');
    return {name,clauses,industries};
  }
  function makeClauses(texts) {
    return texts.map((text,i) => ({number:i+1,text,basis_type:'专业补写',source_refs:[],basis_note:'用户通过BMJD持续补全工具人工录入；无原BMJD来源引用。'}));
  }
  function add(input,draft,now=new Date().toISOString()) {
    const state=clone(input), fields=validateFields(state,draft), proposal=allocate(state,draft);
    const f=state.functions.find(x => x.id === draft.functionId);
    let s=proposal.series;
    if (proposal.newSeries) {
      const name=clean(draft.seriesName);
      need(name && name.length <= 100,'新建系列需要填写明确的专业方向名称，最多100字。');
      need(!allSeries(state).some(x => x.function_id === f.id && key(x.name) === key(name)),'该职能已有同名职责系列，请选择已有系列。');
      s={id:identifier('BS-ADD-'),prefix:proposal.prefix,name,function_id:f.id,function_name:f.name,job_ids:[]};
      state.newSeries.push(s);claimBlock(state,s.prefix.slice(0,2),f.id);
    }
    let id;
    const ids=new Set(allJobs(state,true).map(j => j.id));
    do { id=identifier('UJ-'); } while(ids.has(id));
    const job={id,code:proposal.code,name:fields.name,level:Number(draft.level),function_id:f.id,function_name:f.name,
      series_id:s.id,series_name:s.name,series_prefix:s.prefix,aliases:[],source_ids:[],industries:fields.industries,
      name_code_status:'人工新增；编码规则校验通过',identity_contains_inference:false,decision:'持续补全-人工新增',previous_job_ids:[],
      jd:jdText(fields.clauses),jd_clauses:makeClauses(fields.clauses),jd_review_status:'新增-人工编写',
      jd_review_reasons:['由用户录入，保留人工编写记录；工具未自动审定专业内容。'],jd_profile:null,jd_role_mode:'未核定',jd_version:'BMJD-COMPLETION-LOCAL',
      manual_entry:{origin:'BMJD持续补全工具',created_at:now,updated_at:now,author:clean(draft.author || '')}};
    const record={job,status:'active',created_at:now,updated_at:now};state.records.push(record);
    state.knownCodes=unique([...state.knownCodes,job.code]);state.knownPrefixes=unique([...state.knownPrefixes,s.prefix]);
    state.auditLog.push({action:'add',job_id:id,code:job.code,at:now});state.revision++;
    return {state,record};
  }
  function edit(input,id,draft,now=new Date().toISOString()) {
    const state=clone(input),r=state.records.find(r => r.job.id === id);
    need(r && r.status === 'active','仅可编辑本机尚未并入主库的新增岗位。');
    const fields=validateFields(state,draft,id);
    r.job.name=fields.name;r.job.industries=fields.industries;r.job.jd=jdText(fields.clauses);r.job.jd_clauses=makeClauses(fields.clauses);
    r.job.manual_entry.updated_at=now;r.updated_at=now;state.auditLog.push({action:'edit',job_id:id,code:r.job.code,at:now});state.revision++;
    return {state,record:r};
  }
  function setStatus(input,id,status,now=new Date().toISOString()) {
    const state=clone(input),r=state.records.find(r => r.job.id === id);
    need(r && r.status !== 'integrated','已并入基库的岗位不能在草稿区撤回或修改。');
    need(status === 'withdrawn' || status === 'active','无效状态。');
    if (status === 'active') need(!findNames(state,r.job.name,id).length,'该名称已由另一岗位使用，不能恢复。');
    r.status=status;r.updated_at=now;state.auditLog.push({action:status==='active'?'restore':'withdraw',job_id:id,code:r.job.code,at:now});state.revision++;
    return {state,record:r};
  }
  function assertRegistry(state) {
    const localIds=new Set(),localPrefixes=new Set();
    for(const s of state.newSeries) {
      need(s && typeof s.id==='string' && PREFIX.test(s.prefix) && clean(s.name) && state.functions.some(f => f.id===s.function_id && f.name===s.function_name),'补全系列登记无效。');
      need(!localIds.has(s.id) && !localPrefixes.has(s.prefix),'补全系列登记重复。');
      const b=state.baseSeries.find(x => x.id===s.id || x.prefix===s.prefix);
      need(!b || ['id','prefix','name','function_id','function_name'].every(k => b[k]===s[k]),'补全系列与基库系列冲突。');
      localIds.add(s.id);localPrefixes.add(s.prefix);
    }
    const ids=new Set(),codes=new Set(),series=new Map(allSeries(state).map(s => [s.id,s]));
    const reserved=occupied(state);
    for (const r of state.records) {
      need(r && ['active','withdrawn','integrated'].includes(r.status) && r.job && CODE.test(r.job.code) && typeof r.job.id==='string' && /^[A-Za-z0-9_-]{3,90}$/.test(r.job.id),'新增记录格式无效。');
      const j=r.job,s=series.get(j.series_id);
      need(!ids.has(j.id) && !codes.has(j.code),'新增登记存在重复ID或代码。');
      need(s && s.prefix===j.code.slice(0,4) && s.prefix===j.series_prefix && s.function_id===j.function_id && s.function_name===j.function_name && s.name===j.series_name,'新增记录与职责系列不一致。');
      need(j.level===Number(j.code.slice(-1)) && reserved.has(j.code),'新增记录代码与层级不一致。');
      const base=state.baseJobs.find(b => b.id===j.id || b.code===j.code);
      need(!base || (r.status==='integrated' && sameIdentity(base,j)),'新增记录与基库代码冲突。');
      need(r.status!=='integrated' || base,'并入记录必须存在于当前基库。');
      need(typeof j.name==='string' && clean(j.name) && Array.isArray(j.industries) && j.industries.length && j.industries.every(i=>state.industries.includes(i)),'新增记录名称或行业无效。');
      need(Array.isArray(j.jd_clauses) && [4,5].includes(j.jd_clauses.length) && typeof j.jd==='string' && jdText(parseJD(j.jd))===j.jd && j.jd_clauses.every((c,i)=>c.number===i+1 && c.text===parseJD(j.jd)[i]),'新增记录JD或条款无效。');
      ids.add(j.id);codes.add(j.code);
    }
  }
  function registry(state) {
    return {schema:SCHEMA,known_codes:clone(state.knownCodes),known_prefixes:clone(state.knownPrefixes),new_series:clone(state.newSeries),records:clone(state.records),audit_log:clone(state.auditLog)};
  }
  function exportMaster(base,state,now=new Date().toISOString()) {
    need(base.jobs.length===state.baseJobs.length && base.jobs.every((j,i) => sameIdentity(j,state.baseJobs[i])),'基库已在另一窗口更新，请刷新后再导出。');
    assertRegistry(state);
    const out=clone(base),active=state.records.filter(r => r.status==='active');
    out.jobs.push(...active.map(r => clone(r.job)));
    const sById=new Map(out.series.map(s => [s.id,s]));
    for (const r of active) {
      const j=r.job;
      if (!sById.has(j.series_id)) { const s=clone(allSeries(state).find(x => x.id===j.series_id));s.job_ids=[];out.series.push(s);sById.set(s.id,s); }
      const s=sById.get(j.series_id);if(!s.job_ids.includes(j.id))s.job_ids.push(j.id);
    }
    out.parent_version=base.version;out.version='BMJD-COMPLETION-'+now.replace(/[^0-9]/g,'').slice(0,14);
    out.phase='持续补全工作版；原主库岗位保持，新岗位由用户录入';
    out.base_summary=clone(base.base_summary || base.summary || {});
    out.summary={...(base.summary || {}),jobs:out.jobs.length,unique_codes:new Set(out.jobs.map(j => j.code)).size,functions:new Set(out.jobs.map(j => j.function_id)).size,series:out.series.length,
      manual_jobs:out.jobs.filter(j => j.manual_entry).length,retained:out.jobs.filter(j => j.jd_review_status==='匹配保留').length,rewritten:out.jobs.filter(j => j.jd_review_status==='重写').length};
    out.completion_registry=registry(state);out.completion_exported_at=now;
    validateMaster(out);
    return out;
  }
  function exportDelta(state,now=new Date().toISOString()) {
    assertRegistry(state);
    return {schema:SCHEMA,type:'increment',base_version:state.baseVersion,exported_at:now,...registry(state)};
  }
  function validateIncomingJob(state,j) {
    need(j && CODE.test(j.code) && typeof j.id==='string' && /^[A-Za-z0-9_-]{3,90}$/.test(j.id),'增量岗位ID或代码无效。');
    need(Number.isInteger(j.level) && Number(j.code.slice(-1))===j.level,'增量代码与层级不一致。');
    const f=state.functions.find(f => f.id===j.function_id);need(f && f.name===j.function_name,'增量岗位职能不在当前字典中。');
    need(Array.isArray(j.jd_clauses) && [4,5].includes(j.jd_clauses.length) && typeof j.jd==='string','增量岗位JD格式无效。');
    const fields=validateFields(state,{name:j.name,jd:j.jd,industries:j.industries});
    need(jdText(fields.clauses)===j.jd && j.jd_clauses.every((c,i) => c.number===i+1 && c.text===fields.clauses[i] && c.basis_type==='专业补写' && Array.isArray(c.source_refs) && !c.source_refs.length),'增量JD条款或依据无效。');
    need(Array.isArray(j.source_ids) && !j.source_ids.length && j.manual_entry,'增量必须保留人工录入标记，不得伪造原BMJD来源。');
  }
  function mergeDelta(input,delta,now=new Date().toISOString()) {
    need(delta && delta.schema===SCHEMA && delta.type==='increment' && Array.isArray(delta.records) && Array.isArray(delta.new_series),'请选择本工具导出的增量JSON。');
    const state=clone(input),existing=new Map(state.records.map(r => [r.job.id,r]));
    let added=0,skipped=0;
    for (const s of delta.new_series) {
      need(s && typeof s.id==='string' && PREFIX.test(s.prefix) && clean(s.name) && state.functions.some(f => f.id===s.function_id && f.name===s.function_name),'增量系列无效。');
      const found=allSeries(state).find(x => x.id===s.id || x.prefix===s.prefix);
      if(found) {need(['id','prefix','name','function_id','function_name'].every(k => found[k]===s[k]),'增量系列与现有系列冲突。');continue;}
      need(!state.knownPrefixes.includes(s.prefix),'增量使用历史保留系列：'+s.prefix);
      const block=s.prefix.slice(0,2),owners=state.blockOwners[block];
      need(!owners || (owners.length===1 && owners[0]===s.function_id),'增量系列占用了其他职能的码段。');
      const usedBlocks=new Set(state.knownPrefixes.map(p => p.slice(0,2)));
      need(owners || !usedBlocks.has(block),'增量使用了归属未明确的历史码段。');
      if(state.researchFunctions.includes(s.function_id))need(block[0]==='R' && !state.reservedR.includes(block),'新增研发系列必须使用非保留的R段。');
      else if(!owners)need(block[0]!=='R','新增非研发系列不能占用新的R段。');
      need(!allSeries(state).some(x => x.function_id===s.function_id && key(x.name)===key(s.name)),'增量新增了重复职责系列，请先协调命名。');
      state.newSeries.push({...clone(s),job_ids:[]});state.knownPrefixes.push(s.prefix);claimBlock(state,block,s.function_id);
    }
    for(const r of delta.records) {
      need(r && ['active','withdrawn','integrated'].includes(r.status) && r.job,'增量记录格式无效。');
      const found=existing.get(r.job.id);
      if(found) {need(found.status==='integrated'?sameIdentity(found.job,r.job):(JSON.stringify(found.job)===JSON.stringify(r.job) && found.status===(r.status==='integrated'?'active':r.status)),'同一新增记录存在不同版本，请先导出对照后处理。');skipped++;continue;}
      const base=state.baseJobs.find(j => j.id===r.job.id || j.code===r.job.code);
      if(base) {need(sameIdentity(base,r.job),'增量代码与主库其他岗位冲突：'+r.job.code);state.records.push({...clone(r),status:'integrated'});existing.set(r.job.id,state.records.at(-1));skipped++;continue;}
      need(!occupied(state).has(r.job.code),'增量代码已经占用或历史保留：'+r.job.code);
      validateIncomingJob(state,r.job);
      const s=allSeries(state).find(s => s.id===r.job.series_id);
      need(s && s.prefix===r.job.code.slice(0,4) && s.function_id===r.job.function_id && s.name===r.job.series_name && s.prefix===r.job.series_prefix,'增量岗位与系列不一致。');
      const local={...clone(r),status:r.status==='integrated'?'active':r.status};
      state.records.push(local);existing.set(r.job.id,local);state.knownCodes.push(r.job.code);added++;
    }
    need((delta.known_codes || []).every(c => CODE.test(c)) && (delta.known_prefixes || []).every(p => PREFIX.test(p)),'增量历史保留信息无效。');
    state.knownCodes=unique([...state.knownCodes,...(delta.known_codes || [])]);state.knownPrefixes=unique([...state.knownPrefixes,...(delta.known_prefixes || [])]);
    state.auditLog.push({action:'merge-increment',added,skipped,at:now});state.revision++;
    assertRegistry(state);
    return {state,added,skipped};
  }
  function importMaster(input,master,policy,now=new Date().toISOString()) {
    validateMaster(master);
    const incoming=new Map(master.jobs.map(j => [j.id,j]));
    for (const old of input.baseJobs) need(incoming.has(old.id) && sameIdentity(old,incoming.get(old.id)),'导入会删除或改动现有岗位身份：'+old.code+'。本工具仅支持追加主库。');
    const oldIds=new Set(input.baseJobs.map(j=>j.id)),used=occupied(input),localSeries=allSeries(input);
    for(const j of master.jobs.filter(j=>!oldIds.has(j.id))) {
      const local=input.records.find(r=>r.job.id===j.id || r.job.code===j.code);
      if(local)need(sameIdentity(local.job,j),'导入岗位与本机新增身份冲突：'+j.code);
      else need(!used.has(j.code),'导入岗位复用了历史保留代码：'+j.code);
      const series=localSeries.find(s=>s.id===j.series_id || s.prefix===j.series_prefix);
      if(series)need(series.id===j.series_id && series.prefix===j.series_prefix && series.name===j.series_name && series.function_id===j.function_id && series.function_name===j.function_name,'导入系列与本机系列冲突：'+j.series_prefix);
      else {
        need(!input.knownPrefixes.includes(j.series_prefix),'导入岗位复用了历史系列：'+j.series_prefix);
        const block=j.code.slice(0,2),owners=input.blockOwners[block];
        need(owners ? owners.length===1 && owners[0]===j.function_id : !input.knownPrefixes.some(p=>p.startsWith(block)),'导入系列占用了其他职能或历史码段。');
        if(input.researchFunctions.includes(j.function_id))need(block[0]==='R' && !input.reservedR.includes(block),'新增研发系列必须使用非保留的R段。');
        else if(!owners)need(block[0]!=='R','新增非研发系列不能占用新的R段。');
      }
    }
    let state=makeState(master,policy);
    for(const [b,owners] of Object.entries(input.blockOwners))for(const f of owners)claimBlock(state,b,f);
    const currentIds=new Set(state.records.map(r => r.job.id));
    const delta={...exportDelta(input),records:input.records.filter(r => !currentIds.has(r.job.id))};
    const result=mergeDelta(state,delta,now);state=result.state;
    state.knownCodes=unique([...state.knownCodes,...input.knownCodes]);state.knownPrefixes=unique([...state.knownPrefixes,...input.knownPrefixes]);
    state.auditLog.push({action:'import-master',jobs:master.jobs.length,at:now});state.revision=input.revision+1;
    return {state,base:clone(master)};
  }
  function csv(jobs) {
    function cell(value) {
      let s=String(value ?? '');if(/^[\s]*[=+\-@]/.test(s))s="'"+s;
      return '"'+s.replace(/"/g,'""')+'"';
    }
    const rows=[['岗位ID','岗位代码','岗位名称','职能','职责系列','层级','适用行业','岗位JD'],...jobs.map(j => [j.id,j.code,j.name,j.function_name,j.series_name,j.level,(j.industries||[]).join('、'),j.jd])];
    return '\uFEFF'+rows.map(row => row.map(cell).join(',')).join('\r\n');
  }
  return {SCHEMA,key,clean,parseJD,jdText,validateMaster,makeState,allSeries,allJobs,occupied,findNames,allocate,add,edit,setStatus,exportMaster,exportDelta,mergeDelta,importMaster,csv,assertRegistry,sameIdentity};
});
