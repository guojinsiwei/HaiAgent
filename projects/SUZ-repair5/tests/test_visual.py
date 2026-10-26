import base64
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from python.visual import render_overlay,diagnostic_crops,image_metrics
from python.actions import click_points
from python.offline_demo import run

def image(color='white'):
    output=io.BytesIO();Image.new('RGB',(560,560),color).save(output,format='PNG');return output.getvalue()

class VisualTests(unittest.TestCase):
    def test_overlay_keeps_original_size_coordinates_and_source_immutable(self):
        original=image();before=hashlib.sha256(original).hexdigest()
        warning={'id':'V1','status':'active','anchor_sha256':before,'style':'red_cross','box':[.4,.4,.6,.6]}
        view=render_overlay(original,[warning],'F2')
        self.assertEqual(Image.open(io.BytesIO(view['bytes'])).size,(560,560))
        self.assertEqual(hashlib.sha256(original).hexdigest(),before)
        self.assertNotEqual(view['bytes'],original)
        self.assertEqual(view['metadata']['source_sha256'],before)
        self.assertIsNone(render_overlay(image('black'),[warning],'F3'))
        warning['status']='needs_revalidation'
        self.assertIsNone(render_overlay(original,[warning],'F3'))

    def test_crop_contains_source_coordinates_and_raw_frame_provenance(self):
        raw=image();url='data:image/png;base64,'+base64.b64encode(raw).decode()
        images=[{'id':'F0','dataUrl':url},{'id':'F1','dataUrl':url}]
        crops=diagnostic_crops(images,{'E1':{'frame_ids':['F0','F1'],'action':{'points':[{'x':.5,'y':.5}]}}})
        self.assertEqual(len(crops),2)
        self.assertEqual(crops[0]['metadata']['box'],[.4,.4,.6,.6])
        self.assertEqual(crops[1]['metadata']['source_frame'],'F1')
        self.assertEqual(click_points(['pyautogui.click(280, 140)'],(560,560))[0]['x'],.5)

    def test_pixel_metrics_do_not_claim_progress(self):
        metrics=image_metrics(image(),image())
        self.assertEqual(metrics['mean_absolute_difference'],0)
        self.assertEqual(metrics['changed_pixel_fraction'],0)
        self.assertNotIn('progress',metrics)
        self.assertGreater(image_metrics(image('black'),image())['mean_absolute_difference'],.99)

    def test_real_solver_receives_overlay_and_advisor_receives_raw_crops(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run(Path(folder)/'demo')
            self.assertEqual(result['visual_warnings'],1)
            self.assertEqual(len(result['overlay_files']),1)
            derived=Path(folder)/'demo'/'derived-views'
            self.assertEqual(len(list(derived.glob('advisor-*.png'))),2)
            self.assertEqual(len(list(derived.glob('critic-*.png'))),0)

if __name__=='__main__':unittest.main()
