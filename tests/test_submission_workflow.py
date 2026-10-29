"""Release-specific integrity tests; all candles here are fabricated fixtures."""
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from quant.data import digest, json_write
from quant.ledger import Ledger
from quant.publication import _seal
from scripts.build_bibliography import build
from scripts import restore_market_inputs as inputs
from scripts import reproduce_complete_study as master
from scripts import package_submission as package
from scripts.market_interval_diagnostics import expected_mbb_mean


def fixture_project(tmp_path):
    project=tmp_path/'project'; supplied=tmp_path/'cache'
    supplied.mkdir()
    filename='BTCUSDT-1d-2017-09.zip'
    opened=1504224000000
    rows=[[opened+i*86400000,1,2,.5,1.5,10,opened+(i+1)*86400000-1] for i in range(2)]
    payload=io.BytesIO()
    with ZipFile(payload,'w') as z:
        z.writestr(filename.replace('.zip','.csv'),''.join(','.join(map(str,r+[15,3,4,5,0]))+'\n' for r in rows))
    raw=payload.getvalue(); raw_sha=hashlib.sha256(raw).hexdigest()
    (supplied/filename).write_bytes(raw)
    (supplied/(filename+'.CHECKSUM')).write_text(raw_sha+'  '+filename+'\n')
    metadata={'provider':'binance-public-data','symbol':'BTCUSDT','interval':'1d',
        'requested_start':'2017-09-01','requested_end':'2017-09-02',
        'csv_sha256':hashlib.sha256(inputs.canonical_csv(rows)).hexdigest(),
        'quarantined_rows':[],'sources':[{'cache_path':'old-machine/'+filename,'sha256':raw_sha,
        'url':'https://data.binance.vision/fixture/'+filename,'checksum_url':'https://data.binance.vision/fixture/'+filename+'.CHECKSUM'}]}
    manifest=project/'data/frozen.manifest.json'; json_write(manifest,metadata)
    frozen={'inputs':[{'kind':'csv','path':'data/frozen.csv','sha256':metadata['csv_sha256']},
        {'kind':'manifest','path':'data/frozen.manifest.json','sha256':digest(manifest)}]}
    freeze=project/'results/publication-v1/source-snapshots/market-freeze-v1.json'
    json_write(freeze,{**frozen,'freeze_sha256':_seal(frozen)})
    return project,supplied,freeze


def test_input_restore_reconstructs_exact_bytes_and_independently_audits(tmp_path,monkeypatch):
    project,cache,_=fixture_project(tmp_path)
    monkeypatch.setattr(inputs,'download',lambda url:pytest.fail('Fixture restoration must not use the network'))
    destination=tmp_path/'restored'
    result=inputs.restore(destination,project=project,cache_root=cache)
    assert result['status']=='completed'
    assert result['datasets'][0]['independent_audit']['retained_bars']==2
    assert digest(destination/'data/frozen.csv')==json.loads((project/'data/frozen.manifest.json').read_text())['csv_sha256']
    assert (destination/'data/frozen.manifest.json').read_bytes()==(project/'data/frozen.manifest.json').read_bytes()


@pytest.mark.parametrize('fault',['raw','checksum','existing_csv','manifest','freeze'])
def test_input_restore_refuses_silent_revision_or_overwrite(tmp_path,fault):
    project,cache,freeze=fixture_project(tmp_path)
    output=tmp_path/'restored'
    if fault=='raw':next(cache.glob('*.zip')).write_bytes(b'changed vendor bytes')
    elif fault=='checksum':next(cache.glob('*.CHECKSUM')).write_text('0'*64+'  different.zip')
    elif fault=='existing_csv':
        (output/'data').mkdir(parents=True); (output/'data/frozen.csv').write_bytes(b'user input')
    elif fault=='manifest':(project/'data/frozen.manifest.json').write_bytes(b'{}')
    else:
        value=json.loads(freeze.read_text()); value['inputs'][0]['sha256']='0'*64; json_write(freeze,value)
    with pytest.raises(ValueError):inputs.restore(output,project=project,cache_root=cache)
    if fault=='existing_csv':assert (output/'data/frozen.csv').read_bytes()==b'user input'


def test_restore_rejects_a_path_escape_even_with_a_consistent_seal(tmp_path):
    project,cache,freeze=fixture_project(tmp_path)
    saved=json.loads(freeze.read_text()); saved.pop('freeze_sha256'); saved['inputs'][0]['path']='../outside.csv'
    json_write(freeze,{**saved,'freeze_sha256':_seal(saved)})
    with pytest.raises(ValueError,match='escapes'):
        inputs.restore(tmp_path/'output',project=project,cache_root=cache)
    assert not (tmp_path/'outside.csv').exists()


@pytest.mark.parametrize('url',['http://data.binance.vision/file','https://example.com/file'])
def test_restoration_download_hosts_are_explicit(url):
    with pytest.raises(ValueError,match='vendor hosts'):inputs.download(url)


@pytest.mark.parametrize('full,verify_only',[(True,False),(False,True)])
def test_results_only_never_claims_full_replay_or_integrity_only(tmp_path,monkeypatch,full,verify_only):
    monkeypatch.setattr(master,'ROOT',tmp_path)
    with pytest.raises(ValueError):
        master.reproduce(tmp_path/'output',full=full,verify_only=verify_only,results_only=True)
    assert Ledger(tmp_path/'runs/research.sqlite').rows()[0]['status']=='failed'
    assert not (tmp_path/'output').exists()


