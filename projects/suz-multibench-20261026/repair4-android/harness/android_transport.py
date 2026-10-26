"""CPU cold-start allowance without changing official commands or retry counts."""
def command_timeout(args,timeout):
    app_start=(args[:3]==['shell','am','start'] or args[:2]==['shell','monkey'])
    if app_start:return max(float(timeout or 0),45)
    return timeout


def install_cpu_launch_timeout():
    from android_env.components import adb_controller
    cls=adb_controller.AdbController
    if getattr(cls,'_suz_cpu_launch_timeout',False):return
    execute=cls.execute_command
    def bounded(self,args,timeout=None,device_specific=True):
        return execute(self,args,timeout=command_timeout(args,timeout),device_specific=device_specific)
    cls.execute_command=bounded
    cls._suz_cpu_launch_timeout=True
