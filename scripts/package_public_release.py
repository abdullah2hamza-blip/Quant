"""Assemble a reviewed public tree, research archive and standalone TeX source.

The allowlist excludes local histories and superseded distributions. Accepted
scientific collections are copied unchanged; nothing is committed or uploaded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED

from quant.data import digest, json_write
from quant.ledger import Ledger
from scripts.package_replication import completed_report, portable_inventory, staged_paper
from scripts.package_submission import contains_vendor_candles, submission_metadata
from scripts.kaggle_review import MANIFEST, verify_archive, verify_directory
from scripts.build_publication_artifacts import verify_results
from scripts.build_followup_artifacts import verify_collection
from scripts.bot_extension_study import verify as verify_bot_extension

ROOT = Path(__file__).resolve().parents[1]
MAX_GITHUB_FILE = 100 * 1024**2
ROOT_FILES = ('README.md', 'LICENSE', 'LICENSE-PAPER.md', 'THIRD_PARTY.md',
              'CITATION.cff', 'pyproject.toml', 'uv.lock', '.python-version',
              '.gitattributes', '.gitignore')
PUBLIC_DOCS = ('README.md', 'STATUS.md', 'REPRODUCE.md', 'SUBMIT.md', 'COVER-LETTER.md',
               'bibliography.json', 'literature-comparison.md', 'protocol-v1.md',
               'protocol-v1-addendum-01.md', 'market-protocol-v1.md',
               'followup-protocol-v2.md', 'bot-extension-protocol-2026-10-23.md',
               'reporting-note-01.md', 'reporting-note-02.md',
               'RELEASE-REVIEW-2026-10-28.md', 'CLAIM-EVIDENCE.md',
               'DATASET-CARD.md', 'RELEASE-NOTES.md')
EXCLUDED_PARTS = {'__pycache__', '.venv', '.pytest_cache', 'plot-cache', 'state'}


def validate_payloads(files: dict[str, bytes], *, limit=MAX_GITHUB_FILE) -> None:
    portable_inventory(list(files))
    for name, payload in files.items():
        parts = Path(name).parts
        if (set(parts) & EXCLUDED_PARTS or '.git' in parts
                or any(p == '.env' or p.startswith('.env.') for p in parts)
                or name.endswith(('.sqlite-wal', '.sqlite-shm'))
                or name.startswith(('runs/', 'tmp/', 'output/submission-', 'output/replication/'))):
            raise ValueError('Local/private payload in public tree: ' + name)
        if len(payload) > limit:
            raise ValueError('File exceeds GitHub regular-file limit: ' + name)
        if contains_vendor_candles(name, payload):
            raise ValueError('Raw vendor candles in public release: ' + name)
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', payload):
            raise ValueError('Private-key material in public payload: ' + name)
        if re.search(rb'\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,})\b', payload):
            raise ValueError('Credential-like token in public payload: ' + name)


def source_files(root: Path) -> dict[str, bytes]:
    result = {}
    def add(p, name=None):
        if p.is_symlink():
            raise ValueError('Symlink in public source')
        result[name or p.relative_to(root).as_posix()] = p.read_bytes()
    for directory in ('src', 'scripts', 'tests', 'configs', '.github', 'results', 'kaggle'):
        for p in sorted((root/directory).rglob('*')):
            if (p.is_file() and not set(p.parts) & EXCLUDED_PARTS
                    and p.suffix not in ('.pyc', '.log', '.aux', '.out', '.xdv', '.sqlite-wal', '.sqlite-shm')):
                add(p)
    for name in ROOT_FILES:
        add(root/name)
    for name in PUBLIC_DOCS:
        add(root/'docs/publication'/name)
    for name in ('GITHUB.md', 'KAGGLE.md'):
        add(root/'docs'/name)
    frozen = json.loads((root/'results/publication-v1/source-snapshots/market-freeze-v1.json').read_text())
    for item in frozen['inputs']:
        if item['kind'] == 'manifest':
            p = root/item['path']
            if digest(p) != item['sha256']:
                raise ValueError('Pinned data manifest changed')
            add(p)
    # Preserve the accepted delivered source, excluding its four vendor seeds.
    delivered = root/'results/bot-extension-v1/delivered/bot'
    for p in sorted(delivered.rglob('*')):
        if p.is_file():
            add(p, 'bots/btc_trend_bot/'+p.relative_to(delivered).as_posix())
    return result


def archive(path: Path, files: dict[str, bytes], manifest: dict, *, marker=MANIFEST) -> None:
    portable_inventory([*files, marker])
    with ZipFile(path, 'x') as zipped:
        for name, payload in sorted(files.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = ZIP_STORED if Path(name).suffix in ('.npz', '.zip', '.pdf', '.png') else ZIP_DEFLATED
            zipped.writestr(info, payload)
        zipped.writestr(marker, json.dumps(manifest, indent=2, allow_nan=False)+'\n', compress_type=ZIP_DEFLATED)


def inventory(files):
    return {name: {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
            for name, payload in sorted(files.items())}


def create(output: Path, *, rebuild: Path, qa: Path, pdf: Path, root=ROOT,
           revision: str = 'v6') -> dict:
    root = Path(root)
    if not re.fullmatch(r'v[1-9][0-9]*', revision):
        raise ValueError('Revision must be a portable v-number, such as v4')
    if output.exists():
        raise ValueError('Preserve prior release candidates; choose a new directory')
    saved = json.loads((rebuild/'reproduction.json').read_text())
    report = completed_report(rebuild/'reproduction.json', Ledger(root/'runs/research.sqlite'),
                              kind='complete_publication_reproduction', mode=saved['mode'])
    if report['mode'] not in ('paper rebuild from preserved substantive results',
                              'results-only paper rebuild; no raw-data audit or computation'):
        raise ValueError('Require a current completed manuscript rebuild')
    for name, expected in report['executed_source_guard'].items():
        if digest(root/name) != expected:
            raise ValueError('Executed source changed after manuscript rebuild: '+name)
    verified = (verify_results(root/'results/publication-v1'),
                verify_collection(root/'results/publication-v2'),
                verify_bot_extension(root/'results/bot-extension-v1'))
    del verified
    registries = {}
    for key, name in (('baseline_registry_sha256', 'publication-v1'),
                      ('followup_registry_sha256', 'publication-v2'),
                      ('bot_extension_registry_sha256', 'bot-extension-v1')):
        relative = 'results/'+name+'/registry.json'
        if digest(root/relative) != report[key]:
            raise ValueError('Scientific registry differs from the manuscript rebuild')
        registries[relative] = report[key]
    qa_record = json.loads(qa.read_text())
    from pypdf import PdfReader
    pages = len(PdfReader(pdf).pages)
    if (digest(pdf) != report['pdf']['sha256'] or digest(pdf) != qa_record['pdf_sha256']
            or qa_record['pages_rendered'] != pages
            or qa_record['pages_visually_inspected'] != list(range(1, pages+1))
            or qa_record['observed_layout_defects'] or not qa_record['all_fonts_embedded']):
        raise ValueError('Matching all-page visual/font QA is required')
    paper = staged_paper(rebuild, report)
    files = source_files(root)
    files.update(paper)
    files[f'output/pdf/cost-aware-bitcoin-research-{revision}.pdf'] = pdf.read_bytes()
    provenance = {'kind': 'public_manuscript_build_receipt', 'originating_report_sha256': digest(rebuild/'reproduction.json'),
                  'pdf_sha256': digest(pdf), 'pages': pages, 'scientific_registries': registries,
                  'executed_source_guard': report['executed_source_guard'],
                  'source_inventory_scope': 'Executed source and compiled paper inputs are included; historical local working-document snapshots are excluded.',
                  'compiler': {k: report['pdf'][k] for k in ('version', 'compiler_binary_sha256')},
                  'qa_sha256': digest(qa)}
    files['provenance/manuscript-build.json'] = (json.dumps(provenance, indent=2)+'\n').encode()
    files['provenance/manuscript-qa.json'] = qa.read_bytes()
    for name, expected in report['executed_source_guard'].items():
        if hashlib.sha256(files[name]).hexdigest() != expected or digest(root/name) != expected:
            raise ValueError('Captured executed source differs: '+name)
    if any(hashlib.sha256(files[name]).hexdigest() != expected for name, expected in registries.items()):
        raise ValueError('A registry changed during public capture')
    validate_payloads(files)
    manifest = {'schema_version': 1, 'profile': 'research-release-'+revision,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'files': inventory(files), 'scientific_registries': registries,
                'paper': {'sha256': digest(pdf), 'pages': pages},
                'rights': 'Original software MIT; original prose/synthetic displays CC BY4.0; market-material exceptions in THIRD_PARTY.md.',
                'scope': 'Prepared local release; no upload, hosted CI, hosted notebook execution or new scientific evidence asserted.'}
    output.mkdir(parents=True)
    tree = output/'github'; tree.mkdir()
    for name, payload in files.items():
        destination = tree/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    json_write(tree/MANIFEST, manifest)
    verify_directory(tree)
    # Validate the captured collection bytes, not only the originating tree or
    # the registry files. This also catches a payload changing during capture.
    verify_results(tree/'results/publication-v1')
    verify_collection(tree/'results/publication-v2')
    verify_bot_extension(tree/'results/bot-extension-v1')
    research = output/f'quant-research-release-{revision}.zip'
    archive(research, files, manifest)
    verify_archive(research)
    source = {name.removeprefix('paper/'): payload for name, payload in paper.items()
              if Path(name).suffix in ('.tex', '.bib', '.png', '.sty', '.cls')}
    for name in ('LICENSE-PAPER.md', 'THIRD_PARTY.md', 'CITATION.cff'):
        source[name] = files[name]
    tex = output/f'manuscript-source-{revision}.zip'
    archive(tex, source, {'schema_version': 1, 'profile': 'standalone-manuscript-'+revision,
                         'files': inventory(source), 'pdf_sha256': digest(pdf)}, marker='MANUSCRIPT-RELEASE.json')
    json_write(output/'submission-metadata.json', {**submission_metadata(paper), 'version': 'release-'+revision})
    for name in ('COVER-LETTER.md', 'SUBMIT.md'):
        (output/name).write_bytes(files['docs/publication/'+name])
    receipt = {'status': 'created and byte-verified; extracted execution is a separate final gate',
               'created_at': manifest['created_at'], 'public_manifest_sha256': digest(tree/MANIFEST),
               'scientific_registries': registries, 'pdf_sha256': digest(pdf), 'pages': pages,
               'archives': {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in (research, tex)},
               'public_files': len(files), 'public_bytes': sum(len(p) for p in files.values()),
               'largest_regular_file_bytes': max(map(len, files.values())),
               'github_limit_bytes': MAX_GITHUB_FILE, 'next_gate': 'Validate extracted research/source archives and execute the offline notebook on these exact bytes.'}
    json_write(output/'release-receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rebuild', type=Path, required=True)
    parser.add_argument('--qa', type=Path, required=True)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--revision', default='v6', help='Artifact revision, for example v6')
    args = parser.parse_args()
    print(json.dumps(create(args.output, rebuild=args.rebuild, qa=args.qa, pdf=args.pdf,
                            revision=args.revision), indent=2))