def test_bibtex_export_preserves_journal_and_conference_semantics(tmp_path):
    source=tmp_path/'bib.json'
    records=[{'key':kind,'authors':['A. Author'],'title':'Fixture','year':2026,'venue':'Fixture venue',
              'url':'https://example.com','entry_type':kind,'note':'Internal access audit not for print'}
             for kind in ('article','inproceedings','misc')]
    json_write(source,{'records':records})
    build(source,tmp_path/'paper')
    bib=(tmp_path/'paper/references.bib').read_text()
    assert '@article{article' in bib and 'journal = {Fixture venue}' in bib
    assert '@inproceedings{inproceedings' in bib and 'booktitle = {Fixture venue}' in bib
    assert '@misc{misc' in bib and 'howpublished = {Fixture venue}' in bib
    assert 'Internal access audit' not in bib


def test_block_centering_diagnostic_matches_every_possible_resample():
    import itertools
    import numpy as np
    values=np.array([0.,1.,2.,4.,8.]); block=2
    means=[]
    for starts in itertools.product(range(len(values)-block+1),repeat=3):
        sampled=np.concatenate([values[s:s+block] for s in starts])[:len(values)]
        means.append(sampled.mean())
    assert expected_mbb_mean(values,block)==pytest.approx(np.mean(means))
    assert expected_mbb_mean(values,block)!=pytest.approx(values.mean())


def test_submission_bundle_inventory_and_fresh_extraction(tmp_path):
    archive=tmp_path/'paper.zip'
    record=package.write_archive(archive,{'main.tex':b'fixture tex'},
        {'schema_version':1,'profile':'manuscript'})
    assert record['files_verified']==1
    destination=tmp_path/'copy'
    package.verify(archive,extract=destination)
    assert (destination/'main.tex').read_bytes()==b'fixture tex'
    with pytest.raises(ValueError,match='exists'):package.verify(archive,extract=destination)


def test_submission_verifier_rejects_corruption_and_unsafe_names(tmp_path):
    archive=tmp_path/'bad.zip'
    with ZipFile(archive,'w') as z:
        z.writestr('main.tex',b'changed')
        z.writestr(package.MANIFEST,json.dumps({'schema_version':1,'profile':'manuscript',
            'files':{'main.tex':{'bytes':7,'sha256':'0'*64}}}))
    with pytest.raises(ValueError,match='hash'):package.verify(archive)
    with pytest.raises(ValueError,match='Unsafe'):
        package.write_archive(tmp_path/'unsafe.zip',{'../escape':b'x'},
            {'schema_version':1,'profile':'manuscript'})


def test_no_raw_data_profile_detects_candles_inside_nested_source_archive():
    archive=io.BytesIO()
    with ZipFile(archive,'w') as z:z.writestr('data/prices.csv',b'open_time_ms,open,high,low,close,volume,close_time_ms\n')
    assert package.contains_vendor_candles('source.zip',archive.getvalue())
    assert not package.contains_vendor_candles('table.csv',b'policy,return\nfixed,0\n')


def test_build_logging_preserves_unicode_on_an_ascii_windows_console(tmp_path,monkeypatch):
    import sys
    from scripts.reproduce_publication import _run
    raw=io.BytesIO(); console=io.TextIOWrapper(raw,encoding='ascii')
    monkeypatch.setattr(sys,'stdout',console)
    log=tmp_path/'child.log'
    _run([sys.executable,'-c',"import sys; sys.stdout.buffer.write('Unicode author: \\u015alepaczuk\\n'.encode('utf-8'))"],tmp_path,log)
    assert '\u015alepaczuk' in log.read_text(encoding='utf-8')
    console.flush()
    assert b'\\u015a' in raw.getvalue()


def test_bibliography_author_accents_are_valid_utf8_and_tex_escaped(tmp_path):
    root=Path(__file__).resolve().parents[1]
    source=root/'docs/publication/bibliography.json'
    records=json.loads(source.read_text(encoding='utf-8'))['records']
    authors={r['key']:r['authors'] for r in records}
    assert authors['bysik2026'][-1]=='Robert \u015alepaczuk'
    assert authors['kunsch1989'][0]=='Hans R. K\u00fcnsch'
    build(source,tmp_path/'paper')
    references=(tmp_path/'paper/references.tex').read_text(encoding='utf-8')
    assert "\\'{S}lepaczuk" in references and '\\"{u}nsch' in references


def test_submission_metadata_uses_compiled_number_macros_and_no_invented_identifiers():
    files={'paper/main.tex':b'\\title{Fixture\\\\ Paper}\\author{A}\\begin{abstract}Return \\Result\\%.\\end{abstract}',
           'paper/generated/numbers.tex':b'\\newcommand{\\Result}{2.607}'}
    record=package.submission_metadata(files)
    assert record['title']=='Fixture Paper' and record['abstract']=='Return 2.607%.'
    assert 'doi' not in record and record['authors'][0]['email']=='abdullah2hamza@gmail.com'
