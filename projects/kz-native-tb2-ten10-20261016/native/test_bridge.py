import json,unittest
from unittest.mock import patch
from anthropic_bridge import payload_for,envelope_from,request
class BridgeTest(unittest.TestCase):
 def test_messages_preserve_content_and_no_native_tools(self):
  p=payload_for(dict(model='deepseek-flash',messages=[dict(role='system',content='{{raw}}'),dict(role='user',content='quoted " text')],max_tokens=32768,temperature=0))
  self.assertEqual(p['system'],'{{raw}}');self.assertEqual(p['messages'][0]['content'],'quoted " text');self.assertNotIn('tools',p)
 def test_usage_and_truncation(self):
  x=envelope_from(dict(content=[dict(type='text',text='{}')],stop_reason='max_tokens',usage=dict(input_tokens=10,cache_read_input_tokens=20,output_tokens=5)))
  self.assertEqual(x['usage']['prompt_tokens'],30);self.assertEqual(x['choices'][0]['finish_reason'],'length')
 def test_native_tools_never_become_actions(self):
  with self.assertRaises(ValueError):envelope_from(dict(content=[dict(type='tool_use',name='bash')]))
 def test_http_preserves_original_contract(self):
  import urllib.error
  with patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('https://test',401,'unauthorized',{},None)):
   p=dict(model='deepseek-flash',messages=[],max_tokens=32768,temperature=0)
   self.assertEqual(request('',p,'fake-fixture',1),('http',401))
if __name__=='__main__':unittest.main()
