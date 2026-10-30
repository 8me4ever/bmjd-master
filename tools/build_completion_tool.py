"""Build a single offline HTML tool with the complete BMJD base and reservations."""
import argparse
import base64
import gzip
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'BMJD持续补全工具_20261029'
MASTER=ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
SOURCE=ROOT/'completion_tool'
HISTORICAL=[ROOT/p for p in ['全库统一完成_20261029/统一主库.json','主库推定整理_20261029/统一主库.json','岗位名称代码统一_20261029/名称代码主库.json','全量名称代码统一_20261029/名称代码主库.json']]
METADATA=ROOT/'全量名称代码统一_20261029/全量原表元数据.json'
RESEARCH={'研发','软件开发','设计研发','产品研发','药品研发'}


def read(path):return json.loads(path.read_text('utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    master=read(MASTER);codes=set();prefixes=set();owners=defaultdict(set)
    for path in HISTORICAL+[MASTER]:
        for job in read(path)['jobs']:
            assert re.fullmatch('[A-Z]{2}[0-9]{2}[1-7]',job['code'])
            codes.add(job['code']);prefixes.add(job['code'][:4]);owners[job['code'][:2]].add(job['function_id'])
    for row in read(METADATA):
        for version in ['原版BMJD','最新输入_修改版6']:
            code=unicodedata.normalize('NFKC',str(row[version]['code'])).strip().upper()
            if re.fullmatch('[A-Z]{2}[0-9]{2}[1-7]',code):codes.add(code)
            if re.match('^[A-Z]{2}[0-9]{2}',code):prefixes.add(code[:4])
    industry_names=sorted({i for j in master['jobs'] for i in j['industries']})
    research_ids=sorted({j['function_id'] for j in master['jobs'] if j['function_name'] in RESEARCH})
    current_codes={j['code'] for j in master['jobs']}
    checks={
        '完整内置9111岗且主键代码唯一':len(master['jobs'])==len(current_codes)==len({j['id'] for j in master['jobs']})==9111,
        '263规范职能与3077职责系列':len({j['function_id'] for j in master['jobs']})==263 and len(master['series'])==3077,
        '11行业范围':len(industry_names)==11,
        '全部当前代码均已登记占用':current_codes<=codes,
        '原5类研发职能均遵守R段规则':len(research_ids)==len(RESEARCH),
        'RA_RC_RM_RP非研发保留段完整':set(master['reserved_nonresearch_r_prefixes'])=={'RA','RC','RM','RP'},
        '所有职责系列前四位都保留':{s['prefix'] for s in master['series']}<=prefixes,
    }
    policy={'reserved_codes':sorted(codes),'reserved_prefixes':sorted(prefixes),
            'block_owners':{p:sorted(v) for p,v in sorted(owners.items())},
            'research_function_ids':research_ids,'reserved_nonresearch_r_prefixes':master['reserved_nonresearch_r_prefixes'],
            'industries':industry_names}
    meta={'tool_version':'BMJD-COMPLETION-20261029-01','base_version':master['version'],'base_sha256':sha(MASTER),
          'base_jobs':len(master['jobs']),'known_codes':len(codes),'historical_only_codes':len(codes-current_codes),'known_series_prefixes':len(prefixes)}
    data=json.dumps({'meta':meta,'policy':policy,'master':master},ensure_ascii=False,separators=(',',':')).encode()
    compressed=gzip.compress(data,mtime=0)
    template=(SOURCE/'template.html').read_text()
    for marker,path in [('/*__STYLES__*/',SOURCE/'styles.css'),('/*__CORE__*/',SOURCE/'completion-core.js'),('/*__APP__*/',SOURCE/'completion-app.js')]:
        text=path.read_text();assert '</script' not in text.lower(),path
        assert template.count(marker)==1;template=template.replace(marker,text)
    assert template.count('__PAYLOAD__')==1
    html=template.replace('__PAYLOAD__',base64.b64encode(compressed).decode()).encode()
    inputs=[MASTER,METADATA,*HISTORICAL,*[SOURCE/p for p in ['template.html','styles.css','completion-core.js','completion-app.js']],Path(__file__)]
    report={'version':meta['tool_version'],'summary':meta,'all_passed':all(checks.values()),'checks':checks,
            'html_bytes':len(html),'payload_gzip_bytes':len(compressed),'html_sha256':hashlib.sha256(html).hexdigest(),
            'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
            'scope':'内置全局主库和已知历史码；浏览器端只追加，导出新文件，不写原主库及行业专业JD。'}
    return {'BMJD岗位持续补全.html':html,'内置数据与构建核验.json':(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()},report


def main():
    parser=argparse.ArgumentParser(description=__doc__);g=parser.add_mutually_exclusive_group();g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');parser.add_argument('--output-dir',type=Path,default=OUT);args=parser.parse_args()
    files,report=build()
    assert report['all_passed'],report['checks']
    if args.write or args.check:
        for name,data in files.items():
            path=args.output_dir/name
            if path.exists() and path.read_bytes()!=data:raise ValueError('已有不同文件，不覆盖；请使用新的输出目录：'+str(path))
            if args.check and not path.exists():raise ValueError('缺少输出：'+str(path))
        if args.write:
            args.output_dir.mkdir(parents=True,exist_ok=True)
            for name,data in files.items():
                path=args.output_dir/name
                if not path.exists():path.write_bytes(data)
    print(json.dumps({**report['summary'],'html_mb':round(report['html_bytes']/1048576,2),'all_passed':report['all_passed']},ensure_ascii=False))


if __name__=='__main__':main()
