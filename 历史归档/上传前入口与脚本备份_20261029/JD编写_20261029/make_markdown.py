import json, io, sys, collections, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = r'D:\czm\岗位代码匹配\JD编写_20261029\out'
INP = r'D:\czm\岗位代码匹配\双线协作交接_20261029\JD编写输入.json'

d = json.load(open(os.path.join(OUT, 'JD回传_常规岗.json'), encoding='utf-8'))
src = {j['job_id']: j for j in json.load(open(INP, encoding='utf-8'))['jobs']}
jobs = d['jobs']
INDUSTRY_ORDER = ['高科技', '能源化工', '医药', '地产', '制造', '消费品', '教育', '金融', '传媒', '物流', '综合服务']


def industry(j):
    inds = src[j['job_id']]['industries']
    return inds[0] if inds else '其他'


groups = collections.OrderedDict((i, []) for i in INDUSTRY_ORDER + ['其他'])
for j in jobs:
    groups.setdefault(industry(j), []).append(j)

lines = []
lines.append('# BMJD 常规岗位JD（阅读版）\n')
lines.append('- 基线：%s（交接包 %s）' % (d['baseline_version'], d['package_id']))
lines.append('- 范围：常规岗位 %d 岗（不含 JD 推定岗 3,288 岗，按用户指示留待下一轮）' % len(jobs))
lines.append('- 处理方式：先核对岗位名称与本岗现有JD是否匹配；匹配的原样保留，不匹配才按名称重写')
lines.append('- 状态：无需修改-已复核 %d 岗；已提交（按名称重写）%d 岗' % (
    sum(1 for j in jobs if j['writing_status'] == '无需修改-已复核'),
    sum(1 for j in jobs if j['writing_status'] == '已提交')))
lines.append('- 条款数分布：%s' % '、'.join('%d条 %d岗' % (k, v) for k, v in sorted(collections.Counter(len(j['clauses']) for j in jobs).items())))
lines.append('')

for ind, js in groups.items():
    if not js:
        continue
    lines.append('## %s（%d岗）\n' % (ind, len(js)))
    for j in sorted(js, key=lambda x: x['baseline_code']):
        s = src[j['job_id']]
        lines.append('### %s %s\n' % (j['baseline_code'], s['baseline_name']))
        lines.append('职能：%s ｜ 职责系列：%s ｜ 层级：%d级 ｜ 状态：%s\n' % (
            s['function_name'], s['series_name'], s['level'], j['writing_status']))
        for c in j['clauses']:
            lines.append('%d、%s' % (c['number'], c['text']))
        if j['industry_issue'] if 'industry_issue' in j else j.get('identity_issue'):
            lines.append('\n> 待Codex复核：%s' % j['identity_issue']['description'])
        lines.append('')

open(os.path.join(OUT, 'JD阅读版_常规岗.md'), 'w', encoding='utf-8').write('\n'.join(lines))
print('markdown lines:', len(lines))
print('bytes:', os.path.getsize(os.path.join(OUT, 'JD阅读版_常规岗.md')))
