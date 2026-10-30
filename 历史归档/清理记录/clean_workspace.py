"""Archive obsolete workspace files, preserve current evidence and verify every byte.

No recursive deletion, no traversal of reparse points, no writes outside workspace.
"""
import csv,hashlib,json,os,re,stat,zipfile
from pathlib import Path
ROOT=Path(r'D:\czm\岗位代码匹配').resolve()
HISTORY=ROOT/'历史归档';LOG=HISTORY/'清理记录'
ARCHIVE=HISTORY/'过期版本与过程资料_20261029.zip'
INDEX=HISTORY/'文件位置索引.json'
assert Path(__file__).resolve().is_relative_to(ROOT)
assert not ARCHIVE.exists() and not INDEX.exists(),'Already cleaned: do not re-run destructively.'
LOG.mkdir(parents=True,exist_ok=True)
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def rel(p):return p.relative_to(ROOT).as_posix()
def safe(p):
    assert p.is_absolute() and p!=ROOT and p.resolve().is_relative_to(ROOT),str(p)
    return p
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n','utf-8')
def write(p,s):p.write_text(s.strip()+'\n','utf-8')
def is_reparse(p):return bool(p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)

inventory=[];directories=[];links=[]
def scan(parent):
    for p in sorted(parent.iterdir(),key=lambda p:p.name):
        if parent==ROOT and (p.name.startswith('.') or p.name in ['历史归档','原始资料']):continue
        if is_reparse(p):
            links.append({'path':rel(p),'target':os.readlink(p),'is_directory':p.is_dir()});continue
        if p.is_dir():directories.append(p);scan(p)
        elif p.is_file():
            safe(p);inventory.append({'original_path':rel(p),'bytes':p.stat().st_size,'sha256':sha(p)})
scan(ROOT)
root_before=len(list(ROOT.iterdir()))
root_docs={'README.md','项目交接文档_20261029.md','项目目标与验收标准.md'}
active_roots={'全库统一完成_20261029','双线协作交接_20261029'}
retired_scripts={'全库统一完成_20261029/unify_all.py','全库统一完成_20261029/deliver_all.py','全库统一完成_20261029/verify_all.py','双线协作交接_20261029/prepare_handoff.py'}
evidence_moves={
 '现状审阅_20261028/修改版6_只读提取.json':'原始资料/结构化依据/修改版6_只读提取.json',
 '现状审阅_20261028/工作区文件清单.csv':'原始资料/结构化依据/原始265文件清单.csv',
 '职能重构_20261029/原版BMJD_只读提取.json':'原始资料/结构化依据/原版BMJD_只读提取.json',
 '职能重构_20261029/原BMJD职能基线.json':'原始资料/结构化依据/原BMJD职能基线.json',
 '职能重构_20261029/JD模板与写作规则.md':'原始资料/结构化依据/JD模板与写作规则_历史参考.md',
}
for r in inventory:
    p=Path(r['original_path']);top=p.parts[0];name=p.name
    r['storage']='archive';r['archive_path']=rel(ARCHIVE);r['entry']=r['original_path']
    if r['original_path'] in root_docs or (top in active_roots and r['original_path'] not in retired_scripts) or r['original_path']=='统一收口_20261029/岗位职责原文.json':
        r.update(storage='workspace',current_path=r['original_path']);r.pop('archive_path');r.pop('entry')
    elif top=='2025BMJD Excel版' and p.suffix.lower()=='.xlsx':
        r.update(storage='workspace',current_path='原始资料/原版BMJD/'+name)
    elif top=='2025BMJD修改版6' and p.suffix.lower()=='.xlsx':
        r.update(storage='workspace',current_path='原始资料/最新输入_修改版6/'+name)
    elif len(p.parts)==1 and (p.suffix.lower()=='.docx' or (p.suffix.lower()=='.xlsx' and name!='test_preserved.xlsx')):
        r.update(storage='workspace',current_path='原始资料/补充参考/'+name)
    elif r['original_path'] in evidence_moves:r.update(storage='workspace',current_path=evidence_moves[r['original_path']])
    if r['storage']=='workspace':r.pop('archive_path',None);r.pop('entry',None)

archived=[r for r in inventory if r['storage']=='archive']
moved=[r for r in inventory if r['storage']=='workspace' and r['current_path']!=r['original_path']]
kept=[r for r in inventory if r['storage']=='workspace' and r['current_path']==r['original_path']]
for r in moved:
    dest=safe(ROOT/r['current_path']);assert not dest.exists(),str(dest)
