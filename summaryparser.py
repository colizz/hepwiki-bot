import os, re
from translator import DeepLTranslator as Translator
from logger import _logger

class SummaryParser(object):

    def __init__(self):
        pass

    @staticmethod
    def check_consistency(path):
        """Check if zh-hans/SUMMARY.md and en/SUMMARY.md structure is consistent"""

        text, dir_check, stc_check = {}, {}, {}
        for lang in ('zh-hans', 'en'):
            with open(os.path.join(path, lang, 'SUMMARY.md')) as (f):
                text[lang] = f.read()
                dir_check[lang] = re.findall('([ ]*)\\*([ ]*)\\[.+\\]([ ]*)\\((.+)\\)', text[lang])
                stc_check[lang] = re.findall('\n[ ]*', text[lang])
        else:
            return dir_check['zh-hans'] == dir_check['en'] and stc_check['zh-hans'] == stc_check['en']

    @staticmethod
    def produce_target_summary_patch(path, target_lang, patch):
        """If one of zh-hans/SUMMARY.md and en/SUMMARY.md is changed, modify the others
            - patch: a git diff patch (best with -U0 structure) that manifest the changes of one file
        """

        def dual(lang):
            return 'en' if lang == 'zh' else 'zh'

        def gb_format(lang):
            """The Gitbook format of lang"""
            return 'zh-hans' if lang == 'zh' else lang

        modif_lang = dual(target_lang)
        with open(os.path.join(path, gb_format(target_lang), 'SUMMARY.md')) as (f):
            text = f.read()
            parsed = re.findall('[ ]*\*[ ]*\[(.+)\]\((.+)\)', text)
            target_title_dic = {fpath:title for title, fpath in parsed} # the file -> title dictionary from the target lang
        _logger.debug(f'Read original patch: {patch}')
        patch_newfpath_dic = {title:fpath for title, fpath in re.findall('\+[ ]*\*[ ]*\[(.+)\]\((.+)\)', patch)}
        patch_oldfpath_dic = {title:fpath for title, fpath in re.findall('\-[ ]*\*[ ]*\[(.+)\]\((.+)\)', patch)}
        patch_orig = patch
        lines = patch.split('\n')
        n_trans, trans_list = 0, []
        for i, line in enumerate(lines):
            parsed = re.findall('([\+\- ])[ ]*\*[ ]*\[(.+)\]\((.+)\)', line)
            if len(parsed) > 0:
                mark, title, fpath = parsed[0][0], parsed[0][1], parsed[0][2]
                _logger.debug(f'Paserd mark: {mark}, title: {title}, fpath: {fpath}')
                if mark in ['-', ' ']:
                    ## The path must exists in the unmodified file. Replace the title using the file->title dic from the target lang
                    lines[i] = line.replace(title, target_title_dic[fpath])
                else: # marker=='+'
                    if title in patch_newfpath_dic and title in patch_oldfpath_dic:
                        ## Title is unchanged but the file path changes (file is moved) -> restore the old title then
                        lines[i] = line.replace(title, target_title_dic[patch_oldfpath_dic[title]])
                    else:
                        trans_list.append(title)
                        lines[i] = line.replace(title, f"$TRANS{str(n_trans).zfill(5)}")
                        n_trans += 1

        patch_mod = '\n'.join(lines)
        patch_mod = patch_mod.replace(gb_format(modif_lang) + '/', gb_format(target_lang) + '/')
        
        ## Do translation if necessary
        if len(trans_list) > 0:
            trans = Translator(selenium_configs={'http_proxy':'127.0.0.1:8090', 'headless':True}, make_banner=False)
            res_trans = trans.launch(('\n'.join(trans_list)), target_lang=target_lang, source_lang=modif_lang)
            res_trans = trans.post(res_trans)
            res_trans_list = res_trans.split('\n')
            for i in range(n_trans):
                patch_mod = patch_mod.replace(f"$TRANS{str(i).zfill(5)}", res_trans_list[i])
        return patch_mod
