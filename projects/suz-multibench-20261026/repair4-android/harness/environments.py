"""Official task setup/scoring isolated from screenshot-only agent observations."""
import io,json,os,subprocess,time,types,sys,uuid
from pathlib import Path
from PIL import Image
from action_bridge import DesktopActions,AndroidActions


def forbidden_judge(*args,**kwargs):
    raise RuntimeError('LLM grading forbidden in this experiment')


def install_no_llm_grading():
    # Official deterministic evaluators import this function but selected tasks
    # never invoke it. Deny all calls even if task-selection validation regresses.
    for name in ['llms','llms.providers','llms.providers.openai_utils']:
        module=types.ModuleType(name);module.__path__=[];sys.modules[name]=module
    sys.modules['llms.providers.openai_utils'].generate_from_openai_chat_completion=forbidden_judge


class WebEnvironment:
    def __init__(self,task,directory):
        self.task=task;self.directory=Path(directory);self.controller=self
        self.processes=[];self.browser=None;self.playwright=None
    def reset(self,task_config=None):
        from playwright.sync_api import sync_playwright
        Path.home().joinpath('.Xauthority').touch(exist_ok=True)
        os.environ['XDG_SESSION_TYPE']='x11'
        self.processes=[subprocess.Popen(['Xvfb',':99','-screen','0','1280x900x24','-nolisten','tcp'])]
        time.sleep(1)
        self.processes.append(subprocess.Popen(['fluxbox'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        self.playwright=sync_playwright().start()
        self.browser=self.playwright.chromium.launch(headless=False,args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--window-position=0,0','--window-size=1280,900'])
        self.context=self.browser.new_context(no_viewport=True,record_har_path=str(self.directory/'network.har'))
        self.page=self.context.new_page();site=self.task['sites'][0]
        if self.task.get('require_login'):
            from browser_env.env_config import ACCOUNTS
            account=ACCOUNTS[site];url=os.environ[site.upper()]
            if site=='reddit':
                self.page.goto(url+'/login');self.page.get_by_label('Username').fill(account['username']);self.page.get_by_label('Password').fill(account['password']);self.page.get_by_role('button',name='Log in').click()
            elif site=='shopping':
                self.page.goto(url+'/customer/account/login/');self.page.get_by_label('Email',exact=True).fill(account['username']);self.page.get_by_label('Password',exact=True).fill(account['password']);self.page.get_by_role('button',name='Sign In').click()
            else:raise ValueError('site not provisioned in pilot')
        self.page.goto(self.task['start_url'],wait_until='domcontentloaded');time.sleep(2)
        subprocess.run(['wmctrl','-r',':ACTIVE:','-b','add,maximized_vert,maximized_horz'],check=False)
        self.actions=DesktopActions();return {'screenshot':self.get_screenshot()}
    def get_screenshot(self):
        import pyautogui
        target=self.directory/('screen-'+uuid.uuid4().hex+'.png')
        try:
            buf=io.BytesIO();pyautogui.screenshot(imageFilename=str(target)).save(buf,format='PNG');return buf.getvalue()
        finally:target.unlink(missing_ok=True)
    def transport_preflight(self):
        # Independent synthetic page; DOM assertions belong only to deployment tests.
        test=self.context.new_page()
        test.set_content('<html><body style="padding:40px"><input autofocus id="t"><button onclick="document.body.dataset.done=document.querySelector(\'#t\').value;document.body.style.background=\'#00b500\'">Save</button></body></html>')
        test.bring_to_front();test.locator('#t').focus();time.sleep(1)
        actions=["pyautogui.write('SUZ-preflight-42')", "pyautogui.press('tab')", "pyautogui.press('enter')"]
        for i,action in enumerate(actions):
            obs,_,_,_=self.step(action,pause=.5)
            (self.directory/f'probe-{i}.png').write_bytes(obs['screenshot'])
        assert test.evaluate('document.body.dataset.done')=='SUZ-preflight-42'
        im=Image.open(io.BytesIO(obs['screenshot'])).convert('RGB')
        assert im.getpixel((600,400))==(0,181,0),'Screenshot stale or wrong active window'
        test.close();self.page.bring_to_front()
        return {'sequential_batches':3,'input_and_activation_verified':True}
    def step(self,action,pause=2):
        if action not in {'WAIT','DONE','FAIL'}:self.actions.execute(action)
        time.sleep(pause)
        return {'screenshot':self.get_screenshot()},0,action in {'DONE','FAIL'},{}
    def evaluate(self):
        assert set(self.task['eval']['eval_types'])<={'program_html','url_match'}
        install_no_llm_grading()
        from browser_env.actions import create_stop_action
        from evaluation_harness.evaluators import evaluator_router
        pages=[p for p in self.context.pages if not p.is_closed()]
        visible=[p for p in pages if p.evaluate('document.visibilityState')=='visible']
        page=visible[-1] if visible else pages[-1]
        cfg=self.directory/'official-task.json';cfg.write_text(json.dumps(self.task))
        trajectory=[{'observation':{'text':''},'info':{}},create_stop_action('')]
        return float(evaluator_router(str(cfg))(trajectory,str(cfg),page,self.context.new_cdp_session(page)))
    def close(self):
        if self.browser:self.browser.close()
        if self.playwright:self.playwright.stop()
        for p in reversed(self.processes):p.terminate();p.wait(timeout=10)


class AndroidEnvironment:
    def __init__(self,task,directory):
        self.spec=task;self.directory=Path(directory);self.controller=self;self.env=None
    def reset(self,task_config=None):
        from android_world import registry
        from android_world.env import env_launcher,json_action
        from instance_codec import decode
        import random,numpy as np
        from android_controller import load_environment
        self.env=load_environment()
        cls=registry.TaskRegistry().get_registry(registry.TaskRegistry.ANDROID_WORLD_FAMILY)[self.spec['class']]
        params=decode(self.spec['params']);random.seed(params['seed']);np.random.seed(params['seed'])
        self.task=cls(params);self.task.initialize_task(self.env)
        self.env.reset(go_home=True)
        self.actions=AndroidActions(self.env,json_action.JSONAction)
        return {'screenshot':self.get_screenshot()}
    def get_screenshot(self):
        state=self.env.get_state(wait_to_stabilize=True)
        buf=io.BytesIO();Image.fromarray(state.pixels).save(buf,format='PNG');return buf.getvalue()
    def step(self,action,pause=2):
        if action not in {'WAIT','DONE','FAIL'}:self.actions.execute(action)
        time.sleep(pause)
        return {'screenshot':self.get_screenshot()},0,action in {'DONE','FAIL'},{}
    def evaluate(self):return float(self.task.is_successful(self.env))
    def transport_preflight(self):
        actions=["pyautogui.press('home')", "pyautogui.scroll(-1)", "pyautogui.press('home')"]
        for i,action in enumerate(actions):
            obs,_,_,_=self.step(action,pause=1)
            (self.directory/f'probe-{i}.png').write_bytes(obs['screenshot'])
        return {'sequential_batches':3,'screenshots_verified':True}
    def close(self):
        if self.env:self.env.close()


def boot_android(directory):
    log=(Path(directory)/'emulator.log').open('a')
    # SwiftShader is CPU software rasterization. Container exposes only /dev/kvm,
    # with runc and no physical graphics devices or GPU runtime.
    process=subprocess.Popen(['emulator','-avd','AndroidWorldAvd','-no-window','-no-snapshot','-noaudio','-no-boot-anim','-gpu','swangle','-accel','on','-memory','4096','-cores','4','-grpc','8554'],stdout=log,stderr=subprocess.STDOUT)
    for _ in range(120):
        if process.poll() is not None:raise RuntimeError('CPU emulator exited; inspect emulator.log')
        try:p=subprocess.run(['adb','-s','emulator-5554','shell','getprop','sys.boot_completed'],capture_output=True,text=True,timeout=15)
        except subprocess.TimeoutExpired:continue
        if p.stdout.strip()=='1':
            from android_ready import wait_ready
            try:wait_ready(process,directory)
            except BaseException:
                process.terminate()
                try:process.wait(timeout=20)
                except subprocess.TimeoutExpired:process.kill()
                raise
            return process
        time.sleep(3)
    process.terminate()
    try:process.wait(timeout=20)
    except subprocess.TimeoutExpired:process.kill()
    raise RuntimeError('CPU emulator startup timeout')
