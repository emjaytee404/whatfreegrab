#!/usr/bin/env python
# -*- coding: utf-8 -*-

import htmlentitydefs
import logging
import logging.handlers
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
LOCK_FILE   = os.path.join(SCRIPT_DIR, 'wfg.pid')
LOG_FILE    = os.path.join(SCRIPT_DIR, 'wfg.log')

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

        requests_zip = "https://github.com/kennethreitz/requests/archive/v2.0.1.zip"

        data = urllib2.urlopen(requests_zip)
        data = StringIO.StringIO(data.read())
        data = zipfile.ZipFile(data)

        filelist = data.namelist()
        root = filelist[0]
        dirname = os.path.join(root, 'requests')
        filelist = [filename for filename in filelist if filename.startswith(dirname)]

        cwd = os.getcwd()

        os.chdir(SCRIPT_DIR)

        data.extractall(members=filelist)

        os.rename(dirname, 'requests')
        os.rmdir(root)

        os.chdir(cwd)

        print "Extraction complete. Will attempt to continue..."

    download_requests()
    import requests

class WFGException(Exception): pass

class WhatFreeGrab(object):

    NAME  = "WhatFreeGrab"
    VER   = "0.1"
    IDENT = "%s v%s" % (NAME, VER)

    INVALID_CHARS = r'\/:*<>|?"'
    HTML_RE = re.compile("&#?\w+;")

    headers = {
        'Content-type': "application/x-www-form-urlencoded",
        'Accept-Charset': "utf-8",
        'User-Agent': IDENT
    }

    loginpage   = "https://what.cd/login.php"
    ajaxpage    = "https://what.cd/ajax.php"
    torrentpage = "https://what.cd/torrents.php"

    defaults = {
        'log_level': "INFO",
        'max_torrents': "3000",
        'quiet': "false",
        'template_music': "${artist} - ${groupName} (${format} ${encoding}) [${torrentId}]",
        'template_other': "${groupName} [${torrentId}]"
    }

    timeformat = "%Y-%m-%d %H:%M:%S"

    log_size = 10 * 1024 * 1024 # 10MB

    def __init__(self, config_file, state_file, lock_file, log_file):

        self.config_file = config_file
        self.state_file  = state_file
        self.lock_file   = lock_file
        self.log_file    = log_file

        self.instance = SingleInstance(self.lock_file)

        self.start_time = time.time()

        self.session = requests.session()
        self.session.headers = WhatFreeGrab.headers

        self.config = ConfigParser.SafeConfigParser(WhatFreeGrab.defaults)

        if not os.path.exists(self.config_file):
            self._first_run()

        self.config.read(self.config_file)

        # This is necessary because otherwise we get 'NoSectionError' even if
        # the value is set in the defaults.
        try:
            self.config.add_section('output')
        except ConfigParser.DuplicateSectionError:
            pass

        self.quiet = self.config.getboolean('output', 'quiet')
        self.log_level = self.config.get('output', 'log_level')

        numeric_level = getattr(logging, self.log_level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % self.log_level)

        self.log = logging.getLogger()
        self.log.setLevel(logging.INFO)
        handler = logging.handlers.RotatingFileHandler(filename=log_file, maxBytes=WhatFreeGrab.log_size, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt=WhatFreeGrab.timeformat)
        handler.setFormatter(formatter)
        self.log.addHandler(handler)

        self.log.info("%s starting up", WhatFreeGrab.IDENT)

        self.message(WhatFreeGrab.IDENT)
        self.message("-" * len(WhatFreeGrab.IDENT))
        self.message("Startup time: %s" % time.strftime(WhatFreeGrab.timeformat, time.localtime(self.start_time)))

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

        if os.path.exists(self.state_file):
            self.state = pickle.load(open(self.state_file, 'rb'))
        else:
            self.state = {}

        if 'cookies' in self.state:
            self.session.cookies = self.state['cookies']
        else:
            self._login()

        self.authkey = None
        self.passkey = None

        try:
            self._get_accountinfo()
        except WFGException: # Expired/invalid cookie?
            try:
                self._login()
            except WFGException:
                self.quit("Unable to login. Check your configuration.", error=True)
            else:
                self._get_accountinfo()

        self.history = self.state.get('history', set())
        self.torrent_list = []

        self.counter = {}
        for key in 'total', 'downloaded', 'skipped', 'exists', 'error':
            self.counter[key] = 0

    def _first_run(self):
        import getpass
        import random

        config = ConfigParser.SafeConfigParser()
        rand_minutes = str(random.randrange(60)).zfill(2)
        script_path = os.path.join(SCRIPT_DIR, sys.argv[0])

        message = """
Hey there! It looks like you are running this script for the first time.

Let's go ahead and create a new configuration file."""

        print message

        while True:

            print "\nFirst we will need your What.CD username and password."

            username = raw_input("Enter your username: ")
            if not username:
                continue

            password = getpass.getpass("Enter your password (will not be shown on screen): ")
            if not password:
                continue

            print "\nGot it. The script will try to login with this info...",

            self.username = username
            self.password = password

            try:
                self._login()
            except WFGException:
                print "failed. :("
                print "Let's try again."
                continue
            else:
                print "success!"
                break

        config.add_section('login')
        config.set('login', 'username', username)
        config.set('login', 'password', password)

        while True:

            print "\nThe directory where the script downloads .torrent files is called the target."

            target = raw_input("Enter target: ")

            full_target = os.path.realpath(os.path.expanduser(target))

            if not os.path.exists(full_target):
                try:
                    os.makedirs(full_target)
                except:
                    print "Unable to access the '%s' directory." % target
                    print "Let's try again."
                    continue
                else:
                    print "\nLooks good."
                    break
            else:
                print "\nLooks good."
                break

        config.add_section('download')
        config.set('download', 'target', full_target)

        print "\nFinally, do you want to use the same filename format that Yoink! used?"
        print "See README for the default used otherwise, as well as other formats available."
        if raw_input("Use Yoink! filename format? [Y/N] ").lower().startswith("y"):
            config.set('download', 'template_music', "${torrentId}. ${yoinkFormat}")
            config.set('download', 'template_other', "${torrentId} ${yoinkFormat}")
        else:
            # Use defaults, no need to save them in config.
            pass

        with open(self.config_file, 'w') as f:
            config.write(f)

        message = """
Configuration file created successfully.

-------------------------------------------------------------------------------

If you plan on adding the script to your cron file, consider using the
following line:

%s * * * * python %s

The minutes field above has been randomly-determined.

Spreading the scheduling like this helps avoid having a bunch of scripts all
hitting the server every hour on the hour.

Enjoy!
""" % (rand_minutes, script_path)

        print message
        raw_input("Press ENTER to continue... ")

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

        if hasattr(self, 'state'):
            self.state['cookies'] = self.session.cookies
            self.save_state()

    def add_to_history(self, torrent_id):

        self.history.add(torrent_id)

        self.state['history'] = self.history
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

            if torrent_id in self.history:
                self.counter['skipped'] += 1
                continue

            filename = self.create_filename(torrent)
            filepath = os.path.join(self.target, filename)

            # This is an ugly hack, but it'll have to do for now
            if len(filepath) > 247: # 247 + 9 for .torrent suffix = 255
                filepath = filepath[:123] + "~" + filepath[-123:]

            if os.path.exists(filepath):
                self.log.info("File exists for torrent ID %s: '%s'", torrent_id, filepath)
                self.message("*", newline=False)
                self.add_to_history(torrent_id)
                self.counter['exists'] += 1
                continue

            data = self.get_torrent(torrent_id)
            if not data:
                self.log.info("Error downloading torrent ID %s", torrent_id)
                self.message("!", newline=False)
                self.counter['error'] += 1
                continue

            with open(filepath, 'wb') as f:
                f.write(data)

            self.log.info("Downloaded torrent ID %s: '%s'", torrent_id, filepath)
            self.message("+", newline=False)
            self.counter['downloaded'] += 1

            self.add_to_history(torrent_id)

    def get_freeleech(self, page, custom_params):

        params = {'freetorrent': 1, 'page': page}

        params.update(custom_params)

        response = self.request('browse', **params)

        for group in response['results']:
            if 'torrents' in group:
                for torrent in group.pop('torrents'):
                    yoink_format = {
                        'yoinkFormat':
                        "%s - %s - %s (%s - %s - %s)" %
                        (group['artist'][:50], group['groupYear'], group['groupName'][:50],
                        torrent['media'], torrent['format'], torrent['encoding'])
                    }
                    self.torrent_list.append(dict(group.items() + torrent.items() + yoink_format.items()))
            else:
                yoink_format = {'yoinkFormat': group['groupName'][:100]}
                self.torrent_list.append(dict(group.items() + yoink_format.items()))

        return response['pages']

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
        if error:
            log = self.log.critical
        else:
            log = self.log.info

        exec_time = "Script finished in: %s" % self.human_time(time.time() - self.start_time)

        log(msg)
        log(exec_time)
        log("-" * 40)

        self.message(msg, error)
        self.message(exec_time)
        sys.exit(int(error))

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

        self.message("Building torrent list:", newline=False)
        self.log.info("Building torrent list")

        for params in self.filters:

            page = pages = 1
            while True:

                # Sometimes the request() call inside get_freeleech() will
                # throw an exception because the site is busy. In that case we
                # just skip this page and we'll catch up on the next run.
                try:
                    pages = self.get_freeleech(page, params)
                except WFGException:
                    pass

                self.message(".", newline=False)

                if len(self.torrent_list) > self.max_torrents:
                    self.message("")
                    self.quit("Number of torrents found exceeds maximum limit of %s." % self.max_torrents, error=True)

                page +=1
                if page > pages:
                    break

        self.counter['total'] = len(self.torrent_list)

        self.log.info("%s torrents found", self.counter['total'])

        self.message("")
        self.message("%s torrents found" % self.counter['total'])


        self.log.info("Downloading torrents")
        self.download_torrents()

        self.log.info("%s skipped", self.counter['skipped'])
        self.log.info("%s exist", self.counter['exists'])
        self.log.info("%s errors", self.counter['error'])
        self.log.info("%s downloaded", self.counter['downloaded'])

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
    WhatFreeGrab(config_file=CONFIG_FILE, state_file=STATE_FILE, lock_file=LOCK_FILE, log_file=LOG_FILE).run()
