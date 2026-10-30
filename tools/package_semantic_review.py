"""Assemble one review package from the frozen latest master and verified HTML."""
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/'BMJD主库汇总预览_20261030'
MASTER=ROOT/'原版分类编码收口_20261030'
OUTPUT=ROOT.parent/'outputs'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    build=read(PAGE/'页面构建核验.json');browser=read(PAGE/'页面浏览器核验.json')
    audit=read(MASTER/'独立核验报告.json');master=read(MASTER/'主库.json')
    assert build['all_passed'] and browser['all_passed'] and audit['all_passed']
    assert build['master_version']==master['version']==audit['version']
    html=PAGE/'BMJD主库汇总预览.html'
    assert sha(html)==build['html_sha256']==browser['html_sha256']
    for name,h in audit['sha256'].items():assert sha(ROOT/name)==h,name
    for name,h in build['input_sha256'].items():assert sha(ROOT/name)==h,name
    sources={'BMJD主库汇总预览.html':html,'使用说明.md':PAGE/'使用说明.md',
      '核验/页面构建核验.json':PAGE/'页面构建核验.json','核验/页面浏览器核验.json':PAGE/'页面浏览器核验.json'}
    for p in sorted(MASTER.iterdir()):
        if p.is_file():sources[MASTER.name+'/'+p.name]=p
    manifest={'version':'BMJD-REVIEW-PACKAGE-20261030-01','date':'2026-10-30','master_version':master['version'],
      'page_version':build['version'],'jobs':9111,'html_sha256':sha(html),
      'entry':'BMJD主库汇总预览.html','source_master_unchanged':True,
      'files':{n:{'bytes':p.stat().st_size,'sha256':sha(p),'source':p.relative_to(ROOT).as_posix()} for n,p in sources.items()},
      'scope':'包内只有最新主库成果、原版映射与核验、新版查询HTML；行业JD按ID沿用，未带入旧新增工具或旧版HTML。'}
    path=PAGE/'发布清单.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    sources['发布清单.json']=path
    OUTPUT.mkdir(exist_ok=True)
    direct=[(html,'BMJD主库查岗_汇总版_20261030.html'),(MASTER/'原版分类岗位代码及JD.xlsx','BMJD主库_汇总版_20261030.xlsx')]
    for p,n in direct:
        shutil.copyfile(p,OUTPUT/n);assert sha(p)==sha(OUTPUT/n)
    archive=OUTPUT/'BMJD主库与HTML_汇总版_20261030.zip'
    prefix='BMJD主库与HTML汇总版_20261030/'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for n,p in sources.items():z.write(p,prefix+n)
    with ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(sources)
        for n,p in sources.items():assert hashlib.sha256(z.read(prefix+n)).hexdigest()==sha(p),n
    print(json.dumps({'all_passed':True,'files':len(sources),'zip_bytes':archive.stat().st_size,
      'downloads':[n for _,n in direct]+[archive.name],'master_version':master['version']},ensure_ascii=False))


if __name__=='__main__':main()
