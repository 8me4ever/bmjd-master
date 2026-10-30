"""Independently audit additive v2 roles, v1 backup, all grade decisions and XLSX."""
import collections
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from audit_unified_master_codes import xlsx

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'主库v2_层级补全_20261030';BACKUP=ROOT/'主库备份_20261030_v1';BASE=ROOT/'原版分类编码收口_20261030/主库.json'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(t):return ''.join(c for c in unicodedata.normalize('NFKC',t) if not c.isspace() and unicodedata.category(c)!='Cf').casefold()


def main():
    old=read(BASE);new=read(OUT/'主库v2.json');added=read(OUT/'新增岗位候选.json');slots=read(OUT/'逐层级补全审查.json');ledger=read(OUT/'职责系列层级审查.json');report=read(OUT/'核验报告.json');policy=read(OUT/'补全规则.json')
    by_old={j['id']:j for j in old['jobs']};by={j['id']:j for j in new['jobs']};addby={j['id']:j for j in added};before_series={s['id']:s for s in old['series']};after_series={s['id']:s for s in new['series']};sums=new['summary']
    old_codes={j['code'] for j in old['jobs']};checks={}
    checks['v1备份主库字节及固定SHA256一致']=sha(BASE)==sha(BACKUP/'主库.json')==read(BACKUP/'备份清单.json')['master_sha256']=='0479043ca8a8f3d0cc53e414b9bd87a20476ff383f1278037c95e3b19bc7900d'
    backup=read(BACKUP/'备份清单.json')
    checks['全部10份v1原文件及发布快照备份指纹准确']=len(backup['files'])==10 and all(sha(BACKUP/n)==r['sha256'] and (BACKUP/n).stat().st_size==r['bytes'] for n,r in backup['files'].items())
    checks['原9111岗全部字段及顺序逐值不变']=len(old['jobs'])==9111 and new['jobs'][:9111]==old['jobs']
    checks['只在原岗之后追加明确新增集合']=new['jobs'][9111:]==added and len(by)==len(new['jobs'])==9111+len(added) and not set(addby)&set(by_old)
    checks['标准名称NFKC归一化全局唯一']=len({norm(j['name']) for j in by.values()})==len(by) and all(j['name'].strip()==j['name'] and j['name'] for j in by.values())
    checks['全局五位码唯一且末位即实际层级']=len({j['code'] for j in by.values()})==len(by) and all(re.fullmatch('[A-Z]{2}[0-9]{2}[1-7]',j['code']) and j['code'][-1]==str(j['level']) for j in by.values())
    checks['新增仅3至6级且不占任何v1活跃码']=all(j['level'] in {3,4,5,6} and j['code'] not in old_codes for j in added)
    checks['3077原系列ID顺序名称四位码全部保持']=list(after_series)==list(before_series) and len(after_series)==len({s['prefix'] for s in after_series.values()})==3077 and all({k:v for k,v in s.items() if k!='job_ids'}=={k:v for k,v in before_series[i].items() if k!='job_ids'} for i,s in after_series.items())
    checks['系列仅追加新岗原引用顺序保持']=all(s['job_ids']==before_series[i]['job_ids']+[j['id'] for j in added if j['series_id']==i] for i,s in after_series.items())
    checks['新增四位前缀及分类完全继承本系列']=all(j['series_prefix']==j['code'][:4]==before_series[j['series_id']]['prefix'] and j['series_name']==before_series[j['series_id']]['name'] and all(j[k]==before_series[j['series_id']][k] for k in ['function_id','function_name','function_group_id','function_group_name','function_direction_id','function_direction_name']) for j in added)
    checks['每个系列每个层级只有一个岗位']=all(len([by[i]['level'] for i in s['job_ids']])==len({by[i]['level'] for i in s['job_ids']}) for s in after_series.values())
    checks['新增岗位全部标推定且不伪造原表来源']=all(j['identity_contains_inference'] and j['source_ids']==[] and j['previous_job_ids']==[] and j['level_completion']['requires_review'] and not j['level_completion']['source_level_direct_evidence'] for j in added)
    provenance=True;industry_ok=True;new_jd=True
    for j in added:
        s=before_series[j['series_id']];parents=[by_old[i] for i in s['job_ids']];basis=j['level_completion']
        provenance &= basis['parent_job_ids']==s['job_ids'] and basis['jd_reference_job_id'] in s['job_ids'] and basis['context_source_ids']==sorted({z for p in parents for z in p['source_ids']}) and basis['sources_are_context_only']
        industry_ok &= j['industries']==sorted({i for p in parents for i in p['industries']}) and '推定' in basis['industry_assignment_status']
        new_jd &= len(j['jd_clauses']) in {4,5} and [c['number'] for c in j['jd_clauses']]==list(range(1,len(j['jd_clauses'])+1)) and j['jd']=='\n'.join(f"{c['number']}、{c['text']}" for c in j['jd_clauses']) and all(c['source_refs']==[] and c['basis_type']=='v2层级推定补写' and c['text'] for c in j['jd_clauses'])
    checks['全部新增均可回到本系列v1父岗和上下文来源']=provenance
    checks['行业建议范围来自同系列并明确未拆库']=industry_ok
    checks['新增JD四或五条编号连续无伪造引文']=new_jd
    checks['新增职称边界与权限模式一致']=all(j['jd_role_mode']=='资深专业' for j in added if j['level'] in {3,4} and j['level_completion']['naming_type'] in {'clinical','medical_tech','pharmacy'}) and all(j['level']!=3 for j in added if j['level_completion']['naming_type'] in {'operations','driving'})
    checks['六级辅助岗有指导或协助边界']=all(re.search('指导|协助|配合',j['jd']) for j in added if j['level']==6 and j['jd_role_mode']=='辅助或初级')
    checks['不新增初级高管或将职称改成经理']=not any(re.search(r'初级.{0,12}(?:总经理|总裁|校长)|(?:医师|药师|厨师)经理|助理助理|高级高级|经理经理|主管主管',j['name']) for j in added)
    checks['新名称未用代码或数字级后缀强造区分']=all(j['code'] not in j['name'] and not re.search(r'[（(][^（）()]*[1-7]级[^（）()]*[）)]',j['name']) for j in added)
    issues={r['job_id'] for r in read(ROOT/policy['known_jd_issues_path'])}
    checks['已知3条旧JD不改且不扩散到新岗']=len(issues)==3 and all(by[i]==by_old[i] for i in issues) and not any(issues&set(j['level_completion']['parent_job_ids']) for j in added)
    checks['暂缓叉车搬运未借补层级恢复']=not any(any(t in j['name'] for t in policy['paused_topics']) for j in added) and sums['paused_original_sources_retained']==23
    expected_slots={(s['id'],level) for s in old['series'] for level in {3,4,5,6}-{by_old[i]['level'] for i in s['job_ids']}}
    slots_by={(r['series_id'],r['level']):r for r in slots}
    checks['全部4104个原空位逐项审查不遗漏重复']=len(slots)==len(slots_by)==len(expected_slots)==4104 and set(slots_by)==expected_slots
    slot_ok=True
    alias_index=collections.defaultdict(set)
    qual=re.compile(r'[（(][^（）()]*[1-7]级[^（）()]*[）)]')
    for j in by.values():
        for label in [j['name'],*j['aliases']]:alias_index[norm(label)].add(j['id']);alias_index[norm(qual.sub('',label))].add(j['id'])
    for r in slots:
        if r['new_job_id']:
            j=addby[r['new_job_id']];slot_ok &= r['status']=='新增推定岗位' and r['candidate_name']==j['name'] and r['proposed_code']==j['code'] and r['level']==j['level'] and r['series_id']==j['series_id']
        elif r['related_jobs']:
            slot_ok &= r['reason']!='' and all(v['id'] in by and all(v[k]==by[v['id']][k] for k in ['name','code','level','series_id']) and v['id'] in alias_index[norm(r['candidate_name'])] for v in r['related_jobs'])
            same=any(v['level']==r['level'] for v in r['related_jobs']);slot_ok &= r['status']==('同名或别名已有同级岗位-跨系列核对' if same else '名称或别名已占用其他层级-暂不新增')
        else:slot_ok &= r['status']=='保留专业边界' and bool(r['reason'])
    checks['每个空位新增或留空的处置和引用可复算']=slot_ok
    old_aliases={key for p in old['jobs'] for v in [p['name'],*p['aliases']] for key in [norm(v),norm(qual.sub('',v))]}
    checks['新增名称不与旧名称及旧别名混用']=all(norm(j['name']) not in old_aliases for j in added)
    levels_ok=True
    for r in ledger:
        before={by_old[i]['level'] for i in before_series[r['series_id']]['job_ids']};after={by[i]['level'] for i in after_series[r['series_id']]['job_ids']}
        levels_ok &= r['levels_before']==sorted(before) and r['levels_after']==sorted(after) and r['missing_before']==sorted({3,4,5,6}-before) and r['missing_after']==sorted({3,4,5,6}-after)
    checks['3077系列补前补后层级和剩余缺口准确']=len(ledger)==len({r['series_id'] for r in ledger})==3077 and levels_ok
    checks['95分类270方向263职能保持字典人数准确']=len(new['function_groups'])==95 and len(new['function_directions'])==270 and len({j['function_id'] for j in by.values()})==263 and all(g['jobs']==sum(j['function_group_id']==g['id'] for j in by.values()) and g['code_blocks']==dict(sorted(collections.Counter(j['code'][:2] for j in by.values() if j['function_group_id']==g['id']).items())) for g in new['function_groups']) and all(d['jobs']==sum(j['function_direction_id']==d['id'] for j in by.values()) for d in new['function_directions'])
    with (OUT/'主库v2岗位名称代码及JD.tsv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f,delimiter='\t'))
    with (OUT/'仅新增岗位名称代码及JD.tsv').open(encoding='utf-8-sig',newline='') as f:newrows=list(csv.reader(f,delimiter='\t'))
    checks['全量TSV岗位ID码名级及JD逐值一致']=len(rows)==len(by)+1 and all(len(r)==15 and r[0]==j['id'] and r[1]==j['code'] and r[2]==j['name'] and r[3]==str(j['level']) and r[10]==j['jd'] for r,j in zip(rows[1:],new['jobs']))
    checks['新增TSV无旧岗位且内容完整']=len(newrows)==len(added)+1 and newrows==[rows[0]]+[r for r in rows[1:] if r[0] in addby]
    book=xlsx(OUT/'BMJD主库v2_层级补全.xlsx')
    checks['实际Excel全量与仅新增两表逐列一致']=book['主库v2全部岗位']==rows and book['仅新增岗位']==newrows
    checks['实际Excel全缺口及全系列审查无遗漏']=len(book['3至6级缺口审查'])==4105 and len(book['全部职责系列'])==3078 and len(book['保留边界及名称占用'])==1+4104-len(added)
    checks['报告所有关键统计实际复算一致']=sums==report['summary'] and sums['jobs']==len(by) and sums['added_jobs']==len(added) and sums['complete_series_before']==sum(not r['missing_before'] for r in ledger) and sums['complete_series_after']==sum(not r['missing_after'] for r in ledger) and sums['gap_decisions']==dict(collections.Counter(r['status'] for r in slots)) and sums['gap_slots_after']==4104-len(added) and sums['added_by_level']==dict(sorted(collections.Counter(str(j['level']) for j in added).items()))
    checks['v2当前版本与编码版本一致且另存工作稿']=new['version']==new['name_code_version']==new['code_review']['version']==report['version'] and new['parent_version']==old['version']
    checks['全部构建输入及备份保持']=all(sha(ROOT/p)==h for p,h in report['input_sha256'].items())
    manifest=read(ROOT/'项目文件清单.json')['files'];protected={p:d['sha256'] for p,d in manifest.items() if p.startswith(('原版分类编码收口_20261030/','行业子库同步_20261030/','BMJD内外双版_20261030/','audience_portal/'))}
    checks['v1主库全目录子库HTML和界面源码未修改']=all(sha(ROOT/p)==h for p,h in protected.items())
    assert all(checks.values()),{k:v for k,v in checks.items() if not v}
    result={'version':new['version'],'all_passed':True,'passed':sum(checks.values()),'total':len(checks),'summary':sums,'checks':checks,
      'sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(OUT.iterdir()) if p.suffix in {'.json','.tsv','.xlsx'} and p.name!='独立核验报告.json'},
      'protected_v1_and_downstream_sha256':protected,'scope':'全量岗位与全部缺口、独立按ID/字节/码/名称及实际Excel核验；不导入新增生成器。职业梯队适宜性为明确记录的编辑判断，不伪称逐岗原表证据或资格认证。'}
    (OUT/'独立核验报告.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'all_passed':True,'passed':result['passed'],'total':result['total'],'summary':sums},ensure_ascii=False))


if __name__=='__main__':main()
