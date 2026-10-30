"""Unify every source-backed role's name/code, without using JD content.

The result is a complete rules-based work catalog, with source-specific evidence
and explicit inference assumptions, rather than a claim of expert JD review.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import name_code_master as prior

ROOT = prior.ROOT
OUT = ROOT / '全量名称代码统一_20261029'
VERSION = 'BMJD-NAME-CODE-20261029-ALL'
PREVIOUS = prior.OUT / '名称代码主库.json'
RESEARCH = {'研发', '软件开发', '设计研发', '产品研发', '药品研发'}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def clean(value):
    value = unicodedata.normalize('NFKC', value).strip()
    value = re.sub(r'\s+', '', value)
    value = value.replace('构架', '架构').replace('工程工程师', '工程师')
    value = value.replace('人事', '人力资源').replace('客诉处理', '客户投诉')
    value = value.replace('方案解决', '解决方案').replace('剪切切割', '剪切/切割')
    value = value.replace('国际贸易跟单', '外贸跟单').replace('稽核审计', '内部审计').replace('内审', '内部审计')
    value = value.replace('主管会计', '会计主管').replace('初级筹建工程', '初级筹建工程师') if value == '初级筹建工程' else value.replace('主管会计', '会计主管')
    value = re.sub(r'应收/应付', '应收应付', value)
    value = re.sub(r'高级程序员\(([^()]+)\)', r'高级\1开发工程师', value, flags=re.I)
    value = re.sub(r'初级程序员\(([^()]+)\)', r'初级\1开发工程师', value, flags=re.I)
    value = re.sub(r'程序员\(([^()]+)\)', r'\1开发工程师', value, flags=re.I)
    for pattern, replacement in [(r'android', 'Android'), (r'tensorflow', 'TensorFlow'), (r'\bpack\b', 'PACK'),
                                  (r'linux', 'Linux'), (r'python', 'Python'), (r'delphi', 'Delphi'),
                                  (r'java', 'Java'), (r'\.net', '.NET'), (r'php', 'PHP'), (r'ios', 'iOS')]:
        value = re.sub(pattern, replacement, value, flags=re.I)
    value = value.replace('网站UI设计', 'UI设计').replace('平面设计师(市场)', '平面设计师')
    value = value.replace('平面设计经理(市场)', '平面设计经理').replace('平面设计助理(市场)', '平面设计助理')
    # Spaces/bracket variants in originals are recorded separately. Display uses
    # consistent full-width parentheses while retaining technical slash/plus.
    return value.replace('(', '（').replace(')', '）')


def key(value):
    return clean(value).casefold()


def generic_test_title(title):
    return re.fullmatch(r'(?:资深|高级|中级|初级|助理)?测试(?:经理|主管|专员|助理|工程师)', title) is not None


def test_scope_title(title, metadata, current):
    if not generic_test_title(title):
        return title, False
    fine = clean(metadata['最新输入_修改版6']['specialty'])
    scope = next((s for s in ('软件测试', '产品测试', '设备测试', '硬件测试', '网络测试') if s in fine), None)
    inferred = False
    if scope is None:
        scope = {'RB11': '软件测试', 'TE02': '软件测试', 'AK02': '产品测试'}.get(current['series_prefix'])
        inferred = scope is not None
    # A scoped spelling is an explicit metadata/family work assumption. It
    # prevents a generic "测试工程师" alias from joining software and product
    # testing transitively. The original unqualified name remains in evidence.
    return (title.replace('测试', scope, 1) if scope else title), inferred


def metadata_all(baseline):
    cache, hashes, records, differences = {}, {}, [], []
    for source in baseline['sources']:
        if source['state'] == '用户暂缓':
            continue
        sid = source['source_id']
        row = int(re.search(r'!B(\d+):', source['range']).group(1))
        record = {'source_id': sid}
        for folder in ('原版BMJD', '最新输入_修改版6'):
            relative = f'原始资料/{folder}/2025BMJD-{source["industry"]}.xlsx'
            if relative not in cache:
                cache[relative] = prior.metadata_rows(ROOT / relative, source['industry'])
                hashes[relative] = prior.sha(ROOT / relative)
            values = cache[relative].get(row)
            need(values is not None and values[1] and values[2], '原表行缺失: ' + sid)
            record[folder] = {'file': relative, 'sheet': source['industry'], 'row': row,
                              'code': values[1], 'name': values[2], 'system': values[3],
                              'function': values[4], 'specialty': values[5], 'industry_tag': values[6]}
        old, current = record['原版BMJD'], record['最新输入_修改版6']
        need((clean(current['code']), clean(current['name'])) ==
             (clean(source['source_code']), clean(source['source_name'])), '定位不匹配，禁止按同码误接: ' + sid)
        if (current['code'], current['name']) != (source['source_code'], source['source_name']):
            differences.append({'source_id': sid, 'type': '空白规范化', 'raw': [current['code'], current['name']],
                                'ledger': [source['source_code'], source['source_name']], 'decision': '保留原值，名称规范化后承接'})
        if prior.title_key(old['name']) != prior.title_key(current['name']):
            differences.append({'source_id': sid, 'type': '原版到修改版名称修订', 'before': old, 'after': current,
                                'decision': '采用修改版6当前名称；原名原码保留，非定位错误'})
        records.append(record)
    need(len(records) == 19226 and len(cache) == 22, '全库原表提取不完整')
    return records, hashes, differences


def route_function(title, metadata, current):
    """Auditable metadata/title rules; no JD text is accepted by this function."""
    original = metadata['原版BMJD']['function']
    specialty = clean(metadata['最新输入_修改版6']['specialty'])
    if generic_test_title(title) or current['series_prefix'] in ('RB11', 'TE02', 'AK02'):
        return '测试', '按原名称/原细分确定测试专业；软件、产品等对象分别保留，不经泛称串岗'
    rules = [
        (r'原料血浆开发', '药品研发', '原名原料血浆开发及原版药品研发类型'),
        (r'门店财务|门店会计', '财务', '原名明确为财务/会计，不按门店部门归人力资源'),
        (r'营养师', '临床科室', '原名营养师及原版临床科室/营养细分'),
        (r'驻店药师', '医技科室', '原名药师为药学专业服务，门店作为场景标签'),
        (r'空间设计', '空间设计', '设计专业名称，不与店面工程施工混岗'),
        (r'用户体验|UED|交互设计', '用户体验', '原名明确用户体验/交互专业'),
        (r'UI设计', '美工', '原名UI设计与UI程序开发分开'),
        (r'云安全|网络安全|信息安全', '信息安全', '原名为信息系统安全，不并售前或现场EHS'),
        (r'软件测试', '测试', '软件测试保留测试专业对象，不作为软件编写岗位'),
        (r'软件|程序员|Java|Python|C\+\+|C#|\.NET|Delphi|PHP|Android|iOS|TensorFlow|Linux|UI开发|前端开发|WEB开发|虚幻|framework|数据库开发|数据仓库开发|数据开发|DMP研发', '软件开发', '原名包含明确软件/语言/平台开发对象'),
        (r'结构组装工艺', '研发', '原版研发及实物结构组装工艺，非软件开发'),
        (r'生产设备统计|生产统计', '生产管理', '原名明确生产统计，不并设备资产管理'),
        (r'内部审计', '审计', '内部审计为审计专业，不按财务部门另建身份'),
        (r'仓储', '仓储', '原名仓储专业，物流部门不形成第二身份'),
        (r'产品项目', '项目管理', '原名产品项目管理，非工程建设施工身份'),
        (r'厨师|厨工', '厨房', '烹饪职业按同一厨房专业归一，不因行政/会所/餐饮旧部门重复建岗'),
        (r'保安|门卫', '秩序保护', '安保职业按原名归秩序保护，不以所属部门重复建岗'),
        (r'运输司机', '运输', '运输司机按同一运输专业归一'),
        (r'收银', '门店', '收银按同一收银业务归一，主管/领班/收银员分职务保留'),
        (r'经销商管理', '销售管理', '按原名经销商管理对象归销售管理，不把渠道管理一律称为电商平台运营'),
    ]
    for pattern, function, reason in rules:
        if re.search(pattern, title, re.I):
            return function, reason
    if re.match(r'^(?:资深|高级|中级|初级|助理)?算法(?:经理|主管|专员|助理|工程师)', title):
        return '研发', '泛算法原名及原细分一致，取消旧研发/软件分叉；特定产品算法另保留'
    if re.match(r'^(?:资深|高级|中级|初级|助理)?研发(?:经理|主管|专员|助理|工程师)', title):
        return '研发', '原名为通用研发，无软件对象证据时不自动归软件开发'
    if '架构设计' in title and '软件' not in title:
        return '研发', '泛架构设计按相同原名和细分归一，不擅加软件限定'
    if '结构设计' in title and current['function_name'] in ('软件开发', '研发', '设计研发', '规划设计'):
        return ('规划设计' if original == '规划设计' else '设计研发'), '结构设计按原版专业范围归类，不因错贴JD变成软件'
    if re.match(r'^投资(?:管理)?(?:副总经理|总监|经理|主管|专员|助理)$', title):
        return '投资业务', '投资/投资管理同级按同一职业工作归并；旧部门不另拆岗，保留范围推定'
    if '垃圾分类' in title:
        return '物业管理', '按地产行业及垃圾分类现场管理名称作物业管理工作推定'
    if title.startswith('内部统计') and current['series_prefix'] == 'AF11':
        return '生产管理', '原生产统计来源从设备管理混合组拆出，内部统计归属保留工作推定'
    if '设备管理' in title and current['series_prefix'] in ('AF11', 'ET01'):
        return '设备工程', '原名设备管理与设备维修专业分开'
    if current['series_prefix'] == 'OA21' and re.search(r'工程维修|物业工程', title):
        return '物业工程', '行政/物业旧部门的同名设施工程维修统一到物业工程专业'
    if re.match(r'^项目(?:管理)?(?:经理|主管|专员|助理)$', title):
        return '项目管理', '原名通用项目管理不加JD派生营销或建设限定'
    return current['function_name'], '保留已建专业分类；本轮原表名码证据未提供更明确的改类依据，分类为工作承接'


def contextual_title(title, metadata, current):
    specialty = clean(metadata['最新输入_修改版6']['specialty'])
    if re.fullmatch(r'项目(?:管理)?(?:经理|主管|专员|助理)', title):
        title = title.replace('项目管理', '项目')
        if '职业教育' in specialty:
            return '职业教育' + title
        return title.replace('项目', '项目管理', 1)
    if current['series_prefix'] == 'MS29':
        return '销售' + title if not title.startswith('销售') else title
    if current['series_prefix'] == 'LO23':
        return '物流' + title if not title.startswith('物流') else title
    if re.fullmatch(r'(?:资深|高级|中级|初级|助理)?(?:工程师|设计师|技术员|经理|主管|专员|助理|总监)', title):
        scope = specialty.split(',')[0].split('、')[0]
        if scope and scope not in ('综合管理', '研发', '通用研发', '管理', '其他'):
            return scope + title
    return title


def explicit_title(title):
    """Small reviewed terminology equivalences; never remove C++/C#/slash broadly."""
    title = re.sub(r'^投资管理(?=副总经理|总监|经理|主管|专员|助理)', '投资', title)
    title = title.replace('在线服务', '在线客服').replace('中控员工', '中控员').replace('中控操作工', '中控员')
    return title


