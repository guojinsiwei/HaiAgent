"""Readable terminal projections; originals stay in tool_call.result audit records.

Not a terminal emulator: never apply screen erasure or cursor overwriting, which
could erase earlier errors. Preserve carriage-return refresh frames as lines.
"""
def project_terminal(value):
    pieces, removed, incomplete, i = [], 0, False, 0
    while i < len(value):
        char = value[i]
        start = i
        kind = None
        if char == '\x1b':
            i += 1
            if i >= len(value):
                incomplete = True; removed += 1; break
            char = value[i]
            kind = 'csi' if char == '[' else ('osc' if char == ']' else
                'string' if char in 'P^_X' else 'escape')
            i += 1
        elif char in '\x9b\x9d\x90\x9e\x9f\x98':
            kind = 'csi' if char == '\x9b' else 'osc' if char == '\x9d' else 'string'
            i += 1
        if kind:
            removed += 1
            if kind == 'csi':
                while i < len(value) and '\x30' <= value[i] <= '\x3f': i += 1
                while i < len(value) and '\x20' <= value[i] <= '\x2f': i += 1
                if i < len(value) and '\x40' <= value[i] <= '\x7e': i += 1
                else: incomplete = True
            elif kind in {'osc','string'}:
                while i < len(value):
                    if value.startswith('\x1b\\', i): i += 2; break
                    if value[i] == '\x9c' or kind == 'osc' and value[i] == '\x07': i += 1; break
                    i += 1
                else: incomplete = True
            else:
                # Escape intermediates precede a final ASCII byte (e.g. ESC ( B).
                final = value[start+1]
                if '\x20' <= final <= '\x2f':
                    while i < len(value) and '\x20' <= value[i] <= '\x2f': i += 1
                    if i < len(value) and '\x30' <= value[i] <= '\x7e': i += 1
                    else: incomplete = True
                elif not '\x30' <= final <= '\x7e':
                    incomplete = True
                    i = start+1  # Keep a printable following character, if any.
            continue
        if char == '\r':
            pieces.append('\n')
            i += 2 if value.startswith('\r\n',i) else 1
            continue
        if ord(char) < 32 and char not in '\n\t' or '\x7f' <= char <= '\x9f':
            removed += 1; i += 1; continue
        pieces.append(char); i += 1
    if incomplete:
        pieces.append('\n[terminal-control sequence incomplete; projection may omit text]\n')
    return ''.join(pieces), dict(policy='terminal-readable-v1', controls_removed=removed,
        carriage_returns=value.count('\r'), incomplete=incomplete,
        cursor_rewrites_applied=False, raw_preserved_in='tool_call.result')


def clean_terminal(value):
    return project_terminal(value)[0]
