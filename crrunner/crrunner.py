'''
Brief:
    crruner.py - File for cRemote Runner

Description:
    Use this to have something get copied, run and executed remotely.

Author(s):
    Charles Machalow via MIT License
'''

import os
import paramiko
import stat
import time

from event import *

class cRRunner(object):
    '''
    Brief:
        Object used to have events ran remotely via SSH
    '''
    def __init__(self, remoteIp, eventList, remoteUsername=None, remotePassword=None, remotePort=22, quiet=True):
        '''
        Brief:
            Configuration (and runner) for cRemote Runner

        Argument(s):
            remoteIp - (Required) - IP for remote SSH connection
            eventList - (Required) - List of events to execute (in order)
            remoteUsername - (Optional; Defaults to None) - Text username for remote SSH connection
                If None is given, will assume we don't need credentials.
            remotePassword - (Optional; Defaults to None) - Text password for remote SSH connection
                If None is given, will assume we don't need credentials.
            remotePort - (Optional; Defaults to 22) - Port for SSH connection
            quiet - (Optional; Defaults to True) - If True, be quiet and don't log to screen
        '''
        self._sshClient = None
        self._sftpClient = None

        if type(remoteUsername) is not type(remotePassword):
            raise ValueError("If remoteUsername is provided, we also need remotePassword")

        self.remoteIp = remoteIp
        self.remoteUsername = remoteUsername
        self.remotePassword = remotePassword # lol security
        self.remotePort = remotePort

        self.eventList = eventList

        self.quiet = quiet

    def _getSshClient(self):
        '''
        Brief:
            Uses the ip/port to connect to remote if needed. Otherwise returns existing ssh client.
            Will reopen if needed.
        '''
        if self._sshClient is None or self._sshClient.get_transport() is None:
            self._sshClient = paramiko.SSHClient()

            # Only use AutoAddPolicy if we have user/password
            if self.remoteUsername is not None and self.remotePassword is not None:
                self._sshClient.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self._sshClient.connect(self.remoteIp, username=self.remoteUsername, password=self.remotePassword)

        return self._sshClient

    def _getSftpClient(self):
        '''
        Brief:
            Gets the SFTP client for the given connection.
                Will reopen if needed.
        '''
        if self._sftpClient is None or self._sftpClient.get_channel().closed:
            self._sftpClient = self._getSshClient().open_sftp()
        return self._sftpClient

    def _raw_execute(self, remoteCmd, timeoutSeconds):
        '''
        Brief:
            Executes the remote cmd on remote and passes back stdout, stderr
        '''
        self.log("Calling %s with a timeout of %f" % (remoteCmd, timeoutSeconds))
        ssh = self._getSshClient()
        (stdin, stdout, stderr) = ssh.exec_command(remoteCmd, get_pty=True)

        deathTime = time.time() + timeoutSeconds

        while time.time() < deathTime:
            if stdout.channel.exit_status_ready():
                break
            time.sleep(.1) # sleep a bit to let other threads do things as needed
        else:
            ssh.close() # kill command
            t = TimeoutError('Command timed out')
            t.stdout = stdout
            t.stderr = stderr
            raise t

        return stdout, stderr

    def _safeMkdir(self, newDir):
        '''
        Brief:
            Calls mkdir for a new remote directory and throws out any errors
        '''
        sftp = self._getSftpClient()
        try:
            sftp.mkdir(newDir)
        except:
            pass

    def _put(self, local, remote):
        '''
        Brief:
            Can put files or folders on remote
                Returns list of remote files put with paths to them.
        '''
        sftp = self._getSftpClient()

        if remote is None:
            remote = os.path.basename(local)

        self.log("Putting %s -> %s" % (local, remote))

        retList = []
        if os.path.isfile(local):
            retList.append(remote)
            sftp.put(local, remote)
        else: # folder
            self._safeMkdir(remote)
            for item in os.listdir(local):
                fullPath = os.path.join(local, item)
                retList.extend(self._put(fullPath, '%s/%s' % (remote, item)))

        return retList

    def _remoteIsDir(self, remote):
        '''
        Brief:
            Checks if remote is a directory
        '''
        sftp = self._getSftpClient()
        try:
            attributes = sftp.stat(remote)
            return stat.S_ISDIR(attributes.st_mode)
        except:
            return False # stat failed

    def _get(self, remote, local):
        '''
        Brief:
            Can get files or folders from remote
        '''
        sftp = self._getSftpClient()

        if local is None:
            local = os.path.basename(remote)

        self.log("Getting %s -> %s" % (remote, local))

        attributes = sftp.stat(remote)
        # not using _remoteIsDir() since it doesn't say if remote was a file or non-existant
        isDir = stat.S_ISDIR(attributes.st_mode)
        if not isDir: # is a file:
            sftp.get(remote, local)
        else:
            # is a folder
            try:
                os.makedirs(local)
            except:
                pass

            for remoteThing in sftp.listdir(remote):
                remoteThingFullPath = '%s/%s' % (remote, remoteThing)
                localThingFullPath = '%s/%s' % (local, remoteThing)
                self._get(remoteThingFullPath, localThingFullPath)

    def log(self, s):
        '''
        Brief:
            If not quiet, will print s to the screen as a log item
        '''
        if not self.quiet:
            print('cRunner Log - ' + str(s))

    def close(self):
        '''
        Brief:
            Closes all known connections
        '''
        # do not call the _getSftpClient/_getSshClient() functions
        #  since they will create if not needed
        if self._sftpClient:
            self._sftpClient.close()
            self._sftpClient = None

        if self._sshClient:
            self._sshClient.close()
            self._sshClient = None

    def run(self):
        '''
        Brief:
            Runs the CRRunner. Runs all given Events. Returns all the results.
        '''
        self.results = []
        for i in self.eventList:
            r = i.run(self) # pass the runner to run
            self.results.append(r)

        self.close()

        return self.results

if __name__ == '__main__': # pragma: no cover
    # test code
    remoteIp = os.environ['REMOTE_IP']
    remotePassword = os.environ['REMOTE_PASSWORD']

    c = cRRunner(remoteIp=remoteIp, eventList=[
        ExecuteEvent('ls'),
        CopyToRemoteEvent(
            [
                CopyObject(r"C:\Users\csm10495\Desktop\Stuff\app")
            ]
        ),
        ExecuteEvent('sleep 5', 2),
        DeleteAllCopiedToRemote(),
        ExecuteEvent('echo hey > /tmp/mytmp.txt'),
        CopyFromRemoteEvent(
            [
                CopyObject('mytmp.txt', '/tmp/mytmp.txt')
            ]
        )
        ],
    remoteUsername='test', remotePassword=remotePassword, quiet=False)