import unittest
from desktop_ready import required_windows,windows_ready

class ReadyTests(unittest.TestCase):
    def test_launch_targets_only_no_evaluator_or_related_app_hints(self):
        task={'config':[{'type':'launch','parameters':{'command':['libreoffice','--impress']}},
          {'type':'launch','parameters':{'command':['socat','tcp-listen:9222,fork']}}],
          'related_apps':['vlc'],'evaluator':{'expected':'code'}}
        required=required_windows(task)
        self.assertEqual(required,[['libreoffice','soffice']])
        self.assertFalse(windows_ready([],required))
        self.assertFalse(windows_ready([{'class':'code.Code'}],required))
        self.assertTrue(windows_ready([{'class':'libreoffice.libreoffice-impress'}],required))
    def test_multiple_declared_windows_all_required(self):
        required=[['vlc'],['google-chrome']]
        self.assertFalse(windows_ready([{'class':'vlc.Vlc'}],required))
        self.assertTrue(windows_ready([{'class':'vlc.Vlc'},{'class':'google-chrome.Google-chrome'}],required))
if __name__=='__main__':unittest.main()
