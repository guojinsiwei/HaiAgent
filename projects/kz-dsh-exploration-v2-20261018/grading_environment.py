"""Restore original Dockerfile ENV lost by rootfs export; official tests unchanged."""
def install(grader,experiment):
 if getattr(grader,'_restored_environment',False):return
 original=grader.docker
 def docker(*args,**kwargs):
  if args and args[0]=='run':
   assert 'experiment='+experiment in args,'Refuse to change a foreign grading container'
   args=(args[0],'-e','PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
      '-e','NVM_DIR=/root/.nvm',*args[1:])
  return original(*args,**kwargs)
 grader.docker=docker;grader._restored_environment=True
