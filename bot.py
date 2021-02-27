import subprocess
import yaml
import os, shutil, time
from logger import _logger
from gitutils import get_commit_list, get_diff_tree, get_patch, check_clean, get_commit_author, get_file_last_commit_author
from gitutils import git_clone, git_pull, git_push
from translator import DeepLTranslator as Translator
from translator import fix_broken_mkdown
from mail import send_mail
from summaryparser import SummaryParser as sp
from externalprocess import ExternalProcess

def runcmd(cmd):
    """Run a shell command"""
    p = subprocess.Popen(
        cmd, shell=True, universal_newlines=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE
    )
    out, _ = p.communicate()
    return (out, p.returncode)

class Builder(ExternalProcess):
    """Maintain the main gitbook service"""

    def __init__(self, args):
        super(Builder, self).__init__(args=args, name='builder')

    def keep(self):
        """Maintain the main gitbook service"""
        ## Run super: record pid
        super(Builder, self).keep()

        ## serve the gitbook
        args = self.args
        path = args['workarea']['relpath']
        if not os.path.exists(path): # if the workarea does not exist
            git_clone(git_remote=args['workarea']['git_remote'], setup_dir=path, args=args)
        if not os.path.exists(os.path.join(path, 'node_modules')): # if not built for the first time
            out, ret = runcmd(f'cd {path} && gitbook init && gitbook install')
            if ret != 0:
                _logger.error(f'Gitbook init failed. Path: {path}. Output:\n{out}')
                raise RuntimeError()
        
        with open(f'{self.name}.out', 'w') as fout:
            p = subprocess.Popen(
                f'cd {path} && gitbook serve --port 3001', 
                shell=True, universal_newlines=True, stderr=fout, stdout=fout
            ) 
            p.wait()

        ## Should not go this far...
        with open(f'{self.name}.out') as f:
            self.errormsg.value = '\n'.join(f.readlines()[-50:]) # takes the last 50 rows
        

