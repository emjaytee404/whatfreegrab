#!/usr/bin/env python2

import getpass
import os
import random
import shutil
import sys
import urllib2
import zipfile

import cStringIO as StringIO
import ConfigParser

SCRIPT_DIR  = os.path.dirname(os.path.realpath(sys.argv[0]))
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'wfg.cfg')


def setup():
    print MESSAGES['welcome']

    pause()

    print "First, let's setup the WhatFreeGrab dependencies."
    print ""

    try:
        print "Installing/updating Requests module: ",
        download_module("requests", "https://github.com/kennethreitz/requests/archive/v2.0.1.zip")
        import requests
    except:
        print MESSAGES['module_error'] % "requests"
        raise

    try:
        print "Installing/updating WhatAPI module: ",
        download_module('whatapi', 'https://github.com/emjaytee404/whatapi/archive/stable.zip')
        from whatapi import whatapi
    except:
        print MESSAGES['module_error'] % "whatapi"
        raise

    pause()

    if not sys.getfilesystemencoding().upper() in ('UTF-8', 'MBCS'):
        print MESSAGES['filesystem_error']
        sys.exit(1)

    config = ConfigParser.RawConfigParser()

    while True:

        print "Next we will need your What.CD username and password."

        username = raw_input("Enter your username: ")
        if not username:
            continue

        password = getpass.getpass("Enter your password (will not be shown on screen): ")
        if not password:
            continue

        print ""
        print "Attempting login...",

        try:
            whatapi.WhatAPI(username=username, password=password).logout()
        except whatapi.LoginException:
            print "failed. :("
            print "Let's try again."
            continue
        except:
            raise
        else:
            print "success!"
            break

    config.add_section('login')
    config.set('login', 'username', username)
    config.set('login', 'password', password)

    pause()

    while True:

        print "The directory where the script downloads torrent files is called the target."

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
                print ""
                print "Looks good."
                break
        else:
            print ""
            print "Looks good."
            break

    config.add_section('download')
    config.set('download', 'target', target)

    pause()

    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

    print MESSAGES['config-finished'] % CONFIG_FILE

    pause()

    script_path = os.path.join(SCRIPT_DIR, "WFG.py")

    print MESSAGES['skip-downloads'] % script_path

    pause()

    rand_minutes = str(random.randrange(60)).zfill(2)

    print MESSAGES['cron'] % (rand_minutes, script_path)

    pause()

    print MESSAGES['finished']

    pause("Press ENTER to exit. ")

def pause(msg="Press ENTER to continue... "):
    print ""
    raw_input(msg)
    print "-" * 80
    print ""

def download_module(module_name, module_url):

    print "downloading... ",

    data = urllib2.urlopen(module_url)
    data = StringIO.StringIO(data.read())
    data = zipfile.ZipFile(data)

    filelist = data.namelist()
    root     = filelist[0]
    dirname  = os.path.join(root, module_name)
    filelist = [filename for filename in filelist if filename.startswith(dirname)]

    cwd = os.getcwd()

    os.chdir(SCRIPT_DIR)

    print "extracting... ",

    data.extractall(members=filelist)

    # Remove previous version first.
    shutil.rmtree(module_name, ignore_errors=True)

    os.rename(dirname, module_name)
    os.rmdir(root)

    os.chdir(cwd)

    print "done!"


MESSAGES = {}

MESSAGES['welcome'] = """
WhatFreeGrab Setup
------------------

Hey there! This little program will help you setup WhatFreeGrab.

You will need your What.CD username and password, so have those ready.
"""
MESSAGES['module_error'] = """
An error ocurred trying to download/extract the '%s' module.
Please try to run this script again.
"""
MESSAGES['filesystem_error'] = """
Your filesystem encoding is not able to handle Unicode filenames. This means
that files containing non-Latin characters in their names will not be able to
be saved. Please read your system's documentation for changing the encoding
used to save filenames.

On Linux, this is accomplished by changing your locale to one supporting UTF-8.
"""
MESSAGES['config-finished'] = """
Configuration file created successfully.

You can re-run this setup file at any time to change the settings, or you can
change the values directly. The config file is located at:

%s
"""
MESSAGES['skip-downloads'] = """
If you want to run the script and have it record all current freeleech torrents
without downloading any of them you can do so like this:

python2 %s --skip-downloads
"""
MESSAGES['cron'] = """
If you plan on adding the script to your cron file, consider using the
following line:

%s * * * * python2 %s

The minutes field above has been selected at random.

Spreading the scheduling like this helps avoid having a bunch of scripts all
hitting the server every hour on the hour.
"""
MESSAGES['finished'] = """
The setup is now complete.

Enjoy!
"""

if __name__ == '__main__':
    try:
        setup()
    except KeyboardInterrupt:
        print "Setup process had been cancelled."
    except:
        print "Unhandled error has occurred:"
        raise
