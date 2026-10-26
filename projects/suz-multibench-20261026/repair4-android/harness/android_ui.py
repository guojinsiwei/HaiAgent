"""Fresh, bounded UIAutomator reads for the official AndroidWorld controller.

UI trees stay inside environment actions and grading; model input is screenshots.
Never reuse a previous dump, and never substitute an empty tree after failure.
"""
import time
import uuid
import xml.etree.ElementTree as ET


def fresh_hierarchy(request, attempts=4, sleep=time.sleep):
    failures=[]
    for attempt in range(attempts):
        path='/sdcard/suz-ui-'+uuid.uuid4().hex+'.xml'
        try:
            output=request(['shell','uiautomator','dump',path])
            if 'UI hierchary dumped to:' not in output and 'UI hierarchy dumped to:' not in output:
                raise RuntimeError('UIAutomator did not confirm a completed dump: '+output[:250])
            xml=request(['shell','cat',path])
            tree=ET.fromstring(xml)
            if tree.tag!='hierarchy' or not list(tree):
                raise ValueError('UIAutomator returned an empty or invalid hierarchy')
            return xml
        except Exception as exc:
            failures.append(type(exc).__name__+': '+str(exc)[:300])
        finally:
            try:request(['shell','rm','-f',path])
            except Exception:pass
        if attempt+1<attempts:sleep(2)
    raise RuntimeError('Fresh UI hierarchy unavailable after bounded retries: '+'; '.join(failures))
