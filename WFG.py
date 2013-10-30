#!/usr/bin/env python
# -*- coding: utf-8 -*-

import htmlentitydefs
import os
import re
import string
import sys
import time

import ConfigParser
import cPickle as pickle

SCRIPT_DIR  = os.path.dirname(os.path.realpath(sys.argv[0]))
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'wfg.cfg')
STATE_FILE  = os.path.join(SCRIPT_DIR, 'wfg.dat')

try:
    import requests
except ImportError:
    def download_requests():

        print "It seems you are missing the required 'requests' module."
        print "Press ENTER to automatically download and extract this module."
        print "Press Ctrl+C if you wish to cancel and install it manually."
        try:
            raw_input()
        except KeyboardInterrupt:
            print "You must install the 'requests' module before attempting to run this script."
            print "Visit http://docs.python-requests.org/en/latest/user/install/ for instructions."
            sys.exit(1)

        import urllib2
        import zipfile

        import cStringIO as StringIO

        requests_zip = "https://github.com/kennethreitz/requests/zipball/master"

        data = urllib2.urlopen(requests_zip)
        data = StringIO.StringIO(data.read())
        data = zipfile.ZipFile(data)

        filelist = data.namelist()
        root = filelist[0]
        dirname = os.path.join(root, 'requests')
        filelist = [filename for filename in filelist if filename.startswith(dirname)]

        data.extractall(SCRIPT_DIR, filelist)

        os.rename(dirname, 'requests')
        os.rmdir(root)

        print "Extraction complete. Will attempt to continue..."

    download_requests()
    import requests

class WFGException(Exception): pass

