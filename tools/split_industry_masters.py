"""Partition the reviewed BMJD master into its original 11 industry subcatalogs.

Membership comes from active original source routes, independently compared with
the parent's industry tags. Job identities and all existing JD fields are copied
verbatim. Shared jobs keep the same identity/code in every applicable subcatalog.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / '行业一级子库_20261029'
MASTER = ROOT / '岗位JD匹配审查_20261029/岗位JD主库.json'
ROUTES = ROOT / '全量名称代码统一_20261029/来源去向映射.json'
VERSION = 'BMJD-INDUSTRY-20261029-01'
INDUSTRIES = ('传媒', '制造', '医药', '地产', '教育', '消费品', '物流', '综合服务', '能源化工', '金融', '高科技')
HEADER = ['岗位ID', '岗位代码', '岗位名称', '职能', '职责系列', '层级', '所属子库', '全部适用行业', '岗位JD']


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()


def partition(jobs, routes, industries=INDUSTRIES):
    by_id = {j['id']: j for j in jobs}
    if len(by_id) != len(jobs) or len({j['code'] for j in jobs}) != len(jobs):
        raise ValueError('主库岗位ID或代码不唯一，禁止拆分。')
    if len({r['source_id'] for r in routes}) != len(routes):
        raise ValueError('来源ID重复，禁止拆分。')
    if {r['industry'] for r in routes} - set(industries):
        raise ValueError('来源出现原BMJD 11行业以外的行业。')
    memberships = {i: collections.defaultdict(list) for i in industries}
    expected_sources = collections.defaultdict(set)
    for route in routes:
        if route['state'] == '用户暂缓':
            if route['target_job_ids']:
                raise ValueError('暂缓来源仍指向活动岗位。')
            continue
        if len(set(route['target_job_ids'])) != len(route['target_job_ids']):
            raise ValueError('同来源目标岗位重复。')
        for target in route['target_job_ids']:
            if target not in by_id:
                raise ValueError('来源指向未知主库岗位。')
            memberships[route['industry']][target].append(route['source_id'])
            expected_sources[target].add(route['source_id'])
    for job in jobs:
        industries_from_sources = {i for i, targets in memberships.items() if job['id'] in targets}
        if not industries_from_sources or industries_from_sources != set(job['industries']):
            raise ValueError(f"{job['code']}行业标签与原BMJD活动来源不一致。")
        if expected_sources[job['id']] != set(job['source_ids']) or len(job['source_ids']) != len(set(job['source_ids'])):
            raise ValueError(f"{job['code']}主库来源与来源去向映射不一致。")
    children = {}
    for industry in industries:
        children[industry] = [dict(job, industry_membership={'industry': industry,
                              'source_ids': sorted(memberships[industry][job['id']])})
                              for job in jobs if job['id'] in memberships[industry]]
    return children


def table_rows(jobs, industry):
    return [HEADER] + [[j['id'], j['code'], j['name'], j['function_name'], j['series_name'], str(j['level']),
                       industry, '、'.join(j['industries']), j['jd']] for j in jobs]


def tsv_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')


def build():
    master = read(MASTER)
    routes = read(ROUTES)
    jobs = master['jobs']
    original_paths = [ROOT / f'原始资料/原版BMJD/2025BMJD-{i}.xlsx' for i in INDUSTRIES]
    modified_paths = [ROOT / f'原始资料/最新输入_修改版6/2025BMJD-{i}.xlsx' for i in INDUSTRIES]
    assert {p.stem.removeprefix('2025BMJD-') for p in (ROOT/'原始资料/原版BMJD').glob('*.xlsx')} == set(INDUSTRIES)
    assert all(p.is_file() for p in original_paths + modified_paths)
    children = partition(jobs, routes)
    parent_hash = sha(MASTER)
    files = {}
    summaries = []
    checks = {}
    all_ids = set()
    all_membership_sources = set()
    for industry in INDUSTRIES:
        child_jobs = children[industry]
        ids = {j['id'] for j in child_jobs}
        local_routes = [r for r in routes if r['industry'] == industry]
        active = [r for r in local_routes if r['state'] != '用户暂缓']
        source_ids = {s for j in child_jobs for s in j['industry_membership']['source_ids']}
        all_ids.update(ids)
        all_membership_sources.update(source_ids)
        functions = {}
        for job in child_jobs:
            f = functions.setdefault(job['function_id'], {'id': job['function_id'], 'name': job['function_name'], 'job_ids': []})
            f['job_ids'].append(job['id'])
        series = [dict(s, job_ids=[jid for jid in s['job_ids'] if jid in ids])
                  for s in master['series'] if any(jid in ids for jid in s['job_ids'])]
        summary = {'industry': industry, 'jobs': len(child_jobs), 'unique_codes': len({j['code'] for j in child_jobs}),
                   'functions': len(functions), 'series': len(series), 'original_source_records': len(local_routes),
                   'active_original_sources': len(active), 'paused_original_sources': len(local_routes)-len(active),
                   'shared_across_industries': sum(len(j['industries']) > 1 for j in child_jobs),
                   'jd_retained': sum(j['jd_review_status'] == '匹配保留' for j in child_jobs),
                   'jd_rewritten': sum(j['jd_review_status'] == '重写' for j in child_jobs),
                   'path': f'{industry}/岗位主库.json'}
        summaries.append(summary)
        child = {'version': VERSION, 'tier': 1, 'industry': industry, 'parent_version': master['version'],
                 'parent_master_path': MASTER.relative_to(ROOT).as_posix(), 'parent_master_sha256': parent_hash,
                 'membership_basis': '原BMJD行业活动来源映射；同岗跨行业共享同一名称和代码，不新增行业码。',
                 'summary': summary, 'jobs': child_jobs, 'functions': list(functions.values()), 'series': series,
                 'sources': local_routes}
        files[f'{industry}/岗位主库.json'] = encode(child)
        files[f'{industry}/岗位名称代码及JD.tsv'] = tsv_bytes(table_rows(child_jobs, industry))
        original = {j['id']: j for j in jobs}
        checks[industry+'子库ID代码名称唯一'] = len(child_jobs) == len(ids) == len({j['code'] for j in child_jobs}) == len({j['name'] for j in child_jobs})
        checks[industry+'所有原主库字段逐值不变'] = all(all(j[k] == v for k, v in original[j['id']].items()) and set(j) == set(original[j['id']]) | {'industry_membership'} for j in child_jobs)
        checks[industry+'来源无遗漏且不恢复暂缓'] = source_ids == {r['source_id'] for r in active}
        checks[industry+'系列及职能无子库外岗位引用'] = all(set(s['job_ids']) <= ids and s['job_ids'] for s in series + list(functions.values()))
    index = [{'job_id': j['id'], 'code': j['code'], 'name': j['name'], 'industries': j['industries'],
              'subcatalog_paths': [f'{i}/岗位主库.json' for i in j['industries']]} for j in jobs]
    checks['恰好原BMJD11行业一级子库'] = len(children) == 11 and set(children) == set(INDUSTRIES)
    checks['主库9111岗位全覆盖且无子库额外岗位'] = len(jobs) == len(all_ids) == 9111 and all_ids == {j['id'] for j in jobs}
    checks['19226活动来源全部分配到原行业'] = len(all_membership_sources) == 19226 and all_membership_sources == {r['source_id'] for r in routes if r['state'] != '用户暂缓'}
    checks['23条暂缓来源未形成子库岗位'] = sum(s['paused_original_sources'] for s in summaries) == 23 and not all_membership_sources & {r['source_id'] for r in routes if r['state'] == '用户暂缓'}
    checks['行业分配条数与主库标签组合数一致'] = sum(s['jobs'] for s in summaries) == sum(len(j['industries']) for j in jobs)
    inputs = [MASTER, ROUTES, Path(__file__)] + original_paths + modified_paths
    report = {'version': VERSION, 'parent_version': master['version'], 'all_passed': all(checks.values()),
              'passed': sum(checks.values()), 'total': len(checks), 'summary': {
                  'industry_subcatalogs': len(children), 'master_jobs': len(jobs), 'unique_codes': len({j['code'] for j in jobs}),
                  'industry_job_memberships': sum(s['jobs'] for s in summaries),
                  'shared_jobs': sum(len(j['industries']) > 1 for j in jobs),
                  'single_industry_jobs': sum(len(j['industries']) == 1 for j in jobs),
                  'active_original_sources': len(all_membership_sources), 'paused_original_sources': 23,
                  'missing_master_jobs': len(jobs)-len(all_ids), 'changed_names': 0, 'changed_codes': 0, 'changed_jds': 0},
              'industries': summaries, 'checks': checks,
              'input_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs}}
    basis = {'version': VERSION, 'industry_order': list(INDUSTRIES),
             'policy': ['一级按原BMJD的11个行业划分，不创建新的行业口径。',
                        '以原活动来源定位所属行业，逐岗与现有industry标签交叉核对。',
                        '同岗可属于多个行业，但当前ID、岗位名称、代码、JD及其全部原字段不变。',
                        '子库内一岗一码；跨行业相同代码表示共享同一主库岗位，不是重码。',
                        '原行业未出现的岗位不自行扩配，23条暂缓来源只留总账，不恢复活动岗位。'],
             'references': [{'industry': i, 'original_workbook': original_paths[n].relative_to(ROOT).as_posix(),
                             'latest_workbook': modified_paths[n].relative_to(ROOT).as_posix(),
                             'source_membership': ROUTES.relative_to(ROOT).as_posix()}
                            for n, i in enumerate(INDUSTRIES)]}
    files['子库总览.json'] = encode({'version': VERSION, 'parent_master_sha256': parent_hash, 'summary': report['summary'], 'industries': summaries})
    files['岗位行业索引.json'] = encode(index)
    files['行业划分依据.json'] = encode(basis)
    files['核验报告.json'] = encode(report)
    return files, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--write', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files, report = build()
    if not report['all_passed']:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    if args.write or args.check:
        for name, data in files.items():
            path = DIRECTORY/name
            if path.exists() and path.read_bytes() != data:
                raise ValueError(f'{name}已有不同内容，不覆盖已有工作，请建立下一版本。')
            if args.check and not path.exists():
                raise ValueError('缺少子库文件：'+name)
        if args.write:
            for name, data in files.items():
                path = DIRECTORY/name
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
    print(json.dumps({**report['summary'], 'all_passed': report['all_passed'], 'checks': f"{report['passed']}/{report['total']}"}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
