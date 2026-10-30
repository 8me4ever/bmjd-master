(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BMJDPortalCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function key(value) {
    return String(value ?? '').normalize('NFKC').toLowerCase().replace(/[\u200b-\u200f\ufeff]/g, '').replace(/[^\p{L}\p{N}+#]/gu, '');
  }
  function prepare(data) {
    const jobs = data.jobs.map(j => ({ ...j,
      _name: key(j.name), _code: key(j.code), _aliases: (j.aliases || []).map(key),
      _identity: key([j.code, j.name, ...(j.aliases || []), j.function_name, j.direction_name, j.source_function_name, j.series_name].join(' ')),
      _all: key([j.code, j.name, ...(j.aliases || []), j.function_name, j.direction_name, j.source_function_name, j.series_name, j.jd].join(' '))
    }));
    const byId = new Map(jobs.map(j => [j.id, j]));
    return { ...data, jobs, byId };
  }
  function search(data, filter = {}) {
    const tokens = String(filter.query || '').trim().split(/\s+/).map(key).filter(Boolean), exact = key(filter.query);
    const matches = data.jobs.filter(j =>
      (!filter.industry || j.industries.includes(filter.industry)) &&
      (!filter.functionId || j.function_id === filter.functionId) &&
      (!filter.directionId || j.direction_id === filter.directionId) &&
      (!filter.seriesId || j.series_id === filter.seriesId) &&
      (!filter.level || j.level === Number(filter.level)) &&
      tokens.every(t => (filter.searchScope === 'name' ? j._identity : filter.industry ? j._identity + key(jdFor(data, j, filter.industry).text) : j._all).includes(t))
    );
    const score = j => !exact ? 0 : j._code === exact ? 100 : j._name === exact ? 90 : j._aliases.includes(exact) ? 80 : j._name.includes(exact) ? 60 : j._code.startsWith(exact) ? 50 : 10;
    return matches.sort((a, b) => score(b) - score(a) || a.code.localeCompare(b.code));
  }
  function jdFor(data, job, industry = '') {
    if (industry && !job.industries.includes(industry)) throw new Error('该岗位不属于所选行业。');
    const local = industry && data.industryJD[industry]?.[job.id];
    return { text: local || job.jd, industry, specialized: Boolean(local), label: industry ? `${industry}行业职责` : '全局通用职责' };
  }
  const levels = [
    { level:1, name:'决策层', range:'15–25' },
    { level:2, name:'高级管理层', range:'13–19' },
    { level:3, name:'经营管理层', range:'11–15' },
    { level:4, name:'执行 / 高级专业', range:'8–11' },
    { level:5, name:'专业人员', range:'5–8' },
    { level:6, name:'初级专业', range:'3–5' },
    { level:7, name:'操作人员', range:'1–3' }
  ];
  function matrixRows(data, filter = {}, matches = search(data, filter)) {
    const rank = new Map(matches.map((j,i) => [j.id,i]));
    const wanted = new Set(matches.map(j => j.series_id)), groups = new Map();
    for (const j of data.jobs) {
      if (!wanted.has(j.series_id) || (filter.industry && !j.industries.includes(filter.industry)) || (filter.directionId && j.direction_id!==filter.directionId)) continue;
      if (!groups.has(j.series_id)) groups.set(j.series_id, { id:j.series_id, name:j.series_name, functionId:j.function_id, functionName:j.function_name, directionName:j.direction_name, prefix:j.series_prefix, cells:Array(7).fill(null), rank:Infinity });
      const row = groups.get(j.series_id);
      if (row.cells[j.level-1]) throw new Error('同一职责系列的相同层级存在重复岗位。');
      row.cells[j.level-1] = { job:j, matched:rank.has(j.id) }; row.rank = Math.min(row.rank, rank.get(j.id) ?? Infinity);
    }
    const common = ['产品','财务与资金','人力资源与人才服务','行政与综合服务','综合管理','销售','客户服务','采购与物流','研发','软件与应用研发'];
    const priority = name => common.includes(name) ? common.indexOf(name) : common.length;
    return [...groups.values()].sort((a,b) => filter.query ? a.rank-b.rank || a.prefix.localeCompare(b.prefix) : priority(a.functionName)-priority(b.functionName) || a.functionName.localeCompare(b.functionName,'zh-CN') || a.prefix.localeCompare(b.prefix));
  }
  function clauses(text) {
    return String(text || '').split(/\r?\n/).map(s => s.replace(/^\s*\d+\s*[、.．)]\s*/, '').trim()).filter(Boolean);
  }
  function parseSaved(text, data) {
    try {
      const parsed = JSON.parse(text || '[]');
      if (!Array.isArray(parsed)) return [];
      const seen = new Set();
      return parsed.filter(x => {
        const j = x && data.byId.get(x.id);
        if (!j || seen.has(x.id) || typeof x.industry !== 'string' || (x.industry && !j.industries.includes(x.industry))) return false;
        seen.add(x.id); return true;
      }).map(x => ({ id: x.id, industry: x.industry }));
    } catch (_) { return []; }
  }
  function csvCell(value) {
    let s = String(value ?? '');
    if (/^[\s\u0000-\u001f]*[=+@-]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  }
  function csv(data, records) {
    const rows = [['岗位代码', '标准岗位名称', '浏览分类', '专业方向', '规范职能', '职责系列', '岗位层级', '适用行业', '职责版本', '岗位JD', '岗位ID', '主库版本', '原版职能', '原版代码', '扩展自', '子库版本']];
    for (const r of records) {
      const j = data.byId.get(r.id); if (!j) continue;
      const v = jdFor(data, j, r.industry || '');
      rows.push([j.code, j.name, j.function_name, j.direction_name, j.source_function_name, j.series_name, j.level, j.industries.join('、'), v.label, v.text, j.id, data.master_version, (j.original_functions || []).join('、'), (j.original_codes || []).join('、'), j.extension_of || '', r.industry ? data.industry_version : '']);
    }
    return '\ufeff' + rows.map(row => row.map(csvCell).join(',')).join('\r\n');
  }
  return { key, prepare, search, matrixRows, levels, jdFor, clauses, parseSaved, csv, csvCell };
});
