"""Narrow diagnosis classification, not an authorization or sandbox bypass."""
import ast
import shlex


def _python_probe(argv):
    # Avoid site/project startup hooks. Never classify arbitrary Python as read-only.
    if len(argv) != 5 or set(argv[1:3]) != {'-I','-S'} or argv[3] != '-c':
        return False
    if len(argv[4]) > 2048:
        return False
    try:
        tree = ast.parse(argv[4])
    except (SyntaxError,ValueError):
        return False
    def value(node):
        if isinstance(node,ast.Constant):
            return isinstance(node.value,(str,int,float,bool,type(None)))
        if isinstance(node,(ast.Tuple,ast.List)):
            return all(value(x) for x in node.elts)
        return (imported and isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name)
                and node.value.id == 'sys' and node.attr in
                {'version','version_info','executable','platform','prefix','base_prefix'})
    imported = False
    prints = 0
    for node in tree.body:
        if isinstance(node,ast.Import) and len(node.names)==1:
            alias = node.names[0]
            if alias.name != 'sys' or alias.asname is not None:
                return False
            imported = True
            continue
        if not isinstance(node,ast.Expr) or not isinstance(node.value,ast.Call):
            return False
        call = node.value
        if not isinstance(call.func,ast.Name) or call.func.id != 'print':
            return False
        if not all(value(x) for x in call.args):
            return False
        if any(k.arg not in {'sep','end'} or not isinstance(k.value,ast.Constant)
               or not isinstance(k.value.value,str) for k in call.keywords):
            return False
        prints += 1
    return prints > 0


def _simple(argv):
    if not argv or any(not isinstance(a,str) or '\x00' in a for a in argv):
        return False
    program = argv[0]
    name = program.rsplit('/',1)[-1]
    if program not in {name,'/bin/'+name,'/usr/bin/'+name}:
        return False
    if name in {'pwd','ls','cat','head','tail','wc','stat','file','grep','rg','diff'}:
        return not any(a.startswith(('--pre','--pre-glob','--files-with-matches=')) for a in argv[1:])
    if name == 'git':
        args = argv[1:]
        if args and args[0] == '--no-pager':
            args = args[1:]
        if not args or args[0] not in {'diff','status','ls-files','rev-parse'}:
            return False
        return not any(a in {'-c','--exec','--ext-diff','--textconv','--output','--paginate'}
                       or a.startswith(('--output=','--exec=','--config-env=')) for a in args[1:])
    if name in {'python','python3'}:
        return _python_probe(argv)
    return False


def readonly_action(action):
    argv = action.get('argv',[])
    if not argv or action.get('stdin') is not None:
        return False
    if argv[0] not in {'bash','sh','/bin/bash','/bin/sh','/usr/bin/bash','/usr/bin/sh'}:
        return _simple(argv)
    if len(argv)!=3 or argv[1] not in {'-c','-lc'}:
        return False
    script = argv[2]
    if any(c in script for c in '$`\n\r\\'):
        return False
    try:
        lexer = shlex.shlex(script,posix=True,punctuation_chars=';&|<>()')
        lexer.whitespace_split = True
        lexer.commenters = ''
        words = list(lexer)
    except ValueError:
        return False
    segment = []
    for word in words:
        if word in {'&&','|'}:
            if not _simple(segment):
                return False
            segment = []
        elif word and all(c in ';&|<>()' for c in word):
            return False
        else:
            segment.append(word)
    return _simple(segment)