class WhatFreeGrab(object):

    NAME = "WhatFreeGrab"
    VER  = "0.1"

    INVALID_CHARS = r'\/:*<>|?"'
    HTML_RE = re.compile("&#?\w+;")

    headers = {
        'Content-type': "application/x-www-form-urlencoded",
        'Accept-Charset': "utf-8",
        'User-Agent': "%s: %s" % (NAME, VER)
    }

    loginpage   = "https://what.cd/login.php"
    ajaxpage    = "https://what.cd/ajax.php"
    torrentpage = "https://what.cd/torrents.php"

    def __init__(self, config_file, state_file):

        self.config_file = config_file
        self.state_file = state_file

        self.config = ConfigParser.ConfigParser()
        self.config.read(self.config_file)

        self.username = self.config.get('login', 'username')
        self.password = self.config.get('login', 'password')
        self.target   = self.config.get('download', 'target')

        if not (self.username and self.password):
            self.quit("No username or password specified in configuration.")

        if not self.target:
            self.quit("No target directory specified in configuration.")

        if not os.path.exists(self.target):
            os.makedirs(self.target)

        self.template_music = self.config.get('download', 'template_music')
        self.template_other = self.config.get('download', 'template_other')

        if not '${torrentId}' in (self.template_music and self.template_other):
            self.quit("Naming templates in configuration MUST contain ${torrentId}")

        self.template_music = string.Template(self.template_music)
        self.template_other = string.Template(self.template_other)

        self.authkey = None
        self.passkey = None

        self.session = requests.session()

        self.session.headers = WhatFreeGrab.headers

        if os.path.exists(self.state_file):
            self.state = pickle.load(open(self.state_file))
        else:
            self.state = {}

        if 'cookies' in self.state:
            self.session.cookies = self.state['cookies']
        else:
            self._login()

        self.history = self.state.get('history', set())

        try:
            self._get_accountinfo()
        except WFGException: # Expired/invalid cookie?
            try:
                self._login()
            except WFGException:
                self.quit("Unable to login. Check your configuration.")
            else:
                self._get_accountinfo()

    def _get_accountinfo(self):

        response = self.request('index')

        self.authkey = response['authkey']
        self.passkey = response['passkey']

    def _login(self):

        data = {'username': self.username,
                'password': self.password,
                'keeplogged': 1,
                'login': "Login"
        }

        r = self.session.post(WhatFreeGrab.loginpage, data=data, allow_redirects=False)
        if r.status_code != 302:
            raise WFGException

        self.state['cookies'] = self.session.cookies
        self.save_state()

    def create_filename(self, torrent):

        if 'artist' in torrent:
            filename = self.template_music.substitute(torrent).strip()
        else:
            filename = self.template_other.substitute(torrent).strip()

        filename = self.unescape_html(filename)
        filename = self.remove_invalid_chars(filename)

        filename = "%s.torrent" % filename

        return filename

    def download_torrents(self, torrent_list):

        for torrent in torrent_list:

            filename = self.create_filename(torrent)
            filepath = os.path.join(self.target, filename)

            # This is an ugly hack, but it'll have to do for now
            if len(filepath) > 247: # 247 + 9 for .torrent suffix = 255
                filepath = filepath[:123] + "~" + filepath[-123:]

            torrent_id = torrent['torrentId']

            if torrent_id in self.history:
                print "%s - torrent has been previously downloaded" % torrent_id
                continue

            if os.path.exists(filepath):
                print "%s - torrent already exists: '%s'" % (torrent_id, filename)
                continue

            data = self.get_torrent(torrent_id)
            if not data:
                print "%s - unable to download torrent" % torrent_id
                continue

            with open(filepath, 'wb') as f:
                f.write(data)

            print "%s - saved to '%s'" % (torrent_id, filename)

            self.history.add(torrent_id)

            self.state['history'] = self.history
            self.save_state()

    def get_freeleech(self, page):

        response = self.request('browse', **{'freetorrent': 1, 'page': page})

        torrent_list = []

        for group in response['results']:
            if 'torrents' in group:
                for torrent in group.pop('torrents'):
                    torrent_list.append(dict(group.items() + torrent.items()))
            else:
                torrent_list.append(group)

        return response['pages'], torrent_list

    def get_torrent(self, torrent_id):

        params = {'action': 'download', 'id': torrent_id}

        if self.authkey:
            params['authkey'] = self.authkey
            params['torrent_pass'] = self.passkey

        r = self.session.get(WhatFreeGrab.torrentpage, params=params, allow_redirects=False)

        time.sleep(2) # Be nice.

        if r.status_code == 200 and 'application/x-bittorrent' in r.headers['content-type']:
            return r.content

        return None

    def quit(self, msg):

        print "Exiting: %s" % msg

        sys.exit(0)

    def request(self, action, **kwargs):

        params = {'action': action}

        if self.authkey:
            params['auth'] = self.authkey

        params.update(kwargs)

        r = self.session.get(WhatFreeGrab.ajaxpage, params=params, allow_redirects=False)

        time.sleep(2) # Be nice.

        try:
            json_response = r.json()
            if json_response['status'] != "success":
                raise WFGException
            return json_response['response']
        except ValueError:
            raise WFGException

    def remove_invalid_chars(self, item):

        item = "".join(c in WhatFreeGrab.INVALID_CHARS and " " or c for c in item)
        item = " ".join(item.split())
        return item

    def run(self):

        page = 1
        while True:

            pages, torrent_list = self.get_freeleech(page)

            self.download_torrents(torrent_list)

            page +=1
            if page > pages:
                break

        self.quit("Process complete")

    def save_state(self):

        pickle.dump(self.state, open(self.state_file, 'w'))

    # http://effbot.org/zone/re-sub.htm#unescape-html
    def unescape_html(self, text):
        def fixup(m):
            text = m.group(0)
            if text[:2] == "&#":
                # character reference
                try:
                    if text[:3] == "&#x":
                        return unichr(int(text[3:-1], 16))
                    else:
                        return unichr(int(text[2:-1]))
                except ValueError:
                    pass
            else:
                # named entity
                try:
                    text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
                except KeyError:
                    pass
            return text # leave as is
        return WhatFreeGrab.HTML_RE.sub(fixup, text)

if __name__ == '__main__':
    WhatFreeGrab(config_file=CONFIG_FILE, state_file=STATE_FILE).run()
