import subprocess
from subprocess import PIPE
from logger import _logger
import os

def get_commit_list(path='.', n_show=1, remote=False):
    """Get the 'n_show' number of git commits from the top, in the directory 'path'"""
    
    _logger.debug('Enter get_commit_list')
    cmd = 'git fetch && git log origin/master' if remote else 'git log'
    out = subprocess.check_output(f'cd {path} && {cmd} --format="%H" -n {n_show}',
                            shell=True, universal_newlines=True, timeout=60) ## set timeout
    return out.split('\n')[:-1]

def get_diff_tree(path='.', commit_id=None):
    """Get the diff for given commit(s)"""

    _logger.debug(f'Enter get_diff_tree. commit_id: {commit_id}')
    out = subprocess.check_output(f'cd {path} && git diff --name-status -C {commit_id}',
                            shell=True, universal_newlines=True, timeout=60) ## set timeout
    result = []
    for line in out.split('\n')[:-1]:
        result.append(line.split()) ## e.g. ['R100', 'test/a.py', 'test/cc.py']
    return result

def get_patch(path='.', commit_id=None, ext_cmd='-U0'):
    """Get the patch file for given commit range"""

    _logger.debug(f'Enter get_patch. commit_id: {commit_id}, ext_cmd: {ext_cmd}')
    out = subprocess.check_output(f'cd {path} && git diff {commit_id} {ext_cmd}',
                            shell=True, universal_newlines=True, timeout=60) ## set timeout
    return out

def check_clean(path='.'):
    _logger.debug(f'Enter check_clean.')
    out = subprocess.check_output(f'cd {path} && git status --porcelain',
                            shell=True, universal_newlines=True, timeout=60) ## set timeout
    return True if out == '' else False
    
def extact_author(out):
    import re
    result = re.findall('Author:[ ]*(.+)[ ]+<(.+)>', out)
    if len(result) == 0:
        return (None, None)
    else:
        return result[0]

def get_commit_author(path='.', commit_id=None):
    """Get the author info for a given commit"""

    _logger.debug(f'Enter get_commit_author. commit_id: {commit_id}')
    out = subprocess.check_output(f'cd {path} && git show {commit_id} | grep Author',
                            shell=True, universal_newlines=True, timeout=60) ## set timeout
    return extact_author(out)

def get_file_last_commit_author(path='.', fpath='.'):
    """Get the author info for the last commit that changes a given file"""

    _logger.debug(f'Enter get_commit_author. fpath: {fpath}')
    out = subprocess.check_output(f'cd {path} && git show -n 1 -p {fpath} | grep Author',
                            shell=True, universal_newlines=True, timeout=60) ## set timeout
    return extact_author(out)

def get_extra_git_ssh_cmd(args):
    if 'ssh_key' in args['bot']:
        return 'GIT_SSH_COMMAND="ssh -i {ssh_key} -o IdentitiesOnly=yes"'.format(ssh_key=args['bot']['ssh_key'])
    else:
        return ''

def git_clone(git_remote, setup_dir, **kwargs):
    """Do git clone"""
    
    _logger.debug(f'Enter git_clone. setup_dir: {setup_dir}')
    if 'args' in kwargs:
        args = kwargs['args']
    subprocess.check_output(f'{get_extra_git_ssh_cmd(args)} git clone {git_remote} {setup_dir}',
                            shell=True, universal_newlines=True, timeout=60) ## set timeout

def git_pull(path='.', **kwargs):
    """Do git pull"""
    
    _logger.debug(f'Enter git_pull. path: {path}')
    if 'args' in kwargs:
        args = kwargs['args']
    subprocess.check_output(f'cd {path} && {get_extra_git_ssh_cmd(args)} git pull origin master',
                            shell=True, universal_newlines=True, timeout=60) ## set timeout

def git_push(path='.', msg='', **kwargs):
    """Push current repo to master Do git pull"""
    
    _logger.debug(f'Enter git_push. path: {path}, msg: {msg}')
    if 'args' in kwargs:
        args = kwargs['args']
    author, email = args['bot']['author'], args['bot']['email']
    subprocess.check_output(f'cd {path} && git add . && git commit -m "{msg}" --author="{author} <{email}>" && {get_extra_git_ssh_cmd(args)} git push origin master', 
                            shell=True, universal_newlines=True, timeout=60) ## set timeout
    