for link in links:
    lp=ROOT/link['path']
    # A junction target may be outside ROOT. Check the entry's parent, not its target.
    assert lp.parent.resolve().is_relative_to(ROOT) and lp.absolute()!=ROOT and is_reparse(lp)

critical_paths=['全库统一完成_20261029/统一主库.json','全库统一完成_20261029/规范职能字典.json','全库统一完成_20261029/岗位JD及条款依据.json','统一收口_20261029/岗位职责原文.json','双线协作交接_20261029/朋友JD编写交接包.zip','双线协作交接_20261029/交接包清单与核验.json']
protected={r['original_path']:r['sha256'] for r in inventory if r['storage']=='workspace' and r['original_path'] not in root_docs}
plan={'date':'2026-10-29','root':str(ROOT),'root_entries_before':root_before,'inventory':inventory,'reparse_links':links,'protected_files':protected,'critical_files':{p:sha(ROOT/p) for p in critical_paths}}
dump(LOG/'清理前清单与计划.json',plan)
print(json.dumps({'phase':'planned','real_files':len(inventory),'archive_files':len(archived),'relocate_files':len(moved),'keep_files':len(kept),'junctions':len(links)},ensure_ascii=False),flush=True)

# Archive original relative paths, plus pre-cleanup copies of the three entry documents.
temporary=safe(HISTORY/'过期版本与过程资料_20261029.part.zip')
with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
    for r in archived:z.write(ROOT/r['original_path'],arcname=r['original_path'])
    for p in sorted(root_docs):z.write(ROOT/p,arcname='_清理前入口文档/'+p)
    z.writestr('_归档说明.json',json.dumps({'date':'2026-10-29','contents':'旧版本、历史阶段、过程文件、旧HTML；原始相对路径保留','file_count':len(archived),'reparse_links':links,'warning':'共享运行库未归档、未删除；只清理工作区目录链接。'},ensure_ascii=False,indent=2))

# Verify archive contents against full SHA256 values BEFORE removing any originals.
with zipfile.ZipFile(temporary) as z:
    assert z.testzip() is None,'Archive CRC failed'
    for r in archived:
        assert hashlib.sha256(z.read(r['original_path'])).hexdigest()==r['sha256'],r['original_path']
    for p in root_docs:assert hashlib.sha256(z.read('_清理前入口文档/'+p)).hexdigest()==sha(ROOT/p)
archive_hash=sha(temporary);temporary.rename(ARCHIVE)
print(json.dumps({'phase':'archive_verified','archive_MB':round(ARCHIVE.stat().st_size/1024/1024,2)},ensure_ascii=False),flush=True)

# Ensure no concurrent edits occurred, then move evidence and unlink archived originals.
for r in inventory:assert sha(ROOT/r['original_path'])==r['sha256'],r['original_path']
for r in moved:
    src=safe(ROOT/r['original_path']);dest=safe(ROOT/r['current_path']);dest.parent.mkdir(parents=True,exist_ok=True)
    src.rename(dest);assert sha(dest)==r['sha256']
for r in archived:
    src=safe(ROOT/r['original_path']);src.unlink()
for link in links:
    lp=ROOT/link['path'];assert lp.parent.resolve().is_relative_to(ROOT) and is_reparse(lp)
    if link['is_directory']:os.rmdir(lp) # Remove the junction entry only; never recurse into its target.
    else:lp.unlink()
residual=[]
for p in sorted(directories,key=lambda p:len(p.parts),reverse=True):
    if not p.exists():continue
    safe(p)
    try:p.rmdir()
    except OSError:residual.append(rel(p))

location_index={'date':'2026-10-29','archive':rel(ARCHIVE),'archive_sha256':archive_hash,'interpretation':'original_path为清理前/历史证据路径；workspace看current_path，archive看entry。冻结JSON及交接包中的旧路径按此索引解析。','locations':{r['original_path']:{k:v for k,v in r.items() if k!='original_path'} for r in inventory},'reparse_links_removed':links,'root_document_backups':'_清理前入口文档/'}
dump(INDEX,location_index)

