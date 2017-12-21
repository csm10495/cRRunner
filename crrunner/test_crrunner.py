'''
Brief:
    Contains tests for cRemote Runner.
        The stuff that actually would do SSH/SFTP is mocked out though the core code flow is still tested.

Author(s):
    Charles Machalow via the MIT License
'''

import shlex
import shutil
import signal
import subprocess
import threading

from crrunner import *

class MockStream(object):
    '''
    Brief:
        Mocked out stdout/stderr from exec_command()
    '''
    def __init__(self, mockSshClient, stream):
        '''
        Brief:
            init takes in the ssh client and stream (ex: stdout)
        '''
        self.mockSshClient = mockSshClient
        self.stream = stream

    def __call__(self, *args, **kwargs):
        '''
        Brief:
            If they call this as a method, just return self
        '''
        return self

    def __getattr__(self, thing):
        '''
        Brief:
            If we get anything we don't know... return self
        '''
        if hasattr(self.stream, thing):
            return getattr(self.stream, thing)
        return self

    def exit_status_ready(self):
        '''
        Brief:
            Goes to the ssh client to see if a command is in progress (in progress means status is not ready)
        '''
        return self.mockSshClient.process is None

    def recv_exit_status(self):
        '''
        Brief:
            Gives back the last known exit code
        '''
        return self.mockSshClient.lastExitCode

