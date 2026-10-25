import json
import urllib.error
from prepare_images import resolve_image
try:
    print(resolve_image('alexgshaw/crack-7z-hash:20251031'))
except urllib.error.URLError as error:
    print(json.dumps({'type':type(error).__name__,'reason_type':type(error.reason).__name__,'reason':str(error.reason)[:200]}))
