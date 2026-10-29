"""Select and verify the minimal BMJD project files. Python standard library only."""
import argparse,ast,hashlib,json,re,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'项目文件清单.json'
def load(p):return json.loads(p.read_text('utf-8'))
def fingerprint(p):
    size=p.stat().st_size;a=hashlib.sha256();b=hashlib.sha1(f'blob {size}\0'.encode())
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):a.update(chunk);b.update(chunk)
    return dict(bytes=size,sha256=a.hexdigest(),git_blob_sha1=b.hexdigest())
def selected():
    names=['.gitignore','.gitattributes','README.md','项目交接文档_20261029.md','项目目标与验收标准.md','原始资料/README.md','tools/project_files.py','统一收口_20261029/岗位职责原文.json','原始资料/结构化依据/原BMJD职能基线.json']
    names+=['全库统一完成_20261029/'+n for n in ['统一主库.json','规范职能字典.json','岗位JD及条款依据.json','推定与层级修正记录.json','源级分流记录.json','岗位归并记录.json','全来源新旧码映射.csv','C3工作码至统一码映射.csv','统计.json','输入指纹.json','验收报告.json']]
    names+=['双线协作交接_20261029/'+n for n in ['00_当前进度与分工交接.md','01_朋友_JD编写说明.md','02_Codex_主库与推定整理说明.md','JD编写输入.json','JD原文证据.json','JD回传模板.json','JD回传格式.schema.json','主库推定整理输入.json','主库变更回传模板.json','交接包清单与核验.json']]
    names+=['JD编写_20261029/'+n for n in ['交付说明_常规岗.md','build_jd.py','name_check.py','schema_check.py','make_markdown.py','out/JD回传_常规岗.json','out/JD阅读版_常规岗.md','out/validation_errors.json']]
    for folder in ['原始资料/原版BMJD','原始资料/最新输入_修改版6']:
        paths=sorted((ROOT/folder).glob('*.xlsx'));assert len(paths)==11,folder
        names += [p.relative_to(ROOT).as_posix() for p in paths]
    return sorted(set(names))
def ignore_rules(paths):
    children={}
    for name in set(paths)|{'项目文件清单.json'}:
        parts=name.split('/')
        for i,part in enumerate(parts):children.setdefault('/'.join(parts[:i]),set()).add((part,i<len(parts)-1))
    lines=['# Explicit allowlist. Archives, local configuration, caches and duplicate ZIPs stay local.']
    def emit(parent):
        prefix='/'+parent+'/' if parent else '/';lines.append(prefix+'*')
        for name,isdir in sorted(children[parent]):lines.append('!'+prefix+name+('/' if isdir else ''))
        for name,isdir in sorted(children[parent]):
            if isdir:emit(parent+'/'+name if parent else name)
    emit('');return '\n'.join(lines)+'\n'
def write_manifest():
    paths=selected();(ROOT/'.gitignore').write_text(ignore_rules(paths),'utf-8')
    files={n:fingerprint(ROOT/n) for n in paths}
    assert all(x['bytes']<100*1024*1024 for x in files.values()),'Oversized Git file'
    m={'date':'2026-10-29','baseline_version':'BMJD-ALL-20261029','purpose':'Only files required to continue the current master and JD project; historical archive excluded.','tracked_file_count':len(files)+1,'total_bytes_excluding_manifest':sum(x['bytes'] for x in files.values()),'exclusions':['历史归档/','.claude/','.impeccable/','缓存、node_modules、重复ZIP','重复只读提取、可再生成的分册、旧HTML及补充参考'],'files':files}
    MANIFEST.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf-8');return m
