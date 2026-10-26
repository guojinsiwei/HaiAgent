"""Explicit full-screen pixel adapter around the pinned OpenCUA parser."""
import ast
import math
import operator
import re

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv}

def constant(node, depth=0):
    if depth > 8: raise ValueError('constant expression too deep')
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        a, b = constant(node.left, depth+1), constant(node.right, depth+1)
        if type(a) not in (int, float) or type(b) not in (int, float):
            raise ValueError('arithmetic requires numbers')
        value = OPS[type(node.op)](a, b)
    else:
        value = ast.literal_eval(node)
    if type(value) in (int,float) and (not math.isfinite(value) or abs(value)>100000):
        raise ValueError('constant outside bounds')
    return value

def adapt_response(text, size):
    """Convert declared pixel calls to fractions for the unchanged relative parser.

    Fractional legacy pairs in [0,1] are accepted only when at least one is
    nonintegral. Integer (0,1) stays pixels. Never infer units from crop size.
    """
    matches=list(re.finditer(r'```(?:python|code)?\s*(.*?)\s*```', text, re.S|re.I))
    if not matches: raise ValueError('missing fenced GUI action')
    match=matches[-1]; tree=ast.parse(match.group(1))
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call): continue
        for i,a in enumerate(node.args): node.args[i]=ast.Constant(constant(a)) if isinstance(a,ast.BinOp) else a
        for k in node.keywords:
            if isinstance(k.value,ast.BinOp): k.value=ast.Constant(constant(k.value))
        if not isinstance(node.func,ast.Attribute) or not isinstance(node.func.value,ast.Name): continue
        module, method=node.func.value.id,node.func.attr
        if module=='computer':
            if len(tree.body)!=1 or method not in {'wait','terminate'}: raise ValueError('invalid control action')
            if method=='terminate':
                values={k.arg:constant(k.value) for k in node.keywords}
                if values.get('status') not in {'success','fail'}: raise ValueError('invalid termination')
            continue
        if module!='pyautogui' or method not in {'click','doubleClick','tripleClick','rightClick','middleClick','moveTo','dragTo','mouseDown','mouseUp','scroll','hscroll','vscroll'}: continue
        offset=1 if method in {'scroll','hscroll','vscroll'} else 0
        refs={k.arg:k.value for k in node.keywords if k.arg in {'x','y'}}
        for i,key in enumerate(('x','y')):
            if len(node.args)>i+offset: refs[key]=node.args[i+offset]
        if not refs: continue
        if set(refs)!={'x','y'}: raise ValueError('supply both x and y, or neither')
        xy=[constant(refs[key]) for key in ('x','y')]
        if not all(type(v) in (int,float) for v in xy): raise ValueError('invalid coordinates')
        legacy=all(0<=v<=1 for v in xy) and any(v!=int(v) for v in xy)
        pixels=[round(xy[i]*size[i]) if legacy else round(xy[i]) for i in range(2)]
        if not all(0<=pixels[i]<size[i] for i in range(2)): raise ValueError('coordinates outside full screenshot')
        # Upstream converts only these methods. Other methods already take pixels.
        projected=method in {'click','doubleClick','tripleClick','rightClick','middleClick','moveTo','dragTo'}
        if not projected:
            # Upstream recognizes these methods only with explicit x/y keywords.
            for i,key in enumerate(('x','y')):
                if len(node.args)>i+offset:
                    node.keywords.append(ast.keyword(arg=key,value=node.args[i+offset]))
            node.args=node.args[:offset]
        for i,key in enumerate(('x','y')):
            value=pixels[i]/size[i]
            if len(node.args)>i+offset: node.args[i+offset]=ast.Constant(value)
            for kw in node.keywords:
                if kw.arg==key: kw.value=ast.Constant(value)
    code=ast.unparse(ast.fix_missing_locations(tree))
    return text[:match.start()]+'```python\n'+code+'\n```'+text[match.end():]