class TestMonitor(ExternalProcess):
    """An external process that do the test monitoring job. Takes most of a bot's job"""

    def __init__(self, args):
        super(TestMonitor, self).__init__(args=args, name='test_monitor')

    def keep(self):
        """Git pull the lastest commits, launch local test, do translation when necessary, then provide feedbacks"""
        ## Run super: record pid
        super(TestMonitor, self).keep()

        def gitbook_built_success(path):
            """Build gitbook and check if success"""
            if not os.path.exists(os.path.join(path, 'node_modules')):
                _logger.info('Initiating Gitbook...')
                out, ret = runcmd(f'cd {path} && gitbook init && gitbook install')
                if ret != 0:
                    _logger.error(f'Gitbook init failed. Path: {path}. Output:\n{out}')
                    raise RuntimeError()
            out, ret = runcmd(f'cd {path} && gitbook build')
            if ret != 0:
                _logger.error(f'Gitbook build failed. Path: {path}. Output:\n{out}')
                return (False, out)
            return (True, None)

        def dual(path):
            if 'zh-hans/' in path:
                return {'name':path.replace('zh-hans/', 'en/'), 'trans':('zh','en')}
            elif 'en/' in path:
                return {'name':path.replace('en/', 'zh-hans/'), 'trans':('en','zh')}
            else:
                raise SyntaxError('Wrong path')

        def notify_error(text):
            _logger.error(text)
            send_mail(subject=args['bot']['commit_prefix']+'Wikibot detect error: '+text, text=text, args=args)
        
        def translate_from_to(_translator, lang, from_path, to_path):
            with open(from_path) as f:
                text = f.read()
            text = _translator.launch(text, target_lang=lang[1], source_lang=lang[0])
            text = _translator.post(text)
            with open(to_path, 'w') as fw:
                fw.write(text)

        ## Set up testarea if not exists / update the testarea to sync the remote
        args = self.args
        path = args['testarea']['relpath']
        if not os.path.exists(args['testarea']['relpath']):
            _logger.debug(f"Git clone to {args['testarea']['relpath']}")
            git_clone(git_remote=args['testarea']['git_remote'], setup_dir=path, args=args)
        else:
            git_pull(path=path, args=args)
        last_cid = get_commit_list(path=path, n_show=1)[0]

        ## Assert that current repo can be built successfully, and SUMMARY.md has consistent format
        if gitbook_built_success(path)[0] and sp.check_consistency(path):
            last_success_cid = last_cid
        else:
            _logger.warning('Problem detected with current remote repo! It is either a build failure, or inconsistency in SUMMARY.md. We will read the last success commit id')
            with open('.commit_success') as f:
                last_success_cid = f.read().split('\n')[0]
        _logger.debug(f'last_success_cid while enter: {last_success_cid}')
            
        with open('.commit_success', 'w') as fw:
            fw.write(last_success_cid)

        ## Init translator
        trans = Translator(selenium_configs={'http_proxy':'127.0.0.1:8090', 'headless':True})

        ## Start test monitoring
        while True:
            time.sleep(10)
            remote_last_cid = get_commit_list(path=path, n_show=1, remote=True)[0]
            if last_cid == remote_last_cid: # nothing changed. Go to next iteration
                continue
            
            ## New remote changes detected. First do git pull
            git_pull(path=path, args=args)
            
            ## Get all untracked cid by looking back to the commit list (not used now. we treat all untracked cid as a whole)
            untracked_cid = []
            for cid in get_commit_list(path=path, n_show=20):
                untracked_cid.append(cid)
                if cid == last_cid:
                    break
            _logger.info(f"New commits pulled to local: {', '.join(untracked_cid[:-1][::-1])}")

            ## Update last commit id, get the author
            last_cid = remote_last_cid
            commit_author = get_commit_author(path=path, commit_id=remote_last_cid)
            
            ## First check if can successfully built
            gb_success, gb_out = gitbook_built_success(path)
            if not gb_success:
                mail_templ = 'Dear {author},\n\nThe commit {cid}\nis successfully pushed to origin/master.\n'
                mail_templ += 'However it cannot be built successfully. See the log below:\n\n{gb_out}\n\nCheers,\nBot\n'
                send_mail(
                    subject=args['bot']['commit_prefix']+'Commit {cid8} merged to hepwiki. Problem detected'.format(cid8=remote_last_cid[:8]),
                    text=mail_templ.format(
                        author=commit_author[0],
                        cid=os.path.join(args['gitlab']['home'], args['testarea']['git_remote'].split(':')[-1][:-4], '-/commit', remote_last_cid),
                        gb_out=gb_out,
                    ),
                    args=args, receiver='{} <{}>'.format(*commit_author), cc_admin=True,
                )
            else: # success! Do bot's job
                ## Get the diff tree list
                diff_tree = get_diff_tree(path=path, commit_id=f'{last_success_cid}..{remote_last_cid}')
                _logger.info('Tree diff: \n{df}'.format(df='\n'.join(['\t'.join(line) for line in diff_tree])))
                
                ## Get list of modified files and moved files
                modif_files, modif_sum_files, moved_files = [], [], []
                auto_trans, need_manual_trans = [], []
                for line in diff_tree:
                    if (line[-1].startswith('zh-hans/') or line[-1].startswith('en/')) and line[-1].endswith('.md'):
                        if line[-1].endswith('/SUMMARY.md'):
                            modif_sum_files.append(line[-1]) ## specially record the changed summary file
                        else:
                            modif_files.append(line[-1])
                        if len(line)==3:
                            moved_files.append(line[1])
                _logger.info(f"modif_files:       [{', '.join(modif_files)}]")
                _logger.info(f"modif_files (sum): [{', '.join(modif_sum_files)}]")
                _logger.info(f"moved_files:       [{', '.join(moved_files)}]")

                ## ================================================================================
                ## 1. First handles the SUMMARY.md file
                ## ================================================================================
                is_modif_sum_lang = ['zh-hans/SUMMARY.md' in modif_sum_files, 'en/SUMMARY.md' in modif_sum_files]
                if sum(is_modif_sum_lang) == 2: # modified both
                    # Check if consistent
                    if not sp.check_consistency(path=path):
                        mail_templ = 'Dear {author},\n\nThe commit {cid}\nis successfully pushed to origin/master.\n'
                        mail_templ += 'It seems you have modified both SUMMARY.md in zh-hans/ and en/, while they are not consistent after revision.'
                        mail_templ += 'Please check the syntax of two SUMMARY.md files below (especially check the spacing) and make another commit:\n\n{weblink}\n\nCheers,\nBot\n'
                        send_mail(
                            subject=args['bot']['commit_prefix']+'Commit {cid8} merged to hepwiki. Problem detected'.format(cid8=remote_last_cid[:8]),
                            text=mail_templ.format(
                                author=commit_author[0],
                                cid=os.path.join(args['gitlab']['home'], args['testarea']['git_remote'].split(':')[-1][:-4], '-/commit', remote_last_cid),
                                weblink='\n'.join([
                                    os.path.join(args['gitlab']['home'], args['testarea']['git_remote'].split(':')[-1][:-4], '-/raw', remote_last_cid, 'zh-hans/SUMMARY.md'),
                                    os.path.join(args['gitlab']['home'], args['testarea']['git_remote'].split(':')[-1][:-4], '-/raw', remote_last_cid, 'en/SUMMARY.md'),
                                ]),
                            ),
                            args=args, receiver='{} <{}>'.format(*commit_author), cc_admin=True,
                        )
                        continue # directly go to next iteration and wait for future fix
                elif sum(is_modif_sum_lang) == 1:
                    fpath = 'zh-hans/SUMMARY.md' if is_modif_sum_lang[0] else 'en/SUMMARY.md'
                    ## Obtain the target patch that modifies the dual file
                    patch_text_dual = sp.produce_target_summary_patch(
                        path=path, 
                        target_lang='en' if is_modif_sum_lang[0] else 'zh', # target lang is the dual of modified lang
                        patch=get_patch(path=path, commit_id=f'{last_success_cid}..{remote_last_cid}', ext_cmd=f'-U0 -- {fpath}')
                    )
                    with open('.tmp.patch', 'w') as fw:
                        fw.write(patch_text_dual)
                    ## Modify the dual file
                    out, ret = runcmd('patch --dry-run {fp} .tmp.patch'.format(fp=os.path.join(path, dual(fpath)['name'])))
                    if ret != 0: # dry-run fails. This should not happen
                        notify_error(f"In commit {remote_last_cid}: Bot failed to modify the dual SUMMARY.md file. Please fix this manually")
                        need_manual_trans.append(dual(fpath)['name'])
                    else: # patch the dual file
                        runcmd('patch {fp} .tmp.patch'.format(fp=os.path.join(path, dual(fpath)['name'])))
                        auto_trans.append(dual(fpath)['name'])
                    
                elif sum(is_modif_sum_lang) == 0:
                    if not sp.check_consistency(path=path): # this should never happen
                        notify_error(f"In commit {remote_last_cid}: nothing changed to lang/SUMMARY.md but inconsistency detected.")


                ## ================================================================================
                ## 2. Then check line by line and handles all detected file changes
                ## ================================================================================
                for line in diff_tree:
                    if not (line[-1].startswith('zh-hans/') or line[-1].startswith('en/')): # files not related to lingual
                        continue
                    if line[-1].endswith('/SUMMARY.md'): # they are handled already
                        continue
                    fpath = line[-1]
                    absfpath = os.path.join(path, fpath)
                    absfpath_dual = os.path.join(path, dual(fpath)['name'])
                    if not os.path.exists(os.path.dirname(absfpath_dual)): # make dual folder if not exists
                        os.makedirs(os.path.dirname(absfpath_dual))    

                    if line[0] == 'D': # case: a file is deleted
                        if fpath not in moved_files: # not moved away
                            _logger.info(f"In commit {remote_last_cid}: {dual(fpath)['name']} will be removed")
                            os.remove(absfpath_dual)
                    if line[0] == 'A': # case: a new file is added. We create the dual file.
                        if os.path.exists(absfpath_dual):
                            notify_error(f"In commit {remote_last_cid}: {dual(fpath)['name']} should not exist, since {fpath} is just created")
                        if fpath.endswith('.md'): # need translation
                            if os.path.exists(dual(fpath)['name']) and get_file_last_commit_author(path=path, fpath=dual(fpath)['name'])[0] == args['bot']['author']:
                                _logger.info(f"In commit {remote_last_cid}: {dual(fpath)['name']} is auto-translated")
                                translate_from_to(
                                    trans,
                                    lang=dual(fpath)['trans'],
                                    from_path=absfpath,
                                    to_path=absfpath_dual,
                                )
                                auto_trans.append(dual(fpath)['name'])
                        else: # direct copy is fine
                            shutil.copy(absfpath, absfpath_dual)

                    elif line[0] == 'M': # case: modify a file. We check if corresponding file was previous modified. Do translation if not.
                        if fpath.endswith('.md'): # need translation
                            if os.path.exists(absfpath_dual):
                                if fpath not in moved_files: # not moved away. Means that this is a "real" modification
                                    if dual(fpath)['name'] not in modif_files: # dual file not modified in the same commit
                                        # and its last revision is made by bot => can do auto-translate
                                        if get_file_last_commit_author(path=path, fpath=dual(fpath)['name'])[0] == args['bot']['author']:
                                            _logger.info(f"In commit {remote_last_cid}: {dual(fpath)['name']} is auto-translated")
                                            translate_from_to(
                                                trans,
                                                lang=dual(fpath)['trans'], 
                                                from_path=absfpath,
                                                to_path=absfpath_dual,
                                            )
                                            auto_trans.append(dual(fpath)['name'])
                                        else:
                                            need_manual_trans.append(dual(fpath)['name'])
                            else:
                                notify_error(f"In commit {remote_last_cid}: {dual(fpath)['name']} should have existed")
                        else: # direct copy is fine (may overide)
                            shutil.copy(absfpath, absfpath_dual)

                    elif line[0].startswith('C') or line[0].startswith('R'):
                        fpath_orig = line[1]
                        if os.path.exists(os.path.join(path, dual(fpath_orig)['name'])):
                            if line[0][1:] == '100': # 100% changed (simply move/copy)
                                ## Simply move to new dir. The file may be either .md or others
                                os.system(f"cd {path} && git mv {dual(fpath_orig)['name']} {dual(fpath)['name']} && cd -")
                            else: ## despite of pure copy/move, also detect revision
                                if fpath.endswith('.md'): # need translation
                                    ## Check the latest author of the original dual file (before moving)
                                    if get_file_last_commit_author(path=path, fpath=dual(fpath_orig)['name'])[0] == args['bot']['author']:
                                        translate_from_to(
                                            trans, 
                                            lang=dual(fpath)['trans'], 
                                            from_path=absfpath, 
                                            to_path=absfpath_dual,
                                        )
                                        auto_trans.append(dual(fpath)['name']) # append to auto translated list
                                        os.remove(os.path.join(path, dual(fpath_orig)['name'])) # remove the original
                                    else:
                                        need_manual_trans.append(dual(fpath)['name']) # warn users that the file needs manual translation
                                        os.rename(os.path.join(path, dual(fpath_orig)['name']), absfpath_dual) # simply rename the original file
                                else: # direct copy is fine
                                    shutil.copy(absfpath, absfpath_dual)
                
                ## Do git push if workspace is not clean (file changed by bot)
                need_push = not check_clean(path=path)
                if need_push:
                    ## Check if can sill build successfully
                    if not gitbook_built_success(path):
                        notify_error('Cannot built successful after our bot\'s works... Will stop here')
                        raise RuntimeError()
                    git_push(path=path, msg=args['bot']['commit_prefix']+f'Auto-translation for commit {remote_last_cid}', args=args)
                
                last_cid = get_commit_list(path=path, n_show=1)[0]
                last_success_cid = last_cid
                ## Update successful commit
                with open('.commit_success', 'w') as fw:
                    fw.write(last_success_cid)
                new_diff_tree = get_diff_tree(path=path, commit_id=f'{remote_last_cid}..{last_success_cid}')

                mail_templ = 'Dear {author},\n\nThe commit {cid}\nis successfully pushed to origin/master.\n'
                mail_templ += 'The repo can be successfully built. Listed below is the file changes w.r.t. lastest successful build:\n\n'
                mail_templ += '\n'.join(['\t'.join(line) for line in diff_tree])+'\n\n'
                if len(auto_trans) == 0:
                    mail_templ += 'No files are auto translated translation.\n\n'
                else:
                    mail_templ += '📙 Following files are auto-translated:\n\n{auto_trans_text}\n\n'
                if len(need_manual_trans) == 0:
                    mail_templ += 'No files need manual translation.\n\n'
                else:
                    mail_templ += '⚠️ Following files may need manual translation:\n\n{need_manual_trans_text}\n\n'
                if need_push:
                    mail_templ += 'I have made another submit dealing with the translation. The latest commit is at:\n{bot_cid}\n\n'
                    mail_templ += 'Listed below is the file changes w.r.t. your commit:\n\n'
                    mail_templ += '\n'.join(['\t'.join(line) for line in new_diff_tree])+'\n\n'
                
                mail_templ += 'Cheers,\nBot\n'
                send_mail(
                    subject=args['bot']['commit_prefix']+'Commit {cid8} merged to hepwiki. Built successfully'.format(cid8=remote_last_cid[:8]),
                    text=mail_templ.format(
                        author=commit_author[0],
                        cid=os.path.join(args['gitlab']['home'], args['testarea']['git_remote'].split(':')[-1][:-4], '-/commit', remote_last_cid),
                        auto_trans_text='\n'.join(auto_trans),
                        need_manual_trans_text='\n'.join(need_manual_trans),
                        bot_cid=os.path.join(args['gitlab']['home'], args['testarea']['git_remote'].split(':')[-1][:-4], '-/commit', last_success_cid),
                    ),
                    args=args, receiver='{} <{}>'.format(*commit_author), cc_admin=True,
                )

                ## Finally, do git pull in workarea. The remote can be sync-ed to workarea now
                git_pull(path=args['workarea']['relpath'], args=args)
                

if __name__ == '__main__':
    with open('config.yml') as f, open('.mail_config.yml') as _f:
        args = yaml.safe_load(f)
        args['mail'] = yaml.safe_load(_f)
    
    p_test = TestMonitor(args)
    p_test.launch()
    p_buld = Builder(args)
    p_buld.launch()
    ExternalProcess.monitor_all()