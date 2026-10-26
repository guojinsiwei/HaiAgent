"""Official AndroidWorld UIAUTOMATOR backend, without fragile a11y gRPC service.

UI structure remains controller/evaluator-only; Solver receives PNG screenshots.
Task generation, initializers, action implementations and graders are unchanged.
"""
def load_environment():
    from android_transport import install_cpu_launch_timeout
    install_cpu_launch_timeout()
    from android_env import loader
    from android_env.components import config_classes
    from android_world.env import android_world_controller as official
    from android_world.env import interface,env_launcher
    launcher=config_classes.EmulatorLauncherConfig(emulator_console_port=5554,
        adb_port=5555,grpc_port=8554)
    if hasattr(launcher,'connect_to_existing'):launcher.connect_to_existing=True
    cfg=config_classes.AndroidEnvConfig(
        task=config_classes.FilesystemTaskConfig(path=official._write_default_task_proto()),
        simulator=config_classes.EmulatorConfig(emulator_launcher=launcher,
            adb_controller=config_classes.AdbControllerConfig(adb_path='/opt/android/platform-tools/adb')))
    base=loader.load(cfg)
    from android_world.env import adb_utils,representation_utils
    from android_ui import fresh_hierarchy
    class StableUIController(official.AndroidWorldController):
        def get_ui_elements(self):
            def request(args):
                return adb_utils.issue_generic_request(args,self._env,timeout_sec=30).generic.output.decode('utf-8')
            return representation_utils.xml_dump_to_ui_elements(fresh_hierarchy(request))
    controller=StableUIController(base,a11y_method=official.A11yMethod.UIAUTOMATOR,
        install_a11y_forwarding_app=False)
    env=interface.AsyncAndroidEnv(controller)
    env_launcher.setup_env(env,emulator_setup=False)
    return env
