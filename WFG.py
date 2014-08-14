#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import htmlentitydefs
import os
import re
import string
import sys
import time

import ConfigParser
import cPickle as pickle

import requests
import whatapi

class WFGException(Exception): pass

class WhatFreeGrab(object):

    IDENT = "WhatFreeGrab v0.1"

    INVALID_CHARS = r'\/:*<>|?"'
    HTML_RE = re.compile("&#?\w+;")

    SCRIPT_DIR  = os.path.dirname(os.path.realpath(sys.argv[0]))
    CONFIG_FILE = os.path.join(SCRIPT_DIR, 'wfg.cfg')
    STATE_FILE  = os.path.join(SCRIPT_DIR, 'wfg.dat')
    LOCK_FILE   = os.path.join(SCRIPT_DIR, 'wfg.pid')

    defaults = {
        'max_torrents': "3000",
        'quiet': "false",
        'template_music': "${artist} - ${groupName} (${format} ${encoding}) [${torrentId}]",
        'template_other': "${groupName} [${torrentId}]"
    }

    def __init__(self, config_file=None, state_file=None, lock_file=None):

        self.config_file = config_file or WhatFreeGrab.CONFIG_FILE
        self.state_file  = state_file or WhatFreeGrab.STATE_FILE
        self.lock_file   = lock_file or WhatFreeGrab.LOCK_FILE

        self.instance = SingleInstance(self.lock_file)

        self.start_time = time.time()

        self.config = ConfigParser.RawConfigParser(WhatFreeGrab.defaults)

        try:
            self.config.read(self.config_file)
        except:
            self.quit("Unable to read configuration file.", error=True)

        # This is necessary because otherwise we get 'NoSectionError' even if
        # the value is set in the defaults.
        try:
            self.config.add_section('output')
        except ConfigParser.DuplicateSectionError:
            pass

        self.quiet = self.config.getboolean('output', 'quiet')

        self.message(WhatFreeGrab.IDENT)
        self.message("-" * len(WhatFreeGrab.IDENT))
        self.message("Startup time: %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time)))

        self.username = self.config.get('login', 'username')
        self.password = self.config.get('login', 'password')

        if not (self.username and self.password):
            self.quit("No username or password specified in configuration.", error=True)

        self.target = self.config.get('download', 'target')

        if not self.target:
            self.quit("No target directory specified in configuration.", error=True)

        self.target = os.path.realpath(os.path.expanduser(self.target))

        if not os.path.exists(self.target):
            os.makedirs(self.target)

        self.max_torrents = self.config.getint('download', 'max_torrents')

        self.template_music = self.config.get('download', 'template_music')
        self.template_other = self.config.get('download', 'template_other')

        if not '${torrentId}' in (self.template_music and self.template_other):
            self.quit("Naming templates in configuration MUST contain ${torrentId}", error=True)

        self.template_music = string.Template(self.template_music)
        self.template_other = string.Template(self.template_other)

        # Look out! No default values available from here on.
        self.config._defaults.clear()
        self.filters = []
        for section in self.config.sections():
            if section.startswith("filter-"):
                self.filters.append(dict(self.config.items(section)))

        if not self.filters:
            self.filters = [{}]

        try:
            self.state = pickle.load(open(self.state_file, 'rb'))
        except:
            self.state = {}

        cookies = self.state.get('cookies')
        try:
            self.what = whatapi.WhatAPI(config_file=self.config_file, cookies=cookies)
        except whatapi.whatapi.LoginException:
            self.quit("Unable to login. Check your configuration.", error=True)
        self.state['cookies'] = self.what.session.cookies
        self.save_state()

        if not 'history' in self.state:
            self.state['history'] = set()

        self.torrent_list = []

        self.counter = {}
        for key in 'total', 'downloaded', 'skipped', 'exists', 'error':
            self.counter[key] = 0

    def add_to_history(self, torrent_id):
        self.state['history'].add(torrent_id)
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

    def download_torrents(self):

        self.message("Legend: (+) downloaded (*) file exists (!) error")

        for torrent in self.torrent_list:

            torrent_id = torrent['torrentId']

            if torrent_id in self.state['history']:
                self.counter['skipped'] += 1
                continue

            filename = self.create_filename(torrent)
            filepath = os.path.join(self.target, filename)

            # This is an ugly hack, but it'll have to do for now
            if len(filepath) > 247: # 247 + 9 for .torrent suffix = 255
                filepath = filepath[:123] + "~" + filepath[-123:]

            if os.path.exists(filepath):
                self.message("* %s" % filepath)
                self.add_to_history(torrent_id)
                self.counter['exists'] += 1
                continue

            data = self.what.get_torrent(torrent_id)
            if not data:
                self.message("! %s" % filepath)
                self.counter['error'] += 1
                continue

            with open(filepath, 'wb') as f:
                f.write(data)

            self.message("+ %s" % filepath)
            self.counter['downloaded'] += 1

            self.add_to_history(torrent_id)

    def get_freeleech(self, page, custom_params):

        params = {'freetorrent': 1, 'page': page}

        params.update(custom_params)

        response = self.what.request('browse', **params)

        for group in response['response']['results']:
            if 'torrents' in group:
                for torrent in group.pop('torrents'):
                    self.torrent_list.append(dict(group.items() + torrent.items()))
            else:
                self.torrent_list.append(dict(group.items()))

        return response['response']['pages']

    def human_time(self, t):
        # Yes, I know about datetime.datetime, but this was fun.
        m, s = divmod(t, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)

        out = ""
        if h: out += "%d hours, " % h
        if m: out += "%d minutes, " % m
        out += "%.2f seconds" % s

        return out

    def message(self, msg, error=False, newline=True):
        if (not self.quiet) or (error):
            if newline:
                print msg
            else:
                print msg,
            sys.stdout.flush()

    def quit(self, msg, error=False):

        exec_time = "Script finished in: %s" % self.human_time(time.time() - self.start_time)

        self.message(msg, error)
        self.message(exec_time)
        sys.exit(int(error))

    def remove_invalid_chars(self, item):

        item = "".join(c in WhatFreeGrab.INVALID_CHARS and " " or c for c in item)
        item = " ".join(item.split())
        return item

    def run(self):

        self.message("Building torrent list:", newline=False)

        for params in self.filters:

            page = pages = 1
            while True:

                # Sometimes the request() call inside get_freeleech() will
                # throw an exception because the site is busy. In that case we
                # just skip this page and we'll catch up on the next run.
                try:
                    pages = self.get_freeleech(page, params)
                except whatapi.whatapi.RequestException:
                    pass

                self.message(".", newline=False)

                if len(self.torrent_list) > self.max_torrents:
                    self.message("")
                    self.quit("Number of torrents found exceeds maximum limit of %s." % self.max_torrents, error=True)

                page +=1
                if page > pages:
                    break

        self.counter['total'] = len(self.torrent_list)

        self.message("")
        self.message("%s torrents found" % self.counter['total'])

        self.download_torrents()

        self.message("")
        self.message("%s skipped" % self.counter['skipped'])
        self.message("%s exist" % self.counter['exists'])
        self.message("%s errors" % self.counter['error'])
        self.message("%s downloaded" % self.counter['downloaded'])
        self.message("")
        self.quit("Process complete.")

    def save_state(self):

        pickle.dump(self.state, open(self.state_file, 'wb'))

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

# https://github.com/pycontribs/tendo/blob/master/tendo/singleton.py
class SingleInstance:

    def __init__(self, lockfile):
        import sys
        self.initialized = False
        self.lockfile = lockfile

        if sys.platform == 'win32':
            try:
                # file already exists, we try to remove (in case previous execution was interrupted)
                if os.path.exists(self.lockfile):
                    os.unlink(self.lockfile)
                self.fd = os.open(self.lockfile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except OSError:
                type, e, tb = sys.exc_info()
                if e.errno == 13:
                    print "Another instance is already running, quitting."
                    sys.exit(-1)
                print e.errno
                raise
        else: # non Windows
            import fcntl
            self.fp = open(self.lockfile, 'w')
            try:
                fcntl.lockf(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                print "Another instance is already running, quitting."
                sys.exit(-1)
        self.initialized = True

    def __del__(self):
        import sys
        import os
        if not self.initialized:
            return
        try:
            if sys.platform == 'win32':
                if hasattr(self, 'fd'):
                    os.close(self.fd)
                    os.unlink(self.lockfile)
            else:
                import fcntl
                fcntl.lockf(self.fp, fcntl.LOCK_UN)
                # os.close(self.fp)
                if os.path.isfile(self.lockfile):
                    os.unlink(self.lockfile)
        except Exception as e:
            print "Unloggable error: %s" % e
            sys.exit(-1)

if __name__ == '__main__':
    WhatFreeGrab().run()