def career(title):
    part = title.split('/')[0]
    part = re.sub(r'（[1-7]级）$', '', part)
    part = re.sub(r'^(资深|高级|中级|初级|助理)', '', part)
    track = '班组' if re.search(r'组长|班长|领班|队长', part) else ''
    part = re.sub(r'(副总经理|总经理|总监|经理|主管|专员|助理|工程师|设计师|技师|技术员|管理员|管理师|程序员|研究员|顾问|领班|组长|班长|队长|主任|员)$', '', part)
    part = part.replace('仓储管理', '仓储').replace('人力资源综合', '人力资源')
    return part or title, track


def qualify_cross_level_names(groups):
    names = defaultdict(list)
    for group in groups:
        names[key(group['title'])].append(group)
    records = []
    for values in names.values():
        if len(values) < 2:
            continue
        need(len({g['level'] for g in values}) > 1, '同级同名必须先解决实质归并或对象区分')
        original_name = values[0]['title']
        multiple_functions = len({g['function'] for g in values}) > 1
        for group in values:
            group['unqualified_title'] = group['title']
            if not group['locked']:
                qualifier = (group['function'] + '，' if multiple_functions else '') + str(group['level']) + '级'
                group['aliases'].append(group['title'])
                group['title'] += '（' + qualifier + '）'
                group['display_grade_qualification'] = True
        records.append({'original_display_name': original_name,
                        'decision': '保留已有不同工作职级，在名称注明职级；不凭同名强制升降级，不视为专家已确认级差',
                        'jobs': [{'code': g['code'], 'name': g['title'], 'level': g['level'], 'function': g['function'],
                                  'source_ids': g['source_ids']} for g in values]})
    return records


