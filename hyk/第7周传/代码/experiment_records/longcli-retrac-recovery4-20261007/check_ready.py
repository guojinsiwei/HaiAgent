import json
from common import validate
from docker_terminal import docker
p=validate()
for image in p['base_images'].values():
    assert docker('image','inspect',image['tag'],'--format','{{.Id}}').stdout.strip()==image['id']
import check_grading
print(json.dumps({'state':'accepted_not_started','tasks':len(p.get('run_tasks',p['tasks'])),'paid_api_requests':0}))
