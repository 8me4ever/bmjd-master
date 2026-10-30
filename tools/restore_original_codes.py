"""DRAFT ONLY: investigate unsupported function letters against original BMJD.

Historical catalogs are immutable inputs. Only code and series-prefix fields may
change in the new delivery. A two-letter block can be shared by professions;
four-letter series and five-character active codes remain globally unique.
No apply/migration entry point exists. Capacity scanning and collision decisions
are not independently validated; all generated target codes are proposals only.
"""
import argparse
import collections
import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '岗位编码校正_20261030'
MASTER = ROOT / '岗位JD匹配审查_20261029/岗位JD主库.json'
META = ROOT / '全量名称代码统一_20261029/全量原表元数据.json'
VERSION = 'BMJD-CODE-RESTORE-20261030-01'
RESEARCH = {'研发', '软件开发', '设计研发', '产品研发', '药品研发'}
CORE = {'人力资源': ['HR'], '财务': ['FA'], '综合管理': ['GM']}
PROTECTED = {'GM001', 'HR963', 'DP203', 'DP204', 'DP205', 'DP206', 'AC435', 'CT205'}


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def norm(text):
    return re.sub(r'[\s\W_]+', '', unicodedata.normalize('NFKC', text)).lower()


def make_plan(master, metadata):
    originals = {r['source_id']: r['原版BMJD'] for r in metadata if r.get('原版BMJD')}
    original_prefixes = {x['code'][:4] for x in originals.values()}
    historical_prefixes = original_prefixes | {s['prefix'] for s in master['series']}
    for path in ['全库统一完成_20261029/统一主库.json', '主库推定整理_20261029/统一主库.json', '岗位名称代码统一_20261029/名称代码主库.json']:
        historical_prefixes.update(j['code'][:4] for j in read(ROOT / path)['jobs'])
    original_by_function = collections.defaultdict(collections.Counter)
    sources_by_function = collections.defaultdict(collections.Counter)
    for x in originals.values():
        original_by_function[x['function']][x['code'][:2]] += 1
    jobs_by_series = collections.defaultdict(list)
    for j in master['jobs']:
        jobs_by_series[j['series_id']].append(j)
        for sid in j['source_ids']:
            if sid in originals:
                sources_by_function[j['function_name']][originals[sid]['code'][:2]] += 1
    allowed = {}
    for f in {j['function_name'] for j in master['jobs']}:
        allowed[f] = CORE.get(f) or list(dict.fromkeys([*original_by_function[f], *sources_by_function[f]]))
        if f == '会展':
            allowed[f] = ['ME']  # HR96 is a pinned, explicit legacy exception only.
    plan, used = [], set()
    for s in master['series']:
        js = jobs_by_series[s['id']]
        pinned = sorted(PROTECTED & {j['code'] for j in js})
        research = s['function_name'] in RESEARCH and s['prefix'].startswith('R')
        keep = bool(pinned or research or s['prefix'][:2] in allowed[s['function_name']])
        votes, names, exact = collections.Counter(), collections.Counter(), collections.Counter()
        evidence = {}
        for j in js:
            for sid in j['source_ids']:
                x = originals.get(sid)
                if not x or x['code'][:2] not in allowed[s['function_name']]:
                    continue
                p = x['code'][:4]
                votes[p] += 1
                names[p] += int(norm(x['name']) in {norm(j['name']), *map(norm, j.get('aliases', []))})
                exact[p] += int(x['code'][-1:] == str(j['level']))
                evidence.setdefault(p, []).append({'source_id': sid, 'file': x['file'], 'sheet': x['sheet'], 'row': x['row'], 'code': x['code'], 'name': x['name'], 'function': x['function']})
        candidates = sorted(votes, key=lambda p: (-names[p], -exact[p], -votes[p], p))
        row = {'series_id': s['id'], 'function_id': s['function_id'], 'function_name': s['function_name'], 'series_name': s['name'], 'previous_prefix': s['prefix'], 'current_prefix': s['prefix'] if keep else None, 'job_ids': [j['id'] for j in js], 'allowed_blocks': allowed[s['function_name']], 'original_candidates': [{'prefix': p, 'source_count': votes[p], 'name_matches': names[p], 'level_matches': exact[p]} for p in candidates], 'evidence': evidence, 'reason': '指定代码例外保留' if pinned else '保留前期明确的研发R段规则' if research else '原版职能字母段已合理，保持不动' if keep else '', 'protected_codes': pinned}
        if keep:
            assert s['prefix'] not in used
            used.add(s['prefix'])
        plan.append(row)
    pending = [r for r in plan if not r['current_prefix']]
    pending.sort(key=lambda r: (r['function_name'] not in CORE, -max((x['name_matches'] for x in r['original_candidates']), default=0), -max((x['source_count'] for x in r['original_candidates']), default=0), r['previous_prefix']))
    # Reserve all previous codes while finding destinations: even a capacity
    # exception must not have its current slot silently taken by another family.
    owner = {r['current_prefix']: r for r in plan if r['current_prefix']}
    for row in pending:
        owner[row['previous_prefix']] = row
        row['current_prefix'] = row['previous_prefix']
    movable = {r['series_id'] for r in pending}

    def move(row, visited):
        if row['series_id'] in visited:
            return False
        visited = visited | {row['series_id']}
        for item in row['original_candidates']:
            p = item['prefix']
            if p == row['current_prefix']:
                continue
            other = owner.get(p)
            if other and (other['series_id'] not in movable or not move(other, visited)):
                continue
            del owner[row['current_prefix']]
            owner[p] = row
            row['current_prefix'] = p
            row['reason'] = '恢复本系列有原版来源支持的原四位码段'
            return True
        return False

    for row in pending:
        move(row, set())
    used = set(owner)
    # Split identities can outnumber original series. Extend inside a documented
    # original block, avoiding every historical series, rather than inventing AI.
    for row in pending:
        if row['current_prefix'] != row['previous_prefix']:
            continue
        candidate_blocks = list(dict.fromkeys([x['prefix'][:2] for x in row['original_candidates']] + row['allowed_blocks']))
        for block in candidate_blocks:
            for n in range(100):
                p = block + f'{n:02}'
                if p not in used and p not in historical_prefixes:
                    row['current_prefix'] = p
                    row['reason'] = '原四位码段已被其他职责系列使用，在原字母段内使用未占用新系列'
                    used.add(p)
                    break
            if row['current_prefix']:
                break
        if row['current_prefix'] == row['previous_prefix']:
            row['reason'] = '原版码位被其他有效系列或历史码占用；为最小化变动暂保留原工作码，列明例外'
    return plan, allowed


