"""Independent current-catalog audit, including JSON, TSV and XLSX consistency.

This checker does not import the catalog builder or use its reported pass flags.
Historical versions/codes and non-unique search aliases are not active primary keys.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / '全量名称代码统一_20261029'
EXCEL = DIRECTORY / '全部岗位名称代码表.xlsx'
XML_NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read(path):
    return json.loads(path.read_text('utf-8'))


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(value))
                   if not c.isspace() and unicodedata.category(c) != 'Cf').casefold()


def duplicates(rows, field, normalize=False):
    groups = defaultdict(list)
    for row in rows:
        value = normalized(row.get(field)) if normalize else row.get(field)
        groups[value].append({'id': row.get('id'), 'code': row.get('code'), 'name': row.get('name')})
    return [{'value': value, 'jobs': values} for value, values in groups.items() if len(values) > 1]


def audit_jobs(jobs):
    duplicate_codes = duplicates(jobs, 'code')
    duplicate_ids = duplicates(jobs, 'id')
    normalized_collisions = duplicates(jobs, 'code', normalize=True)
    duplicate_names = duplicates(jobs, 'name', normalize=True)
    invalid = [j.get('code') for j in jobs if not isinstance(j.get('code'), str) or
               re.fullmatch(r'[A-Z]{2}[0-9]{2}[1-7]', j['code']) is None]
    levels = [j.get('code') for j in jobs if not isinstance(j.get('level'), int) or
              not isinstance(j.get('code'), str) or not j['code'][-1:].isdigit() or
              int(j['code'][-1]) != j['level']]
    annotations = []
    for job in jobs:
        match = re.search(r'[（(][^（）()]*?([1-7])级[）)]$', job.get('name', ''))
        if match and int(match.group(1)) != job.get('level'):
            annotations.append(job.get('code'))
    checks = {'岗位代码全局唯一': not duplicate_codes, '岗位ID唯一': not duplicate_ids,
              '代码无大小写全半角及隐形字符冲突': not normalized_collisions,
              '有效代码格式正确': not invalid, '代码末位与层级一致': not levels,
              '标准名称唯一': not duplicate_names, '名称中明示职级与字段一致': not annotations,
              '主键及名称非空': all(isinstance(j.get(k), str) and j[k].strip() for j in jobs for k in ('id', 'code', 'name'))}
    return checks, {'duplicate_codes': duplicate_codes, 'duplicate_ids': duplicate_ids,
                    'normalized_code_collisions': normalized_collisions, 'duplicate_names': duplicate_names,
                    'invalid_codes': invalid, 'level_conflicts': levels, 'name_grade_conflicts': annotations}


def spreadsheet_rows(path, sheet_name):
    """Read all cells from the actual exported XLSX using the standard library."""
    with ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in item.findall('.//m:t', XML_NS))
                       for item in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si', XML_NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        selected = next(s for s in workbook.findall('m:sheets/m:sheet', XML_NS) if s.get('name') == sheet_name)
        rid = selected.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        relations = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(r.get('Target') for r in relations if r.get('Id') == rid)
        location = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        rows = []
        for row in ET.fromstring(archive.read(location)).findall('m:sheetData/m:row', XML_NS):
            values = [''] * 9
            for cell in row.findall('m:c', XML_NS):
                column = re.match(r'[A-Z]+', cell.get('r')).group()
                if len(column) != 1 or column > 'I':
                    continue
                if cell.find('m:f', XML_NS) is not None:
                    raise ValueError('名码表数据不能以公式替代实际值: ' + cell.get('r'))
                v = cell.find('m:v', XML_NS)
                text = v.text if v is not None else ''
                if cell.get('t') == 'inlineStr':
                    text = ''.join(t.text or '' for t in cell.findall('.//m:t', XML_NS))
                elif cell.get('t') == 's':
                    text = strings[int(text)]
                values[ord(column) - ord('A')] = text or ''
            if any(values):
                rows.append(values)
        return rows


def representations(jobs, tsv_rows, excel_rows):
    expected = {j['id']: [j['id'], j['code'], j['name'], j['function_name'], j['series_name'], str(j['level']),
                          '、'.join(j['industries']), j['decision'], '是' if j['identity_contains_inference'] else '否'] for j in jobs}
    result = {}
    for label, rows in [('TSV', tsv_rows), ('Excel', excel_rows)]:
        body = rows[1:]
        keys = [row[0] for row in body if row]
        result[label + '岗位数与ID唯一性一致'] = len(body) == len(jobs) == len(set(keys))
        result[label + '与JSON逐字段一致'] = (len(body) == len(expected) and
                                           len(set(keys)) == len(keys) and set(keys) == set(expected) and
                                           all(row and expected.get(row[0]) == row for row in body))
    return result


def build_report():
    master = read(DIRECTORY / '名称代码主库.json')
    jobs = master['jobs']
    by_id = {j['id']: j for j in jobs}
    checks, errors = audit_jobs(jobs)
    series = master['series']
    by_series = {s['id']: s for s in series}
    checks['职责系列ID及码段唯一'] = len(series) == len(by_series) == len({s['prefix'] for s in series})
    checks['岗位与职责系列及职能一致'] = all(
        j['series_id'] in by_series and
        (j['code'][:4], j['series_prefix'], j['series_name'], j['function_id'], j['function_name']) ==
        (by_series[j['series_id']]['prefix'], by_series[j['series_id']]['prefix'], by_series[j['series_id']]['name'],
         by_series[j['series_id']]['function_id'], by_series[j['series_id']]['function_name']) for j in jobs)
    function_names = defaultdict(set)
    for job in jobs:
        function_names[job['function_id']].add(job['function_name'])
    checks['职能ID对应唯一名称'] = all(len(v) == 1 for v in function_names.values())
    with (DIRECTORY / '全部岗位名称代码表.tsv').open(encoding='utf-8', newline='') as handle:
        tsv_rows = list(csv.reader(handle, delimiter='\t'))
    excel_rows = spreadsheet_rows(EXCEL, '统一岗位名码')
    checks.update(representations(jobs, tsv_rows, excel_rows))
    source_rows = read(DIRECTORY / '来源去向映射.json')
    by_source = {s['source_id']: s for s in source_rows}
    reverse = defaultdict(set)
    for job in jobs:
        for sid in job['source_ids']:
            reverse[sid].add(job['id'])
    checks['来源总账及ID集合完整'] = len(source_rows) == len(by_source) == 19249
    checks['岗位来源无重复及无未知来源'] = all(len(j['source_ids']) == len(set(j['source_ids'])) and
                                              set(j['source_ids']) <= by_source.keys() for j in jobs)
    checks['来源去向ID与当前代码一致'] = all(
        set(s['target_job_ids']) <= by_id.keys() and
        set(s['target_codes']) == {by_id[x]['code'] for x in s['target_job_ids']} for s in source_rows)
    checks['单条来源目标ID及代码无重复'] = all(len(s['target_job_ids']) == len(set(s['target_job_ids'])) ==
                                            len(s['target_codes']) == len(set(s['target_codes'])) for s in source_rows)
    checks['来源与岗位反向引用一致'] = all(set(s['target_job_ids']) == reverse[s['source_id']] for s in source_rows)
    active = [s for s in source_rows if s['state'] != '用户暂缓']
    checks['普通来源唯一归岗'] = all(len(s['target_job_ids']) == 1 for s in active if not s['authorization'])
    checks['授权来源角色不串岗'] = all(
        len(s['target_job_ids']) == 2 and set(s['target_job_ids']) == {a['job_id'] for a in s['authorization']}
        and {by_id[a['job_id']]['code'] for a in s['authorization']} == set(s['target_codes'])
        for s in active if s['authorization'])
    paused = [s for s in source_rows if s['state'] == '用户暂缓']
    checks['23条暂缓未恢复'] = len(paused) == 23 and all(not s['target_job_ids'] and not s['target_codes'] for s in paused)
    for label, input_name, mapping_name, id_field in [
        ('冻结基线', ROOT / '全库统一完成_20261029/统一主库.json', '基线ID名称代码映射.json', 'baseline_job_id'),
        ('前版', ROOT / '岗位名称代码统一_20261029/名称代码主库.json', '前版ID名称代码映射.json', 'previous_job_id')]:
        previous = read(input_name)['jobs']
        mappings = read(DIRECTORY / mapping_name)
        indexes = {m[id_field]: m for m in mappings}
        checks[label + '全部ID映射完整'] = len(mappings) == len(indexes) == len(previous) and set(indexes) == {j['id'] for j in previous}
        consistent = True
        for old in previous:
            wanted = set()
            for sid in old['source_ids']:
                source = by_source[sid]
                if source['authorization']:
                    wanted.update(a['job_id'] for a in source['authorization'] if a['job_id'] == old['id'])
                else:
                    wanted.update(source['target_job_ids'])
            mapped = indexes.get(old['id'], {})
            consistent &= bool(wanted) and set(mapped.get('target_job_ids', [])) == wanted
            consistent &= set(mapped.get('current_codes', [])) == {by_id[x]['code'] for x in wanted}
        checks[label + '映射按来源精确定位'] = consistent
    aliases = defaultdict(set)
    for job in jobs:
        for alias in [job['name'], *job['aliases']]:
            aliases[(job['function_name'], job['level'], normalized(alias))].add(job['code'])
    rules = read(DIRECTORY / '编码自审规则.json')
    reviewed = {(r['function'], r['level'], normalized(r['alias'])): r for r in rules['alias_decisions']}
    overlaps = []
    for identity, codes in sorted(aliases.items()):
        if len(codes) < 2:
            continue
        decision = reviewed.get(identity)
        overlaps.append({'function': identity[0], 'level': identity[1], 'alias': identity[2],
                         'codes': sorted(codes), 'reviewed': bool(decision and sorted(decision['codes']) == sorted(codes)),
                         'decision': decision})
    checks['共享历史别名均有自审结论'] = all(r['reviewed'] for r in overlaps)
    paths = ['名称代码主库.json', '全部岗位名称代码表.tsv', '来源去向映射.json',
             '基线ID名称代码映射.json', '前版ID名称代码映射.json', '编码自审规则.json']
    digests = {str((DIRECTORY / name).relative_to(ROOT)): hashlib.sha256((DIRECTORY / name).read_bytes()).hexdigest() for name in paths}
    digests[str(EXCEL.relative_to(ROOT))] = hashlib.sha256(EXCEL.read_bytes()).hexdigest()
    for relative in ('全库统一完成_20261029/统一主库.json', '岗位名称代码统一_20261029/名称代码主库.json',
                     'tools/audit_job_codes.py'):
        digests[relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    return {'version': master['version'], 'reviewer': 'Codex自审', 'external_reviewer_required': False,
            'scope': '当前有效主库；历史版本和历史别名不作为当前编码主键',
            'all_passed': all(checks.values()), 'jobs': len(jobs), 'unique_codes': len({j['code'] for j in jobs}),
            'unique_ids': len(by_id), 'unique_standard_names': len({normalized(j['name']) for j in jobs}),
            'duplicate_code_groups': len(errors['duplicate_codes']), 'invalid_codes': len(errors['invalid_codes']),
            'level_conflicts': len(errors['level_conflicts']), 'shared_alias_groups_reviewed': len(overlaps),
            'checks': checks, 'passed': sum(checks.values()), 'total': len(checks),
            'errors': errors, 'shared_alias_review': overlaps, 'input_sha256': digests,
            'conclusion': '当前主库一岗一码，代码唯一性与跨格式一致性自审通过' if all(checks.values()) else '自审发现冲突，不能宣称通过',
            'assumption_policy': '原推定标签保留为内部判断依据；后续核定由Codex继续负责，不等待外部专家'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build_report()
    if not report['all_passed']:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    target = DIRECTORY / '编码自审报告.json'
    content = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    if args.write or args.check:
        if target.exists():
            if target.read_bytes() != content:
                raise ValueError('已有自审报告与本次输入不同，请保留旧报告并建立新的审查版本')
        elif args.check:
            raise ValueError('尚无自审报告，请先运行 --write')
        else:
            target.write_bytes(content)
    print(json.dumps({k: report[k] for k in ('all_passed', 'reviewer', 'jobs', 'unique_codes', 'duplicate_code_groups',
                                           'invalid_codes', 'level_conflicts', 'shared_alias_groups_reviewed', 'passed', 'total')}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
