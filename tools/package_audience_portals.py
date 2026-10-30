"""Export the independent internal/customer HTMLs and an internal archive."""
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'BMJD内外双版_20261030';OUTPUT=ROOT.parent/'outputs'
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    build=read(OUT/'构建核验.json');browser=read(OUT/'浏览器核验.json')
    assert build['all_passed'] and browser['all_passed']
    for n,h in build['input_sha256'].items():assert sha(ROOT/n)==h,n
    pointer=ROOT/'当前发布版本.json';current=read(pointer)
    assert current['master']['version']==build['master_version'] and current['industries']['version']==build['industry_version']
    assert sha(ROOT/current['master']['path'])==current['master']['sha256']
    portals={}
    for a,r in build['profiles'].items():
        p=OUT/r['file'];assert sha(p)==r['html_sha256']==browser['html_sha256'][a]
        portals[a]={'path':p.relative_to(ROOT).as_posix(),'version':r['version'],'sha256':sha(p),'audience':a,'pagination':False,'industry_codes_migrated':True}
    current.update(release_version=build['version'],status='MASTER_APPROVED_DUAL_PORTALS_RELEASED',portal=portals['internal'],portals=portals)
    pointer.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    files={r['file']:OUT/r['file'] for r in build['profiles'].values()}
    files.update({'使用说明.md':OUT/'使用说明.md','核验/构建核验.json':OUT/'构建核验.json','核验/浏览器核验.json':OUT/'浏览器核验.json','当前发布版本.json':pointer})
    manifest={'version':build['version'],'date':'2026-10-30','master_version':build['master_version'],'industry_version':build['industry_version'],
      'profiles':portals,'jobs':9111,'pagination':False,'files':{n:{'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in files.items()},
      'distribution':'客户转发使用客户版单文件；双版汇总包用于公司内部保存。'}
    p=OUT/'发布清单.json';p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');files['发布清单.json']=p
    OUTPUT.mkdir(exist_ok=True)
    names={'internal':'BMJD_内部使用版_无分页_20261030.html','client':'BMJD_客户查询版_无分页_20261030.html'}
    for a,n in names.items():
        p=OUT/build['profiles'][a]['file'];shutil.copyfile(p,OUTPUT/n);assert sha(p)==sha(OUTPUT/n)
    archive=OUTPUT/'BMJD_内部与客户双版本_20261030.zip';prefix='BMJD内部与客户双版本_20261030/'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for n,p in files.items():z.write(p,prefix+n)
    with ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(files)
        for n,p in files.items():assert hashlib.sha256(z.read(prefix+n)).hexdigest()==sha(p),n
    print(json.dumps({'all_passed':True,'files':len(files),'zip_bytes':archive.stat().st_size,'downloads':list(names.values())+[archive.name]},ensure_ascii=False))


if __name__=='__main__':main()