class MockSshClient(object):
    '''
    Brief:
        Mocks out the SSH Client to not actually do SSH via Paramiko
    '''
    def __init__(self):
        self.process = None
        self.commandInProgress = False
        self.killCommandInProgress = False
        self.grabbedStreams = False
        self.lastExitCode = 0

    def __getattr__(self, *args, **kwargs):
        '''
        Brief:
            If we get anything we don't know... return None
        '''
        return None

    def _popen_thread(self, cmd):
        '''
        Brief:
            This is passed to a thread to run the subprocess in the background
        '''
        # On Windows we can kill the subprocess... not so much on Linux
        if os.name == 'nt':
            shell = True
        else:
            shell = False

        self.process = subprocess.Popen(shlex.split(cmd), shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self.commandInProgress = True
        self.killCommandInProgress = False
        self.grabbedStreams = False

        while not self.killCommandInProgress:
            self.process.poll()
            if self.process.returncode is not None:
                # done!
                self.commandInProgress = False
                self.lastExitCode = self.process.returncode
                break
            time.sleep(.1)
        else:
            self.process.terminate() # kill the process since killCommandInProgress was set
            self.commandInProgress = False

        # give time for exec_command to grab stdout/stderr
        while self.grabbedStreams is False:
            time.sleep(.1)

        self.process = None
        self.grabbedStreams = False

    def exec_command(self, cmd, get_pty=True):
        '''
        Brief:
            Mocked out exec_command() call to call a command locally
        '''
        t = threading.Thread(target=self._popen_thread, args=(cmd,))
        t.setDaemon(False)
        t.start()

        # wait for process to return stdout/stderr
        while self.process is None:
            time.sleep(.1)

        stdout, stderr = MockStream(self, self.process.stdout), MockStream(self, self.process.stderr)

        self.grabbedStreams = True

        return None, stdout, stderr

    def close(self):
        '''
        Brief:
            Will kill the existing command if it is running
        '''
        if self.commandInProgress:
            self.killCommandInProgress = True

        while self.commandInProgress:
            time.sleep(.1) # wait for death.

        self.killCommandInProgress = False

class MockSftpClient(object):
    '''
    Brief:
        Mocked out SFTP client
    '''
    def put(self, local, remote):
        '''
        Brief:
            Do a copy from local to remote
        '''
        shutil.copyfile(local, remote)

    def get(self, remote, local):
        '''
        Brief:
            Do a copy from remote to local
        '''
        shutil.copyfile(remote, local)

    stat = lambda self, x: os.stat(x)
    listdir = lambda self, x: os.listdir(x)
    sftp = lambda self, x: os.mkdir(x)
    getcwd = lambda self: os.getcwd()
    unlink = lambda self, x: os.unlink(x)
    chdir = lambda self, x: None # don't do anything since we would wind up doing this twice (os.chdir/sftp.chdir)
    rmdir = lambda self, x: os.rmdir(x)
    mkdir = lambda self, x: os.mkdir(x)

class MockCRRunner(cRRunner):
    '''
    Brief:
        Mocks out the cRRunner to not actually do SSH via Paramiko
    '''
    def __init__(self, eventList, quiet=True):
        '''
        init for the MockCRRunner. Only take in an eventList and quiet. Everything else is mocked.
        '''
        self.eventList = eventList
        self.quiet = quiet

    def _getSshClient(self):
        '''
        Brief:
            Get the mocked out SSH client
        '''
        return MockSshClient()

    def _getSftpClient(self):
        '''
        Brief:
            Get the mocked SFTP client
        '''
        return MockSftpClient()

    close = lambda self: None

def test_execute():
    '''
    Brief:
        Test that execute events work properly (and timeouts work)
    '''
    if os.name == 'nt':
        pingForAwhileArg = '-n'
        dir = 'dir'
    else:
        pingForAwhileArg = '-t'
        dir = 'ls'

    m = MockCRRunner(
        [
            ExecuteEvent('ping 127.0.0.1 %s 6' % pingForAwhileArg, 3),
            ExecuteEvent(dir, 3),
        ]
    )

    result = m.run()
    assert len(result) == 2

    assert result[0].didFail()
    assert result[0].statusCode == STATUS_TIMEOUT
    assert len(result[0].stdout.splitlines()) > 1

    assert not result[1].didFail()
    assert result[1].statusCode == STATUS_SUCCESS

def test_copy():
    '''
    Brief:
        Test that copy events work
    '''
    TEST_FILE = 'test'
    OTHER_TEST_FILE = 'test_other'

    m = MockCRRunner(
        [
            CopyToRemoteEvent(
                [
                    CopyObject(local=__file__, remote=TEST_FILE)
                ]
            )
        ]
    )
    result = m.run()

    assert not result[0].didFail()

    assert os.path.isfile(TEST_FILE)

    m = MockCRRunner(
        [
            CopyToRemoteEvent(
                [
                    CopyObject(local=TEST_FILE, remote=OTHER_TEST_FILE)
                ]
            )
        ]
    )
    result = m.run()

    assert not result[0].didFail()

    assert os.path.isfile(OTHER_TEST_FILE)

    os.unlink(TEST_FILE)
    os.unlink(OTHER_TEST_FILE)

def test_delete_copied():
    '''
    Brief:
        Test that we can delete copied files
    '''
    TEST_FILE = 'test'
    m = MockCRRunner(
        [
            CopyToRemoteEvent(
                [
                    CopyObject(local=__file__, remote=TEST_FILE),
                ],
            ),
            ExecuteEvent('''python -c \"import os;assert os.path.isfile('%s')\"''' % TEST_FILE), # make sure the file made it
            DeleteAllCopiedToRemote(),
        ]
    )
    result = m.run()

    assert not result[0].didFail()
    assert result[1].remoteReturnCode == 0 # the file was copied
    assert not result[2].didFail()

    assert not os.path.isfile(TEST_FILE) # should be deleted

def test_dir_create_check():
    '''
    Brief::
        Check that we can create a directory and make sure its a dir
    '''
    m = MockCRRunner([])
    TEST_FOLDER = 'test'

    m._safeMkdir(TEST_FOLDER)
    m._safeMkdir(TEST_FOLDER) # don't traceback

    assert m._remoteIsDir(TEST_FOLDER)

    m._getSftpClient().rmdir(TEST_FOLDER)

    assert not m._remoteIsDir(TEST_FOLDER)