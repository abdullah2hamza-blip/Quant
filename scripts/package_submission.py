"""Build named manuscript and no-raw-data replication bundles for author submission."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED

from quant.data import digest, json_write
from quant.ledger import Ledger
from scripts.package_replication import completed_report, portable_inventory, staged_paper
from scripts.build_publication_artifacts import verify_results
from scripts.build_followup_artifacts import verify_collection
from scripts.bot_extension_study import verify as verify_bot_extension

ROOT=Path(__file__).resolve().parents[1]
MANIFEST='SUBMISSION-MANIFEST.json'


def payloads_from(root: Path) -> dict[str,bytes]:
    files={}
    for directory in ('src','scripts','tests','configs','docs','.github','results'):
        for p in (root/directory).rglob('*'):
            if (p.is_file() and not {'__pycache__','plot-cache'}.intersection(p.parts)
                    and p.suffix not in ('.pyc','.aux','.log','.out','.xdv')):
                if p.is_symlink():raise ValueError('Symlink in submission payload')
                files[p.relative_to(root).as_posix()]=p.read_bytes()
    for name in ('LICENSE','LICENSE-PAPER.md','THIRD_PARTY.md','CITATION.cff','README.md',
                 'pyproject.toml','uv.lock','.python-version','.gitattributes','.gitignore'):
        files[name]=(root/name).read_bytes()
    freeze=json.loads((root/'results/publication-v1/source-snapshots/market-freeze-v1.json').read_text())
    for item in freeze['inputs']:
        if item['kind']=='manifest':
            p=root/item['path']
            if digest(p)!=item['sha256']:raise ValueError('Pinned data manifest changed before packaging')
            files[item['path']]=p.read_bytes()
    return files


def write_archive(path: Path, files: dict[str,bytes], metadata: dict) -> dict:
    if path.exists():raise ValueError('Preserve existing submission archives; choose a new name')
    portable_inventory([*files,MANIFEST])
    manifest={**metadata,'files':{name:{'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
                               for name,payload in sorted(files.items())}}
    path.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(path,'x') as archive:
        for name,payload in sorted(files.items()):
            info=ZipInfo(name,(1980,1,1,0,0,0))
            info.compress_type=ZIP_STORED if Path(name).suffix in ('.npz','.zip','.pdf','.png') else ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,payload)
        archive.writestr(MANIFEST,json.dumps(manifest,indent=2,allow_nan=False)+'\n',compress_type=ZIP_DEFLATED)
    return verify(path)


def contains_vendor_candles(name: str, payload: bytes) -> bool:
    if payload.startswith(b'open_time_ms,open,high,low,close,volume,close_time_ms'):
        return True
    if name.endswith('.zip'):
        import io
        with ZipFile(io.BytesIO(payload)) as archive:
            return any(contains_vendor_candles(member,archive.read(member)) for member in archive.namelist() if not member.endswith('/'))
    return False


def verify(path: Path, *, extract: Path|None=None) -> dict:
    with ZipFile(path) as archive:
        names=archive.namelist()
        portable_inventory(names)
        if MANIFEST not in names:raise ValueError('Missing submission manifest')
        manifest=json.loads(archive.read(MANIFEST))
        if manifest.get('schema_version')!=1 or manifest.get('profile') not in ('manuscript','replication-no-raw-data'):
            raise ValueError('Unrecognized submission profile')
        records=manifest['files']
        if set(names)!={*records,MANIFEST}:raise ValueError('Submission inventory mismatch')
        for name,record in records.items():
            info=archive.getinfo(name)
            if stat.S_ISLNK(info.external_attr>>16):raise ValueError('Symlink archive member')
            if info.file_size!=record['bytes']:raise ValueError('Submission member size mismatch')
            payload=archive.read(name)
            if hashlib.sha256(payload).hexdigest()!=record['sha256']:raise ValueError('Submission member hash mismatch: '+name)
        if extract is not None:
            if extract.exists():raise ValueError('Extraction target exists; preserve it')
            extract.mkdir(parents=True)
            for name in names:
                destination=extract/name
                if not destination.resolve().is_relative_to(extract.resolve()):raise ValueError('Unsafe extraction path')
                destination.parent.mkdir(parents=True,exist_ok=True)
                payload=archive.read(name)
                destination.write_bytes(payload)
                if digest(destination)!=hashlib.sha256(payload).hexdigest():
                    raise ValueError('Extracted member differs from verified bytes')
    return {'status':'verified bytes and inventory','archive_sha256':digest(path),'profile':manifest['profile'],
            'files_verified':len(records),'uncompressed_bytes':sum(r['bytes'] for r in records.values()),
            'extracted_to':str(extract.resolve()) if extract else None,
            'scope':'Archive validation only; actual extracted-source tests, integrity verifier and manuscript build are separate gates'}


def submission_metadata(paper: dict[str,bytes]) -> dict:
    text=paper['paper/main.tex'].decode('utf-8')
    title=re.search(r'\\title\{(.*?)\}\s*\\author',text,re.S).group(1).replace('\\\\',' ')
    abstract=re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',text,re.S).group(1)
    for name,payload in paper.items():
        if name.endswith('numbers.tex'):
            for key,value in re.findall(r'\\newcommand\{\\([A-Za-z]+)\}\{([^}]*)\}',payload.decode('utf-8')):
                abstract=abstract.replace('\\'+key,value)
    abstract=abstract.replace('\\%','%').replace('\\&','&')
    if re.search(r'\\[A-Za-z]+',abstract):raise ValueError('Unexpanded abstract macro in submission metadata')
    return {'title':' '.join(title.split()),'abstract':' '.join(abstract.split()),
        'authors':[{'name':'Abdullah Hamza','affiliation':'Independent Researcher','email':'abdullah2hamza@gmail.com'}],
        'keywords':['Sequential inference','Execution costs','Composite nuisance parameters','Bitcoin','Trend following','Reproducible research'],
        'status':'Prepared manuscript, not yet submitted; no DOI or journal reference assigned',
        'version':'submission-v2','rights':'Original paper CC BY4.0 with explicit third-party market-material exceptions; see LICENSE-PAPER.md.'}


def create(output: Path, *, rebuild: Path, qa: Path, pdf: Path, root: Path=ROOT) -> dict:
    if output.exists():raise ValueError('Choose a new submission output folder')
    ledger=Ledger(root/'runs/research.sqlite')
    saved=json.loads((rebuild/'reproduction.json').read_text())
    report=completed_report(rebuild/'reproduction.json',ledger,kind='complete_publication_reproduction',mode=saved['mode'])
    if report['mode'] not in ('paper rebuild from preserved substantive results',
                              'results-only paper rebuild; no raw-data audit or computation'):
        raise ValueError('Require the final current-manuscript rebuild')
    verify_results(root/'results/publication-v1'); verify_collection(root/'results/publication-v2')
    for key,name in (('baseline_registry_sha256','publication-v1'),('followup_registry_sha256','publication-v2')):
        if report[key]!=digest(root/'results'/name/'registry.json'):raise ValueError('Rebuild used other scientific inputs')
    extension=root/'results/bot-extension-v1'
    extension_anchor=report.get('bot_extension_registry_sha256')
    if extension_anchor is None or digest(extension/'registry.json')!=extension_anchor:
        raise ValueError('Rebuild used another or missing exploratory bot extension')
    verify_bot_extension(extension)
    for name,sha in report['executed_source_guard'].items():
        if digest(root/name)!=sha:raise ValueError('Executed helper changed after rebuild: '+name)
    qa_record=json.loads(qa.read_text())
    from pypdf import PdfReader
    pages=len(PdfReader(pdf).pages)
    if (qa_record['pdf_sha256']!=digest(pdf) or report['pdf']['sha256']!=digest(pdf)
            or qa_record['pages_visually_inspected']!=list(range(1,pages+1))
            or qa_record['pages_rendered']!=pages or qa_record['observed_layout_defects']):
        raise ValueError('Require matching complete final-page visual QA')
    paper=staged_paper(rebuild,report)
    manuscript={name.removeprefix('paper/'):payload for name,payload in paper.items()
                if Path(name).suffix in ('.tex','.bib','.png','.cls','.sty')}
    for name in ('LICENSE-PAPER.md','THIRD_PARTY.md','CITATION.cff'):
        manuscript[name]=(root/name).read_bytes()
    replication=payloads_from(root)
    if hashlib.sha256(replication['results/bot-extension-v1/registry.json']).hexdigest()!=extension_anchor:
        raise ValueError('Exploratory registry changed during package capture')
    verify_bot_extension(extension)
    # Carry the delivered operational source from the accepted capture, never
    # from a later mutable bot checkout. Its four vendor seed files stay out.
    for p in (extension/'delivered/bot').rglob('*'):
        if p.is_file():
            replication['bots/btc_trend_bot/'+p.relative_to(extension/'delivered/bot').as_posix()]=p.read_bytes()
    replication['REPLICATION-NOTES.md']=(
        '# Submission replication profile\n\n'
        'Raw and normalized vendor candles are excluded. The four data manifests\n'
        'identify exact historical bytes. See docs/publication/REPRODUCE.md for\n'
        'saved-result builds, input restoration and archived-source replay.\n\n'
        'bots/btc_trend_bot is the 47-file delivered source/evidence capture,\n'
        'identical to results/bot-extension-v1/delivered/bot. The historical\n'
        '51-file installation included four vendor seed CSV/manifest files,\n'
        'which are not distributed here. After authorized exact-input restoration,\n'
        'the bot seeds can be populated from root data/btc-1d-through-2026-10-20.csv\n'
        'and data/btc-4h-through-2026-10-20.csv and their manifests, with basenames\n'
        'btc-1d and btc-4h in bots/btc_trend_bot/data. Verify their pinned hashes\n'
        'before replay. Recorded bot installation/validation receipts describe\n'
        'the historical complete installation, not a data-free fresh install.\n'
    ).encode('utf-8')
    for name,sha in report['executed_source_guard'].items():
        if digest(root/name)!=sha:raise ValueError('Executed helper changed during package capture: '+name)
    replication.update(paper)
    replication['output/pdf/cost-aware-bitcoin-research-v2.pdf']=pdf.read_bytes()
    replication['provenance/submission-rebuild.json']=(rebuild/'reproduction.json').read_bytes()
    replication['provenance/submission-workflow.sources.zip']=(rebuild/report['workflow_source']['path']).read_bytes()
    replication['provenance/submission-pdf-qa.json']=qa.read_bytes()
    # Provider candles/raw archives are intentionally absent, including nested source ZIPs.
    forbidden=[name for name in replication if name.startswith('data/') and not name.endswith('.manifest.json')]
    forbidden += [name for name,payload in replication.items() if contains_vendor_candles(name,payload)]
    if forbidden:raise ValueError('Raw vendor data in the no-raw-data profile')
    metadata={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),
        'author':'Abdullah Hamza','title':'Cost Uncertainty in Sequential Strategy Validation: A Diagnostic Study with Adaptive Bitcoin Trend Following',
        'version':'submission-v2','pdf_sha256':digest(pdf),'pages':pages,
        'baseline_registry_sha256':report['baseline_registry_sha256'],'followup_registry_sha256':report['followup_registry_sha256'],
        'bot_extension_registry_sha256':extension_anchor,
        'rebuild_report_sha256':digest(rebuild/'reproduction.json'),'qa_sha256':digest(qa),
        'rights':'Original software MIT; original paper CC BY4.0; third-party market-material exceptions in THIRD_PARTY.md and LICENSE-PAPER.md.',
        'readiness_scope':'Prepared for author submission, not uploaded, externally peer-reviewed, or guaranteed acceptance. Exact vendor-input replay requires matching pinned snapshots.'}
    output.mkdir(parents=True)
    results={}
    for name,profile,files in (('manuscript-source-v2.zip','manuscript',manuscript),
                              ('replication-no-raw-data-v2.zip','replication-no-raw-data',replication)):
        results[name]=write_archive(output/name,files,{**metadata,'profile':profile})
    receipt={**metadata,'archives':results,'next_gate':'Run extracted-source tests, accepted-result verification and results-only manuscript build; bind their actual results in a sidecar execution audit.'}
    json_write(output/'submission-metadata.json',submission_metadata(paper))
    for name in ('COVER-LETTER.md','SUBMIT.md'):
        (output/name).write_bytes((root/'docs/publication'/name).read_bytes())
    json_write(output/'package-receipt.json',receipt)
    return receipt


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('path',type=Path)
    ap.add_argument('--verify',action='store_true')
    ap.add_argument('--extract',type=Path)
    ap.add_argument('--rebuild',type=Path)
    ap.add_argument('--qa',type=Path)
    ap.add_argument('--pdf',type=Path)
    args=ap.parse_args()
    if args.verify:
        result=verify(args.path,extract=args.extract)
    else:
        if not all((args.rebuild,args.qa,args.pdf)) or args.extract:ap.error('Creation needs --rebuild, --qa and --pdf')
        result=create(args.path,rebuild=args.rebuild,qa=args.qa,pdf=args.pdf)
    print(json.dumps(result,indent=2))
