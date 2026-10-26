"""Conservative, workspace-relative paths; never interpret a shell program."""
import posixpath
import re
import shlex

from .lean_progress import normalize_workspace_path


def workspace_join(cwd, name):
    if name == '/app':
        return ''
    if name.startswith('/app/'):
        value = name[5:]
    elif name.startswith('/'):
        raise ValueError('outside workspace')
    else:
        if cwd == '/app':
            cwd = ''
        elif cwd.startswith('/app/'):
            cwd = cwd[5:]
        elif cwd.startswith('/'):
            raise ValueError('outside workspace cwd')
        value = posixpath.normpath(posixpath.join(cwd, name))
    if value in ('', '.'):
        return ''
    return normalize_workspace_path(value)


def command_words(action):
    """Resolve one leading literal `cd dir &&`. Ambiguous cwd stays unknown.

    Do not apply a guessed cwd to branches, subshells, extra cd commands or
    expansions. Absolute /app paths can still be tracked in those programs.
    """
    args = action.get('argv', [])
    try:
        cwd = workspace_join('', action.get('cwd', '.'))
    except ValueError:
        return None, []
    if not (len(args) >= 3 and args[0].rsplit('/', 1)[-1] in {'bash', 'sh'}
            and args[1] in {'-c', '-lc'}):
        return cwd, list(args)
    try:
        lexer = shlex.shlex(args[2], posix=True, punctuation_chars=';&|()<>\n')
        lexer.whitespace = ' \t\r'
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return None, []
    if len(words) >= 3 and words[0] == 'cd' and words[2] == '&&':
        target = words[1]
        try:
            if any(c in target for c in '$`*?\n\x00'):
                raise ValueError('dynamic cwd')
            cwd = workspace_join(cwd, target)
        except ValueError:
            cwd = None
        words = words[3:]
    if any(w == 'cd' or w in {'||', '&', '(', ')', 'if', 'for', 'while', 'case'}
           for w in words):
        cwd = None
    return cwd, words


def command_dependency_paths(action, known=(), limit=16):
    cwd, words = command_words(action)
    paths = []
    for word in words:
        word = word.split('=', 1)[-1]
        if (not word or word.startswith('-') or any(c in word for c in '$`*?;|<>\n\x00')
                or re.fullmatch(r'[A-Za-z0-9_./-]+', word) is None
                or len(word.encode()) > 4096
                or any(len(part.encode()) > 255 for part in word.split('/'))
                or not ('.' in word.rsplit('/', 1)[-1] or '/' in word)):
            continue
        if cwd is None and not word.startswith('/app/'):
            continue
        try:
            path = workspace_join(cwd or '', word)
        except ValueError:
            continue
        if path and path not in paths:
            paths.append(path)
    # Stored dependency targets already use workspace-relative coordinates.
    for name in known:
        try:
            path = normalize_workspace_path(name)
        except ValueError:
            continue
        if path not in paths:
            paths.append(path)
    return paths[:limit]
