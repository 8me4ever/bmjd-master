import json, io, sys, os
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / 'out'
SCHEMA = ROOT / '双线协作交接_20261029' / 'JD回传格式.schema.json'

d = json.load(open(os.path.join(OUT, 'JD回传_常规岗.json'), encoding='utf-8'))
s = json.load(open(SCHEMA, encoding='utf-8'))

try:
    import jsonschema
    jsonschema.validate(d, s)
    print('jsonschema: PASS')
except ImportError:
    print('jsonschema 未安装，改用内置逐字段核对')
    req_top = s['required']
    print('顶层必填齐全:', all(k in d for k in req_top))
    consts = {k: v['const'] for k, v in s['properties'].items() if 'const' in v}
    print('常量一致:', all(d.get(k) == v for k, v in consts.items()))
    item = s['properties']['jobs']['items']
    ireq = item['required']
    ienum = item['properties']['writing_status']['enum']
    bad = 0
    for j in d['jobs']:
        if not all(k in j for k in ireq):
            bad += 1
        if j['writing_status'] not in ienum:
            bad += 1
        for c in j['clauses']:
            if not all(k in c for k in ('number', 'text', 'basis_type', 'source_refs', 'basis_note')):
                bad += 1
            if c['basis_type'] not in ('原文提炼', '专业补写', '规则推定'):
                bad += 1
            for r in c['source_refs']:
                if not r.get('source_id') or not r.get('quote'):
                    bad += 1
        if j['identity_issue'] is not None:
            if not all(k in j['identity_issue'] for k in ('description', 'source_ids', 'suggested_name', 'suggested_function', 'suggested_level')):
                bad += 1
    print('字段不合规项:', bad)
    print('岗位数:', len(d['jobs']))