class Union:
    def __init__(self, size):
        self.parents = list(range(size))

    def find(self, index):
        while self.parents[index] != index:
            self.parents[index] = self.parents[self.parents[index]]
            index = self.parents[index]
        return index

    def join(self, left, right):
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parents[max(left, right)] = min(left, right)


def preferred(counter, fallback=None):
    if fallback and fallback in counter:
        return fallback
    # A full source-backed dual title is useful when it explicitly connects
    # management/professional aliases; don't invent a new engineer/manager name.
    return min(counter, key=lambda n: (-counter[n], len(n), n))


def level_basis(code):
    if code == 'LO304':
        return '既有用户确认：配货组长并4级配货主管；原6级永久保留在来源记录'
    if code.startswith('VE64'):
        return '原高级/中级/初级教师连续6/7/8不符合统一等级；沿首批4/5/6工作梯队，非用户逐岗确认'
    if code.startswith('HL00'):
        return '原名医疗产品经理/主管/专员，原6/7/8连续标号按3/4/5工作梯队归一，非法8不入活动码'
    if code.startswith('EC08'):
        return '经销商管理经理/主管/专员原1/2/3连续标号，按同职务3/4/5归一；原级与本轮推定分别保留'
    if code.startswith('AG09'):
        return '同名管道设计梯队多数来源为资深3/高级4/工程师5，燃气来源5/6/7按同名工作梯队对齐'
    if code == 'BC006':
        return '同名初级暖通工程师两条原6级支持，地产原5级沿首批推定统一6级'
    if code == 'CS176':
        return '同名初级电话客服员八条原6级、一条原7级，工作级按多数同名来源6级承接'
    if code == 'GM093':
        return '同名总经理助理十条原3级、一条原2级，工作级按多数同名来源3级承接'
    if code == 'LO054':
        return '同名发货组长两条原4级、一条原5级，沿同名多数4级工作结论，保留推定'
    if code == 'AE066':
        return '同名初级插画师原5/6级各一条，沿插画高级4/普通5/初级6工作梯队；属于推定'
    return '同名原级存在冲突，沿既有工作级并保留推定；本轮未将该级别冒充用户确认或JD已证明'


def read_inputs():
    need(prior.sha(ROOT / prior.BASE) == prior.BASE_HASH, '冻结基线变化')
    manifest = prior.read(ROOT / '项目文件清单.json')
    relative = str(PREVIOUS.relative_to(ROOT))
    need(prior.sha(PREVIOUS) == manifest['files'][relative]['sha256'], '前一名称代码版本被修改')
    mapping_relative = '岗位名称代码统一_20261029/基线名称代码映射.json'
    need(prior.sha(ROOT / mapping_relative) == manifest['files'][mapping_relative]['sha256'], '前版基线映射被修改')
    baseline = prior.read(ROOT / prior.BASE)
    previous = prior.read(PREVIOUS)
    rules = prior.read(OUT / '统一规则.json')
    need(rules['version'] == VERSION, '规则版本错误')
    return baseline, previous, rules


