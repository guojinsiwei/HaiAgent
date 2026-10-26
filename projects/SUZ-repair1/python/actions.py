"""Validate the GUI-only action subset before returning code to the OSWorld VM.

No eval/exec here. The evaluator executes allowed actions in its isolated desktop.
Coordinates remain those projected by the pinned official OpenCUA implementation.
"""
import ast
import math

ALLOWED = {
    "click", "doubleClick", "tripleClick", "rightClick", "middleClick", "moveTo", "moveRel",
    "dragTo", "dragRel", "mouseDown", "mouseUp", "scroll", "hscroll", "vscroll",
    "write", "typewrite", "press", "hotkey", "keyDown", "keyUp", "sleep",
}


def validate_actions(actions, max_calls=20):
    if not isinstance(actions, list) or not actions:
        raise ValueError("empty action list")
    if actions in (["WAIT"], ["DONE"], ["FAIL"]):
        return actions
    count = 0
    for code in actions:
        for statement in ast.parse(code).body:
            if isinstance(statement, ast.Import) and all(x.name in {"pyautogui", "pyperclip", "time"} and x.asname is None for x in statement.names):
                continue
            if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                raise ValueError("only direct GUI calls allowed")
            call = statement.value
            if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
                raise ValueError("dynamic call rejected")
            module, method = call.func.value.id, call.func.attr
            if not ((module == "pyautogui" and method in ALLOWED) or
                    (module == "pyperclip" and method == "copy") or (module == "time" and method == "sleep")):
                raise ValueError("non-GUI function rejected")
            if any(k.arg is None for k in call.keywords):
                raise ValueError("keyword expansion rejected")
            values = [ast.literal_eval(x) for x in call.args] + [ast.literal_eval(x.value) for x in call.keywords]
            def valid(value):
                if isinstance(value, (str, bool)) or value is None:
                    return not isinstance(value, str) or len(value) <= 20000
                if isinstance(value, (int, float)):
                    return math.isfinite(value) and abs(value) <= 100000
                return isinstance(value, (list, tuple)) and len(value) <= 100 and all(valid(x) for x in value)
            if not all(valid(x) for x in values):
                raise ValueError("action argument outside bounds")
            if method == "sleep" and (len(values) != 1 or not isinstance(values[0], (int,float)) or not 0 <= values[0] <= 10):
                raise ValueError("wait must be between 0 and 10 seconds")
            for kw in call.keywords:
                if kw.arg in {"duration", "interval", "pause"} and not 0 <= ast.literal_eval(kw.value) <= 10:
                    raise ValueError("action duration outside bounds")
            count += 1
    if not 0 < count <= max_calls:
        raise ValueError("GUI batch size exceeded")
    return actions


def click_points(actions, screen_size):
    """Read native, already projected absolute coordinates; no model-generated metadata."""
    points=[]
    if actions in (["WAIT"],["DONE"],["FAIL"]):return points
    for code in actions:
        for node in ast.walk(ast.parse(code)):
            if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute):continue
            if not isinstance(node.func.value,ast.Name) or node.func.value.id!='pyautogui':continue
            if node.func.attr not in {'click','doubleClick','tripleClick','rightClick','middleClick'}:continue
            values={k.arg:ast.literal_eval(k.value) for k in node.keywords}
            for name,arg in zip(('x','y'),node.args):values[name]=ast.literal_eval(arg)
            x,y=values.get('x'),values.get('y')
            if isinstance(x,(int,float)) and isinstance(y,(int,float)) and 0<=x<screen_size[0] and 0<=y<screen_size[1]:
                points.append({'x':x/screen_size[0],'y':y/screen_size[1],'gesture':node.func.attr})
    return points[-8:]
