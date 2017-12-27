# cRRunner
cRemote Runner is a module that allows us to copy some files remotely, run or execute on that remote, then copy things back. Internally it uses Paramiko as an SSH interface.

## How to Use
```python
from crrunner import *
eventList = [
  ExecuteEvent('ls')
]

'''
We also have:
CopyToRemoteEvent - To copy files to the remote from local
CopyFromRemoteEvent - To copy files from the remote to local
DeleteAllCopiedToRemote - To delete all files (on remote) copied to remote thus far.
'''

runner = cRRunner(remoteIp=<ip>, remoteUserName=<user>, remotePassword=<password>, eventList=eventList)
resultList = runner.run()

print (resultList[0].stdout)
```

## More Info
See the docstrings for classes in crrunner.py/event.py
Also see ```if __name__ == '__main__':``` in crrunner.py for a more interesting example.

### How to Install
```
pip install cRRunner
```

[![Build Status](https://travis-ci.org/csm10495/cRRunner.svg?branch=master)](https://travis-ci.org/csm10495/cRRunner)

[![Coverage Status](https://coveralls.io/repos/github/csm10495/cRRunner/badge.svg?branch=master)](https://coveralls.io/github/csm10495/cRRunner?branch=master)
