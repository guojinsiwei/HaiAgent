"""Reacquire missing screenshots without repeating any GUI action."""
import io
import time
from PIL import Image


def valid_image(data):
    if not isinstance(data,(bytes,bytearray)) or not data:return False
    try:
        with Image.open(io.BytesIO(data)) as im:im.verify()
        return True
    except Exception:return False


def fresh_observation(env, obs, attempts=3, delay=2):
    if valid_image(obs.get('screenshot')):return obs
    for _ in range(attempts):
        time.sleep(delay)
        try:data=env.controller.get_screenshot()
        except Exception:continue
        if valid_image(data):return {**obs,'screenshot':data}
    raise RuntimeError('fresh screenshot unavailable after bounded read-only recovery')
