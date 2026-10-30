"""Independently verify exported JD identities, evidence and change records.

This checker does not import the JD writer or accept its reported pass flags.
It verifies deliverables and exact references, not universal semantic correctness.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from audit_job_codes import audit_jobs, spreadsheet_rows

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / '岗位JD匹配审查_20261029'
HEADER = ['岗位ID', '岗位代码', '岗位名称', '职能', '职责系列', '层级', '审查处置', '原因', '最终JD']


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_for_jobs(jobs):
    return [HEADER] + [[j['id'], j['code'], j['name'], j['function_name'], j['series_name'], str(j['level']),
                       j['jd_review_status'], '；'.join(j['jd_review_reasons']), j['jd']] for j in jobs]


def compare_export(expected, actual):
    if not actual or actual[0] != expected[0] or len(actual) != len(expected):
        return False
    body = actual[1:]
    keys = [r[0] for r in body if len(r) == 9]
    by_id = {r[0]: r for r in expected[1:]}
    return (len(keys) == len(set(keys)) == len(by_id) and set(keys) == set(by_id)
            and all(r == by_id.get(r[0]) for r in body))


def validate_retained(job, allowed):
    errors = []
    for clause in job['jd_clauses']:
        refs = clause['source_refs']
        if clause['basis_type'] != '原文提炼' or not refs:
            errors.append('missing_direct_evidence')
        for ref in refs:
            if (ref['source_id'] not in job['source_ids'] or ref['source_id'] not in allowed
                    or not ref['quote'] or ref['quote'] not in allowed.get(ref['source_id'], '')):
                errors.append('foreign_or_unquoted_source')
    return errors


def audit():
    identity_path = ROOT/'全量名称代码统一_20261029/名称代码主库.json'
    master_path = DIRECTORY/'岗位JD主库.json'
    ledger_path = DIRECTORY/'逐岗JD审查台账.json'
    identity = read(identity_path)
    final = read(master_path)
    jobs = final['jobs']
    records = read(ledger_path)
    rules = read(DIRECTORY/'JD审查与编写规则.json')
    source_map = read(ROOT/'全量名称代码统一_20261029/来源去向映射.json')
    baseline_map = read(ROOT/'全量名称代码统一_20261029/基线ID名称代码映射.json')
    baseline = {j['job_id']: j for j in read(ROOT/'双线协作交接_20261029/JD编写输入.json')['jobs']}
    evidence = read(ROOT/'双线协作交接_20261029/JD原文证据.json')
    prior = {j['job_id']: j for j in read(ROOT/'主库推定整理_20261029/岗位JD及条款依据.json')}
    prior_map = {r['baseline_job_id']: r['target_job_ids'] for r in read(ROOT/'主库推定整理_20261029/基线到当前ID映射.json')}
    checks, code_errors = audit_jobs(jobs)
    original = {j['id']: j for j in identity['jobs']}
    checks['岗位数量9111且ID集合等于名码主库'] = len(jobs) == 9111 and {j['id'] for j in jobs} == set(original)
    checks['名码及身份全部原字段逐值不变'] = all(j['id'] in original and all(j.get(k) == v for k, v in original[j['id']].items()) for j in jobs)
    checks['9111台账完整无重复'] = len(records) == len({r['job_id'] for r in records}) == 9111 and {r['job_id'] for r in records} == set(original)
    ledger = {r['job_id']: r for r in records}
    checks['每岗一份JD且连续编号'] = all(j['jd_clauses'] and [c['number'] for c in j['jd_clauses']] == list(range(1, len(j['jd_clauses'])+1)) and j['jd'] == '\n'.join(f"{c['number']}、{c['text']}" for c in j['jd_clauses']) for j in jobs)
    checks['改写稿严格4或5条且条款不重复'] = all(len(j['jd_clauses']) in {4, 5} and len({c['text'] for c in j['jd_clauses']}) == len(j['jd_clauses']) for j in jobs if j['jd_review_status'] == '重写')
    checks['新条款均明示专业补写且不伪造原文依据'] = all(c['basis_type'] == '专业补写' and not c['source_refs'] and c['basis_note'] for j in jobs if j['jd_review_status'] == '重写' for c in j['jd_clauses'])
    checks['无未替换占位符及空条款'] = all(c['text'].strip() and '{subject}' not in c['text'] and not re.search(r'待填写|TODO|待编写', c['text']) for j in jobs for c in j['jd_clauses'])
    checks['每岗审查原因及框架可定位'] = all(j['jd_review_status'] in {'匹配保留', '重写'} and j['jd_review_reasons'] and j['jd_profile'] in rules['profiles'] for j in jobs)
    checks['263职能框架覆盖完整'] = set(rules['function_profiles']) == {j['function_name'] for j in jobs} and len(rules['function_profiles']) == 263
    checks['主库与变更台账JD及指纹一致'] = all(j['id'] in ledger and ledger[j['id']]['new_jd'] == j['jd'] and ledger[j['id']]['new_jd_sha256'] == hashlib.sha256(j['jd'].encode()).hexdigest() for j in jobs)
    routes = {r['source_id']: r for r in source_map}
    checks['来源保持原活动范围且不恢复23条暂缓'] = all(s in routes and routes[s]['state'] != '用户暂缓' and j['id'] in routes[s]['target_job_ids'] for j in jobs for s in j['source_ids'])
    errors = []
    mapped = {j['id']: set() for j in jobs}
    for r in baseline_map:
        for target in r['target_job_ids']:
            mapped[target].add(r['baseline_job_id'])
    provenance = []
    for j in jobs:
        record = ledger.get(j['id'], {})
        candidates = record.get('legacy_candidates', [])
        if {c['baseline_job_id'] for c in candidates} != mapped[j['id']]:
            provenance.append([j['code'], 'wrong_baseline_mapping'])
        genuine_jds = {}
        allowed = {s: evidence['texts'][evidence['sources'][s]['jd_sha256']] for s in j['source_ids']}
        for bid in mapped[j['id']]:
            old = baseline[bid]
            received_ids = prior_map[bid]
            draft = prior.get(received_ids[0]) if len(received_ids) == 1 else None
            clauses = draft['clauses'] if draft else old['current_clause_evidence']
            genuine_jds[bid] = '\n'.join(f"{i}、{c['text']}" for i, c in enumerate(clauses, 1))
            for scope in old['role_scoped_evidence']:
                if scope['parent_source_id'] in allowed and scope['role'] == ('CG' if j['code'] == 'CT205' else 'STAGE'):
                    allowed[scope['parent_source_id']] = scope['text']
        for c in candidates:
            if c['old_jd'] != genuine_jds.get(c['baseline_job_id']) or c['old_name'] != baseline[c['baseline_job_id']]['baseline_name']:
                provenance.append([j['code'], 'altered_old_draft'])
        if j['jd_review_status'] == '匹配保留':
            if j['jd'] not in genuine_jds.values():
                errors.append([j['code'], 'retained_text_changed'])
            errors += [[j['code'], e] for e in validate_retained(j, allowed)]
    checks['全部原稿对照与8932基线映射可重建'] = not provenance
    checks['保留稿正文未改且每条引文在当前授权来源内'] = not errors
    checks['透明身份假设3489项保持'] = sum(j['identity_contains_inference'] for j in jobs) == sum(j['identity_contains_inference'] for j in identity['jobs']) == 3489
    expected = rows_for_jobs(jobs)
    with (DIRECTORY/'岗位名称与JD表.tsv').open(encoding='utf-8-sig', newline='') as f:
        checks['TSV与主库9字段逐岗一致'] = compare_export(expected, list(csv.reader(f, delimiter='\t')))
    excel_path = DIRECTORY/'全部岗位名称与JD.xlsx'
    checks['Excel与主库9字段逐岗一致'] = compare_export(expected, spreadsheet_rows(excel_path, '岗位名称与JD'))
    by_code = {j['code']: j for j in jobs}
    checks['原授权灯光两岗无职责交叉'] = (not re.search(r'舞台|灯具|施工', by_code['CT205']['jd']) and not re.search(r'渲染|序列|后期软件', by_code['AC435']['jd']))
    checks['结构绘图岗未错贴软件开发'] = not re.search(r'Java|JSP|SQL|代码|软件开发', by_code['DP045']['jd'], re.I) and '结构' in by_code['DP045']['jd']
    checks['影音领班未改成表演或制造岗位'] = by_code['AC205']['jd_profile'] == '影音技术' and '音视频' in by_code['AC205']['jd']
    checks['资产保全未错套设备维修'] = all(j['jd_profile'] == '催收保全' for j in jobs if j['function_name'] == '资产保全')
    checks['新稿无空泛旧任务模板'] = all(not re.search(r'完成相应工作成果|相关岗位落实问题处理及后续工作|基础任务和日常辅助工作|工作计划，组织落实相关任务', j['jd']) for j in jobs if j['jd_review_status'] == '重写')
    paths = [identity_path, master_path, ledger_path, DIRECTORY/'JD审查与编写规则.json', DIRECTORY/'岗位名称与JD表.tsv', excel_path, Path(__file__)]
    return {'reviewer': 'Codex独立产物核验', 'version': final['version'],
            'all_passed': all(checks.values()), 'passed': sum(checks.values()), 'total': len(checks),
            'jobs': len(jobs), 'unique_codes': len(by_code),
            'retained': sum(j['jd_review_status'] == '匹配保留' for j in jobs),
            'rewritten': sum(j['jd_review_status'] == '重写' for j in jobs),
            'checks': checks, 'code_errors': code_errors, 'evidence_errors': errors, 'provenance_errors': provenance,
            'sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in paths},
            'scope_note': '独立核验身份、来源、格式、导出及重点职业边界；检查通过不等同机器已证明全部专业语义。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--write', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = audit()
    data = (json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode()
    path = DIRECTORY/'独立核验报告.json'
    if not result['all_passed']:
        print(data.decode())
        return 1
    if args.check or args.write:
        if path.exists() and path.read_bytes() != data:
            raise ValueError('独立核验报告已有不同内容，请新建版本，不覆盖已有成果。')
        if args.check and not path.exists():
            raise ValueError('缺少独立核验报告')
        if args.write and not path.exists():
            path.write_bytes(data)
    print(json.dumps({k: result[k] for k in ['all_passed', 'passed', 'total', 'jobs', 'unique_codes', 'retained', 'rewritten']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
