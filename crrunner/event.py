'''
Brief:
    event.py - File for cRemote Runner's Events

Author(s):
    Charles Machalow via MIT License
'''

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

class Event(object):
    '''
    Brief:
        This is an abstract base class for all events
            When an event is run by the cRRunner, the run() method
                is called and return status is remembered by the runner.
    '''
    def run(self, runner):
        '''
        Brief:
            Should perform the event using the runner.
                Should return a Result object
        '''
        raise NotImplementedError

class ExecuteEvent(Event):
    '''
    Brief:
        This event is used to execute a command via SSH on remote
    '''
    def __init__(self, command, timeout=60):
        '''
        Brief:
            init for Event object, takes in a cRRunner object
        '''
        self.command = command
        self.timeout = timeout

    def run(self, runner):
        '''
        Brief:
            Calls the given command with a given timeout
        '''
        self.ex = None
        status = STATUS_SUCCESS
        try:
            stdout, stderr = runner._raw_execute(self.command, self.timeout)
        except TimeoutError as ex:
            self.ex = ex # save for later
            stdout, stderr = ex.stdout, ex.stderr
            status = STATUS_TIMEOUT

        retCode = stdout.channel.recv_exit_status()

        return Result(statusCode=status, remoteReturnCode=retCode, stdout=stdout.read().decode(), stderr=stderr.read().decode(), exception=self.ex)

class CopyToRemoteEvent(Event):
    '''
    Brief:
        This event is used to denote a list of items should be copied to the remote from local
    '''
    def __init__(self, listOfCopyObject):
        '''
        Brief:
            init for CopyToRemoteEvent object.
        '''
        self.listOfCopyObject = listOfCopyObject

    def run(self, runner):
        '''
        Brief:
            Copies the files from local to remote
        '''
        if not hasattr(runner, '_remoteToDelete'):
            runner._remoteToDelete = [] # save on the runner for later use. Do not clear.

        stfp = runner._getSftpClient()
        for copyObj in self.listOfCopyObject:
            runner._remoteToDelete.extend(runner._put(copyObj.local, copyObj.remote))

        return Result() # todo... check status of put?

class CopyFromRemoteEvent(Event):
    '''
    Brief:
        This event is used to denote a list of items should be copied to local from the remote
    '''
    def __init__(self, listOfCopyObject):
        '''
        Brief:
            init for CopyFromRemoteEvent object.
        '''
        self.listOfCopyObject = listOfCopyObject

    def run(self, runner):
        '''
        Brief:
            Copies the files from remote to local
        '''
        stfp = runner._getSftpClient()
        for copyObj in self.listOfCopyObject:
            runner._get(copyObj.remote, copyObj.local)

        return Result() # todo... check status of put?

class DeleteAllCopiedToRemote(Event):
    '''
    Brief:
        This event is used to delete all files we know we already copied to remote.
            This deletes the files on remote (not directories).
    '''
    def run(self, runner):
        '''
        Brief:
            Copies the files from local to remote
        '''
        remoteFiles = getattr(runner, '_remoteToDelete', [])

        sftp = runner._getSftpClient()
        for i in remoteFiles:
            sftp.unlink(i)

        runner.log("Cleaning... Deleted %d remote files" % len(remoteFiles))

        runner._remoteToDelete = []

        return Result() # todo... check status of unlink?

class Result(object):
    def __init__(self, statusCode=STATUS_SUCCESS, remoteReturnCode=None, stdout=None, stderr=None, exception=None, statusCodeDict=None):
        '''
        Brief:
            init for Result object. The result is the result of a command executed remotely.
                It includes the remote return code, stdout, stderr and if generated locally,
                    a Python exception. Typically the Python exception would be for a timeout.
        '''
        self.statusCode = statusCode
        self.remoteReturnCode = remoteReturnCode
        self.stdout = stdout
        self.stderr = stderr
        self.exception = exception

        # allow the user to change the status code dict for getStatus()
        if statusCodeDict is None:
            self.statusCodeDict = STATUS_CODES
        else:
            self.statusCodeDict = statusCodeDict

    def getStatus(self):
        '''
        Brief:
            Parses the statusCode as a string with description
        '''
        return '%d - %s' % (self.statusCode, self.statusCodeDict.get(self.statusCode, 'Unknown'))

    def didFail(self):
        '''
        Brief:
            Returns True if the command failed due to something other than the command itself failing
                For example: Timeout
        '''
        return self.statusCode != STATUS_SUCCESS

    def __str__(self):
        retStr = ''
        retStr += 'statusCode: %d\n' % self.statusCode
        retStr += 'remoteReturnCode: %d\n' % self.remoteReturnCode
        retStr += 'exception: \n%s\n' % self.exception
        retStr += 'stdout:\n%s\n' % self.stdout
        retStr += 'stderr:\n%s\n' % self.stderr
        return retStr

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