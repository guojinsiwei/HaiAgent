"""Verification-only identity; original argv is always passed to the executor."""
import hashlib
import json
import posixpath
import re
import shlex


def verification_key(action, workspace='.'):
    argv=action.get('argv',[])
    cwd=action.get('cwd','.')
    if not posixpath.isabs(cwd):cwd=posixpath.join(str(workspace).replace('\\','/'),cwd)
    exact=False
    if len(argv)==3 and argv[0].split('/')[-1] in ('bash','sh') and argv[1] in ('-c','-lc'):
        source=argv[2]
        exact=True
        if not re.search(r'[$`\\\n\r;|<>#*?~]',source):
            try:
                lexer=shlex.shlex(source,posix=True,punctuation_chars='&');lexer.whitespace_split=True
                words=list(lexer)
                if len(words)>=4 and words[:1]==['cd'] and words[2]=='&&' and words.count('&&')==1:
                    target=words[1]
                    if posixpath.isabs(target) and not any(p in ('.','..') for p in target.split('/')):
                        cwd=target;words=words[3:]
                    else:words=[]
                if words and not any('&' in w for w in words) and '=' not in words[0]:
                    argv=words;exact=False
            except ValueError:pass
    # Do not normalize .. across symlinks. Descriptive purpose has no identity.
    if not exact and not any(p=='..' for p in cwd.split('/')):cwd=posixpath.normpath(cwd)
    value=[argv,cwd,action.get('stdin'),action.get('env'),action.get('timeout_seconds')]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def substantive_silent_check(action):
    argv=action.get('argv',[])
    if not argv:return False
    exe=argv[0].split('/')[-1];args=argv[1:]
    forbidden={'--help','-h','--version','-V','--collect-only','--collectonly','--co','--list-tests','--list','--listTests','--showConfig','--fixtures','--fixtures-per-test','--setup-plan','--dry-run','--no-run'}
    if any(a in forbidden for a in args):return False
    if exe=='make' and any(re.match(r'^-[^-]*[nq]',a) or a in ('--just-print','--recon','--question') for a in args):return False
    if exe=='ctest' and any(re.match(r'^-[^-]*N|^--show-only(?:=|$)',a) for a in args):return False
    if exe=='go' and any(re.match(r'^--?list(?:=|$)',a) or a in ('-n','-c') for a in args):return False
    if exe in ('pytest','py.test','ctest'):return True
    if re.fullmatch(r'python[\d.]*',exe):
        while args and re.fullmatch(r'-[BuEIs]+',args[0]):args=args[1:]
        if len(args)>=2 and args[0]=='-m' and args[1] in ('pytest','unittest','doctest'):
            return args[1]!='doctest' or (any(not a.startswith('-') for a in args[2:]) and not any(a in ('SKIP','-oSKIP','--option=SKIP') for a in args[2:]))
    return exe=='node' and '--test' in args or exe in ('npm','pnpm','yarn','cargo','go','make') and args[:1]==['test']
