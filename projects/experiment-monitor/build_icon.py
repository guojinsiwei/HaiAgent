"""Generate the app's simple geometric chart icon."""
from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent
im=Image.new('RGBA',(256,256),(0,0,0,0));d=ImageDraw.Draw(im)
d.rounded_rectangle((4,4,252,252),radius=52,fill='#172a39')
d.rounded_rectangle((49,139,81,199),radius=8,fill='#78c5ff')
d.rounded_rectangle((111,100,143,199),radius=8,fill='#76dfb1')
d.rounded_rectangle((173,61,205,199),radius=8,fill='#78c5ff')
d.ellipse((49,52,73,76),fill='#76dfb1')
d.line((48,216,206,216),fill='#98aab9',width=7)
im.save(root/'monitor.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
