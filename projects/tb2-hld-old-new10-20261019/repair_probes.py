"""Keyless integration probes for stopped main + live sidecar collection."""
from agents import OfflineHLD

class StoppedMain(OfflineHLD):
    @staticmethod
    def name():return 'offline-stopped-main-recovery'
    async def run(self,instruction,environment,context):
        await self.exec_as_root(environment,'echo recovery-marker > /logs/agent/private-marker && chmod 600 /logs/agent/private-marker',timeout_sec=30)
        # Reproduce the actual task's supervisord shutdown, without a model call.
        await environment._run_docker_compose_command(['exec','-T','main','sh','-c','supervisorctl -c /app/supervisor.conf shutdown'],check=False,timeout_sec=30)
        await environment.stop_service('main')
        context.metadata={'paid_calls':0,'offline_acceptance':True,'simulated_main_shutdown':True}
