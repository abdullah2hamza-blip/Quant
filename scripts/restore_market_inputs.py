"""Restore exact frozen market inputs; changed vendor bytes never count as replay."""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import Path
import shutil
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

from quant.data import COLUMNS, decode_archive, digest, json_write, timestamp
from quant.venues import decode_bitstamp
from quant.publication import _seal
from scripts.audit_publication_data import reconcile as audit_binance
from scripts.audit_bitstamp_data import reconcile as audit_bitstamp

ROOT = Path(__file__).resolve().parents[1]


def download(url: str) -> bytes:
    allowed = {'data.binance.vision', 'www.bitstamp.net'}
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc not in allowed:
        raise ValueError('Only the frozen public vendor hosts are permitted')
    with urlopen(Request(url, headers={'User-Agent':'QuantResearch/exact-input-restoration'}), timeout=30) as response:
        if urlparse(response.geturl()).netloc not in allowed:
            raise ValueError('Unexpected vendor redirect')
        payload = response.read(100_000_001)
    if len(payload) > 100_000_000:
        raise ValueError('Vendor response too large')
    return payload


def raw_file(item: dict, destination: Path, supplied: Path | None, *, allow_download: bool) -> Path:
    name = Path(item['cache_path'].replace('\\','/')).name
    path = destination / name
    source = supplied / name if supplied else path
    if path.exists():
        source = path
    if source.is_file():
        payload = source.read_bytes()
    elif allow_download:
        payload = download(item['url'])
    else:
        raise ValueError('Missing pinned raw snapshot: '+str(source)+'; provide --cache-root or explicitly --download')
    if hashlib.sha256(payload).hexdigest() != item['sha256']:
        raise ValueError('Vendor snapshot differs from frozen SHA-256: '+name+'; obtain the original bytes, do not relabel a revision')
    destination.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        path.write_bytes(payload)
    if item.get('checksum_url'):
        checksum = path.with_name(name+'.CHECKSUM')
        candidate = source.with_name(name+'.CHECKSUM')
        if checksum.exists():
            check = checksum.read_bytes()
        elif candidate.is_file():
            check = candidate.read_bytes()
        elif allow_download:
            check = download(item['checksum_url'])
        else:
            raise ValueError('Missing independently published vendor checksum: '+str(candidate))
        fields = check.decode('ascii').strip().split()
        if len(fields)!=2 or fields[0].lower()!=item['sha256'] or fields[1].lstrip('*')!=name:
            raise ValueError('Vendor checksum record does not match the frozen archive')
        if not checksum.exists():
            checksum.write_bytes(check)
    return path


def canonical_csv(rows: list[list]) -> bytes:
    output = io.StringIO(newline='')
    writer = csv.writer(output,lineterminator='\n')
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([int(row[0]),*(format(float(x),'.17g') for x in row[1:6]),int(row[6])])
    return output.getvalue().encode('utf-8')


def restore(output_root: Path, *, project: Path=ROOT, cache_root: Path|None=None,
            allow_download: bool=False) -> dict:
    frozen = json.loads((project/'results/publication-v1/source-snapshots/market-freeze-v1.json').read_text())
    if frozen.pop('freeze_sha256')!=_seal(frozen):
        raise ValueError('Market input freeze integrity failed')
    inputs = {r['path']:r for r in frozen['inputs'] if r['kind'] in ('csv','manifest')}
    result = {'scope':'Exact original input restoration, not a new vendor snapshot or new trading evidence','datasets':[]}
    for name, expected in inputs.items():
        if expected['kind']!='csv':
            continue
        if not (output_root/name).resolve().is_relative_to(output_root.resolve()):
            raise ValueError('Frozen input path escapes the restoration root')
        manifest_rel = str(Path(name).with_suffix('.manifest.json')).replace('\\','/')
        manifest_path = project/manifest_rel
        if not manifest_path.resolve().is_relative_to(project.resolve()):
            raise ValueError('Frozen manifest path escapes the project')
        if digest(manifest_path)!=inputs[manifest_rel]['sha256']:
            raise ValueError('Pinned input manifest changed')
        metadata = json.loads(manifest_path.read_text())
        if metadata['csv_sha256']!=expected['sha256']:
            raise ValueError('Manifest and freeze disagree about normalized bytes')
        target = output_root/name
        sidecar = target.with_suffix('.manifest.json')
        if target.exists() and digest(target)!=expected['sha256']:
            raise ValueError('Refusing to overwrite a different existing input: '+str(target))
        if sidecar.exists() and digest(sidecar)!=inputs[manifest_rel]['sha256']:
            raise ValueError('Refusing to overwrite a different existing manifest')
        bitstamp = metadata['provider']=='bitstamp-public-ohlc'
        cache = output_root/'data/raw'/('bitstamp' if bitstamp else '')
        supplied = cache_root/('bitstamp' if bitstamp else '') if cache_root else None
        rows, excluded = [], []
        for item in metadata['sources']:
            raw = raw_file(item,cache,supplied,allow_download=allow_download)
            if bitstamp:
                quarantine=[]
                rows.extend(decode_bitstamp(raw.read_bytes(),item['requested_start_seconds'],
                    item['requested_end_exclusive_seconds'],metadata['interval'],quarantine))
                excluded.extend({'source_file':raw.name,**q} for q in quarantine)
            else:
                rows.extend(decode_archive(raw.read_bytes(),raw.with_suffix('.csv').name,metadata['interval'],excluded))
        begin=timestamp(date.fromisoformat(metadata['requested_start']))
        finish=timestamp(date.fromisoformat(metadata['requested_end'])+timedelta(days=1))
        rows=[r for r in rows if begin<=r[0]<finish]
        if excluded!=metadata['quarantined_rows']:
            raise ValueError('Quarantined observations differ from the frozen record')
        payload=canonical_csv(rows)
        if hashlib.sha256(payload).hexdigest()!=expected['sha256']:
            raise ValueError('Reconstructed candles differ from frozen CSV bytes')
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():target.write_bytes(payload)
        if not sidecar.exists():shutil.copyfile(manifest_path,sidecar)
        audited=(audit_bitstamp if bitstamp else audit_binance)(target,cache=cache)
        result['datasets'].append({'path':name,'sha256':digest(target),'independent_audit':audited})
    result['status']='completed'
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,default=ROOT)
    parser.add_argument('--cache-root',type=Path,help='Existing legally obtained data/raw directory; Bitstamp files beneath bitstamp/')
    parser.add_argument('--download',action='store_true',help='Explicitly fetch missing public files; vendor revisions fail pinned hashes')
    parser.add_argument('--receipt',type=Path,default=ROOT/'runs'/('restore-inputs-'+str(uuid.uuid4())+'.json'))
    args=parser.parse_args()
    if args.receipt.exists():raise ValueError('Choose a new receipt; preserve earlier attempts')
    try:
        record=restore(args.output_root.resolve(),cache_root=args.cache_root.resolve() if args.cache_root else None,allow_download=args.download)
    except Exception as error:
        json_write(args.receipt,{'status':'failed','error':str(error)})
        raise
    json_write(args.receipt,record)
    print(json.dumps({'status':record['status'],'datasets':len(record['datasets']),'receipt':str(args.receipt)},indent=2))
