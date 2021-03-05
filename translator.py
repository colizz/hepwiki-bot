from logger import _logger

class DummyTranslator(object):
    """A dummy translator object that naively returns the input text itself"""

    def __init__(self, **kwargs):
        self.make_banner = kwargs['make_banner'] if 'make_banner' in kwargs else True
        self.do_post = kwargs['do_post'] if 'do_post' in kwargs else True
        self.support_mkdown = kwargs['support_mkdown'] if 'support_mkdown' in kwargs else True
    
    def launch(self, text, target_lang=None, source_lang=None):
        _logger.info('Using dummy translator.')
        if self.do_post:
            text = self.post(text)
        return text

    def post(self, text):
        banner = '> Passes a dummy translator\n\n' if self.make_banner else ''
        return banner + fix_broken_mkdown(text)


class DeepLTranslator(DummyTranslator):
    """A DeepL translator object"""

    def __init__(self, use_api=False, selenium_configs={}, **kwargs):
        super(DeepLTranslator, self).__init__(**kwargs)
        if use_api == True:
            raise NotImplemented("Sorry but I haven't got chance to subscribe a DeepL API...")
        ## Will use selenium to mimic the behavior that fetches translation script from DeepL free website
        self.selenium_configs = selenium_configs
    
    def launch(self, text, target_lang, source_lang):
        """Takes the text, the targeted language and original language type, then returns the translated text"""
        self.target_lang = target_lang
        self.source_lang = source_lang
        
        if not self.support_mkdown:
            ## Do translation: should preserve the weblink, and avoid '|' bug...
            text_target = self.launch_selenium(text.replace('/','\/').replace('|','#V#')).replace('#V#', '|')
        else:
            ## Split the code block env if support_mkdown==True
            import re
            rgx_cb = re.compile(r'(```(?:(?!```)(?:.|\r|\n))*```)')
            cb = re.findall(rgx_cb, text)
            cb_idx = list(range(len(cb)))
            text_clean = re.sub(rgx_cb, lambda match: f'#B{str(cb_idx.pop(0)).zfill(5)}#', text)

            text_clean_target = self.launch_selenium(text_clean.replace('/','\/').replace('|','#V#')).replace('#V#', '|')
            if self.target_lang in []: # translate the code block for specific target lang
                cb_target = []
                for block in cb:
                    block_sp = block.split('\n')
                    block_target = self.launch_selenium('\n'.join(block_sp[1:-1]).replace('/','\/').replace('|','#V#')).replace('#V#', '|')
                    block_target = '\n'.join([block_sp[0], block_target, block_sp[-1]])
                    cb_target.append(block_target)
            else:
                cb_target = list(cb)
            ## Stitch the context and code blocks
            text_target = text_clean_target
            for idx in range(len(cb)):
                text_target = re.sub(f'(#B{str(idx).zfill(5)}#)((?:.|\r|\n)*)\\1', '\n\n\\1\\2', text_target) # fix a DeepL bug: duplicate index
                text_target = re.sub(f'#B{str(idx).zfill(5)}#', cb_target[idx], text_target)

        if self.do_post:
            text_target = self.post(text_target)
        return text_target


    def launch_selenium(self, text):
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from urllib.parse import quote
        import time

        chrome_options = webdriver.ChromeOptions()
        ## Use http_proxy due to inaccessibility to DeepL from node13...
        if 'http_proxy' in self.selenium_configs:
            chrome_options.add_argument('--proxy-server=%s' % self.selenium_configs['http_proxy'])
        if 'headless' in self.selenium_configs and self.selenium_configs['headless']:
            chrome_options.add_argument('--headless')
        driver = webdriver.Chrome(chrome_options=chrome_options)

        if (self.target_lang.lower(), self.source_lang.lower()) not in [('en','zh'), ('zh','en')]:
            raise RuntimeError('Only en->zh or zh->en translation is supported.')
        
        ## Preprocess on text
        _logger.debug(f'Text to be translated: {text}')
        quoted_text = quote(text)

        ## Translate
        _logger.debug('Launch DeepL website...')
        driver.get(f'https://www.deepl.com/translator#{self.source_lang.lower()}/{self.target_lang.lower()}/{quoted_text}')

        ## Fetch the translated script
        text_target = ''
        try:
            for _ in range(30): ## wait for 30 sec
                time.sleep(1)
                element = WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.lmt__side_container--target textarea')))
                if element.get_attribute('value') != '':
                    text_target = element.get_attribute('value')
                    break
            if text_target is None:
                raise RuntimeError('unknown error')
        except Exception as e:
            _logger.warning(f'DeepL translation timeout... Error: {e}')

        ## Quit the browser before leaving
        _logger.debug(f'Translations done (raw): {text_target}')
        _logger.debug(f'Quitting DeepL...')
        driver.quit()

        return text_target

    def post(self, text):
        text = fix_broken_mkdown(text)
        if self.make_banner:
            lines = text.split('\n')
            banner = """> [!NOTE|style:flat]\n> *This page is auto-translated by [DeepL](https://www.deepl.com/)*.\n"""
            if lines[0].replace(' ','')[0] == '#' and lines[0].replace(' ','')[1] != '#':
                lines.insert(1, '\n'+banner) # insert the banner after the subject
            else:
                lines.insert(0, banner)
            text = '\n'.join(lines)

        if self.target_lang == 'zh':
            text = add_spaces_zh(text)
        
        return text

def fix_broken_mkdown(text):
    """Fix some broken markdown syntax"""

    import re
    ## Fix broken ![] syntax
    text = re.sub('([\n\s]+[!！]?)[ ]*[\[【](.*)[\]】][ ]*[\(（](.*)[\)）]', '\g<1>[\g<2>](\g<3>)', text)
    text = re.sub('[\[【](.*)[\]】][ ]*[\(（](.*)[\)）]', '[\g<1>](\g<2>)', text)
    ## Fix web link containing ../
    text = re.sub('\.\.\.[ ]?\/', '../', text)
    ## Fix broken <!-- syntax
    text = re.sub('\<\![ ]+\-\-', '<!--', text)
    ## Fix duplicated ` sign
    text = re.sub('(?<!`)``(?!`)', '`', text)
    ## Fix duplicated index in enumerate env that appears at the end of the previous line
    text = re.sub('(\d+\.)([>\s\n\t]+)\\1', '\\2\\1', text)
    ## Fix broken link
    for link in re.findall(r'\[.+\]\((.+)\)', text):
        if ' ' in link:
            link_fix = link.replace(' ','')
            text = text.replace(link, link_fix)
    return text

def add_spaces_zh(text):
    """Fast implementation of adding spaces between zh and en characters (exclude punctuation)"""

    import re
    text = re.sub('([\u4e00-\u9fff])([0-9|a-z|A-Z|\u00A0-\u024f])', '\g<1> \g<2>', text)
    text = re.sub('([0-9|a-z|A-Z|\u00A0-\u024f])([\u4e00-\u9fff])', '\g<1> \g<2>', text)
    return text
