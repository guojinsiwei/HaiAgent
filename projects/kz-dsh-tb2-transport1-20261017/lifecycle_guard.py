"""Observe/guard official Harbor boundaries; never replace its verifier or hooks."""
import contextvars,json,os
from pathlib import Path
from storage import atomic_json
CURRENT=contextvars.ContextVar('kz_trial_collection',default=None)
IN_COLLECT_HOOK=contextvars.ContextVar('kz_in_collect_hook',default=False)

class CollectionFailure(RuntimeError):pass

def record(trial,stage,**detail):
    state=getattr(trial,'_kz_lifecycle',None)
    if state is None:state=trial._kz_lifecycle={'schema_version':2,'attempt_id':os.environ.get('PAIRED_ATTEMPT_ID'),'events':[],'failures':[]}
    state['stage']=stage;state['events'].append(dict(stage=stage,**detail))
    atomic_json(trial.paths.trial_dir/'lifecycle.json',state)

def failure(trial,kind,**detail):
    trial._kz_lifecycle['failures'].append(dict(kind=kind,**detail))
    record(trial,'collection_failed',kind=kind,**detail)

def readable_logs(root):
    # Do not follow a model-created symlink or expose file contents.
    def walk_error(error):raise error
    for folder,dirs,files in os.walk(root,followlinks=False,onerror=walk_error):
        dirs[:]=[d for d in dirs if not (Path(folder)/d).is_symlink()]
        for name in files:
            p=Path(folder)/name
            if not p.is_symlink() and p.is_file():
                with p.open('rb') as stream:stream.read(1)

async def handoff_logs(env):
    await env.prepare_logs_for_host()
    # Fixed trusted bind mount only; find -P never follows solver symlinks.
    command=f"test ! -L /logs/agent && find -P /logs/agent -xdev -type d -exec chown {os.getuid()}:{os.getgid()} {{}} + -exec chmod u+rwx {{}} + && find -P /logs/agent -xdev -type f -exec chown {os.getuid()}:{os.getgid()} {{}} + -exec chmod u+r {{}} +"
    result=await env._run_docker_compose_command(['exec','-T','-u','root','main','sh','-c',command],check=False,timeout_sec=60)
    if result.return_code:raise CollectionFailure('Explicit private log handoff failed')

