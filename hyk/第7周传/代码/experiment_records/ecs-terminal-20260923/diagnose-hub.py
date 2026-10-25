import json
from prepare_images import fetch
for url in ['https://hub.docker.com/v2/repositories/alexgshaw/qemu-alpine-ssh/tags/20251031']:
    try:
        info=json.loads(fetch(url))
        print(json.dumps({key:info.get(key) for key in ('name','digest','full_size','tag_status')}))
    except Exception as error:
        print(type(error).__name__,str(getattr(error,'reason',''))[:150])
