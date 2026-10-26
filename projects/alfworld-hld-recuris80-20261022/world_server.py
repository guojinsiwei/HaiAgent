"""Private ALFWorld process. Only observation/actions cross the solver boundary."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import threading
import time
import sys
import textworld
from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos


def environment(game, training_probe=False):
    return textworld.start(str(game), request_infos=textworld.EnvInfos(won=True, admissible_commands=True, facts=training_probe),
                           wrappers=[AlfredDemangler(shuffle=False), AlfredInfos])


class World:
    def __init__(self, game, output, max_steps=100, training_probe=False):
        self.output = Path(output); self.output.mkdir(parents=True, exist_ok=True)
        self.env = environment(game, training_probe)
        self.state = self.env.reset()
        self.steps = 0; self.max_steps = max_steps; self.cache = {}; self.lock = threading.Lock()
        self.done = False
        self.save()

    def view(self):
        return dict(observation=self.state.feedback, actions=list(self.state.admissible_commands),
                    won=bool(self.state.won), done=self.done, steps=self.steps, max_steps=self.max_steps)

    def save(self):
        data = self.view(); data['updated'] = time.time()
        p = self.output/'state.json'; tmp = p.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False)); tmp.replace(p)

    def step(self, action, request_id):
        with self.lock:
            if request_id in self.cache:
                old_action, answer = self.cache[request_id]
                if old_action != action: raise ValueError('Request id reused for a different action')
                return answer
            if self.done: return self.view()
            if not isinstance(action, str) or not action.strip() or len(action) > 500:
                raise ValueError('Supply one nonempty text action, up to 500 characters')
            action = action.strip()
            before = self.view()
            self.state, reward, done = self.env.step(action)
            self.steps += 1
            self.done = bool(done or self.state.won or self.steps >= self.max_steps)
            answer = self.view()
            self.cache[request_id] = (action, answer)
            with (self.output/'actions.jsonl').open('a') as f:
                f.write(json.dumps(dict(time=time.time(),request_id=request_id,action=action,
                     before=before,after=answer,engine_reward=reward),ensure_ascii=False)+'\n')
            self.save()
            return answer


def main():
    world = World(sys.argv[1], '/results', int(sys.argv[2]))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self, data, code=200):
            body=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(code); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.path not in ('/observe','/health'):return self.reply({'error':'unknown endpoint'},404)
            with world.lock: self.reply(world.view())
        def do_POST(self):
            if self.path!='/step':return self.reply({'error':'unknown endpoint'},404)
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=8192:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(size));rid=data['request_id']
                if not isinstance(rid,str) or not 1<=len(rid)<=100:raise ValueError('Invalid request id')
                self.reply(world.step(data['action'],rid))
            except (ValueError,KeyError,json.JSONDecodeError) as e:self.reply({'error':str(e)},400)
    server=ThreadingHTTPServer(('0.0.0.0',8080),Handler)
    server.serve_forever()


if __name__=='__main__': main()
