"""Copy only checksum-verified public fixtures; isolate all mutable grader output."""
from pathlib import Path
import hashlib,json,shutil

def prepare_cache(assets,destination,task_id):
    assets=Path(assets).resolve();destination=Path(destination).resolve()
    if destination==assets or assets in destination.parents:
        raise ValueError('evaluation cache must be independent of shared assets')
    destination.mkdir(parents=True,exist_ok=False)
    source=assets/task_id
    records=json.loads((source/'download-manifest.json').read_text())
    folder=destination/task_id;folder.mkdir()
    for row in records:
        relative=Path(row['file']).relative_to(Path('assets')/task_id)
        original=(source/relative).resolve();target=(folder/relative).resolve()
        if not original.is_relative_to(source.resolve()) or not target.is_relative_to(folder.resolve()):
            raise ValueError('fixture path outside task cache')
        if hashlib.sha256(original.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('fixture checksum changed')
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,target)  # No hardlinks to mutable grader paths.
    (destination/'fixture-provenance.json').write_text(json.dumps(records,indent=2))
    return destination

def archive_cache(cache,manifest):
    cache=Path(cache)
    rows=[{'path':p.relative_to(cache).as_posix(),'bytes':p.stat().st_size,
           'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
          for p in sorted(cache.rglob('*')) if p.is_file()]
    Path(manifest).write_text(json.dumps(rows,indent=2))
    return rows
