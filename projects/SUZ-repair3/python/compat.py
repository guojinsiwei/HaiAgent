"""Safe absolute-pixel action adapter around the pinned OpenCUA parser."""
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
    """Canonicalize declared pixel calls without regex coordinate conversion.

    Fractional legacy pairs in [0,1] are accepted only when at least one is
    nonintegral. Integer (0,1) stays pixels. Never infer units from crop size.
    """
    matches=list(re.finditer(r'^```(?:python|code)?[ \t]*\r?\n(.*?)^```[ \t]*(?=\r?$)', text, re.S|re.I|re.M))
    if not matches: raise ValueError('missing fenced GUI action')
    if len(matches)!=1: raise ValueError('ambiguous multiple GUI code blocks; return one action only')
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
                if values.get('status') not in {'success','fail','failure'}: raise ValueError('invalid termination')
                # Vendor searches the whole call for "fail". Canonicalize only
                # the explicit status, so explanatory text cannot reverse it.
                status='fail' if values['status']=='failure' else values['status']
                node.args=[];node.keywords=[ast.keyword(arg='status',value=ast.Constant(status))]
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
        for i,key in enumerate(('x','y')):
            value=pixels[i]
            if len(node.args)>i+offset: node.args[i+offset]=ast.Constant(value)
            for kw in node.keywords:
                if kw.arg==key: kw.value=ast.Constant(value)
    code=ast.unparse(ast.fix_missing_locations(tree))
    control=any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and
        isinstance(n.func.value,ast.Name) and n.func.value.id=='computer' for n in ast.walk(tree))
    if not control:
        from .actions import validate_actions
        validate_actions([code])
    # The pinned parser treats inline triple-backtick prose as code delimiters.
    # Preserve that prose while giving it exactly one executable fenced block.
    prefix=text[:match.start()].replace('```','`')
    if not re.search(r'^##\s*Action\s*:',prefix,re.M|re.I):
        prefix+='\n## Action:\nExecute the single validated GUI action below.\n'
    return prefix+'```python\n'+code+'\n```'+text[match.end():].replace('```','`')


def install_absolute_projector(module):
    """Implement the vendor's declared but missing absolute coordinate mode.

    Vendor bytes, history and response parsing remain pinned. Fractions and qwen
    modes still use the original implementation. GUI-only validation is mandatory.
    """
    if getattr(module,'_suz_absolute_projector',False):return
    original=module.project_coordinate_to_absolute_scale
    def project(code,screen_width,screen_height,coordinate_type='relative'):
        if coordinate_type=='absolute':
            from .actions import validate_actions
            validate_actions([code])
            return code
        return original(code,screen_width,screen_height,coordinate_type)
    module.project_coordinate_to_absolute_scale=project
    module._suz_absolute_projector=True
