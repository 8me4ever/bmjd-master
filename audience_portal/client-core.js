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
  return {key,prepare,search,jdFor,clauses};
});
