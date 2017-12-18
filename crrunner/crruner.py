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
import time

STATUS_SUCCESS = 0
STATUS_TIMEOUT = 1
STATUS_CODES = {
    STATUS_SUCCESS : 'Completed Successfully',
    STATUS_TIMEOUT : 'Timeout',
}

class TimeoutError(Exception):
    '''
    Brief:
        Used to denote a timeout
    '''
    pass

class Result(object):
    def __init__(self, statusCode, remoteReturnCode=None, stdout=None, stderr=None, exception=None):
        self.statusCode = statusCode
        self.remoteReturnCode = remoteReturnCode
        self.stdout = stdout
        self.stderr = stderr
        self.exception = exception

    def getStatus(self):
        return '%d - %s' % (self.statusCode, STATUS_CODES.get(self.statusCode, 'Unknown'))

    def didFail(self):
        return self.statusCode != 0

class CopyObject(object):
    def __init__(self, local, remote=None):
        '''
        Brief:
            Init for CopyObject. CopyObject is used to say this thing should be copyied here remotely

        Argument(s):
            local - (Required) - Location of local object (file or folder)
            remote- (Optional; Defaults to None) - Location for this object on remote
                If None is given, will be placed in the cwd
        '''
        self.local = local
        self.remote = remote

class cRRunner(object):
    def __init__(self, remoteIp, remoteCmd, remoteCmdTimeout=60, remoteUsername=None, remotePassword=None, copyObjectsTo=None, copyObjectsFrom=None, remotePort=22, quiet=True):
        '''
        Brief:
            Configuration (and runner) for cRemote Runner

        Argument(s):
            remoteIp - (Required) - IP for remote SSH connection
            remoteCmd - (Required) - Cmd to execute after copying all copyObjects
            remoteCmdTimeout - (Optional; Defaults to 60) - Timeout for remoteCmd in seconds
            remoteUsername - (Optional; Defaults to None) - Text username for remote SSH connection
                If None is given, will assume we don't need credentials.
            remotePassword - (Optional; Defaults to None) - Text password for remote SSH connection
                If None is given, will assume we don't need credentials.
            copyObjectsTo - (Optional; Derfaults to None) - List of CopyObject to copy to (before).
                If None, nothing to copy
            copyObjectsFrom - (Optional; Derfaults to None) - List of CopyObject to copy from (after)
                If None, nothing to copy... TODO. NOT IMPLEMENTED YET.
            remotePort - (Optional; Defaults to 22) - Port for SSH connection
            quiet - (Optional; Defaults to True) - If True, be quiet and don't log to screen
        '''
        self._sshClient = None
        self._sftpClient = None
        self.quiet = quiet

        self.remoteIp = remoteIp
        self.remoteCmdTimeout = remoteCmdTimeout

        if type(remoteUsername) is not type(remotePassword):
            raise ValueError("If remoteUsername is provided, we also need remotePassword")

        self.remoteUsername = remoteUsername
        self.remotePassword = remotePassword # lol security

        self.remoteCmd = remoteCmd

        if copyObjectsTo is None:
            copyObjectsTo = []

        self.copyObjectsTo = copyObjectsTo

        if copyObjectsFrom is None:
            copyObjectsFrom = []

        self.copyObjectsFrom = copyObjectsFrom
        self.remotePort = remotePort

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

    def _execute(self):
        '''
        Brief:
            Executes the saved remoteCmd. Returns stdout, stderr
        '''
        stdout, stderr = self._raw_execute(self.remoteCmd, timeoutSeconds=self.remoteCmdTimeout)
        retCode = stdout.channel.recv_exit_status()
        r = Result(statusCode=STATUS_SUCCESS, remoteReturnCode=retCode, stdout=stdout.read().decode(), stderr=stderr.read().decode(), exception=None)
        return r

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
        '''
        sftp = self._getSftpClient()

        if remote is None:
            remote = os.path.basename(local)

        self.log("Putting %s -> %s" % (local, remote))

        if os.path.isfile(local):
            sftp.put(local, remote)
        else: # folder
            self._safeMkdir(remote)
            for item in os.listdir(local):
                fullPath = os.path.join(local, item)
                if os.path.isfile(fullPath):
                    self._put(fullPath, '%s/%s' % (remote, item))
                else:
                    self._safeMkdir('%s/%s' % (remote, item))
                    self._put(fullPath, '%s/%s' % (remote, item))

    def _get(self, local, remote):
        '''
        Brief:
            Can get files or folders on remote
        '''
        raise NotImplementedError

    def _doCopyObjectsTo(self):
        '''
        Brief:
            Goes through copyObjectsTo and copies all over to remote
        '''
        stfp = self._getSftpClient()
        for copyObj in self.copyObjectsTo:
            self._put(copyObj.local, copyObj.remote)

    def _doCopyObjectsFrom(self):
        '''
        Brief:
            Goes through copyObjectsFrp, and copies all objectes here
        '''
        if len(self.copyObjectsFrom) != 0:
            raise NotImplementedError("copyObjectsFrom is not implemented yet.")

    def log(self, s):
        '''
        Brief:
            If not quiet, will print s to the screen as a log item
        '''
        if not self.quiet:
            print('cRunner Log - ' + str(s))

    def run(self):
        '''
        Brief:
            Runs the CRRuner.
                Copies objects to, executes, then copies objects from
        '''
        self._doCopyObjectsTo()
        try:
            result = self._execute()
        except Exception as ex:
            # remember we are passing the stderr/stdout with the exception
            result = Result(statusCode=STATUS_TIMEOUT, exception=ex, stdout=ex.stdout.read().decode(), stderr=ex.stderr.read().decode())
        self._doCopyObjectsFrom()
        return result