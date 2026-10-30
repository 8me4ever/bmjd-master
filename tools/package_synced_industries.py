"""Package the approved master, synchronized eleven industries and their HTML."""
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1];MASTER=ROOT/'原版分类编码收口_20261030';CHILDREN=ROOT/'行业子库同步_20261030'
PAGE=ROOT/'BMJD行业同步页面_20261030';OUTPUT=ROOT.parent/'outputs'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    master=read(MASTER/'主库.json');children=read(CHILDREN/'子库总览.json');audit=read(CHILDREN/'独立核验报告.json')
    build=read(PAGE/'页面构建核验.json');browser=read(PAGE/'页面浏览器核验.json');html=PAGE/'BMJD主库与行业子库.html'
    assert audit['all_passed'] and build['all_passed'] and browser['all_passed']
    assert master['version']==children['parent_version']==build['master_version'] and children['version']==build['industry_version']
    assert sha(MASTER/'主库.json')==children['parent_master_sha256']
    assert sha(html)==build['html_sha256']==browser['html_sha256']
    for name,h in audit['sha256'].items():assert sha(ROOT/name)==h,name
    for name,h in audit['protected_sha256'].items():assert sha(ROOT/name)==h,name
    for name,h in build['input_sha256'].items():assert sha(ROOT/name)==h,name
    current={'schema_version':1,'release_version':'BMJD-INDUSTRY-RELEASE-20261030-01','date':'2026-10-30','status':'MASTER_APPROVED_INDUSTRIES_AND_PORTAL_SYNCED',
      'master':{'path':(MASTER/'主库.json').relative_to(ROOT).as_posix(),'version':master['version'],'sha256':sha(MASTER/'主库.json'),'approved':True,
        'confirmation_path':(CHILDREN/'主库确认记录.json').relative_to(ROOT).as_posix()},
      'industries':{'path':CHILDREN.relative_to(ROOT).as_posix(),'overview_path':(CHILDREN/'子库总览.json').relative_to(ROOT).as_posix(),'version':children['version'],
        'count':11,'job_memberships':19018,'retained_specialized_jds':843,'audit_path':(CHILDREN/'独立核验报告.json').relative_to(ROOT).as_posix()},
      'portal':{'path':html.relative_to(ROOT).as_posix(),'version':build['version'],'sha256':sha(html),'industry_codes_migrated':True},
      'maintenance_tool':{'migrated':False,'enabled_in_portal':False}}
    pointer=ROOT/'当前发布版本.json';pointer.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    files={'BMJD主库与行业子库.html':html,'使用说明.md':PAGE/'使用说明.md',
      '当前发布版本.json':pointer,'核验/页面构建核验.json':PAGE/'页面构建核验.json','核验/页面浏览器核验.json':PAGE/'页面浏览器核验.json'}
    for folder in [MASTER,CHILDREN]:
        for p in sorted(folder.rglob('*')):
            if p.is_file():files[folder.name+'/'+p.relative_to(folder).as_posix()]=p
    manifest={'version':'BMJD-INDUSTRY-RELEASE-20261030-01','date':'2026-10-30','approved_master_version':master['version'],
      'approved_master_sha256':sha(MASTER/'主库.json'),'industry_version':children['version'],'page_version':build['version'],
      'jobs':9111,'industry_job_memberships':19018,'retained_industry_specialized_jds':843,'entry':'BMJD主库与行业子库.html',
      'files':{n:{'bytes':p.stat().st_size,'sha256':sha(p),'source':p.relative_to(ROOT).as_posix()} for n,p in files.items()},
      'scope':'确认主库保持不变；11个新行业子库和查岗HTML同版；旧行业库、旧HTML、原新增工具不覆盖。'}
    p=PAGE/'发布清单.json';p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');files['发布清单.json']=p
    OUTPUT.mkdir(exist_ok=True)
    downloads=[(html,'BMJD主库与11行业子库_20261030.html'),(CHILDREN/'BMJD_11行业子库.xlsx','BMJD_11行业子库_同步版_20261030.xlsx')]
    for p,n in downloads:shutil.copyfile(p,OUTPUT/n);assert sha(p)==sha(OUTPUT/n)
    archive=OUTPUT/'BMJD主库与11行业子库_同步版_20261030.zip';prefix='BMJD主库与11行业子库_20261030/'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for n,p in files.items():z.write(p,prefix+n)
    with ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(files)
        for n,p in files.items():assert hashlib.sha256(z.read(prefix+n)).hexdigest()==sha(p),n
    print(json.dumps({'all_passed':True,'files':len(files),'zip_bytes':archive.stat().st_size,'downloads':[n for _,n in downloads]+[archive.name]},ensure_ascii=False))


if __name__=='__main__':main()
