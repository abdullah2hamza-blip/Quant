"""Public release boundaries and actual creator/consumer manifest compatibility."""
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import package_public_release as public
from scripts.kaggle_review import verify_archive, verify_directory


@pytest.mark.parametrize('name', ['../outside.py', 'CON.txt', 'a/FILE.py',
                                  '.env', 'a/.env.local', 'runs/state.json',
                                  'tmp/check.py', '.git/config', 'a/.venv/code.py',
                                  'results/live.sqlite-wal', 'results/live.sqlite-shm',
                                  'output/submission-v2/report.json'])
def test_private_nonportable_and_aliased_payloads_are_rejected(name):
    files = {name: b'fixture'}
    if name == 'a/FILE.py':
        files['a/file.py'] = b'another fixture'
    with pytest.raises(ValueError):
        public.validate_payloads(files)


def test_size_gate_and_credentials_gate():
    with pytest.raises(ValueError, match='GitHub'):
        public.validate_payloads({'results/too-large.npz': b'x'*11}, limit=10)
    with pytest.raises(ValueError, match='Private-key'):
        public.validate_payloads({'key.txt': b'-----BEGIN '+b'PRIVATE KEY-----'})
    with pytest.raises(ValueError, match='Credential'):
        public.validate_payloads({'key.txt': b'AKIA'+b'A'*16})


def test_normalized_vendor_candles_rejected_even_in_nested_source_zip():
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w') as zipped:
        zipped.writestr('vendor.csv', b'open_time_ms,open,high,low,close,volume,close_time_ms\n1,2,3,1,2,4,5\n')
    with pytest.raises(ValueError, match='vendor candles'):
        public.validate_payloads({'results/source.zip': buffer.getvalue()})


def test_public_archive_is_accepted_by_independent_kaggle_consumer(tmp_path):
    files = {'README.md': b'fixture\n', 'results/fixture/registry.json': b'{}\n'}
    public.validate_payloads(files)
    anchors = {'results/fixture/registry.json': hashlib.sha256(files['results/fixture/registry.json']).hexdigest()}
    manifest = {'schema_version': 1, 'files': public.inventory(files), 'scientific_registries': anchors}
    path = tmp_path/'release.zip'
    public.archive(path, files, manifest)
    assert verify_archive(path) == manifest
    with ZipFile(path) as zipped:
        zipped.extractall(tmp_path/'source')
    assert verify_directory(tmp_path/'source') == manifest
    (tmp_path/'source/README.md').write_bytes(b'changed')
    with pytest.raises(ValueError, match='differs'):
        verify_directory(tmp_path/'source')


def test_source_allowlist_omits_old_distributions_working_docs_and_seeds(tmp_path):
    for name in public.ROOT_FILES:
        p = tmp_path/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'fixture\n')
    for name in public.PUBLIC_DOCS:
        p = tmp_path/'docs/publication'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'public\n')
    for name in ('GITHUB.md', 'KAGGLE.md'):
        (tmp_path/'docs'/name).write_bytes(b'public\n')
    p = tmp_path/'data/pinned.manifest.json';p.parent.mkdir();p.write_bytes(b'{}\n')
    frozen = {'inputs': [{'kind': 'manifest', 'path': 'data/pinned.manifest.json',
                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}]}
    p = tmp_path/'results/publication-v1/source-snapshots/market-freeze-v1.json'
    p.parent.mkdir(parents=True);p.write_text(json.dumps(frozen))
    extra = {'docs/publication/reviews/private.md': b'working record',
             'docs/publication/FINAL-AUDIT.json': b'old record',
             'output/submission-v2/old.zip': b'old archive',
             'bots/btc_trend_bot/data/btc-4h.csv': b'local seed',
             'results/bot-extension-v1/delivered/bot/bot_core.py': b'pass\n'}
    for name,payload in extra.items():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(payload)
    files=public.source_files(tmp_path)
    assert 'data/pinned.manifest.json' in files
    assert 'bots/btc_trend_bot/bot_core.py' in files
    assert not any(name in files for name in extra if not name.startswith('results/'))
    assert not any(name.startswith(('runs/', 'output/', 'docs/publication/reviews/')) for name in files)
