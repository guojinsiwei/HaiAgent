"""Interpret an allowlisted GUI wire format; never evaluate model Python."""
import ast
import time
from python.actions import validate_actions


def calls(code):
    validate_actions([code])
    result=[]
    for statement in ast.parse(code).body:
        if isinstance(statement,ast.Import):continue
        call=statement.value
        result.append((call.func.value.id,call.func.attr,
                       [ast.literal_eval(a) for a in call.args],
                       {k.arg:ast.literal_eval(k.value) for k in call.keywords}))
    return result


class DesktopActions:
    def __init__(self):
        import pyautogui,pyperclip
        self.modules={'pyautogui':pyautogui,'pyperclip':pyperclip,'time':time}
    def execute(self,code):
        for module,name,args,kwargs in calls(code):getattr(self.modules[module],name)(*args,**kwargs)


class AndroidActions:
    """Same coordinate/text interface, implemented by official touch actions."""
    def __init__(self,env,action_factory):
        self.env=env;self.factory=action_factory;self.clipboard='';self.clear_next=False
        self.pointer=(0,0)
    def compile(self,code):
        result=[];clipboard=self.clipboard;clear=self.clear_next;pointer=self.pointer
        for module,name,args,kw in calls(code):
            if name=='sleep':result.append(('sleep',args[0] if args else next(iter(kw.values()))));continue
            if module=='pyperclip':clipboard=args[0];continue
            if name in {'click','doubleClick','moveTo','mouseDown','mouseUp'}:
                x=kw.get('x',args[0] if args else pointer[0]);y=kw.get('y',args[1] if len(args)>1 else pointer[1]);pointer=(x,y)
                w,h=self.env.device_screen_size
                if not 0<=x<w or not 0<=y<h:raise ValueError('touch outside screen')
                if name=='moveTo':continue
                if name in {'mouseDown','mouseUp'}:raise ValueError('use click or dragTo; split touch is unsupported')
                if kw.get('button','left')!='left':raise ValueError('Android has no right mouse click')
                n=kw.get('clicks',1)
                if not isinstance(n,int) or not 1<=n<=3:raise ValueError('invalid tap count')
                for _ in range(n):result.append(('action',{'action_type':'double_tap' if name=='doubleClick' else 'click','x':int(x),'y':int(y)}))
            elif name in {'write','typewrite'}:
                text=args[0] if args else kw['message']
                if not isinstance(text,str):raise ValueError('Android text must be a string')
                result.append(('action',{'action_type':'input_text','text':text,'clear_text':clear}));clear=False
            elif name in {'scroll','vscroll','hscroll'}:
                amount=args[0] if args else kw['clicks']
                direction=('right' if amount>0 else 'left') if name=='hscroll' else ('up' if amount>0 else 'down')
                if amount:result.append(('action',{'action_type':'scroll','direction':direction}))
            elif name=='hotkey':
                keys=tuple(str(x).lower() for x in args)
                if keys in {('ctrl','v'),('command','v')}:
                    result.append(('action',{'action_type':'input_text','text':clipboard,'clear_text':clear}));clear=False
                elif keys==('ctrl','a'):clear=True
                elif keys==('alt','left'):result.append(('action',{'action_type':'navigate_back'}))
                else:raise ValueError('unsupported Android hotkey')
            elif name=='press':
                keys=args[0] if args else kw['keys'];keys=[keys] if isinstance(keys,str) else keys
                repeats=kw.get('presses',1)
                if not isinstance(repeats,int) or not 1<=repeats<=20:raise ValueError('invalid key repeat count')
                if len(keys)*repeats>20:raise ValueError('Android key batch exceeds 20 actions')
                for key in keys:
                    mapping={'enter':'keyboard_enter','return':'keyboard_enter','esc':'navigate_back','escape':'navigate_back','home':'navigate_home'}
                    if key not in mapping:raise ValueError('unsupported Android key')
                    for _ in range(repeats):result.append(('action',{'action_type':mapping[key]}))
            else:raise ValueError('unsupported Android GUI operation: '+name)
            if len(result)>20:raise ValueError('Android batch exceeds 20 actions')
        return result,clipboard,clear,pointer
    def execute(self,code):
        # Validate the entire batch before any touch; malformed tails cannot partly execute.
        plan,clipboard,clear,pointer=self.compile(code)
        for kind,value in plan:
            if kind=='sleep':time.sleep(value)
            else:self.env.execute_action(self.factory(**value))
        self.clipboard,self.clear_next,self.pointer=clipboard,clear,pointer