def check():
    m=load(MANIFEST);checks={};errors=[]
    checks['允许文件清单一致']=set(m['files'])==set(selected())
    for n,v in m['files'].items():
        if not (ROOT/n).is_file() or fingerprint(ROOT/n)!=v:errors.append(n)
    checks['文件SHA256及Git对象指纹一致']=not errors
    checks['不含归档缓存配置ZIP']=not any(n.startswith(('历史归档/','.claude/','.impeccable/')) or '__pycache__' in n or n.endswith('.zip') for n in m['files'])
    b=load(ROOT/'全库统一完成_20261029/统一主库.json');jobs=b['jobs'];sources=b['sources']
    inp=load(ROOT/'双线协作交接_20261029/JD编写输入.json');tasks={v['job_id']:v for v in inp['jobs']}
    ret=load(ROOT/'JD编写_20261029/out/JD回传_常规岗.json');sent=ret['jobs'];ids=[v['job_id'] for v in sent]
    checks['8932岗位ID代码唯一']=len(jobs)==8932==len({v['code'] for v in jobs})==len({v['id'] for v in jobs})
    checks['五位码及实际层级一致']=all(re.fullmatch(r'[A-Z]{2}\d{2}[1-7]',v['code']) and int(v['code'][-1])==v['level'] for v in jobs)
    checks['263职能2894系列']=len(b['functions'])==263 and len(b['series'])==2894
    checks['19249来源23条暂缓']=len(sources)==19249 and sum(v['state']=='用户暂缓' for v in sources)==23
    checks['基线主库SHA256一致']=fingerprint(ROOT/'全库统一完成_20261029/统一主库.json')['sha256']==inp['baseline_master_sha256']==ret['baseline_master_sha256']
    checks['交接包版本一致']=ret['package_id']==inp['package_id'] and ret['baseline_version']==inp['baseline_version']==b['version']
    checks['5644常规岗覆盖无重复']=len(sent)==len(set(ids))==5644 and set(ids)=={v['job_id'] for v in inp['jobs'] if not v['jd_inferred']}
    fields=['baseline_code','baseline_identity_sha256','baseline_jd_sha256']
    checks['全部回传定位字段匹配']=all(v['job_id'] in tasks and all(v[k]==tasks[v['job_id']][k] for k in fields) for v in sent)
    checks['3288岗未提交统计一致']=len(set(tasks)-set(ids))==3288
    checks['5643保留1改写状态一致']=Counter(v['writing_status'] for v in sent)==Counter({'无需修改-已复核':5643,'已提交':1})
    checks['全部条款非空连续编号']=all(v['clauses'] and [c['number'] for c in v['clauses']]==list(range(1,len(v['clauses'])+1)) and all(c['text'].strip() for c in v['clauses']) for v in sent)
    pool=load(ROOT/'统一收口_20261029/岗位职责原文.json')
    checks['所有原JD来源可查询']=all(v['jd_sha256'] in pool for v in sources)
    syntax=[]
    for n in m['files']:
        if n.endswith('.py'):
            try:ast.parse((ROOT/n).read_text('utf-8-sig'),filename=n)
            except SyntaxError:syntax.append(n)
    checks['脚本语法有效']=not syntax
    missing=[]
    for n in ['README.md','项目交接文档_20261029.md','项目目标与验收标准.md','原始资料/README.md']:
        for t in re.findall(r'\]\(([^)]+)\)',(ROOT/n).read_text('utf-8')):
            if t.startswith(('https:','http:','#')):continue
            if ((ROOT/n).parent/t.split('#')[0]).relative_to(ROOT).as_posix() not in m['files']:missing.append([n,t])
    checks['当前入口链接均已入选']=not missing
    patterns=[r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{40,}',r'AKIA[A-Z0-9]{16}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    suspicious=[]
    for n in m['files']:
        if n!='tools/project_files.py' and Path(n).suffix.lower() in {'.json','.md','.py','.csv'}:
            text=(ROOT/n).read_text('utf-8-sig')
            if any(re.search(p,text) for p in patterns):suspicious.append(n)
    checks['未发现凭证模式']=not suspicious
    result={'all_passed':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),'files':m['tracked_file_count'],'size_mb':round(m['total_bytes_excluding_manifest']/1024/1024,2),'checks':checks,'changed_or_missing':errors,'syntax_errors':syntax,'missing_links':missing,'credential_pattern_files':suspicious}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['all_passed'] else 1
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group();g.add_argument('--write-manifest',action='store_true');g.add_argument('--check',action='store_true');g.add_argument('--list',action='store_true');args=p.parse_args()
    if args.write_manifest:
        m=write_manifest();print(json.dumps({'files':m['tracked_file_count'],'size_mb':round(m['total_bytes_excluding_manifest']/1024/1024,2)},ensure_ascii=False))
    elif args.list:
        for n in selected()+['项目文件清单.json']:print(n)
    else:sys.exit(check())
