import sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'harness'),str(Path(__file__).resolve().parents[2]/'SUZ-repair4')]
from action_bridge import calls,AndroidActions
from environments import forbidden_judge,install_no_llm_grading

class Env:
    device_screen_size=(1080,2400)
    def __init__(self):self.actions=[]
    def execute_action(self,a):self.actions.append(a)

class BridgeTests(unittest.TestCase):
    def test_no_arbitrary_code(self):
        for source in ['import os;os.system("x")','pyautogui.click(x=f(),y=2)','eval("x")']:
            with self.assertRaises((ValueError,TypeError)):calls(source)
    def test_touch_geometry_unicode_and_back(self):
        env=Env();a=AndroidActions(env,lambda **kw:kw)
        a.execute("pyautogui.click(10,20)\npyautogui.write('中文')\npyautogui.press('esc')")
        self.assertEqual(env.actions,[{'action_type':'click','x':10,'y':20},{'action_type':'input_text','text':'中文','clear_text':False},{'action_type':'navigate_back'}])
    def test_invalid_batch_has_no_partial_effect(self):
        env=Env();a=AndroidActions(env,lambda **kw:kw)
        with self.assertRaises(ValueError):a.execute("pyautogui.click(10,20)\npyautogui.hotkey('ctrl','q')")
        self.assertEqual(env.actions,[])
        with self.assertRaises(ValueError):a.execute('pyautogui.click(1080,10)')
        self.assertEqual(env.actions,[])
    def test_replace_and_clipboard_shared_semantics(self):
        env=Env();a=AndroidActions(env,lambda **kw:kw)
        a.execute("pyperclip.copy('abc')\npyautogui.hotkey('ctrl','a')\npyautogui.hotkey('ctrl','v')")
        self.assertEqual(env.actions,[{'action_type':'input_text','text':'abc','clear_text':True}])
    def test_no_gpt_grader_path(self):
        install_no_llm_grading()
        from llms.providers.openai_utils import generate_from_openai_chat_completion
        with self.assertRaisesRegex(RuntimeError,'forbidden'):generate_from_openai_chat_completion('x')
    def test_repeat_bound_before_execution(self):
        env=Env();a=AndroidActions(env,lambda **kw:kw)
        with self.assertRaises(ValueError):a.execute("pyautogui.click(10,20)\npyautogui.press('home',presses=100000)")
        self.assertEqual(env.actions,[])

if __name__=='__main__':unittest.main()
