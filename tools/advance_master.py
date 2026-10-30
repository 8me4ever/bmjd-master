"""Receive the frozen JD submission into a separate, reproducible work version.

No source reassignment or semantic merge is performed by this receiver. Decisions
live in the reviewed batch file; unresolved identities remain explicitly pending.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '主库推定整理_20261029'
VERSION = 'BMJD-WORK-20261029-01'
PINNED = {
    '全库统一完成_20261029/统一主库.json': 'ab972f6c2d6fe0772562f27e95389d2b4c1d9c752be25222305f5208b2cf1ec3',
    '全库统一完成_20261029/岗位JD及条款依据.json': '585ae502a9537d82da4c816e99b0b33e0085c490054734f29a6cd2c4cea4d011',
    '全库统一完成_20261029/规范职能字典.json': 'b9b7747cb7fbdae3823aa826f6dae095aaa527c0f3163c106c7875631ffd548e',
    '双线协作交接_20261029/JD编写输入.json': '048a70dca2176dfb567a4b750554f068d45b6c6f0667419d8ce832999b88a4ef',
    '双线协作交接_20261029/JD原文证据.json': '5541f68e1e97f2145dedb78354c348a20f6ada18e4b88f2d438c7d81afdb3279',
    '双线协作交接_20261029/主库推定整理输入.json': '6f74fbab40ee4ab6e715315249e2de46750a3a23313a02d30e800fbb3b28c400',
    '双线协作交接_20261029/JD回传格式.schema.json': '821b3662d94bd74fa32777dd88aba4a756565c197d6e622084aefe60d12601b7',
    'JD编写_20261029/out/JD回传_常规岗.json': '0ca0cfaf866a76a8cbbfd33cbf8663b642ccedefc6b974de8fd15dc7fc62d1c7',
    '统一收口_20261029/岗位职责原文.json': '48c94f27d707ff33a6dba6f0cd3bbe6be1ebb953ebdfb648e9c9f6c3cc506764',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith('P'))


def render(clauses):
    return '\n'.join(f"{c['number']}、{c['text']}" for c in clauses)


def formatting_key(text):
    lines = []
    for line in text.splitlines():
        # Legacy drafts sometimes contain nested list numbers ("2、2、...").
        previous = None
        while previous != line:
            previous = line
            line = re.sub(r'^\s*\d+\s*[、.．]\s*', '', line)
        lines.append(normalized(line))
    return lines


def literal_quote(quote, original):
    """Return an actual source substring; only inter-character whitespace may vary."""
    require(bool(quote.strip()), '空引文')
    if quote in original:
        return quote
    chars = [re.escape(c) for c in quote if not c.isspace()]
    match = re.search(r'\s*'.join(chars), original)
    require(match is not None, '引文并非原文子串，且不能用空白差异解释')
    return match.group(0)


def validate_clauses(clauses, task, evidence, repairs):
    require(bool(clauses), '空JD')
    require([c['number'] for c in clauses] == list(range(1, len(clauses) + 1)), '条款编号不连续')
    scopes = {s['parent_source_id']: s['original_clauses'] for s in task['role_scoped_evidence']}
    for clause in clauses:
        require(bool(clause['text'].strip()), '空条款')
        require(clause['basis_type'] in ('原文提炼', '专业补写', '规则推定'), '未知依据类型')
        if clause['basis_type'] != '原文提炼':
            require(not clause['source_refs'] and bool(clause['basis_note'].strip()), '补写或推定的依据错误')
            continue
        require(bool(clause['source_refs']), '原文提炼没有引文')
        for ref in clause['source_refs']:
            sid = ref['source_id']
            require(sid in task['source_ids'], '引文来源不属于本岗')
            source = evidence['sources'][sid]
            original = evidence['texts'][source['jd_sha256']]
            actual = literal_quote(ref['quote'], original)
            if actual != ref['quote']:
                repairs.append({'job_id': task['job_id'], 'code': task['baseline_code'],
                                'type': '引文空白校正', 'source_id': sid,
                                'before': ref['quote'], 'after': actual})
                ref['quote'] = actual
            if sid in scopes:
                q = normalized(ref['quote'])
                require(any(q in normalized(a) for a in scopes[sid]), '引文超出该来源分配给本岗的授权条款')


def check_identity(job, task):
    fields = {'id': 'job_id', 'code': 'baseline_code', 'name': 'baseline_name',
              'function_id': 'function_id', 'function_name': 'function_name',
              'classification_series_id': 'series_id', 'classification_series_name': 'series_name',
              'level': 'level', 'source_ids': 'source_ids', 'aliases': 'aliases',
              'role_jd_versions': 'role_scoped_evidence'}
    for current, baseline in fields.items():
        require(job[current] == task[baseline], f"身份字段冲突: {job['id']} {current}")
    require(digest(task['current_jd'].encode()) == task['baseline_jd_sha256'], '基线JD指纹失配')
    require(job['standard_jd'] == task['current_jd'], '当前JD已变化，禁止静默覆盖')


def validate_submission(master, inputs, submission, schema):
    jsonschema.validate(submission, schema)
    for key in ('package_id', 'baseline_version', 'baseline_master_sha256'):
        require(submission[key] == inputs[key], '交接包锚点失配: ' + key)
    jobs = {j['id']: j for j in master['jobs']}
    tasks = {j['job_id']: j for j in inputs['jobs']}
    require(len(jobs) == len(master['jobs']) == len(tasks) == len(inputs['jobs']) == 8932, '岗位全集错误')
    require(jobs.keys() == tasks.keys(), '岗位ID全集不匹配')
    for jid in jobs:
        check_identity(jobs[jid], tasks[jid])
    seen = set()
    for item in submission['jobs']:
        jid = item['job_id']
        require(jid in tasks and jid not in seen, '回传存在未知或重复job_id')
        seen.add(jid)
        task = tasks[jid]
        for key in ('baseline_code', 'baseline_identity_sha256', 'baseline_jd_sha256'):
            require(item[key] == task[key], '回传基线指纹失配: ' + key)
        require(item['writing_status'] in ('已提交', '无需修改-已复核'), '本批回传并非完成状态')
        if item['writing_status'] == '已提交':
            require(4 <= len(item['clauses']) <= 5, '重写稿必须为4—5条')
    require(seen == {j['job_id'] for j in inputs['jobs'] if not j['jd_inferred']}, '常规岗覆盖不完整或混入JD推定岗')
    return jobs, tasks


def reconcile_stage(item, task, baseline_jd):
    """Retain the three separately sourced FS025 clauses missing from the receipt."""
    sid = 'SRC-综合服务-0983'
    extra = {
        2: '1、根据导演的艺术要求能够独立搭建灯光系统，灯光程序设计',
        5: '2、负责完成制定灯光布置方案效果图、施工图设计',
        6: '5、灯光设备的日常维护和保养。',
    }
    require(task['baseline_code'] == 'AC435' and sid in task['source_ids'], '灯光补证目标错误')
    old = baseline_jd['clauses']
    require(len(old) == 6 and len(item['clauses']) == 3, '灯光输入发生变化，需要重新复核')
    result = []
    receipt = iter(item['clauses'])
    for clause in old:
        number = clause['number']
        if number in extra:
            current = {'number': number, 'text': clause['text'], 'basis_type': '原文提炼',
                       'source_refs': [{'source_id': sid, 'quote': extra[number]}],
                       'basis_note': 'Codex接收补证：恢复基线已有、FS025独立支持的条款；不扩张混合来源STAGE授权。'}
        else:
            current = copy.deepcopy(next(receipt))
            require(normalized(current['text']) == normalized(clause['text']), '灯光保留条款正文变化')
            current['number'] = number
            current['text'] = clause['text']
        result.append(current)
    return result


def candidate_scan(jobs):
    """Exact-name and same-series/level candidates only; never a semantic decision."""
    groups = defaultdict(list)
    for job in jobs:
        groups[('同名同层级', normalized(job['name']), job['level'])].append(job)
        groups[('同系列同层级', job['classification_series_id'], job['level'])].append(job)
    result = []
    for key, values in sorted(groups.items(), key=lambda pair: str(pair[0])):
        if len(values) > 1:
            result.append({'type': key[0], 'key': list(key[1:]), 'status': '待语义复核，禁止机械归并',
                           'jobs': [{'job_id': j['id'], 'code': j['code'], 'name': j['name'],
                                     'function': j['function_name']} for j in values]})
    return result


def build():
    for name, expected in PINNED.items():
        require(digest((ROOT / name).read_bytes()) == expected, '冻结输入指纹变化: ' + name)
    master = load(ROOT / '全库统一完成_20261029/统一主库.json')
    inputs = load(ROOT / '双线协作交接_20261029/JD编写输入.json')
    submission = load(ROOT / 'JD编写_20261029/out/JD回传_常规岗.json')
    schema = load(ROOT / '双线协作交接_20261029/JD回传格式.schema.json')
    evidence = load(ROOT / '双线协作交接_20261029/JD原文证据.json')
    baseline_evidence = load(ROOT / '全库统一完成_20261029/岗位JD及条款依据.json')
    decisions = load(OUT / '首批复核决策.json')
    jobs, tasks = validate_submission(master, inputs, submission, schema)
    receipt = {j['job_id']: j for j in submission['jobs']}
    jd_by_id = {j['job_id']: j for j in baseline_evidence}
    reviewed = {d['job_id']: d for d in decisions['identity_reviews']}
    require(len(reviewed) == len(decisions['identity_reviews']), '复核决策ID重复')
    for jid, review in reviewed.items():
        require(jid in jobs and jobs[jid]['inferred_identity'], '复核目标不属于身份推定岗')
        require(review['baseline_code'] == jobs[jid]['code'], '复核目标代码变化')
        require(review['conclusion'] == '继续推定', '首批不允许隐式变更身份')
        for ref in review['evidence']:
            source = evidence['sources'][ref['source_id']]
            require(ref['quote'] in evidence['texts'][source['jd_sha256']], '复核证据不是原文子串')

    mapping, ledger, repairs, changes, impacts, issues = [], [], [], [], [], []
    integrated = held = 0
    for job in master['jobs']:
        jid, task = job['id'], tasks[job['id']]
        job['baseline_inferred_identity'] = job['inferred_identity']
        job['baseline_jd_contains_inference'] = job['jd_contains_inference']
        job['master_review_status'] = '已复核-继续推定' if jid in reviewed else ('待整理' if job['inferred_identity'] else '未列推定，待全库边界复核')
        job['jd_authoring_status'] = receipt[jid]['writing_status'] if jid in receipt else '未提交'
        job['jd_integration_status'] = '未提交，保留基线草稿'
        job['jd_content_review_status'] = '待专业内容审定'
        item = receipt.get(jid)
        record = {'baseline_job_id': jid, 'target_job_ids': [jid], 'baseline_code': job['code'],
                  'current_code': job['code'], 'identity_changed': False,
                  'baseline_identity_sha256': task['baseline_identity_sha256'],
                  'baseline_jd_sha256': task['baseline_jd_sha256'],
                  'submission_sha256': PINNED['JD编写_20261029/out/JD回传_常规岗.json'] if item else None,
                  'received_status': item['writing_status'] if item else '未提交'}
        if item:
            clauses = copy.deepcopy(item['clauses'])
            validate_clauses(clauses, task, evidence, repairs)
            if job['code'] == 'AC435':
                clauses = reconcile_stage(item, task, jd_by_id[jid])
                validate_clauses(clauses, task, evidence, repairs)
                repairs.append({'job_id': jid, 'code': job['code'], 'type': '补回遗漏的独立来源条款',
                                'source_id': 'SRC-综合服务-0983', 'receipt_clauses': 3, 'effective_clauses': 6,
                                'restored_numbers': [2, 5, 6], 'reason': decisions['stage_reconciliation_reason']})
            if jid in reviewed and reviewed[jid]['hold_jd_integration']:
                held += 1
                job['jd_integration_status'] = '暂缓集成-来源身份冲突，保留基线草稿'
                record['reason'] = reviewed[jid]['reason']
                impacts.append({'job_id': jid, 'code': job['code'], 'action': '暂缓本次回填',
                                'reason': reviewed[jid]['reason'], 'source_ids': job['source_ids']})
            else:
                integrated += 1
                before = job['standard_jd']
                effective = render(clauses)
                if item['writing_status'] == '无需修改-已复核':
                    require(formatting_key(before) == formatting_key(effective),
                            '标记保留的回传存在实质增删，必须另行复核: ' + job['code'])
                job['standard_jd'] = effective
                job['standard_jd_version'] = VERSION + ':' + submission['submission_version']
                job['standard_jd_origin'] = '朋友回传；接收时修复见JD接收记录及修复记录'
                job['jd_contains_inference'] = any(c['basis_type'] != '原文提炼' for c in clauses)
                job['jd_integration_status'] = '已集成-工作版，专业内容待审定'
                job['jd_submission_version'] = submission['submission_version']
                job['jd_submission_identity_issue'] = item['identity_issue']
                jd_by_id[jid]['baseline_clauses'] = copy.deepcopy(jd_by_id[jid]['clauses'])
                jd_by_id[jid]['clauses'] = [dict(c, basis=c['basis_note'], inferred=c['basis_type'] != '原文提炼',
                                              source_ids=list(dict.fromkeys(r['source_id'] for r in c['source_refs']))) for c in clauses]
                jd_by_id[jid]['jd_version'] = job['standard_jd_version']
                jd_by_id[jid]['submission_sha256'] = record['submission_sha256']
                if effective != before:
                    changes.append({'job_id': jid, 'code': job['code'], 'name': job['name'],
                                    'type': '正文重写-专业补写待审定' if item['writing_status'] == '已提交' else '标点或编号整理',
                                    'before': before, 'after': effective,
                                    'before_sha256': digest(before.encode()), 'after_sha256': digest(effective.encode())})
            if item['identity_issue']:
                issues.append({'job_id': jid, 'code': job['code'], 'status': '待主库语义复核',
                               'is_confirmed_identity_error': False, 'issue': item['identity_issue']})
        record['integration_status'] = job['jd_integration_status']
        record['current_jd_sha256'] = digest(job['standard_jd'].encode())
        ledger.append(record)
        mapping.append({'baseline_job_id': jid, 'target_job_ids': [jid], 'old_code': job['code'],
                        'new_codes': [job['code']], 'identity_change': False, 'relation': '保留原身份，非语义审定',
                        'jd_reuse_status': '暂缓集成' if '暂缓' in job['jd_integration_status'] else '身份未变可定位接收'})

    # Sources, allocations, role boundaries, codes and identities remain byte-for-byte
    # equivalent as data, including the 23 explicitly paused source records.
    baseline = load(ROOT / '全库统一完成_20261029/统一主库.json')
    require(master['sources'] == baseline['sources'], '来源总账发生变化')
    require(master['functions'] == baseline['functions'] and master['series'] == baseline['series'], '职能或系列意外变化')
    require(len({j['code'] for j in master['jobs']}) == 8932, '代码不唯一')
    require(all(re.fullmatch(r'[A-Z]{2}\d{2}[1-7]', j['code']) and int(j['code'][-1]) == j['level'] for j in master['jobs']), '代码层级错误')
    for job, old in zip(master['jobs'], baseline['jobs']):
        for key in ('id', 'name', 'code', 'aliases', 'level', 'function_id', 'function_name',
                    'classification_series_id', 'classification_series_name', 'source_ids', 'role_jd_versions', 'inferred_identity'):
            require(job[key] == old[key], '意外身份变更: ' + key)
        require(render(jd_by_id[job['id']]['clauses']) == job['standard_jd'], '主库JD与条款依据正文不一致')

    review_queue = []
    for job in master['jobs']:
        if job['baseline_inferred_identity']:
            review_queue.append({'job_id': job['id'], 'code': job['code'], 'name': job['name'],
                                 'master_review_status': job['master_review_status'],
                                 'baseline_identity_sha256': tasks[job['id']]['baseline_identity_sha256'],
                                 'inferred_identity_after': True, 'review': reviewed.get(job['id']),
                                 'source_ids': job['source_ids']})
    candidates = candidate_scan(master['jobs'])
    report = {
        'version': VERSION, 'all_passed': True, 'baseline_jobs': 8932,
        'received_jobs': len(receipt), 'integrated_jobs': integrated, 'held_jobs': held,
        'not_submitted_jobs': 8932 - len(receipt), 'identity_reviews_completed_this_batch': len(reviewed),
        'identity_reviews_pending': len(review_queue) - len(reviewed),
        'identity_inference_jobs': sum(j['inferred_identity'] for j in master['jobs']),
        'jd_inference_jobs': sum(j['jd_contains_inference'] for j in master['jobs']),
        'identity_changes': 0, 'source_records': len(master['sources']),
        'paused_sources': sum(s['state'] == '用户暂缓' for s in master['sources']),
        'identity_issue_records': len(issues), 'candidate_groups': len(candidates),
        'jd_text_changes': len(changes), 'repair_records': len(repairs),
        'full_semantic_review_complete': False, 'jd_professional_review_complete': False,
        'checks': ['冻结输入SHA256', '回传JSON Schema', '全量ID和身份字段', '基线与当前JD冲突检查',
                   '常规岗精确覆盖及基线锚点', '逐条来源原文子串', '按来源检查灯光授权边界',
                   '主库与条款正文一致', '全量身份保持', '来源与授权分配守恒', '代码唯一与层级一致'],
    }
    require((report['received_jobs'], integrated, held, report['not_submitted_jobs']) == (5644, 5643, 1, 3288), '批次数量异常')
    require((len(review_queue), len(master['sources']), report['paused_sources']) == (3092, 19249, 23), '基线数量异常')
    master['baseline_summary'] = master['summary']
    master['summary'] = dict(master['summary'], version=VERSION,
                             jd_inference_jobs=report['jd_inference_jobs'], inferred_jobs=sum(j['inferred_identity'] or j['jd_contains_inference'] for j in master['jobs']),
                             jd_received_jobs=5644, jd_integrated_jobs=integrated,
                             jd_held_jobs=held, jd_not_submitted_jobs=3288,
                             identity_reviewed_jobs=len(reviewed), identity_review_pending_jobs=report['identity_reviews_pending'])
    master['version'] = VERSION
    master['stage'] = '首批JD接收集成及重点身份推定复核；未完成全库语义审定'
    master['baseline_version'] = inputs['baseline_version']
    master['original_jd_pool'] = '../统一收口_20261029/岗位职责原文.json'
    master['input_sha256'] = PINNED
    result = {
        '统一主库.json': master,
        '岗位JD及条款依据.json': list(jd_by_id.values()),
        '规范职能字典.json': master['functions'],
        '基线到当前ID映射.json': mapping,
        'JD接收记录.json': ledger,
        '接收修复及正文变更.json': {'repairs': repairs, 'jd_changes': changes},
        '身份推定结论台账.json': review_queue,
        '受影响JD清单.json': impacts,
        '朋友身份问题线索.json': issues,
        '全库相邻冲突候选.json': {'scope': '同名同层级及同系列同层级候选扫描；不代表语义检查完成', 'groups': candidates},
        '核验报告.json': report,
        '输入指纹.json': {'version': VERSION, 'files': PINNED, 'review_decisions_sha256': digest((OUT / '首批复核决策.json').read_bytes())},
    }
    return result


def save_outputs(outputs, check=False, directory=OUT):
    encoded = {name: (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode() for name, data in outputs.items()}
    # Preflight the whole batch before touching any output. An existing work
    # version may never be silently replaced, including on a normal rerun.
    for name, data in encoded.items():
        path = directory / name
        if path.exists():
            require(path.read_bytes() == data, '工作版本已修改，禁止覆盖；请另建新版本: ' + name)
        else:
            require(not check, '缺少输出: ' + name)
    if not check:
        directory.mkdir(parents=True, exist_ok=True)
        for name, data in encoded.items():
            path = directory / name
            if not path.exists():
                path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs = build()
    save_outputs(outputs, check=args.check)
    print(json.dumps(outputs['核验报告.json'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, jsonschema.ValidationError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
