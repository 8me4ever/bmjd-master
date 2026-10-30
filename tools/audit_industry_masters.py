"""Independently verify industry subcatalogs against actual parent/source/export data.

Does not import the partitioner or exporter, and does not trust their pass flags.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path

from audit_job_codes import audit_jobs, spreadsheet_rows

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/'行业一级子库_20261029'
MASTER = ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
ROUTES = ROOT/'全量名称代码统一_20261029/来源去向映射.json'
HEADER = ['岗位ID', '岗位代码', '岗位名称', '职能', '职责系列', '层级', '所属子库', '全部适用行业', '岗位JD']


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_rows(jobs, industry):
    return [HEADER] + [[j['id'], j['code'], j['name'], j['function_name'], j['series_name'], str(j['level']),
                       industry, '、'.join(j['industries']), j['jd']] for j in jobs]


def same_table(expected, actual):
    if not actual or actual[0] != expected[0] or len(actual) != len(expected):
        return False
    rows = actual[1:]
    expected_by_id = {r[0]: r for r in expected[1:]}
    return (len({r[0] for r in rows}) == len(expected_by_id)
            and all(r == expected_by_id.get(r[0]) for r in rows))


def verify_child(parent_jobs, child, expected_ids, local_routes, industry):
    original = {j['id']: j for j in parent_jobs}
    jobs = child['jobs']
    ids = {j['id'] for j in jobs}
    local_by_id = {r['source_id']: r for r in local_routes}
    checks, code_errors = audit_jobs(jobs)
    checks = {industry+'：'+name: value for name, value in checks.items()}
    checks[industry+'：仅包含原行业全部应有岗位且无重复'] = len(jobs) == len(ids) and ids == expected_ids
    checks[industry+'：岗位全部原字段与主库逐值相同'] = all(j['id'] in original and set(j) == set(original[j['id']]) | {'industry_membership'} and all(j.get(k) == v for k, v in original[j['id']].items()) for j in jobs)
    checks[industry+'：本地来源未串行业且全量指向该岗位'] = all(
        j['industry_membership'] == {'industry': industry, 'source_ids': sorted(r['source_id'] for r in local_routes if r['state'] != '用户暂缓' and j['id'] in r['target_job_ids'])}
        and j['industry_membership']['source_ids']
        and all(s in local_by_id and local_by_id[s]['industry'] == industry and local_by_id[s]['state'] != '用户暂缓' for s in j['industry_membership']['source_ids']) for j in jobs)
    checks[industry+'：原始来源总账含暂缓记录原样保留'] = child['sources'] == local_routes
    checks[industry+'：子库属性行业与一级层级正确'] = child['tier'] == 1 and child['industry'] == industry
    checks[industry+'：函数与系列仅引用子库内岗位'] = all(s['job_ids'] and len(set(s['job_ids'])) == len(s['job_ids']) and set(s['job_ids']) <= ids for s in child['functions'] + child['series'])
    return checks, code_errors


def audit():
    master = read(MASTER)
    original = master['jobs']
    by_id = {j['id']: j for j in original}
    routes = read(ROUTES)
    industries = sorted(p.stem.removeprefix('2025BMJD-') for p in (ROOT/'原始资料/原版BMJD').glob('*.xlsx'))
    child_paths = sorted(p.parent.name for p in DIRECTORY.glob('*/岗位主库.json'))
    overview = read(DIRECTORY/'子库总览.json')
    overview_by_industry = {r['industry']: r for r in overview['industries']}
    index = read(DIRECTORY/'岗位行业索引.json')
    combined = DIRECTORY/'BMJD_11行业一级子库.xlsx'
    checks = {'原BMJD恰好11个行业且实际子库范围相同': len(industries) == 11 and child_paths == industries,
              '原始来源ID全局唯一': len(routes) == len({r['source_id'] for r in routes}),
              '来源行业与原工作簿及sheet一致': all(r['file'].replace('\\', '/').split('/')[-1] == f"2025BMJD-{r['industry']}.xlsx" and r['range'].startswith(r['industry']+'!') for r in routes)}
    errors = {}
    union_ids = set()
    union_sources = set()
    membership_count = 0
    active_union = set()
    actual_summaries = []
    fingerprint_paths = [MASTER, ROUTES, DIRECTORY/'子库总览.json', DIRECTORY/'岗位行业索引.json', DIRECTORY/'行业划分依据.json', combined, Path(__file__)]
    for industry in industries:
        json_path = DIRECTORY/industry/'岗位主库.json'
        tsv_path = DIRECTORY/industry/'岗位名称代码及JD.tsv'
        excel_path = DIRECTORY/industry/'岗位主库.xlsx'
        child = read(json_path)
        jobs = child['jobs']
        local = [r for r in routes if r['industry'] == industry]
        active = [r for r in local if r['state'] != '用户暂缓']
        expected_ids = {target for r in active for target in r['target_job_ids']}
        child_checks, code_errors = verify_child(original, child, expected_ids, local, industry)
        checks.update(child_checks)
        if any(code_errors.values()):
            errors[industry] = code_errors
        checks[industry+'：父库版本及指纹准确'] = child['parent_version'] == master['version'] and child['parent_master_sha256'] == sha(MASTER)
        checks[industry+'：所属行业与主库适用标签一致'] = all(industry in by_id[j['id']]['industries'] for j in jobs) and expected_ids == {j['id'] for j in original if industry in j['industries']}
        expected = expected_rows(jobs, industry)
        with tsv_path.open(encoding='utf-8-sig', newline='') as f:
            checks[industry+'：TSV与实际子库逐字段一致'] = same_table(expected, list(csv.reader(f, delimiter='\t')))
        checks[industry+'：独立Excel与实际子库逐字段一致'] = same_table(expected, spreadsheet_rows(excel_path, '岗位主库'))
        checks[industry+'：合并Excel与实际子库逐字段一致'] = same_table(expected, spreadsheet_rows(combined, industry))
        summary = child['summary']
        stats = {'industry': industry, 'jobs': len(jobs), 'unique_codes': len({j['code'] for j in jobs}),
                 'functions': len({j['function_id'] for j in jobs}), 'series': len({j['series_id'] for j in jobs}),
                 'original_source_records': len(local), 'active_original_sources': len(active),
                 'paused_original_sources': len(local)-len(active), 'shared_across_industries': sum(len(j['industries'])>1 for j in jobs),
                 'jd_retained': sum(j['jd_review_status'] == '匹配保留' for j in jobs),
                 'jd_rewritten': sum(j['jd_review_status'] == '重写' for j in jobs), 'path': f'{industry}/岗位主库.json'}
        checks[industry+'：总览和子库统计可从实际数据重算'] = summary == overview_by_industry[industry] == stats
        actual_summaries.append(stats)
        union_ids.update(j['id'] for j in jobs)
        union_sources.update(r['source_id'] for r in child['sources'])
        active_union.update(s for j in jobs for s in j['industry_membership']['source_ids'])
        membership_count += len(jobs)
        fingerprint_paths += [json_path, tsv_path, excel_path]
    checks['全部9111主库岗位覆盖无遗漏且不新增'] = len(union_ids) == len(original) == 9111 and union_ids == set(by_id)
    checks['全部19249来源跨行业唯一且总账守恒'] = len(union_sources) == len(routes) == 19249 and sum(r['original_source_records'] for r in actual_summaries) == len(union_sources)
    checks['19226活动来源与23条暂缓范围准确'] = len(active_union) == 19226 and active_union == {r['source_id'] for r in routes if r['state'] != '用户暂缓'} and sum(r['paused_original_sources'] for r in actual_summaries) == 23
    checks['19018行业岗位记录与主库标签组合一致'] = membership_count == sum(len(j['industries']) for j in original) == 19018
    expected_index = [{'job_id': j['id'], 'code': j['code'], 'name': j['name'], 'industries': j['industries'], 'subcatalog_paths': [f'{i}/岗位主库.json' for i in j['industries']]} for j in original]
    checks['全量岗位行业索引逐岗准确'] = index == expected_index
    checks['划分依据列明原11行业且原表实物存在'] = read(DIRECTORY/'行业划分依据.json')['industry_order'] == industries and all((ROOT/f'原始资料/原版BMJD/2025BMJD-{i}.xlsx').exists() for i in industries)
    overview_rows = [['行业', '岗位数', '唯一代码', '职能数', '系列数', '活动来源', '暂缓来源', '跨行业共用岗位', '本行业专属岗位']]
    for i in overview['industries']:
        overview_rows.append([i['industry'], str(i['jobs']), str(i['unique_codes']), str(i['functions']), str(i['series']), str(i['active_original_sources']), str(i['paused_original_sources']), str(i['shared_across_industries']), str(i['jobs']-i['shared_across_industries'])])
    checks['Excel总览与实际岗位及来源统计一致'] = overview_rows == spreadsheet_rows(combined, '子库总览')
    shared_expected = [['岗位ID', '岗位代码', '岗位名称', '职能', '职责系列', '层级', '适用行业', '共用行业数', '岗位JD']] + [[j['id'], j['code'], j['name'], j['function_name'], j['series_name'], str(j['level']), '、'.join(j['industries']), str(len(j['industries'])), j['jd']] for j in original if len(j['industries']) > 1]
    checks['2042共用岗位Excel清单及JD完整'] = len(shared_expected)-1 == 2042 and same_table(shared_expected, spreadsheet_rows(combined, '跨行业共用岗位'))
    checks['主库原始版本指纹等于拆分输入'] = sha(MASTER) == overview['parent_master_sha256'] == read(DIRECTORY/'核验报告.json')['input_sha256'][MASTER.relative_to(ROOT).as_posix()]
    return {'version': overview['version'], 'reviewer': 'Codex独立子库产物核验', 'all_passed': all(checks.values()),
            'passed': sum(checks.values()), 'total': len(checks), 'summary': {'industries': len(industries), 'unique_master_jobs': len(union_ids),
            'industry_job_memberships': membership_count, 'shared_jobs': len(shared_expected)-1, 'changed_names': 0, 'changed_codes': 0, 'changed_jds': 0},
            'checks': checks, 'code_errors': errors, 'sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in fingerprint_paths}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--write', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = audit()
    if not report['all_passed']:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    data = (json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode()
    path = DIRECTORY/'独立核验报告.json'
    if args.write or args.check:
        if path.exists() and path.read_bytes() != data:
            raise ValueError('独立报告已有不同内容，不覆盖。')
        if args.check and not path.exists():
            raise ValueError('缺少独立报告。')
        if args.write and not path.exists():
            path.write_bytes(data)
    print(json.dumps({**report['summary'], 'all_passed': report['all_passed'], 'checks': f"{report['passed']}/{report['total']}"}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
