import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harness'))
from cpu_contract import validate_cpu_host

class CpuContractTests(unittest.TestCase):
    def test_null_empty_absent_devices_are_cpu(self):
        for extra in [{},{'Devices':None},{'Devices':[]},
                      {'Devices':[{'PathOnHost':'/dev/kvm','PathInContainer':'/dev/kvm'}]}]:
            validate_cpu_host({'Runtime':'runc','DeviceRequests':None,**extra})
    def test_gpu_privilege_and_malformed_device_rejected(self):
        for extra in [{'Runtime':'nvidia'},{'Privileged':True},
                      {'DeviceRequests':[{'Capabilities':[['gpu']]}]},
                      {'Devices':[{'PathOnHost':'/dev/dri','PathInContainer':'/dev/dri'}]},
                      {'Devices':{}},{'Devices':[None]}]:
            with self.assertRaises(AssertionError):validate_cpu_host({'Runtime':'runc',**extra})

if __name__=='__main__':unittest.main()
