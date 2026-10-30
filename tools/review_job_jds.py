"""Review current name/code identities against legacy JDs; stdlib, immutable inputs.

The editorial profiles are explicit, inspectable professional writing decisions, not
a semantic similarity model. Matching is deliberately conservative: ambiguous,
generic, split-identity and unsupported legacy drafts are rewritten and labelled as
new professional content. No claim of sentence-by-sentence manual review is made.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / '岗位JD匹配审查_20261029'
RULES = DIRECTORY / 'JD审查与编写规则.json'
INPUTS = [
    ROOT / '全量名称代码统一_20261029/名称代码主库.json',
    ROOT / '全量名称代码统一_20261029/基线ID名称代码映射.json',
    ROOT / '全量名称代码统一_20261029/来源去向映射.json',
    ROOT / '双线协作交接_20261029/JD编写输入.json',
    ROOT / '双线协作交接_20261029/JD原文证据.json',
    ROOT / '主库推定整理_20261029/岗位JD及条款依据.json',
    ROOT / '主库推定整理_20261029/基线到当前ID映射.json',
    RULES,
    Path(__file__),
]
GENERIC = re.compile(
    r'具体任务，完成相应工作成果|基础任务和日常辅助工作|相关岗位落实问题处理及后续工作'
    r'|工作计划，组织落实相关任务|整理工作资料和记录，及时反馈|检查相关资料和工作成果'
    r'|整理相关资料和工作记录|配合相关岗位完成职责范围内|建立和优化.{0,30}工作流程，协调相关岗位'
    r'|检查工作成果，整理和分析工作情况|整理工作记录，协助改进相关工作流程')
NOISE = re.compile(r'其他任务|其它任务|其他工作|其它工作|领导交办|上级交办|服从.{0,6}安排')
QUALIFICATION = re.compile(r'(?:具备|具有|有).{0,18}(?:能力|经验)|熟练掌握|专业优先|学历|工作经验|任职资格|持有.{0,8}证书')
INDUSTRY = re.compile(r'摩托车|房地产集团|地产集团|本公司|本集团|总部.{0,8}规定|总经理领导下|财务部门的要求')
OVERREACH = re.compile(r'全面负责|统筹|主导|审批|批准|战略方向|招聘.{0,4}决策|监督.{0,6}部门|团队.{0,4}管理')


def read(path):
    return json.loads(path.read_text('utf-8'))


def encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text)
                   if not c.isspace() and unicodedata.category(c) != 'Cf').casefold()


def identity_name(name):
    return normalized(re.sub(r'[（(][^（）()]*[1-7]级[）)]', '', name))


def choose_profile(job, rules):
    code = job['code']
    if code in rules['exact_code_profiles']:
        return rules['exact_code_profiles'][code], '逐码边界决定'
    title = job['name'] + '\n' + job['series_name']
    for rule in rules['role_rules']:
        if 'functions' in rule and job['function_name'] not in rule['functions']:
            continue
        if re.search(rule['pattern'], title, re.I):
            return rule['profile'], '岗位名称规则：' + rule['pattern']
    return rules['function_profiles'][job['function_name']], '职能及职责系列范围'


def role_mode(job):
    title = re.sub(r'[（(][^（）()]*[1-7]级[）)]', '', job['name'])
    if re.search(r'助理|助教|初级|初中级|学徒|见习|实习|后备|储备', title):
        return '辅助或初级'
    if re.search(r'总经理|副总(?!工程师)|总监|经理|主管(?!医师|药师|护师)|组长|班长|领班|队长|部长|处长|科长|校长|园长|店长|矿长|行长|院长|负责人|护士长|护理部|主任(?!医师|药师|护师|工程师|设计师)|董事会秘书|首席.{0,8}官|监事会主席|总裁|书记', title):
        return '管理'
    if re.search(r'高级|资深|专家|首席|主任医师|副主任医师|主任药师|总工程师|总建筑师|总设计师', title):
        return '资深专业'
    return '专业执行'


def subject(job):
    value = re.sub(r'[（(][^（）()]*[1-7]级[）)]', '', job['series_name'])
    value = re.sub(r'（[^（）]*）', '', value).strip('/（( ')
    # Titles in old series names are labels, not entities on which to perform work.
    value = re.sub(r'^(首席|高级|初级|资深|总)', '', value)
    value = re.sub(r'(副主任医师|主任医师|主治医师|住院医师|医师|医生|教师|讲师|导师|工程师|设计师|专员|经理|主管|总监|组长|科长|部长|处长|管理经理)$', '', value)
    return value or job['function_name']


def render_new(job, profile):
    scope = subject(job)
    texts = [t.format(subject=scope) for t in profile['clauses']]
    if not any('{subject}' in t for t in profile['clauses']):
        # Preserve the distinct professional object even when several series share
        # common core actions (e.g. life vs property insurance underwriting).
        texts[0] = f'围绕{scope}职责，' + texts[0]
    mode = role_mode(job)
    if mode == '辅助或初级':
        # Scope and actions stay professional; authority and responsibility are limited.
        texts = ['在指导下，配合' + t[2:] if t.startswith('组织') else '在指导下，' + t for t in texts]
    elif mode == '管理':
        texts.insert(0, f'统筹{scope}工作，明确目标与人员分工，协调资源并检查工作质量。')
    elif mode == '资深专业':
        texts.append(f'分析{scope}中的复杂专业问题，复核关键成果并提供技术或专业指导。')
    return [{'number': i, 'text': t, 'basis_type': '专业补写', 'source_refs': [],
             'basis_note': '依据当前岗位名称、职责系列、职能及明确专业职责框架重新编写；不冒充原文摘录。'}
            for i, t in enumerate(texts, 1)]


def has_any(text, terms):
    text = text.casefold()
    return any(t.casefold() in text for t in terms)


def semantic_problems(job, texts, profile_key, profile):
    reasons = []
    body = '\n'.join(texts)
    # Lexical coverage is only a traceable screening signal. It must not, by
    # itself, cause a matching legacy JD to be rewritten (project handoff rule).
    if GENERIC.search(body):
        reasons.append('旧稿含空泛任务模板，缺少岗位核心职责')
    if len(texts) < 2 or sum(len(t) for t in texts) < 35:
        reasons.append('原稿职责信息不足')
    if QUALIFICATION.search(body):
        reasons.append('职责混入任职资格或能力要求')
    if INDUSTRY.search(body):
        reasons.append('含特定企业或单一行业情境，需通用化')
    if re.search(r'\d+、.+\d+、|I88|室卫|较色|\bJSP\b|\bSQL\b', body) and profile_key == '建筑结构':
        reasons.append('建筑结构名称与原软件或异常拼贴内容不符')
    if role_mode(job) == '辅助或初级' and OVERREACH.search(body):
        reasons.append('原稿超出辅助或初级岗位职责边界')
    if role_mode(job) == '管理' and not re.search(r'计划|组织|协调|管理|统筹|监督|指导|检查|目标|安排', body):
        reasons.append('缺少名称要求的组织管理职责')
    if profile_key in {'临床医生', '药师', '医学检验', '医学影像'} and role_mode(job) != '管理' and re.search(r'领导所属人员|全面负责.{0,12}管理|团队管理|业绩考核|人员配置|招聘.{0,6}计划', body):
        reasons.append('原稿将专业职称写成部门经营或人事管理岗位')
    if profile_key == '临床医生' and not re.search(r'接诊|诊断|诊疗|治疗|病历|查房|体格检查', body):
        reasons.append('医师名称与仅导诊或服务内容不匹配')
    if profile_key == 'CG渲染' and re.search(r'舞台|施工|灯具|布光经验', body):
        reasons.append('数字渲染稿混入实物舞台职责')
    if profile_key == '舞台灯光' and re.search(r'提交渲染|后期软件|序列|三维场景', body):
        reasons.append('实物灯光稿混入数字渲染职责')
    if profile_key == '软件测试' and not re.search(r'软件|接口|代码|用例|缺陷|脚本|黑盒|白盒|自动化', body):
        reasons.append('软件测试稿缺少软件验证对象')
    if profile_key in {'工程设计', '建筑结构', '总图'} and re.search(r'代码实现|Java|JSP|SQL|软件开发', body, re.I):
        reasons.append('工程设计稿混入软件开发职责')
    if profile_key == '结构设计' and not re.search(r'结构|机械|零件|装配|图纸|三维|建模|设计', body):
        reasons.append('实物结构设计稿缺少结构设计工作')
    if profile_key in {'音响录音', '视频后期', '表演', '服化道', '播控', '舞台灯光'} and re.search(r'汽车零部件|发动机装配|机械零件|车间生产|生产采购', body) and not re.search(r'拍摄|节目|音频|音响|舞台|视频|影视|演出|服装|道具|播控', body):
        reasons.append('文艺制作岗位错贴制造生产职责')
    if profile_key == '临床医生' and re.search(r'药品调配|药品采购|处方调剂|药库管理', body) and not re.search(r'患者|病历|诊疗|接诊|查房', body):
        reasons.append('临床医师岗位错贴药事供应职责')
    if profile_key == 'IT运维' and re.search(r'日活|粉丝|内容发布|社群运营|商品促销', body) and not re.search(r'服务器|系统维护|故障|网络维护|数据库|部署', body):
        reasons.append('IT运行岗位错贴内容或用户运营职责')
    return list(dict.fromkeys(reasons))


def format_jd(clauses):
    return '\n'.join(f"{c['number']}、{c['text']}" for c in clauses)


def export_tsv(jobs):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
    writer.writerow(['岗位ID', '岗位代码', '岗位名称', '职能', '职责系列', '层级', '审查处置', '原因', '最终JD'])
    for j in jobs:
        writer.writerow([j['id'], j['code'], j['name'], j['function_name'], j['series_name'],
                         j['level'], j['jd_review_status'], '；'.join(j['jd_review_reasons']), j['jd']])
    return stream.getvalue().encode('utf-8-sig')


def build():
    master, mappings, source_routes, handoff, evidence, received, received_mapping, rules = map(read, INPUTS[:-1])
    old = {j['job_id']: j for j in handoff['jobs']}
    received_by_id = {j['job_id']: j for j in received}
    received_routes = {v['baseline_job_id']: v['target_job_ids'] for v in received_mapping}
    origins = collections.defaultdict(list)
    for row in mappings:
        for target in row['target_job_ids']:
            origins[target].append(row['baseline_job_id'])
    current_sources = {v['source_id']: v for v in source_routes if v['state'] != '用户暂缓'}
    result = []
    ledger = []
    for job in master['jobs']:
        key, selection = choose_profile(job, rules)
        profile = rules['profiles'][key]
        sids = set(job['source_ids'])
        allowed = {}
        scoped = []
        for bid in origins[job['id']]:
            scoped += [x for x in old[bid]['role_scoped_evidence'] if x['parent_source_id'] in sids]
        # Source-level authorizations remain tied to STAGE vs CG even after ID changes.
        for sid in sorted(sids):
            authorized = [x for x in scoped if x['parent_source_id'] == sid and
                          x['role'] == ('CG' if job['code'] == 'CT205' else 'STAGE')]
            allowed[sid] = '\n'.join(x['text'] for x in authorized) if authorized else evidence['texts'][evidence['sources'][sid]['jd_sha256']]
            if sid in rules['role_scoped_sources']:
                assert authorized, (job['code'], sid, 'Missing authorized source role')
        candidates = []
        for bid in sorted(origins[job['id']]):
            baseline = old[bid]
            ids = received_routes[bid]
            prior = received_by_id[ids[0]] if len(ids) == 1 and ids[0] in received_by_id else None
            clauses = prior['clauses'] if prior else baseline['current_clause_evidence']
            texts = [c['text'] for c in clauses]
            reasons = semantic_problems(job, texts, key, profile)
            names = {identity_name(x) for x in [job['name']] + job['aliases']}
            if identity_name(baseline['baseline_name']) not in names:
                reasons.append('原稿岗位名称与当前标准身份不一致')
            if baseline['function_id'] != job['function_id']:
                reasons.append('原稿职能与当前职能不同')
            if not set(baseline['source_ids']) <= sids:
                reasons.append('旧身份已拆分，原稿含其他当前岗位的来源')
            if len(origins[job['id']]) > 1:
                reasons.append('当前岗位归并多个旧身份，需重组共性职责')
            if baseline['jd_inferred']:
                reasons.append('原JD含补写或规则推定，重新编写专业核心职责')
            preserved = []
            for index, c in enumerate(clauses, 1):
                refs = c.get('source_refs', [])
                valid = [ref for ref in refs if ref.get('source_id') in allowed and ref.get('quote') and ref['quote'] in allowed[ref['source_id']]]
                if not valid or len(valid) != len(refs) or c.get('inferred') or c.get('basis_type') not in {'原文提炼'}:
                    reasons.append('原稿条款证据无法全部在当前授权来源内验证')
                preserved.append({'number': index, 'text': c['text'], 'basis_type': c.get('basis_type', '原文提炼'),
                                  'source_refs': valid, 'basis_note': c.get('basis_note', '当前来源核对后保留原稿')})
            candidates.append({'baseline_job_id': bid, 'old_code': baseline['baseline_code'],
                               'old_name': baseline['baseline_name'], 'old_jd': format_jd(clauses),
                               'lexical_signal': '低覆盖，仅作线索，不单独触发改写' if sum(has_any(t, profile['object_terms']) and has_any(t, profile['action_terms']) for t in texts) < 2 else '工作对象及行动词有覆盖',
                               'reasons': list(dict.fromkeys(reasons)), 'clauses': preserved})
        safe = next((c for c in candidates if not c['reasons']), None)
        if safe:
            clauses = safe['clauses']
            status = '匹配保留'
            reasons = ['原稿名称、职能、专业工作及职责范围一致，逐条来源可核验']
        else:
            clauses = render_new(job, profile)
            status = '重写'
            reasons = list(dict.fromkeys(x for c in candidates for x in c['reasons'])) or ['当前独立身份无可安全复用的原JD']
        item = dict(job, jd=format_jd(clauses), jd_clauses=clauses, jd_review_status=status,
                    jd_review_reasons=reasons, jd_profile=key, jd_role_mode=role_mode(job),
                    jd_version=rules['version'])
        result.append(item)
        ledger.append({'job_id': job['id'], 'code': job['code'], 'name': job['name'],
                       'function_name': job['function_name'], 'series_id': job['series_id'],
                       'profile': key, 'profile_selection': selection, 'role_mode': role_mode(job),
                       'status': status, 'reasons': reasons,
                       'legacy_candidates': [{k: v for k, v in c.items() if k != 'clauses'} for c in candidates],
                       'current_source_ids': job['source_ids'],
                       'source_evidence': [{'source_id': sid, 'jd_sha256': evidence['sources'][sid]['jd_sha256'],
                                            'authorized_quote': allowed[sid][:160]} for sid in sorted(sids)],
                       'role_scoped_evidence': scoped,
                       'new_jd': item['jd'], 'new_jd_sha256': digest(item['jd'].encode()),
                       'content_basis': '原稿逐条原文核验' if safe else 'Codex按名码及专业职责框架补写，非原文复述'})
    counts = collections.Counter(j['jd_review_status'] for j in result)
    checks = {
        '全部9111岗位覆盖且ID代码名称唯一': len(result) == 9111 == len({j['id'] for j in result}) == len({j['code'] for j in result}) == len({j['name'] for j in result}),
        '原名码主库全部字段保持不变': all(all(j[k] == original[k] for k in original) for j, original in zip(result, master['jobs'])),
        '263职能均有显式专业规则': set(rules['function_profiles']) == {j['function_name'] for j in result},
        '全部岗位有JD及最终处置': all(j['jd'] and j['jd_review_status'] in {'匹配保留', '重写'} for j in result),
        '全部新稿4至5条': all(len(j['jd_clauses']) in {4, 5} for j in result if j['jd_review_status'] == '重写'),
        '全部条款顺序编号且格式正确': all([c['number'] for c in j['jd_clauses']] == list(range(1, len(j['jd_clauses'])+1)) and j['jd'] == format_jd(j['jd_clauses']) for j in result),
        '新稿无空泛旧模板或任职资格': all(not GENERIC.search(j['jd']) and not QUALIFICATION.search(j['jd']) for j in result if j['jd_review_status'] == '重写'),
        '新稿补写来源不伪造': all(c['basis_type'] == '专业补写' and not c['source_refs'] for j in result if j['jd_review_status'] == '重写' for c in j['jd_clauses']),
        '保留稿无筛查问题': all(not semantic_problems(j, [c['text'] for c in j['jd_clauses']], j['jd_profile'], rules['profiles'][j['jd_profile']]) for j in result if j['jd_review_status'] == '匹配保留'),
        '无暂缓来源恢复': all(sid in current_sources for j in result for sid in j['source_ids']),
        '全部8932旧ID有审查记录': set(old) == {c['baseline_job_id'] for r in ledger for c in r['legacy_candidates']},
        '主库与台账逐岗JD相同': all(j['id'] == r['job_id'] and j['jd'] == r['new_jd'] for j, r in zip(result, ledger)),
        '改写专业框架均为四条实质职责': all(len(p['clauses']) == 4 and p['object_terms'] and p['action_terms'] for p in rules['profiles'].values()),
    }
    bycode = {j['code']: j for j in result}
    checks['DP045保留结构身份且不含软件职责'] = bycode['DP045']['jd_profile'] == '建筑结构' and not re.search(r'Java|SQL|JSP|代码|软件', bycode['DP045']['jd'], re.I)
    checks['灯光两岗保持授权专业边界'] = bycode['CT205']['jd_profile'] == 'CG渲染' and bycode['AC435']['jd_profile'] == '舞台灯光' and not re.search(r'舞台|灯具|布光经验', bycode['CT205']['jd']) and not re.search(r'渲染|序列|后期软件', bycode['AC435']['jd'])
    checks['配货主管与助理层级不串岗'] = bycode['LO304']['jd_role_mode'] == '管理' and bycode['LO306']['jd_role_mode'] == '辅助或初级'
    report = {'version': rules['version'], 'reviewer': 'Codex',
              'method': '全量来源及身份追溯、显式专业规则筛查、按岗位名称分级补写、重点边界案例自审；不将关键词命中称为逐句人工语义审定。',
              'summary': {'jobs': len(result), 'retained': counts['匹配保留'], 'rewritten': counts['重写'],
                          'unprocessed': len(result) - sum(counts.values()), 'functions': len(rules['function_profiles']),
                          'editorial_profiles': len(rules['profiles']), 'series': len(master['series']),
                          'new_clause_counts': dict(sorted(collections.Counter(len(j['jd_clauses']) for j in result if j['jd_review_status'] == '重写').items())),
                          'identity_inferences_preserved': sum(j['identity_contains_inference'] for j in result)},
              'all_passed': all(checks.values()), 'passed': sum(checks.values()), 'total': len(checks), 'checks': checks,
              'reason_counts': dict(collections.Counter(x for j in result if j['jd_review_status'] == '重写' for x in j['jd_review_reasons']).most_common()),
              'input_sha256': {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in INPUTS},
              'limitations': ['本版为通用职责主库，不新增企业授权、执业范围或任职资格。',
                              '专业补写依据明确标注；保留身份假设及原稿，不以JD反向更改名称或代码。']}
    combined = dict(master, version=rules['version'], name_code_version=master['version'],
                    phase='岗位名称与JD匹配审查及通用职责改写', summary=report['summary'], jobs=result)
    series_rows = []
    for s in master['series']:
        jobs = [bycode[j['code']] for j in master['jobs'] if j['series_id'] == s['id']]
        series_rows.append({'series_id': s['id'], 'function_name': s['function_name'], 'series_name': s['name'],
                            'jobs': [{'code': j['code'], 'name': j['name'], 'profile': j['jd_profile'], 'role_mode': j['jd_role_mode'], 'status': j['jd_review_status']} for j in jobs]})
    return {'岗位JD主库.json': encode(combined), '逐岗JD审查台账.json': encode(ledger),
            '职责系列审查目录.json': encode(series_rows), '岗位名称与JD表.tsv': export_tsv(result),
            '核验报告.json': encode(report)}, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true')
    group.add_argument('--write', action='store_true')
    args = parser.parse_args()
    files, report = build()
    if not report['all_passed']:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    if args.write or args.check:
        # Validate the entire output transaction before writing any file.
        for name, data in files.items():
            path = DIRECTORY/name
            if path.exists() and path.read_bytes() != data:
                raise ValueError(f'{name}已有不同内容，请新建版本；不覆盖已有工作。')
            if args.check and not path.exists():
                raise ValueError(f'缺少输出：{name}')
        if args.write:
            for name, data in files.items():
                path = DIRECTORY/name
                if not path.exists():
                    path.write_bytes(data)
    print(json.dumps({**report['summary'], 'all_passed': report['all_passed'], 'checks': f"{report['passed']}/{report['total']}"}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
