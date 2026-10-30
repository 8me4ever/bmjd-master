(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BMJDPortalCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function key(value) { return String(value ?? '').normalize('NFKC').toLowerCase().replace(/[\u200b-\u200f\ufeff]/g, '').replace(/[^\p{L}\p{N}+#]/gu, ''); }
  function prepare(raw) {
    const jobs = raw.jobs.map(j => ({ ...j, _code:key(j.code), _name:key(j.name),
      _identity:key([j.code,j.name,...j.aliases,j.function_name,j.direction_name,j.series_name].join(' ')) }));
    return { ...raw, jobs, byId:new Map(jobs.map(j => [j.id,j])) };
  }
  function jdFor(data, job, industry='') {
    if (industry && !job.industries.includes(industry)) throw new Error('该岗位不属于所选行业。');
    const local = industry && data.industryJD[industry]?.[job.id];
    return {text:local || job.jd, specialized:Boolean(local), label:industry ? industry+'行业职责' : '通用岗位职责'};
  }
  function search(data, filter={}) {
    const tokens=String(filter.query || '').trim().split(/\s+/).map(key).filter(Boolean), exact=key(filter.query);
    const jobs=data.jobs.filter(j => (!filter.industry || j.industries.includes(filter.industry)) &&
      (!filter.functionId || j.function_id===filter.functionId) && (!filter.directionId || j.direction_id===filter.directionId) &&
      (!filter.level || j.level===Number(filter.level)) && tokens.every(t =>
        (filter.searchScope==='all' ? j._identity+key(jdFor(data,j,filter.industry || '').text) : j._identity).includes(t)));
    const rank=j => !exact ? 0 : j._code===exact ? 100 : j._name===exact ? 90 : j.aliases.some(a=>key(a)===exact) ? 80 : 10;
    return jobs.sort((a,b)=>rank(b)-rank(a) || a.code.localeCompare(b.code));
  }
  function clauses(text) { return String(text || '').split(/\r?\n/).map(s=>s.replace(/^\s*\d+\s*[、.．)]\s*/,'').trim()).filter(Boolean); }
  const levels = [
    {level:1,name:'决策层',range:'15–25'},
    {level:2,name:'高级管理层',range:'13–19'},
    {level:3,name:'经营管理层',range:'11–15'},
    {level:4,name:'执行 / 高级专业',range:'8–11'},
    {level:5,name:'专业人员',range:'5–8'},
    {level:6,name:'初级专业',range:'3–5'},
    {level:7,name:'操作人员',range:'1–3'}
  ];
  function matrixRows(data,filter={},matches=search(data,filter)) {
    const rank=new Map(matches.map((j,i)=>[j.id,i])),wanted=new Set(matches.map(j=>j.series_id)),rows=new Map();
    for(const j of data.jobs) {
      if(!wanted.has(j.series_id)||(filter.industry&&!j.industries.includes(filter.industry))||(filter.functionId&&j.function_id!==filter.functionId)||(filter.directionId&&j.direction_id!==filter.directionId))continue;
      if(!rows.has(j.series_id))rows.set(j.series_id,{id:j.series_id,name:j.series_name,functionName:j.function_name,directionName:j.direction_name,prefix:j.series_prefix,cells:Array(7).fill(null),rank:Infinity});
      const row=rows.get(j.series_id);
      if(row.cells[j.level-1])throw Error('同一职责系列的相同层级存在重复岗位。');
      row.cells[j.level-1]={job:j,matched:rank.has(j.id)};row.rank=Math.min(row.rank,rank.get(j.id)??Infinity);
    }
    const common=['产品','财务与资金','人力资源与人才服务','行政与综合服务','综合管理','销售','客户服务','采购与供应链','研发与软件开发'];
    const priority=n=>common.includes(n)?common.indexOf(n):common.length;
    return [...rows.values()].sort((a,b)=>filter.query?a.rank-b.rank||a.prefix.localeCompare(b.prefix):priority(a.functionName)-priority(b.functionName)||a.functionName.localeCompare(b.functionName,'zh-CN')||a.prefix.localeCompare(b.prefix));
  }
  return {key,prepare,search,jdFor,clauses,levels,matrixRows};
});
