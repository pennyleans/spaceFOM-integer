"""Acquire the pinned official GMAT archive outside the repository; no redistribution."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

URL='https://downloads.sourceforge.net/project/gmat/GMAT/GMAT-R2026a/gmat-win-R2026a.zip'
SHA256='f7b00bdeb51e75f5f0a93380a97109f0505e75396f69a43cd5583c21f5fed9fc'


def acquire(root):
    root.mkdir(parents=True,exist_ok=True)
    archive_path=root/'gmat-win-R2026a.zip'
    if not archive_path.exists():
        urllib.request.urlretrieve(URL,archive_path)
    actual=hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if actual!=SHA256:raise ValueError('pinned GMAT archive hash mismatch')
    destination=root/'GMAT-R2026a-console'
    if destination.exists():raise FileExistsError('use a fresh external directory; existing reference is retained')
    members=[]
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            path=(destination/info.filename).resolve()
            if not path.is_relative_to(destination.resolve()):raise ValueError('archive member escapes destination')
            if info.is_dir():
                path.mkdir(parents=True,exist_ok=True)
            elif info.filename.startswith('data/') or info.filename in ('bin/GmatConsole.exe','bin/libGmatBase.dll','bin/libGmatUtil.dll','bin/gmat_startup_file.txt','License.txt','README.txt'):
                data=archive.read(info)
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(data)
                members.append({'path':info.filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'zip_crc32':f'{info.CRC:08x}'})
    startup=destination/'bin/gmat_startup_file.txt'
    original=startup.read_bytes()
    startup.with_name('gmat_startup_file.original.txt').write_bytes(original)
    text='\n'.join('# qualification: disabled '+line if line.lstrip().startswith('PLUGIN ') else line for line in original.decode().splitlines())
    startup.write_text(text,encoding='utf-8')
    (destination/'output').mkdir(exist_ok=True)
    receipt={'version':'R2026a','source':URL,'archive_sha256':SHA256,'license':'Apache-2.0 for GMAT; bundled third-party/data terms remain external','scope':'development-only console reference; no runtime redistribution','startup_change':'all optional plugins disabled; core runtime binaries unchanged','members':members}
    (root/'gmat-acquisition.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('external_directory',type=Path)
    acquire(parser.parse_args().external_directory)