def build(write_outputs=False):
    master, metadata = read(MASTER), read(META)
    plan, allowed = make_plan(master, metadata)
    pending = [r for r in plan if r['reason'].endswith('列明例外')]
    by_series = {r['series_id']: r for r in plan}
    changes = []
    for j in master['jobs']:
        row = by_series[j['series_id']]
        new_code = (row['current_prefix'] or row['previous_prefix']) + str(j['level'])
        if new_code != j['code']:
            changes.append({'job_id': j['id'], 'name': j['name'], 'function_name': j['function_name'], 'series_id': j['series_id'], 'series_name': j['series_name'], 'level': j['level'], 'previous_code': j['code'], 'current_code': new_code, 'reason': row['reason'], 'original_evidence': row['evidence'].get(new_code[:4], [])})
    functions = []
    for f in sorted(allowed):
        js = [j for j in master['jobs'] if j['function_name'] == f]
        functions.append({'function_name': f, 'original_allowed_blocks': allowed[f], 'previous_blocks': dict(collections.Counter(j['code'][:2] for j in js)), 'corrected_jobs': sum(c['function_name'] == f for c in changes), 'current_blocks': dict(collections.Counter((by_series[j['series_id']]['current_prefix'] or j['series_prefix'])[:2] for j in js)), 'policy': '保留既定研发R段' if f in RESEARCH else '原版字母段优先；职能共享字母段不再互相挤出'})
    report = {'status': 'DRAFT_NOT_VALIDATED_NOT_APPLIED', 'applied': False, 'warning': '仅供核查承接；changed/current等字段为候选目标，非已生效变更；容量扫描及冲突规则待复核，禁止直接批量回写。', 'version': VERSION, 'jobs': len(master['jobs']), 'series': len(plan), 'changed_jobs': len(changes), 'changed_series': sum(r['current_prefix'] != r['previous_prefix'] for r in plan if r['current_prefix']), 'affected_functions': len({c['function_name'] for c in changes}), 'unchanged_jobs': len(master['jobs']) - len(changes), 'unresolved_series': [{k: r[k] for k in ['function_name', 'series_name', 'previous_prefix', 'allowed_blocks', 'original_candidates', 'reason']} for r in pending], 'input_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in [MASTER, META]}, 'functions': functions}
    if write_outputs:
        OUT.mkdir(exist_ok=True)
        write(OUT / '编码核查与校正方案.json', report)
        write(OUT / '系列编码处置.json', plan)
        write(OUT / '新旧岗位代码映射.json', changes)
    print(json.dumps({k: report[k] for k in ['version', 'jobs', 'changed_jobs', 'changed_series', 'affected_functions', 'unchanged_jobs', 'unresolved_series']}, ensure_ascii=False))
    return master, plan, changes, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Write audit/plan only; business inputs remain unchanged.')
    args = parser.parse_args()
    build(args.plan)
