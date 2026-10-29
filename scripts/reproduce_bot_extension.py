"""Replay the exploratory extension from its actual archived source bytes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

import numpy as np

from quant.data import digest,json_write
from quant.ledger import utc_now
from scripts.bot_extension_study import verify
from scripts.package_replication import portable_inventory
from scripts.reproduce_publication import _run

ROOT=Path(__file__).resolve().parents[1]


def reproduce(collection:Path,output:Path,*,input_root:Path=ROOT)->dict:
    accepted=verify(collection)
    f=accepted['freeze'];r=accepted['registry']
    if output.exists():raise ValueError('Choose a new replay folder; preserve earlier attempts')
    output.mkdir(parents=True)
    receipt={'status':'started','started_at':utc_now(),'registry_sha256':digest(collection/'registry.json'),
             'driver_sha256':digest(Path(__file__)),'scope':'Same pinned daily history and frozen exploratory specification; exact compute replay, not independent market evidence'}
    json_write(output/'reproduction.json',receipt)
    try:
        source=output/'source';source.mkdir()
        with ZipFile(collection/f['source_snapshot']) as archive:
            portable_inventory(archive.namelist())
            for name in archive.namelist():
                path=source/name
                if not path.resolve().is_relative_to(source.resolve()):raise ValueError('Unsafe archived source path')
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(name))
        data=input_root/f['input']['path']
        if digest(data)!=f['input']['sha256']:raise ValueError('Replay requires the exact original daily candles')
        target=source/f['input']['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(data,target)
        manifest=data.with_suffix('.manifest.json')
        if digest(manifest)!=f['input']['manifest_sha256']:raise ValueError('Replay requires the pinned daily manifest')
        shutil.copyfile(manifest,target.with_suffix('.manifest.json'))
        replay=output/'collection';replay.mkdir()
        names=['freeze.json',f['source_snapshot'],*f['preserved_inputs']]
        for name in names:
            destination=replay/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(collection/name,destination)
        environment={**os.environ,'PYTHONPATH':str((source/'src').resolve()),'PYTHONUNBUFFERED':'1'}
        origins=subprocess.run([sys.executable,'-c','import json,scripts.bot_extension_study as e,quant.engine as q; print(json.dumps([e.__file__,q.__file__]))'],
            cwd=source,env=environment,capture_output=True,text=True,encoding='utf-8',check=True)
        loaded=json.loads(origins.stdout)
        if not all(Path(p).resolve().is_relative_to(source.resolve()) for p in loaded):raise ValueError('Replay imported the wrong source')
        _run([sys.executable,'-u','-m','scripts.bot_extension_study','run','--collection',str(replay.resolve()),'--root',str(source.resolve())],source,output/'replay.log',environment=environment)
        actual=verify(replay)
        if actual['report']!=accepted['report']:raise ValueError('Replayed scientific JSON differs')
        expected_path=collection/r['matched'];actual_path=replay/actual['registry']['matched']
        if json.loads((expected_path/'trades.json').read_text())!=json.loads((actual_path/'trades.json').read_text()):raise ValueError('Replayed trades differ')
        with np.load(expected_path/'paths.npz',allow_pickle=False) as a,np.load(actual_path/'paths.npz',allow_pickle=False) as b:
            if set(a.files)!=set(b.files):raise ValueError('Replayed array inventory differs')
            for name in a.files:
                if a[name].dtype!=b[name].dtype or a[name].shape!=b[name].shape or not np.array_equal(a[name],b[name],equal_nan=True):
                    raise ValueError('Replayed scientific array differs: '+name)
            arrays=len(a.files)
        if digest(collection/'registry.json')!=receipt['registry_sha256'] or digest(Path(__file__))!=receipt['driver_sha256']:
            raise ValueError('Accepted results or driver changed during replay')
        receipt.update(status='completed',finished_at=utc_now(),import_origins=loaded,arrays_exact=arrays,
            all_scientific_json_and_trades_exact=True,replay_registry_sha256=digest(replay/'registry.json'),
            counts=actual['registry']['counts'])
        json_write(output/'reproduction.json',receipt)
        return receipt
    except Exception as error:
        json_write(output/'reproduction.json',{**receipt,'status':'failed','error':str(error)})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection',type=Path,default=ROOT/'results/bot-extension-v1')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--input-root',type=Path,default=ROOT)
    args=parser.parse_args()
    print(json.dumps(reproduce(args.collection.resolve(),args.output.resolve(),input_root=args.input_root.resolve()),indent=2))
