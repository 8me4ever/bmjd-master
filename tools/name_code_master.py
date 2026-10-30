"""Build the separate name/code phase from reviewed metadata, without JD matching.

Only columns A:G of the original spreadsheets are read. Source names, functions,
specialties, levels and recorded user constraints drive this phase. JD content,
writing status and previously integrated drafts are neither exported nor changed.
"""
import argparse
import csv
import hashlib
import io
import json
import posixpath
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '岗位名称代码统一_20261029'
VERSION = 'BMJD-NAME-CODE-20261029-01'
BASE = '全库统一完成_20261029/统一主库.json'
BASE_HASH = 'ab972f6c2d6fe0772562f27e95389d2b4c1d9c752be25222305f5208b2cf1ec3'
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_id(kind, value):
    return kind + '-' + hashlib.sha256(value.encode()).hexdigest()[:14].upper()


def title_key(text):
    return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith('P')).casefold()


def metadata_rows(path, sheet):
    """Read A:G only, including shared/inline strings; deliberately ignore H (JD)."""
    with ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(t.text or '' for t in item.findall('.//m:t', NS)) for item in root.findall('m:si', NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = workbook.findall('m:sheets/m:sheet', NS)
        chosen = next((s for s in sheets if s.get('name') == sheet), None)
        require(chosen is not None, '原表缺少行业sheet: ' + sheet)
        rid = chosen.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        relations = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(r.get('Target') for r in relations if r.get('Id') == rid)
        xml_path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        result = {}
        with archive.open(xml_path) as handle:
            for _, element in ET.iterparse(handle, events=('end',)):
                if element.tag != '{' + NS['m'] + '}row':
                    continue
                values = [''] * 7
                for cell in element.findall('m:c', NS):
                    letters = re.match(r'[A-Z]+', cell.get('r', '')).group(0)
                    if letters not in 'ABCDEFG' or len(letters) != 1:
                        continue
                    index = ord(letters) - ord('A')
                    value = cell.find('m:v', NS)
                    text = value.text if value is not None and value.text is not None else ''
                    if cell.get('t') == 's':
                        text = strings[int(text)]
                    elif cell.get('t') == 'inlineStr':
                        text = ''.join(t.text or '' for t in cell.findall('.//m:t', NS))
                    values[index] = text
                result[int(element.get('r'))] = values
                element.clear()
        require(result[1][1:3] == ['标准岗位代码', '标准职位名称'], '原表列结构变化')
        return result


def collect_metadata(sources, selected_ids):
    snapshots, files, cache = [], {}, {}
    for sid in sorted(selected_ids):
        source = sources[sid]
        row = int(re.search(r'!B(\d+):', source['range']).group(1))
        records = {}
        for folder in ('原版BMJD', '最新输入_修改版6'):
            relative = f'原始资料/{folder}/2025BMJD-{source["industry"]}.xlsx'
            if relative not in cache:
                cache[relative] = metadata_rows(ROOT / relative, source['industry'])
                files[relative] = sha(ROOT / relative)
            values = cache[relative].get(row)
            require(values is not None and values[1] and values[2], '来源原表行缺失: ' + sid)
            records[folder] = {'file': relative, 'sheet': source['industry'], 'row': row,
                               'code': values[1], 'name': values[2], 'system': values[3],
                               'function': values[4], 'specialty': values[5], 'industry_tag': values[6]}
        modified = records['最新输入_修改版6']
        require((modified['code'], modified['name']) == (source['source_code'], source['source_name']),
                '修改版行与来源ID失配，禁止按同码误配: ' + sid)
        # Rows were retained across these workbook versions. Verify the title,
        # rather than joining on codes that were reassigned between versions.
        require(title_key(records['原版BMJD']['name']) == title_key(modified['name']),
                '原版与修改版同一行名称不同，需要显式核对: ' + sid)
        snapshots.append({'source_id': sid, **records})
    return snapshots, files


def project(job):
    return {'id': job['id'], 'code': job['code'], 'name': job['name'], 'level': job['level'],
            'function_id': job['function_id'], 'function_name': job['function_name'],
            'series_id': job['classification_series_id'], 'series_name': job['classification_series_name'],
            'series_prefix': job['series'], 'aliases': list(job['aliases']),
            'baseline_identity_inferred': job['inferred_identity']}


def validate_master(jobs, series, source_records, baseline_sources, assignments):
    require(len(jobs) == len({j['id'] for j in jobs}) == len({j['code'] for j in jobs}), '岗位ID或代码不唯一')
    ids = {j['id'] for j in jobs}
    series_by_id = {s['id']: s for s in series}
    for job in jobs:
        require(bool(job['name'].strip()) and job['source_ids'], '空岗位名称或无来源岗位')
        require(len(job['source_ids']) == len(set(job['source_ids'])), '同一岗位重复引用来源')
        require(re.fullmatch(r'[A-Z]{2}\d{2}[1-7]', job['code']) is not None, '非法岗位码')
        require(int(job['code'][-1]) == job['level'], '代码与层级不一致')
        require(job['code'][:4] == job['series_prefix'], '代码与系列码不一致')
        definition = series_by_id[job['series_id']]
        require((definition['prefix'], definition['name'], definition['function_id']) ==
                         (job['series_prefix'], job['series_name'], job['function_id']), '职能/系列归属不一致: ' + job['code'])
    require(len(source_records) == len(baseline_sources) == 19249, '来源总账数量变化')
    require(len({s['source_id'] for s in source_records}) == 19249 and
            {s['source_id'] for s in source_records} == {s['source_id'] for s in baseline_sources},
            '来源ID重复或来源总账集合变化')
    require(sum(s['state'] == '用户暂缓' for s in source_records) == 23, '暂缓来源变化')
    before = {s['source_id']: s for s in baseline_sources}
    reverse = defaultdict(set)
    for job in jobs:
        for sid in job['source_ids']:
            reverse[sid].add(job['id'])
    for source in source_records:
        sid = source['source_id']
        old = before[sid]
        require((source['original_name'], source['original_code'], source['file'], source['range'], source['state']) ==
                (old['source_name'], old['source_code'], old['file'], old['range'], old['state']), '原始来源被改写')
        targets = set(source['target_job_ids'])
        require(targets <= ids and reverse[sid] == targets, '岗位来源与来源去向不同步')
        if source['state'] == '用户暂缓':
            require(not targets, '暂缓来源被恢复')
        elif old.get('allocations'):
            require(source['authorization'] == old['allocations'], '既有授权拆分变化')
            require(targets == {x['job_id'] for x in old['allocations']}, '授权来源目标发生变化')
        else:
            require(len(targets) == 1, '普通来源必须唯一归岗')
    # No JD text or writing/integration status is allowed in this phase's master.
    require(all(not any('jd' in key.casefold() for key in job) for job in jobs), '名称代码主库混入JD字段')


def build():
    require(sha(ROOT / BASE) == BASE_HASH, '冻结主库变化')
    baseline = read(ROOT / BASE)
    decisions = read(OUT / '名称代码决策.json')
    require(decisions['version'] == VERSION, '版本不一致')
    old_jobs = {j['code']: j for j in baseline['jobs']}
    jobs = {code: project(job) for code, job in old_jobs.items()}
    sources = {s['source_id']: s for s in baseline['sources']}
    functions = {f['name']: f['id'] for f in baseline['functions']}
    definitions = {s['id']: {'id': s['id'], 'name': s['name'], 'prefix': s['prefix'],
                              'function_id': s['function_id'], 'function_name': s['function_name']} for s in baseline['series']}
    def resolve_series(job):
        existing = next((s['id'] for s in definitions.values() if
                         (s['prefix'], s['name'], s['function_id']) ==
                         (job['series_prefix'], job['series_name'], job['function_id'])), None)
        return existing or identity_id('BS-NC', job['function_id'] + '/' + job['series_prefix'] + '/' + job['series_name'])
    assignments = defaultdict(set)
    for code, job in old_jobs.items():
        for sid in job['source_ids']:
            assignments[sid].add(code)
    reviews = {r['code']: r for r in decisions['reviews']}
    require(len(reviews) == len(decisions['reviews']), '复核代码重复')
    reviewed_codes = set(reviews)
    for merge in decisions['merges']:
        target, old = merge['target'], merge['retire']
        require(target in jobs and old in jobs and target != old, '归并目标错误')
        require(jobs[target]['level'] == jobs[old]['level'], '跨级归并必须另行决策')
        require(title_key(jobs[target]['name']) == title_key(jobs[old]['name']) or merge.get('explicit_title_equivalence'),
                '归并缺少名称等价说明')
        for targets in assignments.values():
            if old in targets:
                targets.remove(old)
                targets.add(target)
        jobs[target]['aliases'] += jobs[old]['aliases'] + [jobs[old]['name']]
        del jobs[old]
        reviewed_codes.update((target, old))
    for operation in decisions['updates']:
        key = operation['key']
        require(key in jobs, '修改目标不存在: ' + key)
        job = jobs[key]
        original_name = job['name']
        job.update({k: operation[k] for k in ('name', 'code', 'level', 'series_prefix', 'series_name') if k in operation})
        if 'function_name' in operation:
            job['function_name'] = operation['function_name']
            job['function_id'] = functions[job['function_name']]
        if operation.get('new_series'):
            job['series_id'] = resolve_series(job)
        if operation.get('replace_id'):
            job['id'] = identity_id('UJ-NC', VERSION + '/' + key + '/' + job['name'])
        if operation.get('keep_old_name_as_alias', True) and original_name != job['name']:
            job['aliases'].append(original_name)
        if operation.get('clear_aliases'):
            job['aliases'] = []
        reviewed_codes.add(key)
    for operation in decisions['new_jobs']:
        key = operation['code']
        require(key not in jobs, '新岗位码已存在')
        template = jobs[operation['template']]
        job = dict(template, aliases=[], baseline_identity_inferred=True)
        for field in ('name', 'code', 'level', 'series_prefix', 'series_name'):
            job[field] = operation[field]
        job['function_name'] = operation['function_name']
        job['function_id'] = functions[job['function_name']]
        job['series_id'] = resolve_series(job)
        job['id'] = identity_id('UJ-NC', VERSION + '/' + key + '/' + job['name'])
        jobs[key] = job
    for move in decisions['source_moves']:
        sid, target = move['source_id'], move['target']
        require(sid in sources and target in jobs and not sources[sid].get('allocations'), '来源改派目标错误或触及授权来源')
        require(assignments[sid], '不可恢复暂缓来源')
        reviewed_codes.update(assignments[sid])
        assignments[sid] = {target}
    selected_ids = {sid for code in reviewed_codes if code in old_jobs for sid in old_jobs[code]['source_ids']}
    selected_ids.update(move['source_id'] for move in decisions['source_moves'])
    metadata, workbook_hashes = collect_metadata(sources, selected_ids)
    metadata_by_id = {item['source_id']: item for item in metadata}
    # Evidence is metadata only: a reviewed role must point to real source rows.
    for code in reviewed_codes:
        if code in old_jobs:
            require(all(s in metadata_by_id for s in old_jobs[code]['source_ids']), '岗位原表证据不完整')
    current_sources = []
    job_sources = defaultdict(list)
    for source in baseline['sources']:
        sid = source['source_id']
        target_keys = sorted(assignments[sid])
        require(all(k in jobs for k in target_keys), '来源指向已退役岗位')
        for key in target_keys:
            job_sources[key].append(sid)
        current_sources.append({'source_id': sid, 'industry': source['industry'],
                                'original_code': source['source_code'], 'original_name': source['source_name'],
                                'original_specialty': source['source_fine'], 'file': source['file'], 'range': source['range'],
                                'state': source['state'], 'target_job_ids': [jobs[k]['id'] for k in target_keys],
                                'target_codes': [jobs[k]['code'] for k in target_keys],
                                'authorization': source.get('allocations', [])})
    reviewed_target_keys = {k for sid in selected_ids for k in assignments[sid]}
    def baseline_source_targets(old, sid):
        if sources[sid].get('allocations'):
            # The source belongs to two authorized roles, but an existing role's
            # identity must not acquire the other role as a successor.
            require(old['code'] in assignments[sid], '原授权身份失去来源')
            return {old['code']}
        return assignments[sid]
    predecessors = defaultdict(set)
    for code, old in old_jobs.items():
        for sid in old['source_ids']:
            for target in baseline_source_targets(old, sid):
                predecessors[target].add(code)
    for key, job in jobs.items():
        job['source_ids'] = job_sources[key]
        require(bool(job['source_ids']), '出现无来源活动岗: ' + key)
        job['industries'] = sorted({sources[s]['industry'] for s in job['source_ids']})
        if key in reviewed_target_keys:
            job['aliases'].extend(sources[s]['source_name'] for s in job['source_ids'])
        job['aliases'] = sorted(set(job['aliases']) - {job['name']})
        job['baseline_identity_inferred'] = any(old_jobs[c]['inferred_identity'] for c in predecessors[key])
        if key in reviewed_target_keys:
            job['name_code_review_status'] = '本批已复核-名称代码工作结论'
        else:
            job['name_code_review_status'] = '待逐项复核'
        if key in reviews and reviews[key]['conclusion'] == '继续推定':
            job['name_code_review_status'] = '本批继续推定-见决策假设'
        job['name_code_version'] = VERSION
        definition = {'id': job['series_id'], 'name': job['series_name'], 'prefix': job['series_prefix'],
                      'function_id': job['function_id'], 'function_name': job['function_name']}
        # validate_master checks all members after applying the complete batch.
        definitions[job['series_id']] = definition
    current = sorted(jobs.values(), key=lambda j: j['code'])
    active_series = sorted({j['series_id'] for j in current})
    series = [definitions[s] for s in active_series]
    validate_master(current, series, current_sources, baseline['sources'], assignments)
    mappings, changes, review_ledger = [], [], []
    for code, old in old_jobs.items():
        targets = sorted({k for sid in old['source_ids'] for k in baseline_source_targets(old, sid)})
        mapped = {'baseline_job_id': old['id'], 'old_code': code, 'old_name': old['name'],
                  'target_job_ids': [jobs[k]['id'] for k in targets], 'new_codes': [jobs[k]['code'] for k in targets],
                  'new_names': [jobs[k]['name'] for k in targets],
                  'source_destinations': {sid: [jobs[k]['code'] for k in sorted(baseline_source_targets(old, sid))] for sid in old['source_ids']}}
        require(mapped['target_job_ids'], '基线岗位失去去向')
        mappings.append(mapped)
        changed = (len(targets) != 1 or jobs[targets[0]]['id'] != old['id'] or
                   any(jobs[targets[0]][k] != project(old)[k] for k in ('code', 'name', 'level', 'function_id', 'series_id', 'series_name')) or
                   set(job_sources[targets[0]]) != set(old['source_ids']))
        if changed:
            changes.append(mapped)
        if old['inferred_identity'] or code in reviewed_codes:
            review_ledger.append({'baseline_job_id': old['id'], 'baseline_code': code,
                                  'baseline_identity_inferred': old['inferred_identity'],
                                  'reviewed_this_batch': code in reviewed_codes,
                                  'decision': reviews.get(code),
                                  'target_codes': mapped['new_codes'],
                                  'status': '本批已有名称代码工作结论' if code in reviewed_codes else '待名称代码推定'})
    require(len(mappings) == 8932, '全量基线映射缺失')
    # Renaming two unresolved branches must not hide the old identity question.
    # Keep original same-name/level candidates even after display qualifiers differ.
    original_groups = defaultdict(list)
    mapped_by_code = {m['old_code']: m for m in mappings}
    for code, old in old_jobs.items():
        original_groups[(title_key(old['name']), old['level'])].append(code)
    unresolved_boundaries = []
    for (_, level), codes in original_groups.items():
        if len(codes) < 2:
            continue
        target_ids = {target for code in codes for target in mapped_by_code[code]['target_job_ids']}
        if len(target_ids) > 1:
            unresolved_boundaries.append({'old_codes': codes, 'old_names': [old_jobs[c]['name'] for c in codes],
                                           'level': level, 'target_job_ids': sorted(target_ids),
                                           'current_codes': sorted(j['code'] for j in current if j['id'] in target_ids),
                                           'status': '已在名称中保留分支区别，是否同一身份仍待确定；不能算已解决重复岗位'})
    # Previously confirmed exceptional identities and source allocations survive.
    current_codes = {j['code']: j for j in current}
    for code in ('GM001', 'HR963', 'DP203', 'DP204', 'DP205', 'DP206', 'AC435', 'CT205'):
        old = old_jobs[code]
        now = current_codes[code]
        require((now['id'], now['name'], now['level'], now['function_id'], now['source_ids']) ==
                (old['id'], old['name'], old['level'], old['function_id'], old['source_ids']), '既有确认岗位被改写: ' + code)
    require(current_codes['LO304']['level'] == 4 and current_codes['LO306']['level'] == 6, '配货4/6约束变化')
    for code, old in old_jobs.items():
        if code[:2] in baseline['reserved_nonresearch_r_prefixes']:
            require(code in current_codes and current_codes[code]['id'] == old['id'], '非研发R段被覆盖')
    duplicates = defaultdict(list)
    for job in current:
        duplicates[(title_key(job['name']), job['level'])].append(job)
    pending_names = [{'name': values[0]['name'], 'level': values[0]['level'],
                      'codes': [j['code'] for j in values], 'status': '尚未消除的同名候选，不能当已统一'}
                     for values in duplicates.values() if len(values) > 1]
    review_count = sum(r['baseline_identity_inferred'] and r['reviewed_this_batch'] for r in review_ledger)
    report = {'version': VERSION, 'all_passed': True, 'phase': '先统一岗位名称代码，JD下一阶段',
              'baseline_jobs': 8932, 'current_jobs': len(current), 'unique_codes': len(current_codes),
              'merge_operations': len(decisions['merges']), 'added_identity_groups': len(decisions['new_jobs']),
              'baseline_jobs_with_changes': len(changes), 'source_reassignments': len(decisions['source_moves']),
              'reviewed_baseline_jobs': len(reviewed_codes & old_jobs.keys()),
              'reviewed_inferred_baseline_jobs': review_count, 'inferred_baseline_pending': 3092 - review_count,
              'metadata_evidence_sources': len(metadata), 'source_records': len(current_sources), 'paused_sources': 23,
              'remaining_same_name_candidates': len(pending_names), 'all_name_code_review_complete': False,
              'checks': ['一岗一码且ID唯一', '代码合法与层级一致', '职能系列归属一致', '8932个基线ID全部有去向',
                         '19249条来源守恒', '普通来源唯一归岗', '23条暂缓保持', '两条授权来源分配保持',
                         '原版与修改版表格元数据核验', '既有确认岗位与配货4/6保持', '不包含JD正文及JD状态']}
    document = {'version': VERSION, 'phase': report['phase'], 'status': '首批工作版；逐项确定尚未完成',
                'baseline_version': baseline['version'], 'baseline_master_sha256': BASE_HASH,
                'summary': report, 'jobs': current, 'series': series,
                'reserved_nonresearch_r_prefixes': baseline['reserved_nonresearch_r_prefixes']}
    tsv = io.StringIO(newline='')
    writer = csv.writer(tsv, delimiter='\t', lineterminator='\n')
    writer.writerow(['岗位ID', '岗位代码', '标准岗位名称', '职能', '职责系列', '层级', '行业标签', '名称代码状态'])
    for job in current:
        writer.writerow([job['id'], job['code'], job['name'], job['function_name'], job['series_name'], job['level'],
                         '、'.join(job['industries']), job['name_code_review_status']])
    return {'名称代码主库.json': document, '岗位名称代码表.tsv': tsv.getvalue(),
            '基线名称代码映射.json': mappings, '名称代码变更记录.json': changes,
            '来源去向映射.json': current_sources, '推定岗位名码台账.json': review_ledger,
            '原表名称职能证据.json': metadata, '同名待核候选.json': pending_names,
            '跨职能边界待定.json': unresolved_boundaries,
            '核验报告.json': report,
            '输入指纹.json': {'baseline_master': {BASE: BASE_HASH}, 'decisions_sha256': sha(OUT / '名称代码决策.json'),
                              'workbooks': workbook_hashes}}


def save(outputs, directory=OUT, check=False):
    encoded = {name: (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
               for name, value in outputs.items()}
    for name, content in encoded.items():
        path = directory / name
        if path.exists():
            require(path.read_bytes() == content, '已有工作文件已变化，禁止覆盖；请建立新版本: ' + name)
        else:
            require(not check, '缺少输出: ' + name)
    if not check:
        for name, content in encoded.items():
            path = directory / name
            if not path.exists():
                path.write_bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs = build()
    save(outputs, check=args.check)
    print(json.dumps(outputs['核验报告.json'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
