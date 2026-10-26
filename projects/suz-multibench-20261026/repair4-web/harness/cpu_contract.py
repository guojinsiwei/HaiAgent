"""Docker may encode absent optional device lists as either null or []."""
def validate_cpu_host(host):
    assert host.get('Runtime')=='runc', 'CPU runc runtime required'
    assert not host.get('Privileged'), 'Privileged containers forbidden'
    assert not host.get('DeviceRequests'), 'Accelerator device requests forbidden'
    devices=host.get('Devices')
    if devices is None:devices=[]
    assert isinstance(devices,list), 'Malformed Docker devices field'
    assert all(isinstance(x,dict) and x.get('PathOnHost')=='/dev/kvm'
               and x.get('PathInContainer')=='/dev/kvm' for x in devices), 'Only /dev/kvm allowed'