write(ROOT/'README.md','''
# BMJD岗位主库：当前工作区

当前共同基线：**BMJD-ALL-20261029**，8,932个岗位、263个职能、2,894个职责系列。代码和规则JD草稿已齐全；朋友负责专业编写/复核JD，Codex负责主库及身份推定整理。新一轮双线工作尚未启动。

- [双线进度与分工交接](双线协作交接_20261029/00_当前进度与分工交接.md)
- [朋友JD编写说明](双线协作交接_20261029/01_朋友_JD编写说明.md) · [可直接转交的完整输入包](双线协作交接_20261029/朋友JD编写交接包.zip)
- [Codex主库整理说明](双线协作交接_20261029/02_Codex_主库与推定整理说明.md)
- [完整岗位与JD表](全库统一完成_20261029/统一岗位与JD.csv) · [统一主库](全库统一完成_20261029/统一主库.json) · [职能字典](全库统一完成_20261029/规范职能字典.json)
- [岗位分册目录](全库统一完成_20261029/岗位目录.md) · [规则统一完成说明](全库统一完成_20261029/完成说明.md)

## 工作区目录

| 位置 | 用途 |
|---|---|
| 全库统一完成_20261029 | 当前冻结主库、字典、JD草稿、映射、分册和核验记录 |
| 双线协作交接_20261029 | 双方工作说明、全量输入、证据及回传模板，朋友交接包 |
| 原始资料 | 原版11行业Excel、最新修改版6、补充资料和结构化依据 |
| 统一收口_20261029 | 仅保留岗位职责原文.json，维持冻结主库和文档的原文引用 |
| 历史归档 | 过期版本、旧阶段成果、旧HTML和过程脚本的压缩归档及位置索引 |

整理主库重点3,092个身份推定岗位，朋友JD重点3,288个JD推定岗位；两者重叠2,819岗，任一推定共3,561岗。23条既有暂缓来源继续隔离。数据核验通过不代表逐岗专业审定。

历史资料已移出日常工作目录，原始内容仍可恢复。原文件路径、冻结输入指纹或旧代码需要追溯时，查[文件位置索引](历史归档/文件位置索引.json)及[清理说明](工作区清理说明.md)。当前入口以本文件和[项目交接](项目交接文档_20261029.md)为准。
''')
write(ROOT/'项目交接文档_20261029.md','''
# 当前项目交接：JD编写与主库整理分工

更新：2026-10-29。当前共同基线BMJD-ALL-20261029，8,932岗、263个职能、2,894个职责系列。所有活动岗位已有统一代码和规则JD草稿，48项数据核验通过；后续专业写作与推定整理仍需分别推进。

## 双方工作入口

- 先读[共同进度与分工](双线协作交接_20261029/00_当前进度与分工交接.md)。
- 朋友按[JD编写说明](双线协作交接_20261029/01_朋友_JD编写说明.md)，编写/复核全库8,932岗，重点改进3,288个JD含推定岗位。[完整交接包](双线协作交接_20261029/朋友JD编写交接包.zip)可脱离工作区直接使用。
- Codex按[主库及推定整理说明](双线协作交接_20261029/02_Codex_主库与推定整理说明.md)，重点整理3,092个身份推定岗位，并检查全库相邻冲突、分类、命名、层级和身份去重。

两类推定重叠2,819岗，合计3,561岗。未标推定不等于已人工审定。当前只完成规则统一及双线交接准备，新一轮专业JD编写和主库推定整理尚未执行。

双方以交接包ID、基线版本和job_id定位，代码和名称不作唯一回填键。朋友只提交JD及身份问题，Codex维护新工作版本、身份变更和基线到当前目标的映射；归并、拆分或职责变化后须核对JD适用。原全库统一目录和交接包保持冻结，不运行旧构建脚本覆盖。

## 清理后的文件位置

- 当前主库、字典、分册、映射均在“全库统一完成_20261029”，内容未改。
- 原JD池仍在“统一收口_20261029/岗位职责原文.json”，保留原相对引用。
- 原版Excel移到“原始资料/原版BMJD”；最新修改版6移到“原始资料/最新输入_修改版6”。
- 原版职能基线、两份只读提取及原265文件清单在“原始资料/结构化依据”。
- 旧版本1—5、C1/C2/C3/U4阶段、旧HTML和过程脚本已压缩归档；历史JSON内的路径是当时位置，按[位置索引](历史归档/文件位置索引.json)查找实际位置或ZIP条目。

必须承接GM001、HR963、DP203—206、配货4/6级和灯光STAGE/CG分条款两岗口径；23条搬运/叉车来源继续暂缓。VE068→6、库管组长→4和原结构6→5是本版推定，交由Codex整理依据，不冒充用户逐项确认。

HTML已作为历史资料归档，未修改其内容；客户平台建设、审议模块删除和历史版本1—5正式映射尚未开展。更早的长篇交接历史保存在归档中的“_清理前入口文档/项目交接文档_20261029.md”，无需在日常入口反复阅读。
''')
write(ROOT/'项目目标与验收标准.md','''
# 项目目标与验收标准

建立全公司共用岗位主库和职能字典，让客户按职能、职责对象及层级找到岗位、代码和JD。11行业作为适用标签，按职责定名及归类，同职能同对象同层级的等价身份归并。

共同冻结基线BMJD-ALL-20261029已完成8,932岗规则统一，代码和JD草稿覆盖100%；现阶段按[双线交接](双线协作交接_20261029/00_当前进度与分工交接.md)推进。

| 工作线 | 完成要求 |
|---|---|
| 朋友JD线 | 全部基线岗位有处理状态，一岗一份编号职责JD，体现专业对象和实际层级，原文提炼/专业补写/推定逐条区分 |
| Codex主库线 | 3,092个身份推定岗逐项有结论，检查全库近邻冲突，分类、命名、层级、归并拆分有依据及去向 |
| 集成 | 通过基线ID和指纹匹配，保留版本与变更映射；职责变化后核对JD适用，不静默覆盖 |
| 数据及原文 | 编码唯一、层级合法、来源守恒，原码原名原JD可追溯；23条用户暂缓来源不恢复 |

GM001、HR963、DP203—206、配货4/6级和灯光两岗继续保留；新研发R段不覆盖原非研发R段。现有核验是数据核验，不能代替专业内容判断，也不能用草稿覆盖率替代新一轮JD写作完成率。

原始及历史文件现位置见[清理说明](工作区清理说明.md)和[位置索引](历史归档/文件位置索引.json)。客户查询平台、旧审议模块删除、历史版本1—5正式映射是后续工作，本阶段不修改HTML。
''')
write(ROOT/'原始资料'/'README.md','''
# 原始及依据资料

- 原版BMJD：原始11行业Excel，供核对原职能体系。
- 最新输入_修改版6：当前来源总账对应的11行业Excel。
- 结构化依据：原版BMJD只读提取、修改版6只读提取、原职能基线、原265文件清单及历史JD模板参考。
- 补充参考：工作区原有补充Excel、Word资料，保留原内容。

这些文件只移动位置，未修改内容。岗位sources.file中的路径仍保留历史原路径，可按[位置索引](../历史归档/文件位置索引.json)查找新位置。历史版本1—5和旧阶段资料保存在压缩归档中。

“JD模板与写作规则_历史参考.md”是早期模板，仅参考编号职责格式；本阶段以双线交接中的写作规则及推定标记约定为准。
''')
write(HISTORY/'README.md','''
# 历史资料归档

[过期版本与过程资料_20261029.zip](过期版本与过程资料_20261029.zip)保留旧版本、旧阶段主库、报告、截图、HTML和构建脚本。ZIP内采用清理前的相对路径；当前入口文档清理前的长篇版本放在“_清理前入口文档”。

查找旧文件时读取[文件位置索引](文件位置索引.json)：storage=workspace时看current_path，storage=archive时看entry。原始文件SHA256、归档校验结果和清理记录均保留。仅在需要时提取指定文件到新目录，避免覆盖当前主库或交接包。

旧构建脚本依赖当时目录结构，只作追溯；不要解压后直接运行以覆盖现有文件。两个node_modules目录原为共享运行库的目录链接，只移除了工作区中的链接，共享库未删除。
''')
summary={'date':'2026-10-29','root_entries_before':root_before,'real_files_before':len(inventory),'archived_files':len(archived),'relocated_evidence_files':len(moved),'unchanged_retained_files':len(kept),'reparse_links_removed':len(links),'archive_path':rel(ARCHIVE),'archive_bytes':ARCHIVE.stat().st_size,'archive_sha256':archive_hash,'residual_directories':residual,'critical_files_unchanged':all(sha(ROOT/p)==h for p,h in plan['critical_files'].items())}
write(ROOT/'工作区清理说明.md',f'''
# 工作区清理说明

2026-10-29已完成清理。原根目录{root_before}项，旧资料集中归档；当前主库、双线交接包、原始职责证据保留。未永久丢弃业务文件。

- 归档{len(archived)}个过期/过程文件，包含历史版本、旧阶段成果、旧HTML、报告、截图、缓存和构建脚本。
- 将{len(moved)}个需日常使用的原始或依据文件集中到“原始资料”。原版11行业和最新修改版6均保留可直接读取的Excel。
- 当前主库及字典、8,932岗JD草稿、全部来源映射、原JD池、推定记录、朋友交接包及回传模板均保留，核心数据指纹未变。
- 旧unify_all.py、deliver_all.py、verify_all.py和prepare_handoff.py随历史资料归档，避免误运行覆盖。旧核验报告作为冻结基线数据核验结果保留；旧脚本不适用于清理后的路径布局。
- 仅移除两个共享运行库目录链接，不删除其目标库。隐藏工具配置保持原样。

## 从哪里继续工作

读[当前项目交接](项目交接文档_20261029.md)及[共同分工](双线协作交接_20261029/00_当前进度与分工交接.md)。朋友交接包文件内容未变，仍可直接转交；其冻结指纹中历史路径按位置索引解析。

新主库整理请使用“原始资料/结构化依据”及当前主库；原JD池特意保留原路径“统一收口_20261029/岗位职责原文.json”，避免改变冻结JSON及原文引用。

## 如何找回历史文件

1. 在[文件位置索引](历史归档/文件位置索引.json)中按原相对路径查找。
2. storage=workspace表示文件仍直接保留，按current_path打开。
3. storage=archive表示文件在[历史ZIP](历史归档/过期版本与过程资料_20261029.zip)内，按entry查找。恢复时提取到单独目录，保留原相对结构，不覆盖当前目录。

归档在移除原文件之前已逐文件验证SHA256和ZIP完整性，全部原265文件均可按索引定位并校验。最终结果见[清理核验报告](历史归档/清理记录/清理核验报告.json)。
''')

