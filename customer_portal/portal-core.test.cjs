const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('./portal-core.js');
const data = C.prepare({ functions:[], series:[], industryJD:{ '医药':{ 'a':'1、完成药品冷链库存盘点。\n2、维护温度记录。' } }, jobs:[
  { id:'a', code:'AX015', name:'仓储专员', aliases:['库管'], level:5, function_id:'store', function_name:'仓储', series_id:'s', series_name:'仓储管理', industries:['医药','制造'], jd:'1、执行物资收发和库存盘点。' },
  { id:'b', code:'AX014', name:'仓储主管', aliases:[], level:4, function_id:'store', function_name:'仓储', series_id:'s', series_name:'仓储管理', industries:['制造'], jd:'1、组织仓储作业。' },
  { id:'c', code:'IT035', name:'数据库管理员', aliases:['DBA'], level:5, function_id:'it', function_name:'运维', series_id:'i', series_name:'数据库运维', industries:['医药'], jd:'1、配置数据库并完成备份恢复。' }
] });
test('精确代码及全半角大小写匹配', () => assert.equal(C.search(data,{query:'ａｘ０１５'})[0].id,'a'));
test('别名查找及多关键词交集', () => { assert.equal(C.search(data,{query:'库管'})[0].id,'a'); assert.deepEqual(C.search(data,{query:'仓储 主管'}).map(j=>j.id),['b']); });
test('行业、职能、层级和系列共同筛选', () => assert.deepEqual(C.search(data,{industry:'医药',functionId:'store',level:'5',seriesId:'s'}).map(j=>j.id),['a']));
test('职责关键词可查询且不会把数据仓库当实物仓储', () => assert.deepEqual(C.search(data,{query:'备份恢复',functionId:'store'}),[]));
test('行业专业职责搜索与父库隔离', () => { assert.equal(C.search(data,{industry:'医药',query:'冷链'})[0].id,'a'); assert.equal(C.jdFor(data,data.jobs[0],'医药').specialized,true); assert.equal(C.jdFor(data,data.jobs[0],'制造').text,data.jobs[0].jd); assert.equal(data.jobs[0].jd,'1、执行物资收发和库存盘点。'); });
test('不能显示不适用行业的JD', () => assert.throws(()=>C.jdFor(data,data.jobs[1],'医药')));
test('清单损坏、未知岗位、重复及不适用行业能安全恢复', () => { assert.deepEqual(C.parseSaved('{broken',data),[]); assert.deepEqual(C.parseSaved(JSON.stringify([{id:'a',industry:'医药'},{id:'a',industry:''},{id:'x',industry:''},{id:'b',industry:'医药'}]),data),[{id:'a',industry:'医药'}]); });
test('CSV保留职责版本及换行，并防公式注入', () => { const csv=C.csv(data,[{id:'a',industry:'医药'}]); assert.ok(csv.startsWith('\ufeff')); assert.ok(csv.includes('冷链库存')); assert.ok(csv.includes('医药行业职责')); assert.equal(C.csvCell('=1+1'),'"\'=1+1"'); assert.equal(C.csvCell('a"b'),'"a""b"'); });

test('矩阵按系列和实际层级排列，保留相邻岗位且不补造空缺', () => {
  const rows=C.matrixRows(data,{query:'AX015',searchScope:'name'});
  assert.equal(rows.length,1); assert.equal(rows[0].cells[4].job.id,'a');
  assert.equal(rows[0].cells[4].matched,true); assert.equal(rows[0].cells[3].job.id,'b');
  assert.equal(rows[0].cells[3].matched,false); assert.equal(rows[0].cells[0],null);
});
test('矩阵上下文不越过行业边界，也不按相似名称合并系列', () => {
  const rows=C.matrixRows(data,{industry:'医药'});
  assert.equal(rows.length,2); assert.equal(rows.find(r=>r.id==='s').cells[3],null);
  assert.equal(rows.find(r=>r.id==='i').cells[4].job.id,'c');
});
test('名称搜索排除JD偶然出现的词，明确扩展搜索才纳入职责', () => {
  assert.equal(C.search(data,{query:'备份恢复',searchScope:'name'}).length,0);
  assert.equal(C.search(data,{query:'备份恢复',searchScope:'all'})[0].id,'c');
  assert.equal(C.search(data,{query:'冷链',industry:'医药',searchScope:'all'})[0].id,'a');
  assert.equal(C.search(data,{query:'物资收发',industry:'医药',searchScope:'all'}).length,0);
});
