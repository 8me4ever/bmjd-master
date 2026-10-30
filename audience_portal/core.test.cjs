const test=require('node:test'),assert=require('node:assert/strict');
const internal=require('./internal-core.js'),client=require('./client-core.js');
function fixture(C){return C.prepare({master_version:'MASTER',industry_version:'INDUSTRY',industryJD:{制造:{a:'1、专业制造职责。'}},jobs:[
 {id:'a',code:'PP005',name:'产品专员',level:5,aliases:['产品人员'],function_id:'p',function_name:'产品',direction_id:'d',direction_name:'产品研发',source_function_name:'产品研发',series_id:'s',series_name:'产品设计',series_prefix:'PP00',industries:['制造','传媒'],jd:'1、通用职责。',original_functions:['原产品研发'],original_codes:['RD005'],extension_of:''},
 {id:'b',code:'PP003',name:'产品经理',level:3,aliases:[],function_id:'p',function_name:'产品',direction_id:'d',direction_name:'产品研发',source_function_name:'产品研发',series_id:'s',series_name:'产品设计',series_prefix:'PP00',industries:['传媒'],jd:'1、管理通用职责。'}]});}
for(const [name,C] of [['internal',internal],['client',client]]){
 test(name+' 精确代码全半角及别名查询',()=>{const d=fixture(C);assert.equal(C.search(d,{query:'ｐｐ００５'})[0].id,'a');assert.equal(C.search(d,{query:'产品人员'})[0].id,'a');});
 test(name+' 行业JD查询隔离并拒绝不适用行业',()=>{const d=fixture(C);assert.equal(C.search(d,{query:'专业制造',industry:'制造',searchScope:'all'}).length,1);assert.equal(C.search(d,{query:'专业制造',industry:'传媒',searchScope:'all'}).length,0);assert.throws(()=>C.jdFor(d,d.jobs[1],'制造'));});
}
test('客户核心仅公开查询、层级矩阵和JD读取能力',()=>assert.deepEqual(Object.keys(client).sort(),['key','prepare','search','jdFor','clauses','levels','matrixRows'].sort()));

test('客户矩阵保留真实相邻层级并突出命中，不补造岗位',()=>{const d=fixture(client),rows=client.matrixRows(d,{query:'PP005'});assert.equal(rows.length,1);assert.equal(rows[0].cells[4].job.id,'a');assert.equal(rows[0].cells[4].matched,true);assert.equal(rows[0].cells[2].job.id,'b');assert.equal(rows[0].cells[2].matched,false);assert.equal(rows[0].cells[0],null);assert.deepEqual(client.levels.map(l=>l.level),[1,2,3,4,5,6,7]);});
test('客户矩阵邻级严格遵守行业和专业方向边界',()=>{const d=fixture(client);assert.equal(client.matrixRows(d,{industry:'制造'})[0].cells[2],null);assert.equal(client.matrixRows(d,{directionId:'not-d'}) .length,0);});
test('客户矩阵相似名称按实际系列分行，不按名称合并',()=>{const raw=fixture(client);raw.jobs.push({...raw.jobs[0],id:'c',code:'PP015',series_id:'s2',series_prefix:'PP01'});const rows=client.matrixRows(client.prepare(raw));assert.equal(rows.length,2);assert.equal(rows.filter(r=>r.cells[4]).length,2);});
test('内部CSV16列逐项对齐且保存所选子库版本',()=>{
 const text=internal.csv(fixture(internal),[{id:'a',industry:'制造'}]).slice(1),lines=text.split('\r\n');
 const parse=s=>[...s.matchAll(/"((?:[^"]|"")*)"/g)].map(x=>x[1].replace(/""/g,'"'));
 const head=parse(lines[0]),row=parse(lines[1]);assert.equal(head.length,16);assert.equal(row.length,16);
 const values=Object.fromEntries(head.map((h,i)=>[h,row[i]]));assert.equal(values['岗位代码'],'PP005');assert.equal(values['职责系列'],'产品设计');assert.equal(values['岗位JD'],'1、专业制造职责。');assert.equal(values['子库版本'],'INDUSTRY');assert.equal(values['原版代码'],'RD005');
});
test('内部矩阵不补岗位且保留实际相邻层级',()=>{const rows=internal.matrixRows(fixture(internal),{query:'PP005',searchScope:'name'});assert.equal(rows[0].cells[4].job.id,'a');assert.equal(rows[0].cells[2].job.id,'b');assert.equal(rows[0].cells[0],null);});
