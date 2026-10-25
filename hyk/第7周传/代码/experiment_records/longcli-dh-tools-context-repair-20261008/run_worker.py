import sys
from runner import worker
if __name__=='__main__':
    key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
    worker(key)