# Final verification: unchanged active data, all original 265 files accessible,
# archive unchanged since pre-removal per-file checks, all active Markdown links valid.
records={r['original_path']:r for r in inventory}
checks={
 '归档CRC及逐文件SHA256删除前已验证':True,
 '归档删除后SHA256未改变':sha(ARCHIVE)==archive_hash,
 '当前主库原文池及朋友交接包指纹未变':summary['critical_files_unchanged'],
 '全部保留文件及搬迁文件内容未变':all(sha(ROOT/r['current_path'])==r['sha256'] for r in inventory if r['storage']=='workspace' and r['original_path'] not in root_docs),
 '归档文件原位置已移出日常目录':all(not (ROOT/r['original_path']).exists() for r in archived),
 '原版及修改版6各11份Excel':len(list((ROOT/'原始资料/原版BMJD').glob('*.xlsx')))==11 and len(list((ROOT/'原始资料/最新输入_修改版6').glob('*.xlsx')))==11,
 '原文池原相对路径保持可用':(ROOT/'统一收口_20261029/岗位职责原文.json').exists(),
 '两个目录链接已移除且目标共享库仍在':len(links)==2 and all(not os.path.lexists(ROOT/l['path']) and Path(l['target']).is_dir() for l in links),
}
with (ROOT/'原始资料/结构化依据/原始265文件清单.csv').open(encoding='utf-8-sig',newline='') as f:original=list(csv.DictReader(f))
checks['原始265份资料均可定位且原SHA一致']=len(original)==265 and all(r['path'].replace('\\','/') in records and records[r['path'].replace('\\','/')]['sha256']==r['sha256'] for r in original)
missing=[]
docs=[ROOT/'README.md',ROOT/'项目交接文档_20261029.md',ROOT/'项目目标与验收标准.md',ROOT/'工作区清理说明.md',ROOT/'原始资料/README.md',HISTORY/'README.md',*(ROOT/'全库统一完成_20261029').rglob('*.md'),*(ROOT/'双线协作交接_20261029').glob('*.md')]
for p in docs:
    for target in re.findall(r'\]\(([^)]+)\)',p.read_text('utf8')):
        if target.startswith(('https:','http:','#')):continue
        q=p.parent/target.split('#')[0]
        if not q.exists() and rel(q)!='历史归档/清理记录/清理核验报告.json':missing.append([rel(p),target])
checks['全部当前文档本地链接有效']=not missing
summary.update(root_entries_after=len(list(ROOT.iterdir())),all_checks_passed=all(checks.values()),checks=checks,missing_links=missing)
dump(LOG/'清理核验报告.json',summary)
assert all(checks.values()),json.dumps(summary,ensure_ascii=False)
print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
