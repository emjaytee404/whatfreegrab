#!/usr/bin/env python2

import getpass
import os
import random
import sys
import urllib2
import zipfile

import cStringIO as StringIO
import ConfigParser

SCRIPT_DIR  = os.path.dirname(os.path.realpath(sys.argv[0]))
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'wfg.cfg')


def setup():
    print MESSAGES['welcome']

    try:
        import requests
    except ImportError:
        try:
            download_module("requests", "https://github.com/kennethreitz/requests/archive/v2.0.1.zip")
            import requests
        except:
            print MESSAGES['module_error'] % "requests"
            raise

    try:
        from whatapi import whatapi
    except ImportError:
        try:
            download_module('whatapi', 'https://github.com/emjaytee404/whatapi/archive/stable.zip')
            from whatapi import whatapi
        except:
            print MESSAGES['module_error'] % "whatapi"
            raise

    config = ConfigParser.RawConfigParser()

    while True:

        print "\nFirst we will need your What.CD username and password."

        username = raw_input("Enter your username: ")
        if not username:
            continue

        password = getpass.getpass("Enter your password (will not be shown on screen): ")
        if not password:
            continue

        print "\nGot it. The script will try to login with this info...",

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

    rand_minutes = str(random.randrange(60)).zfill(2)
    script_path = os.path.join(SCRIPT_DIR, "WFG.py")

    print MESSAGES['cron'] % (rand_minutes, script_path)

    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

    print MESSAGES['finished'] % CONFIG_FILE

    raw_input("Press ENTER to exit.")

def download_module(module_name, module_url):
    print MESSAGES['module_missing'] % module_name
    try:
        raw_input()
    except KeyboardInterrupt:
        print MESSAGES['module_cancelled'] % module_name
        sys.exit(1)

    data = urllib2.urlopen(module_url)
    data = StringIO.StringIO(data.read())
    data = zipfile.ZipFile(data)

    filelist = data.namelist()
    root     = filelist[0]
    dirname  = os.path.join(root, module_name)
    filelist = [filename for filename in filelist if filename.startswith(dirname)]

    cwd = os.getcwd()

    os.chdir(SCRIPT_DIR)

    data.extractall(members=filelist)

    os.rename(dirname, module_name)
    os.rmdir(root)

    os.chdir(cwd)


MESSAGES = {}

MESSAGES['welcome'] = """
Hey there! This little program will attempt to help you setup WhatFreeGrab.

You will need your What.CD username and password, so have those ready.

First, let's setup the WFG dependencies.
"""
MESSAGES['module_missing'] = """
It seems you are missing the '%s' module.
Press ENTER to automatically download and extract this module.
Press Ctrl+C if you wish to cancel and install it manually.
"""
MESSAGES['module_cancelled'] = """
You must install the '%s module before trying to run this script.
"""
MESSAGES['module_error'] = """
An error ocurred trying to download/extract the '%s' module.
Please try to run this script again.
"""
MESSAGES['cron'] = """
-------------------------------------------------------------------------------

If you plan on adding the script to your cron file, consider using the
following line:

%s * * * * python %s

The minutes field above has been selected at random.

Spreading the scheduling like this helps avoid having a bunch of scripts all
hitting the server every hour on the hour.
"""
MESSAGES['finished'] = """
Configuration file created successfully.

You can re-run this setup file at any time to change the settings, or you can
change the values directly. The config file is located at:

%s

Enjoy!

--
Em
"""

if __name__ == '__main__':
    try:
        setup()
    except:
        print "Unhandled error has occurred:"
        raise