def build():
    baseline, previous, rules = read_inputs()
    functions = {f['name']: f['id'] for f in baseline['functions']}
    metadata, workbook_hashes, revision_differences = metadata_all(baseline)
    meta = {r['source_id']: r for r in metadata}
    sources = {s['source_id']: s for s in baseline['sources']}
    old_jobs = {j['id']: j for j in previous['jobs']}
    by_code = {j['code']: j for j in previous['jobs']}
    policies = {r['prefix']: r for r in rules['family_policies']}
    protected = set(rules['protected_codes'])
    source_owners = defaultdict(list)
    for job in previous['jobs']:
        for sid in job['source_ids']:
            source_owners[sid].append(job['id'])
    units, level_changes = [], []
    for old in previous['jobs']:
        policy = policies.get(old['series_prefix'])
        locked = old['code'] in protected
        raw_names = {clean(sources[s]['source_name']) for s in old['source_ids']}
        grade_conflict = any(str(old['level']) != sources[s]['source_code'][-1] for s in old['source_ids'])
        buckets = defaultdict(list)
        for sid in old['source_ids']:
            source = sources[sid]
            name = clean(source['source_name'])
            name = explicit_title(contextual_title(name, meta[sid], old))
            name, scope_inferred = test_scope_title(name, meta[sid], old)
            function, route_reason = route_function(name, meta[sid], old)
            need(function in functions, '未定义规范职能: ' + function)
            level = old['level']
            # Distinct staff/team roles must not inherit a supervisor's level.
            # Known coherent source-name ladders otherwise retain the existing
            # work inference, including the documented teacher/medical shifts.
            if policy and policy['policy'] == 'split_by_metadata_title' and old['series_prefix'] in ('BS02', 'LO09'):
                candidate = int(source['source_code'][-1])
                if 1 <= candidate <= 7:
                    level = candidate
            if locked:
                token, name, function, level = 'LOCK:' + old['id'], old['name'], old['function_name'], old['level']
            elif policy and policy['policy'] == 'same_object_aliases':
                token = 'ALIASES:' + old['id']
            else:
                token = key(name)
            # Function changes may expose an old false merge even in an alias
            # family; routing is never overridden by a shared series/level key.
            buckets[(token, function, level)].append({'source_id': sid, 'name': name, 'route': route_reason,
                                                     'scope_inferred': scope_inferred or generic_test_title(name)})
            if int(source['source_code'][-1]) != level:
                level_changes.append({'source_id': sid, 'source_name': source['source_name'], 'original_code': source['source_code'],
                                      'original_level': int(source['source_code'][-1]), 'work_level': level,
                                      'reason': level_basis(old['code']),
                                      'user_confirmed': old['code'] in ('LO304', 'LO306')})
        for (_, function, level), atoms in sorted(buckets.items()):
            counts = Counter(a['name'] for a in atoms)
            fallback = old['name'] if old['name'] in counts else None
            title = old['name'] if locked else preferred(counts, fallback)
            units.append({'old_id': old['id'], 'old_code': old['code'], 'title': title, 'function': function, 'level': level,
                          'aliases': sorted(counts), 'source_ids': [a['source_id'] for a in atoms], 'atoms': atoms,
                          'locked': locked, 'policy': policy, 'grade_conflict': grade_conflict})
    # Global exact/sourced-alias join requires common profession and level.
    # An audited alias family supplies the semantic evidence, rather than using
    # the old shared series/level itself as a merge condition.
    union = Union(len(units))
    alias_seen = {}
    for index, unit in enumerate(units):
        if unit['locked']:
            continue
        aliases = set(unit['aliases']) | {unit['title']}
        for alias in list(aliases):
            parts = alias.split('/')
            if len(parts) > 1 and all(re.search(r'(经理|主管|专员|助理|工程师|设计师|顾问|技师)$', x) for x in parts):
                aliases.update(parts)
        # Explicitly unify generic algorithm aliases at the same grade.
        if unit['function'] == '研发' and any(re.match(r'^(资深|高级|初级)?算法(经理|工程师|主管|专员|助理)', n) for n in aliases):
            aliases.add('泛算法岗位')
        for alias in sorted(aliases):
            lookup = (unit['function'], unit['level'], key(alias))
            if lookup in alias_seen:
                union.join(index, alias_seen[lookup])
            else:
                alias_seen[lookup] = index
    components = defaultdict(list)
    for index, unit in enumerate(units):
        components[union.find(index)].append(unit)
    groups = []
    for component in components.values():
        locked = [u for u in component if u['locked']]
        need(len(locked) <= 1, '确认岗位被归并')
        counts = Counter(a['name'] for u in component for a in u['atoms'])
        title = locked[0]['title'] if locked else preferred(counts)
        function, level = component[0]['function'], component[0]['level']
        need(all(u['function'] == function and u['level'] == level for u in component), '跨职能或跨级归并')
        source_ids = sorted({sid for u in component for sid in u['source_ids']})
        base_career = career(title)
        if locked:
            family = (function, 'CONFIRMED:' + locked[0]['old_code'][:4])
        else:
            family = (function, key(base_career[0]), base_career[1])
        groups.append({'title': title, 'function': function, 'level': level, 'source_ids': source_ids,
                       'aliases': sorted(set(counts) - {title}), 'units': component, 'family': family,
                       'locked': bool(locked), 'old_ids': sorted({u['old_id'] for u in component})})
    groups.sort(key=lambda g: (str(g['family']), g['level'], g['title'], g['source_ids']))
    # Preserve a valid existing occupational ladder. Stripping words from titles
    # alone can turn e.g. "给排水设计经理" and "给排水设计师" into different
    # artificial families and force unnecessary recoding. Reviewed false-merge
    # families use their explicit partitions; other continuing source ladders
    # keep the original family, joining two old ladders only on sourced aliases.
    stable_roots = sorted({(u['function'], old_jobs[u['old_id']]['series_prefix'])
                           for g in groups for u in g['units']
                           if old_jobs[u['old_id']]['function_name'] == u['function'] and
                           (not u['policy'] or u['policy']['policy'] != 'split_by_metadata_title')})
    root_index = {root: i for i, root in enumerate(stable_roots)}
    root_union = Union(len(stable_roots))
    for group in groups:
        roots = sorted({root_index[(u['function'], old_jobs[u['old_id']]['series_prefix'])]
                        for u in group['units'] if (u['function'], old_jobs[u['old_id']]['series_prefix']) in root_index})
        if not group['locked']:
            for left, right in zip(roots, roots[1:]):
                root_union.join(left, right)
    root_locks = {}
    for group in groups:
        if not group['locked']:
            continue
        for unit in group['units']:
            root = (unit['function'], old_jobs[unit['old_id']]['series_prefix'])
            if root in root_index:
                index = root_union.find(root_index[root])
                need(index not in root_locks or root_locks[index] == group['family'], '确认职业梯队发生跨对象联接')
                root_locks[index] = group['family']
    for group in groups:
        roots = sorted({root_union.find(root_index[(u['function'], old_jobs[u['old_id']]['series_prefix'])])
                        for u in group['units'] if (u['function'], old_jobs[u['old_id']]['series_prefix']) in root_index})
        if roots and not group['locked']:
            locked_families = {root_locks[r] for r in roots if r in root_locks}
            need(len(locked_families) <= 1, '普通岗位不能串联两个确认职业梯队')
            group['family'] = (next(iter(locked_families)) if locked_families else
                               (group['function'], 'SOURCE_LADDER:' + stable_roots[roots[0]][1]))
    # Different same-grade roles can have the same stripped career stem.
    # Preserve the full source-backed role as a distinct series in that case.
    family_grade = defaultdict(list)
    for i, group in enumerate(groups):
        family_grade[(group['family'], group['level'])].append(i)
    for indexes in family_grade.values():
        if len(indexes) > 1:
            for index in indexes:
                groups[index]['family'] += ('ROLE:' + key(groups[index]['title']),)
    # Each four-character series prefix is owned by one profession/family.
    weights = defaultdict(Counter)
    locked_prefix = {}
    for i, group in enumerate(groups):
        for old_id in group['old_ids']:
            old = old_jobs[old_id]
            if old['function_name'] == group['function']:
                overlap = len(set(old['source_ids']) & set(group['source_ids']))
                weights[old['code'][:4]][group['family']] += overlap
                if group['locked']:
                    locked_prefix[old['code'][:4]] = group['family']
    prefix_owner = {prefix: locked_prefix.get(prefix) or sorted(count.items(), key=lambda x: (-x[1], str(x[0])))[0][0]
                    for prefix, count in weights.items()}
    used_codes, used_ids, family_prefixes = set(), set(), defaultdict(list)
    # Protected codes win first, followed by the largest continuing source group.
    order = sorted(range(len(groups)), key=lambda i: (not groups[i]['locked'], -len(groups[i]['source_ids']), groups[i]['title'], groups[i]['level']))
    historical_codes = {j['code'] for j in baseline['jobs']} | set(by_code)
    all_prefixes = {c[:4] for c in historical_codes}
    first_two_functions = defaultdict(set)
    for old in previous['jobs']:
        first_two_functions[old['code'][:2]].add(old['function_name'])
    reserved_r = set(previous['reserved_nonresearch_r_prefixes'])
    def allocate_prefix(function, family):
        choices = sorted(p for p, owners in first_two_functions.items() if owners == {function} and
                         (function not in RESEARCH or (p.startswith('R') and p not in reserved_r)))
        for first in choices:
            for n in range(100):
                prefix = first + f'{n:02}'
                if prefix not in all_prefixes:
                    all_prefixes.add(prefix)
                    prefix_owner[prefix] = family
                    return prefix
        for a in ('R' if function in RESEARCH else 'ABCDEFGHIJKLMNOPQSTUVWXYZ'):
            for b in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                first = a + b
                if first in first_two_functions or (a == 'R' and first in reserved_r):
                    continue
                first_two_functions[first] = {function}
                prefix = first + '00'
                all_prefixes.add(prefix)
                prefix_owner[prefix] = family
                return prefix
        raise ValueError('没有可用码段: ' + function)
    for index in order:
        group = groups[index]
        candidates = []
        for old_id in group['old_ids']:
            old = old_jobs[old_id]
            if (old['function_name'] == group['function'] and old['level'] == group['level'] and
                    prefix_owner.get(old['code'][:4]) == group['family'] and old['code'] not in used_codes):
                overlap = len(set(old['source_ids']) & set(group['source_ids']))
                candidates.append((-overlap, old['code']))
        if candidates:
            code = min(candidates)[1]
        else:
            prefix = next((p for p in family_prefixes[group['family']] if p + str(group['level']) not in used_codes and
                           p + str(group['level']) not in historical_codes), None)
            if prefix is None:
                prefix = allocate_prefix(group['function'], group['family'])
            code = prefix + str(group['level'])
        group['code'] = code
        used_codes.add(code)
        if code[:4] not in family_prefixes[group['family']]:
            family_prefixes[group['family']].append(code[:4])
        continuing = [old_jobs[j] for j in group['old_ids'] if
                      old_jobs[j]['function_name'] == group['function'] and old_jobs[j]['level'] == group['level'] and
                      set(old_jobs[j]['source_ids']) == set(group['source_ids'])]
        if group['locked']:
            current_id = group['old_ids'][0]
        elif continuing:
            current_id = min(continuing, key=lambda j: (j['code'] != code, j['code']))['id']
        else:
            current_id = prior.identity_id('UJ-ALLNC', group['function'] + '/' + str(group['level']) + '/' + key(group['title']) + '/' + '|'.join(group['source_ids']))
        need(current_id not in used_ids, '岗位ID重复')
        used_ids.add(current_id)
        group['id'] = current_id
    # Give genuinely distinct professions/scopes readable names. Keep the source
    # evidence and explicit inference; this display step is not semantic dedup.
    names = defaultdict(list)
    for group in groups:
        names[(key(group['title']), group['level'])].append(group)
    for duplicates in names.values():
        if len(duplicates) > 1:
            for group in duplicates:
                need(not group['locked'], '确认名称与另岗冲突，需显式处理')
                group['title'] += '（' + group['function'] + '）'
    cross_level_names = qualify_cross_level_names(groups)
    jobs, decisions, series = [], [], {}
    group_by_source_role = {}
    for group in sorted(groups, key=lambda g: g['code']):
        units = group['units']
        old_ids = group['old_ids']
        split = any(len(set(old_jobs[j]['source_ids']) - set(group['source_ids'])) for j in old_ids)
        merge = len(old_ids) > 1
        different_raw_names = len({a['name'] for u in units for a in u['atoms']}) > 1
        inherited_inference = any(old_jobs[j]['baseline_identity_inferred'] for j in old_ids)
        class_changed = any(old_jobs[j]['function_name'] != group['function'] for j in old_ids)
        scope_inferred = any(a['scope_inferred'] for u in units for a in u['atoms'])
        grade_display_inferred = group.get('display_grade_qualification', False)
        inferred = inherited_inference or different_raw_names or any(u['grade_conflict'] for u in units) or class_changed or scope_inferred or grade_display_inferred
        renamed = any(clean(old_jobs[j]['name']) != clean(group['title']) for j in old_ids)
        action = ('归并' if merge else '拆分' if split else '修正职能' if class_changed else
                  '修正名称' if renamed else '保留并补证' if not inferred else '继续推定-已确定工作名码')
        prefix = group['code'][:4]
        family_name = career(group.get('unqualified_title', group['title']))[0]
        if prefix in series:
            family_name = series[prefix]['name']
        else:
            series[prefix] = {'id': prior.identity_id('BS-ALLNC', VERSION + '/' + prefix), 'prefix': prefix,
                              'name': family_name, 'function_id': functions[group['function']], 'function_name': group['function'], 'job_ids': []}
        series[prefix]['job_ids'].append(group['id'])
        job = {'id': group['id'], 'code': group['code'], 'name': group['title'], 'level': group['level'],
               'function_id': functions[group['function']], 'function_name': group['function'],
               'series_id': series[prefix]['id'], 'series_name': family_name, 'series_prefix': prefix,
               'aliases': sorted((set(group['aliases']) | {sources[s]['source_name'] for s in group['source_ids']}) - {group['title']}), 'source_ids': group['source_ids'],
               'industries': sorted({sources[s]['industry'] for s in group['source_ids']}),
               'name_code_status': '已形成唯一工作名称代码', 'identity_contains_inference': inferred,
               'decision': action, 'previous_job_ids': old_ids}
        jobs.append(job)
        reasons = sorted({a['route'] for u in units for a in u['atoms']})
        family_reasons = sorted({u['policy']['reason'] for u in units if u['policy']})
        assumptions = []
        if inherited_inference:
            assumptions.append('源基线含身份推定；本轮仅以名称/职能/细分/层级确定工作身份，未用JD消除该历史不确定性')
        if different_raw_names:
            assumptions.append('按已列明的同义及同对象规则采用一个标准名；原称谓全部作为别名和来源保留')
        if any(u['grade_conflict'] for u in units):
            assumptions.append('存在原级与工作级差异；采用记录的工作梯队，逐来源原级和目标级可追溯')
        if class_changed:
            assumptions.append('职能按原名称及原表元数据调整；属于本轮分类工作结论，非JD匹配已完成')
        if scope_inferred:
            assumptions.append('原名为通用测试称谓；具体软件/产品范围按已列明同族元数据作工作推定，不能靠泛称把不同对象串为一岗')
        if grade_display_inferred:
            assumptions.append('相同原名称存在不同工作职级，名称括注职级用于一一对照；沿用级差为工作结论，不以显示区别替代专家审定')
        decisions.append({'job_id': job['id'], 'code': job['code'], 'name': job['name'], 'action': action,
                          'inferred': inferred, 'basis': reasons, 'alias_or_partition_basis': family_reasons,
                          'assumptions': assumptions, 'evidence_source_ids': group['source_ids'],
                          'evidence_locations': [{'source_id': s, 'original_file': meta[s]['原版BMJD']['file'],
                                                  'row': meta[s]['原版BMJD']['row'], 'original_name': meta[s]['原版BMJD']['name'],
                                                  'current_input_name': meta[s]['最新输入_修改版6']['name']} for s in group['source_ids']],
                          'scope_limit': '本结论仅统一名称代码；JD在下一阶段按ID及来源重新定位'})
        for sid in group['source_ids']:
            for unit in units:
                if sid in unit['source_ids']:
                    group_by_source_role[(sid, unit['old_id'])] = job
    current_by_id = {j['id']: j for j in jobs}
    source_records = []
    for source in baseline['sources']:
        sid = source['source_id']
        target_jobs = {group_by_source_role[(sid, owner)]['id']: group_by_source_role[(sid, owner)] for owner in source_owners[sid]}
        source_records.append({'source_id': sid, 'original_name': source['source_name'], 'original_code': source['source_code'],
                               'file': source['file'], 'range': source['range'], 'industry': source['industry'], 'state': source['state'],
                               'target_job_ids': sorted(target_jobs), 'target_codes': sorted(j['code'] for j in target_jobs.values()),
                               'authorization': source.get('allocations', [])})
    previous_mappings = []
    for old in previous['jobs']:
        targets = {group_by_source_role[(sid, old['id'])]['id'] for sid in old['source_ids']}
        previous_mappings.append({'previous_job_id': old['id'], 'previous_code': old['code'], 'previous_name': old['name'],
                                  'target_job_ids': sorted(targets), 'current_codes': sorted(current_by_id[t]['code'] for t in targets),
                                  'current_names': sorted(current_by_id[t]['name'] for t in targets),
                                  'source_destinations': {sid: group_by_source_role[(sid, old['id'])]['code'] for sid in old['source_ids']}})
    prev_map = {m['previous_job_id']: m for m in previous_mappings}
    old_baseline_mapping = prior.read(prior.OUT / '基线名称代码映射.json')
    baseline_mappings, inference_ledger = [], []
    baseline_jobs = {j['id']: j for j in baseline['jobs']}
    for old in old_baseline_mapping:
        targets = set()
        # Resolve each source through its exact predecessor role, rather than
        # composing broad split mappings that include other sources' successors.
        for sid, previous_codes in old['source_destinations'].items():
            for code in previous_codes:
                predecessor = by_code[code]
                targets.add(group_by_source_role[(sid, predecessor['id'])]['id'])
        mapped = {'baseline_job_id': old['baseline_job_id'], 'old_code': old['old_code'], 'old_name': old['old_name'],
                  'target_job_ids': sorted(targets), 'current_codes': sorted(current_by_id[t]['code'] for t in targets),
                  'current_names': sorted(current_by_id[t]['name'] for t in targets)}
        baseline_mappings.append(mapped)
        if baseline_jobs[old['baseline_job_id']]['inferred_identity']:
            inference_ledger.append(dict(mapped, status='已逐项形成名称代码工作处置',
                                         actions=[next(d['action'] for d in decisions if d['job_id'] == t) for t in sorted(targets)],
                                         current_inference_retained=any(current_by_id[t]['identity_contains_inference'] for t in targets),
                                         evidence_source_ids=baseline_jobs[old['baseline_job_id']]['source_ids']))
    need(len(inference_ledger) == 3092, '身份推定基线处置覆盖不完整')
    validate(jobs, list(series.values()), source_records, baseline, previous, previous_mappings, baseline_mappings, inference_ledger, rules)
    report = {'version': VERSION, 'all_passed': True, 'name_code_rules_complete': True, 'expert_review_complete': False,
              'jd_matching_started': False, 'previous_jobs': len(previous['jobs']), 'current_jobs': len(jobs),
              'unique_codes': len({j['code'] for j in jobs}), 'functions': len({j['function_id'] for j in jobs}),
              'series': len(series), 'baseline_ids_covered': len(baseline_mappings), 'inferred_baseline_dispositions': len(inference_ledger),
              'unprocessed_baseline_inference_jobs': 0, 'source_records': len(source_records), 'active_sources': len(metadata),
              'paused_sources': 23, 'original_workbooks': 22, 'original_metadata_differences': len(revision_differences),
              'current_jobs_containing_inference': sum(j['identity_contains_inference'] for j in jobs),
              'previous_identities_split': sum(len(m['target_job_ids']) > 1 for m in previous_mappings),
              'current_identities_merging_predecessors': sum(len(j['previous_job_ids']) > 1 for j in jobs),
              'preserved_codes': sum(j['code'] in by_code for j in jobs),
              'level_difference_records': len(level_changes),
              'cross_level_name_groups': len(cross_level_names),
              'checks': ['全量名称代码覆盖', '3092个推定基线逐项处置', '一岗一码及ID唯一', '代码合法且末位等于层级',
                         '职能系列码段一致', '原始来源和23条暂缓守恒', '普通来源唯一归岗', '授权来源不串角色',
                         '8932个基线ID精确来源映射', '8925个前版ID映射', '22个原表元数据及版本差异留痕',
                         '确认岗位及配货4/6保持', '无JD字段和JD状态', '没有未处理岗位状态']}
    document = {'version': VERSION, 'phase': '全部岗位名称代码规则统一；JD下一阶段',
                'quality': '全量工作统一版（透明保留推定）；不代表专业职责或JD已审定',
                'summary': report, 'jobs': jobs, 'series': sorted(series.values(), key=lambda s: s['prefix']),
                'reserved_nonresearch_r_prefixes': previous['reserved_nonresearch_r_prefixes']}
    table = io.StringIO(newline='')
    writer = csv.writer(table, delimiter='\t', lineterminator='\n')
    writer.writerow(['岗位ID', '岗位代码', '统一岗位名称', '职能', '职责系列', '层级', '行业标签', '处置', '是否含推定'])
    for job in jobs:
        writer.writerow([job['id'], job['code'], job['name'], job['function_name'], job['series_name'], job['level'],
                         '、'.join(job['industries']), job['decision'], '是' if job['identity_contains_inference'] else '否'])
    return {'名称代码主库.json': document, '全部岗位名称代码表.tsv': table.getvalue(),
            '全量岗位处置台账.json': decisions, '基线推定岗位处置.json': inference_ledger,
            '基线ID名称代码映射.json': baseline_mappings, '前版ID名称代码映射.json': previous_mappings,
            '来源去向映射.json': source_records, '全量原表元数据.json': metadata,
            '原表版本差异.json': revision_differences, '原级与工作级差异.json': level_changes,
            '同名跨职级说明.json': cross_level_names,
            '透明推定清单.json': [d for d in decisions if d['inferred']], '边界统一结论.json': rules['boundary_decisions'],
            '核验报告.json': report,
            '输入指纹.json': {'baseline': {prior.BASE: prior.BASE_HASH}, 'previous': {str(PREVIOUS.relative_to(ROOT)): prior.sha(PREVIOUS)},
                              'rules_sha256': prior.sha(OUT / '统一规则.json'), 'workbooks': workbook_hashes}}


