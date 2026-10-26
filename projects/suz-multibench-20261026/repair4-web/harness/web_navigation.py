"""Navigation transport for server-rendered official grading pages.

Preserve the upstream grader and exact task criteria. Waiting for DOMContentLoaded
lets the official grader inspect HTML without waiting for all remote embeds.
Applies only during grading; agent observations and interaction are unchanged.
"""
from contextlib import contextmanager
import json,time


@contextmanager
def grading_navigation(page,log_path):
    original=page.goto
    def goto(url,*args,**kwargs):
        kwargs.setdefault('wait_until','domcontentloaded')
        started=time.time()
        response=original(url,*args,**kwargs)
        with log_path.open('a') as f:
            f.write(json.dumps({'url':url,'wait_until':kwargs['wait_until'],
                'response_status':getattr(response,'status',None),'seconds':time.time()-started})+'\n')
        return response
    page.goto=goto
    try:yield
    finally:page.goto=original
