"""Adapter contract tests: no task container or Docker daemon needed."""
from types import SimpleNamespace
import json
import time
import unittest
from bestfgs.lean_docker import ContinuousDockerEnvironment


class State:
    def __init__(self):
        self.initial=SimpleNamespace(snapshot_id='root',location='/mirror/root',fingerprint='root-sha')
        self.snapshots={'root':{'snapshot':self.initial}}
        self.containers=set(); self.branches=[]; self.captures=[]; self.deliveries=[]; self.commands=[]
        self.deadline=time.monotonic()+600
    def branch(self,snapshot):
        name='c'+str(len(self.branches)); self.branches.append(snapshot.snapshot_id)
        self.containers.add(name); return name
    def owned_container(self,c):
        if c not in self.containers: raise ValueError('not owned')
    def remove(self,c): self.owned_container(c); self.containers.remove(c)
    def docker(self,*args,**kwargs):
        if 'input' in kwargs:
            return json.dumps({name:'file:fixture' for name in json.loads(kwargs['input'])})
        return 'workspace-fingerprint'
    def command(self,c,action):
        self.owned_container(c); self.commands.append((c,action))
        return SimpleNamespace(exit_code=0,stdout='ok',stderr='',duration_seconds=0,timed_out=False,
                               blocked=False,output_truncated=False)
    def capture(self,c,parent):
        self.owned_container(c)
        sid='s'+str(len(self.captures)); self.captures.append((c,parent.snapshot_id))
        value=SimpleNamespace(snapshot_id=sid,location='/mirror/'+sid,fingerprint=sid+'-sha')
        self.snapshots[sid]={'snapshot':value}; return value
    def deliver(self,snapshot): self.deliveries.append(snapshot.snapshot_id)


class DockerTests(unittest.TestCase):
    def test_live_commands_do_not_commit_or_create_new_containers(self):
        state=State(); env=ContinuousDockerEnvironment(state)
        for _ in range(4): env.execute({'argv':['echo','ok']},state.deadline)
        self.assertEqual(len(state.branches),1)
        self.assertEqual(len({c for c,a in state.commands}),1)
        self.assertEqual(state.captures,[])
        checkpoint=env.checkpoint('candidate')
        self.assertEqual(len(state.captures),1)
        env.execute({'argv':['echo','new']},state.deadline)
        env.restore(checkpoint)
        self.assertEqual(len(state.containers),1)
        self.assertEqual(state.branches[-1],checkpoint['snapshot_id'])
        env.delivery(); env.close()
        self.assertEqual(state.containers,set())
    def test_repeated_checkpoint_without_changes_has_distinct_handles(self):
        state=State(); env=ContinuousDockerEnvironment(state)
        a=env.checkpoint('first'); b=env.checkpoint('second')
        self.assertNotEqual(a['id'],b['id'])
        env.restore(a); env.restore(b)
    def test_tampered_or_foreign_handle_rejected(self):
        state=State(); env=ContinuousDockerEnvironment(state)
        a=env.checkpoint('first')
        with self.assertRaises(ValueError): env.restore(dict(a,fingerprint='bad'))
    def test_external_writes_still_mark_snapshot_dirty(self):
        state=State(); env=ContinuousDockerEnvironment(state)
        before=env.scope()
        env.execute({'argv':['install','dependency']},state.deadline)
        self.assertEqual(env.scope(),before)
        env.delivery()
        self.assertEqual(len(state.captures),1)
    def test_dependency_inspection_is_path_scoped_and_validated(self):
        state=State(); env=ContinuousDockerEnvironment(state)
        self.assertEqual(env.dependency_state(['config/app.yaml']),
                         {'config/app.yaml':'file:fixture'})
        with self.assertRaises(ValueError): env.dependency_state(['../host-secret'])


if __name__=='__main__': unittest.main()
