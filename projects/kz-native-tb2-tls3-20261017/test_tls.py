import ssl,unittest,os
from pathlib import Path
from unittest.mock import patch
from connection_probe import PROBE
class TLSConfigurationTests(unittest.TestCase):
 def test_bundle_loads_with_peer_and_hostname_verification(self):
  with patch.dict(os.environ,{'SSL_CERT_FILE':str(Path(__file__).parent/'native/cacert.pem')}):
   ctx=ssl.create_default_context()
   self.assertGreater(ctx.cert_store_stats()['x509_ca'],0)
   self.assertEqual(ctx.verify_mode,ssl.CERT_REQUIRED)
   self.assertTrue(ctx.check_hostname)
 def test_preflight_cannot_generate_or_authenticate(self):
  self.assertIn("method='GET'",PROBE)
  self.assertNotIn('Authorization',PROBE)
  self.assertNotIn('API_KEY',PROBE)
if __name__=='__main__':unittest.main()
