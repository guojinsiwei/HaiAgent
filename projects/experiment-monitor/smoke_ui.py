"""Exercise the native UI against live collector cache, without extra SSH polls."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tkinter as tk
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
loader=importlib.machinery.SourceFileLoader('monitor_gui',str(ROOT/'app.pyw'))
spec=importlib.util.spec_from_loader(loader.name,loader)
gui=importlib.util.module_from_spec(spec);loader.exec_module(gui)
root=tk.Tk();root.withdraw()
with patch.object(gui.Dashboard,'refresh',lambda *_:None):
    app=gui.Dashboard(root)
    # Mark cached fixture data freshly connected for exercising all live views.
    for state in app.states.values():state['ok']=True
    app.render();root.update()
    assert len(app.tree.get_children())>=5
    lats=next(c for c in app.campaigns.values() if c['method']=='lats')
    app.selection=lats['id'];app.show_details();root.update()
    assert len(app.tasks.get_children())==20
    assert 'LATS' in app.detail_title.cget('text')
    app.running_only.set(True);app.render();root.update()
    assert app.tree.get_children()
    app.running_only.set(False);app.history.set(True);app.render();root.update()
    assert len(app.tree.get_children())>5
    app.history.set(False);app.search.set('TACO');app.render();root.update()
    assert len(app.tree.get_children())==1
    print('Native UI smoke passed: latest experiments, 20-task details, live/history/search filters.')
root.destroy()