def install(Trial,DockerEnvironment,ArtifactHandler):
    if getattr(Trial,'_kz_guard_installed',False):return
    # Check the entire adapter contract before mutating any upstream class.
    for cls,names in ((Trial,('_collect_artifacts_phased','_run_collect_hooks','_verify_with_timeout','_finalize')),
                      (DockerEnvironment,('stop_service','_run_docker_compose_command','service_exec','prepare_logs_for_host')),
                      (ArtifactHandler,('_download_artifact',))):
        for name in names:
            if not callable(getattr(cls,name,None)):
                raise RuntimeError(f'Unsupported Harbor interface: {cls.__name__}.{name}')
    collect=Trial._collect_artifacts_phased
    collect_hooks=Trial._run_collect_hooks
    verify=Trial._verify_with_timeout
    finalize=Trial._finalize
    stop_service=DockerEnvironment.stop_service
    compose=DockerEnvironment._run_docker_compose_command
    service_exec=DockerEnvironment.service_exec
    download=ArtifactHandler._download_artifact

    async def observed_hooks(self,*a,**kw):
        token=IN_COLLECT_HOOK.set(True)
        try:return await collect_hooks(self,*a,**kw)
        finally:IN_COLLECT_HOOK.reset(token)

    async def guarded_collect(self,*a,**kw):
        record(self,'solver_finished');record(self,'collecting')
        token=CURRENT.set(self)
        try:
            await handoff_logs(self.agent_environment)
            await collect(self,*a,**kw)
            readable_logs(self.paths.agent_dir)
            if self._kz_lifecycle['failures']:raise CollectionFailure('Trusted artifact collection failed; see lifecycle.json')
            record(self,'artifacts_collected')
        except Exception as error:
            if not self._kz_lifecycle['failures']:failure(self,'collection_or_log_handoff',error_type=type(error).__name__)
            raise
        finally:CURRENT.reset(token)

    async def guarded_stop(self,service):
        trial=CURRENT.get()
        if trial is not None and self is trial.agent_environment:
            if service!='main':
                failure(trial,'premature_sidecar_stop',service=service)
                raise CollectionFailure('Sidecar stop before collection is forbidden')
            # The main service will no longer be executable after this boundary.
            await handoff_logs(self)
            readable_logs(trial.paths.agent_dir)
            record(trial,'logs_handed_to_host')
        return await stop_service(self,service)

    async def guarded_compose(self,command,*a,**kw):
        trial=CURRENT.get()
        if trial is not None and self is trial.agent_environment and command and (
            command[0]=='down' or command[0]=='stop' and command!=['stop','main']):
            failure(trial,'premature_project_stop')
            raise CollectionFailure('Project teardown before collection is forbidden')
        if command==['down']:command=['down','--volumes']
        return await compose(self,command,*a,**kw)

    async def observed_exec(self,*a,**kw):
        trial=CURRENT.get();service=kw.get('service') or 'main'
        try:
            result=await service_exec(self,*a,**kw)
            if IN_COLLECT_HOOK.get() and trial is not None and self is trial.agent_environment and service!='main' and result.return_code!=0:
                failure(trial,'sidecar_collect_hook',service=service,exit_code=result.return_code)
            return result
        except Exception as error:
            if IN_COLLECT_HOOK.get() and trial is not None and self is trial.agent_environment and service!='main':
                failure(trial,'sidecar_collect_exception',service=service,error_type=type(error).__name__)
            raise

    async def observed_download(self,*a,**kw):
        result=await download(self,*a,**kw);trial=CURRENT.get()
        if trial is not None and result.service not in (None,'main'):
            bad=result.status!='ok'
            if not bad and result.type=='file':
                base=Path(kw['artifacts_dir']).resolve();relative=Path(result.destination)
                # Official manifest destinations are prefixed with artifacts/,
                # including when artifacts_dir is a step-specific directory.
                target=(base/Path(*relative.parts[1:])).resolve() if relative.parts and relative.parts[0]=='artifacts' else base.parent
                bad=not target.is_relative_to(base) or not target.is_file() or target.stat().st_size==0
            if bad:failure(trial,'sidecar_artifact_missing_or_empty',service=result.service,status=result.status)
        return result

    async def guarded_verify(self,*a,**kw):
        state=getattr(self,'_kz_lifecycle',{})
        if state.get('failures') or state.get('stage')!='artifacts_collected':
            raise CollectionFailure('Verification requires successful trusted collection')
        from verifier_setup import prepare_verifier,validate_test_report,verifier_network
        verifier=a[0] if a else kw['verifier']
        try:
            with verifier_network(verifier):
                await prepare_verifier(verifier)
                record(self,'verifying')
                result=await verify(self,*a,**kw)
                validate_test_report(verifier)
                record(self,'verifier_finished');return result
        except Exception as error:record(self,'verifier_failed',error_type=type(error).__name__);raise

    async def observed_finalize(self,*a,**kw):
        # A broken audit disk must not prevent the official cleanup attempt.
        audit_error=None
        try:record(self,'cleanup_started')
        except OSError as error:audit_error=error
        try:
            result=await finalize(self,*a,**kw)
        except BaseException as error:
            try:
                state=getattr(self,'_kz_lifecycle',None)
                if state is not None:state['failures'].append(dict(kind='cleanup_failed',error_type=type(error).__name__))
                record(self,'cleanup_failed',error_type=type(error).__name__)
            except OSError:pass  # Preserve the actual cleanup exception.
            raise
        if audit_error is not None:raise audit_error
        record(self,'cleanup_succeeded')
        return result

    Trial._collect_artifacts_phased=guarded_collect
    Trial._run_collect_hooks=observed_hooks
    Trial._verify_with_timeout=guarded_verify
    Trial._finalize=observed_finalize
    DockerEnvironment.stop_service=guarded_stop
    DockerEnvironment._run_docker_compose_command=guarded_compose
    DockerEnvironment.service_exec=observed_exec
    ArtifactHandler._download_artifact=observed_download
    Trial._kz_guard_installed=True