def validate(jobs, series, source_records, baseline, previous, previous_mappings, baseline_mappings, inference_ledger, rules):
    prior.validate_master(jobs, series, source_records, baseline['sources'], {})
    need(len(previous_mappings) == len(previous['jobs']) and len(baseline_mappings) == 8932, '全量映射缺失')
    ids = {j['id'] for j in jobs}
    need(len({r['previous_job_id'] for r in previous_mappings}) == len(previous['jobs']) and
         {r['previous_job_id'] for r in previous_mappings} == {j['id'] for j in previous['jobs']}, '前版ID映射集合错误')
    need({r['baseline_job_id'] for r in baseline_mappings} == {j['id'] for j in baseline['jobs']}, '基线ID映射集合错误')
    for record in previous_mappings + baseline_mappings:
        need(record['target_job_ids'] and set(record['target_job_ids']) <= ids, '旧身份无去向')
    need(len({r['baseline_job_id'] for r in inference_ledger}) == 3092, '推定基线覆盖错误')
    need({r['baseline_job_id'] for r in inference_ledger} == {j['id'] for j in baseline['jobs'] if j['inferred_identity']},
         '推定处置不属于原3092岗位全集')
    need(all(r['current_inference_retained'] for r in inference_ledger), '原推定不确定性被无依据取消')
    need(len({(key(j['name']), j['level']) for j in jobs}) == len(jobs), '同一标准名称及层级仍对应多个代码')
    need(len({key(j['name']) for j in jobs}) == len(jobs), '同一显示名称仍对应多个代码')
    current = {j['code']: j for j in jobs}
    before = {j['code']: j for j in previous['jobs']}
    for code in rules['protected_codes']:
        a, b = current.get(code), before[code]
        need(a is not None and all(a[k] == b[k] for k in ('id', 'code', 'name', 'level', 'function_id')), '确认身份变化: ' + code)
        need(set(a['source_ids']) == set(b['source_ids']), '确认来源变化: ' + code)
    prev_mapping = {r['previous_code']: r for r in previous_mappings}
    for code in ('AC435', 'CT205'):
        need(prev_mapping[code]['current_codes'] == [code], '灯光授权来源造成身份串岗')
    need(all(j['name_code_status'] == '已形成唯一工作名称代码' for j in jobs), '仍有未处理名称代码')
    for prefix in previous['reserved_nonresearch_r_prefixes']:
        for code, old in before.items():
            if code.startswith(prefix):
                need(code in current and current[code]['id'] == old['id'], '非研发R段被覆盖: ' + code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--write', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs = build()
    prior.save(outputs, directory=OUT, check=args.check)
    print(json.dumps(outputs['核验报告.json'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
