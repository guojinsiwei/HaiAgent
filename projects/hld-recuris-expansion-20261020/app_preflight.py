"""Verify each new task's isolated world and official grader before paid solving."""
import fcntl,secrets
from pathlib import Path
from runner import R,read,save,docker,world_args,wait_world,grade
def ensure(row):
 folder=R/'preflight'/row['task'];folder.mkdir(parents=True,exist_ok=True)
 with (folder/'lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX)
  if read(folder/'ready.json').get('passed'):return read(folder/'ready.json')
  tag=secrets.token_hex(5);net='aw70-check-net-'+tag;name='aw70-check-world-'+tag
  d=folder/tag;(d/'world').mkdir(parents=True)
  image=read(R/'image.json')['image']
  try:
   docker('network','create','--internal','--label','experiment='+R.name,net)
   docker(*world_args(row,d,net,name,image))
   health=wait_world(name);assert health['task']==row['task'] and not health['ground_truth_loaded']
   docker('stop','-t','3',name)
   score=grade(row,d,image);assert score['total_count']>0 and score['success'] is False
   result=dict(passed=True,task=row['task'],blank_success=False,total_tests=score['total_count'],paid_calls=0)
   save(folder/'ready.json',result);return result
  finally:
   if docker('inspect',name,check=False).returncode==0:
    logs=docker('logs',name,check=False);(d/'world.log').write_text(logs.stdout+logs.stderr)
    docker('rm','-f',name,check=False)
   docker('network','rm',net,check=False)
if __name__=='__main__':
 print(ensure(read(R/'task-manifest.json')['tasks'][0]))
