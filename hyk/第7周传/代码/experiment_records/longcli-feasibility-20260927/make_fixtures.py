"""Evaluator-only partial correct/incorrect patches; never ship these to Raw workspaces."""
import io
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parent
source = root / 'cube-inputs-v1.tar.gz'
for variant in ['correct-frame', 'wrong-frame', 'protected-tamper']:
    with tarfile.open(source) as original, tarfile.open(root / (variant + '.tar.gz'), 'w:gz') as out:
        for member in original:
            content = original.extractfile(member).read() if member.isfile() else None
            if member.name == 'cs61_fa24_scheme/scheme_classes.py':
                text = content.decode()
                marker = '        "*** YOUR CODE HERE ***"'
                # Implements only the public Frame define/lookup contract, not the full task.
                text = text.replace(marker, '        self.bindings[symbol] = value', 1)
                lookup = ('        if symbol in self.bindings:\n            return self.bindings[symbol]\n'
                          '        if self.parent is not None:\n            return self.parent.lookup(symbol)')
                if variant == 'wrong-frame':
                    lookup = '        return None'
                text = text.replace(marker, lookup, 1)
                content = text.encode()
            if variant == 'protected-tamper' and member.name == 'cs61_fa24_scheme/scheme.py':
                content += b'\n# integrity-negative-fixture\n'
            if content is not None:
                member.size = len(content)
            out.addfile(member, io.BytesIO(content) if content is not None else None)
    print(variant, flush=True)
