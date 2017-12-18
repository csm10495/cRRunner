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
    def __init__(self, local=None, remote=None):
        '''
        Brief:
            Init for CopyObject. CopyObject is used to say this thing should be copyied here remotely

        Argument(s):
            local - (Optional; Defaults to None) - Location of local object (file or folder)
                If None is given, will be placed/grabbed in/from the cwd
            remote- (Optional; Defaults to None) - Location for this object on remote
                If None is given, will be placed/grabbed in/from  in the cwd
        '''
        if local is None and remote is None:
            raise ValueError('local and remote cannot both be None')

        self.local = local
        self.remote = remote

class cRRunner(object):
    def __init__(self, remoteIp, remoteCmd=None, remoteCmdTimeout=60, remoteUsername=None, remotePassword=None, copyObjectsTo=None, copyObjectsFrom=None, remotePort=22, cleanRemote=True, quiet=True):
        '''
        Brief:
            Configuration (and runner) for cRemote Runner

        Argument(s):
            remoteIp - (Required) - IP for remote SSH connection
            remoteCmd - (Optional; Defaults to None) - Cmd to execute after copying all copyObjects
                If None, won't use execute a command.
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
            cleanRemote - (Optional; Defaults to True) - If True, delete copied files on remote
                after copying objects from back.
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
        self.cleanRemote = cleanRemote

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
                if os.path.isfile(fullPath):
                    retList.extend(self._put(fullPath, '%s/%s' % (remote, item)))
                else:
                    self._safeMkdir('%s/%s' % (remote, item))
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
        self._remoteToDelete = []
        stfp = self._getSftpClient()
        for copyObj in self.copyObjectsTo:
            self._remoteToDelete.extend(self._put(copyObj.local, copyObj.remote))

    def _doCopyObjectsFrom(self):
        '''
        Brief:
            Goes through copyObjectsFrp, and copies all objectes here
        '''
        if len(self.copyObjectsFrom) != 0:
            raise NotImplementedError("copyObjectsFrom is not implemented yet.")

    def _doDeleteRemote(self):
        '''
        Brief:
            Deletes all known (copied) remote files
        '''
        sftp = self._getSftpClient()
        for i in self._remoteToDelete:
            sftp.unlink(i)
        self.log("Cleaning... Deleted %d remote files" % len(self._remoteToDelete))

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
            Runs the CRRunner.
                Copies objects to, executes, then copies objects from
        '''
        self._doCopyObjectsTo()
        result = None
        if self.remoteCmd is not None:
            try:
                result = self._execute()
            except Exception as ex:
                # remember we are passing the stderr/stdout with the exception
                result = Result(statusCode=STATUS_TIMEOUT, exception=ex, stdout=ex.stdout.read().decode(), stderr=ex.stderr.read().decode())
        self._doCopyObjectsFrom()
        if self.cleanRemote:
            self._doDeleteRemote()
        return result

if __name__ == '__main__':
    # test code
    remoteIp = os.environ['REMOTE_IP']
    remotePassword = os.environ['REMOTE_PASSWORD']

    copyTos = [CopyObject(r"C:\Users\csm10495\Desktop\Stuff\app")]

    c = cRRunner(remoteIp=remoteIp, remoteUsername='test', remotePassword=remotePassword, remoteCmd='ls', copyObjectsTo=copyTos, quiet=False)