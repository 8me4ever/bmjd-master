"""Package the audited additive master separately from the approved v1 release."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '主库v2_层级补全_20261030'
BACKUP = ROOT / '主库备份_20261030_v1'
DELIVERY = ROOT / '主库v2交付_20261030'


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def archive(path, files):
    with ZipFile(path, 'w', compression=ZIP_DEFLATED, compresslevel=6) as z:
        for source in sorted(files):
            info = ZipInfo(source.relative_to(ROOT).as_posix(), (2026, 10, 30, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, source.read_bytes())
    with ZipFile(path) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(files)
        for source in files:
            assert hashlib.sha256(z.read(source.relative_to(ROOT).as_posix())).hexdigest() == sha(source)


def main():
    audit = read(OUT / '独立核验报告.json')
    assert audit['all_passed']
    for name, fingerprint in audit['sha256'].items():
        assert sha(ROOT / name) == fingerprint, name
    for name, fingerprint in audit['protected_v1_and_downstream_sha256'].items():
        assert sha(ROOT / name) == fingerprint, name
    for name, record in read(BACKUP / '备份清单.json')['files'].items():
        assert sha(BACKUP / name) == record['sha256'], name
    approved = read(ROOT / '当前发布版本.json')
    assert approved['master']['sha256'] == sha(BACKUP / '主库.json')
    pointer = ROOT / '主库v2工作版本.json'
    write(pointer, {
        'version': audit['version'],
        'status': 'ADDITIVE_WORKING_MASTER_PENDING_USER_REVIEW',
        'master': {'path': (OUT / '主库v2.json').relative_to(ROOT).as_posix(), 'sha256': sha(OUT / '主库v2.json')},
        'excel': {'path': (OUT / 'BMJD主库v2_层级补全.xlsx').relative_to(ROOT).as_posix(), 'sha256': sha(OUT / 'BMJD主库v2_层级补全.xlsx')},
        'audit': {'path': (OUT / '独立核验报告.json').relative_to(ROOT).as_posix(), 'sha256': sha(OUT / '独立核验报告.json')},
        'v1_backup': BACKUP.relative_to(ROOT).as_posix(),
        'summary': audit['summary'],
        'release_policy': '仅新增工作版；当前发布版本.json及11行业子库、内外HTML继续指向已确认v1。全部新增岗位单列待复核。',
    })
    DELIVERY.mkdir(exist_ok=True)
    groups = {
        'BMJD主库v2_层级补全_含审查_20261030.zip': [p for p in OUT.iterdir() if p.is_file()] + [pointer],
        'BMJD_v1主库原样备份_20261030.zip': [p for p in BACKUP.iterdir() if p.is_file()],
    }
    packages = {}
    for name, files in groups.items():
        archive(DELIVERY / name, files)
        packages[name] = {
            'bytes': (DELIVERY / name).stat().st_size, 'sha256': sha(DELIVERY / name),
            'files': {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)},
        }
    write(DELIVERY / '打包核验.json', {
        'version': audit['version'], 'all_passed': True,
        'checks': {'全部独立核验文件指纹一致': True, 'v1备份及正式下游保持': True, 'ZIP逐文件解压SHA256一致': True},
        'packages': packages,
    })
    print(json.dumps({'all_passed': True, 'packages': {n: r['bytes'] for n, r in packages.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
