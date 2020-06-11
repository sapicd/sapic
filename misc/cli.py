#!/usr/bin/env python
# -*- coding: utf8 -*-

__version__ = "0.1.0"
__author__ = "staugur"

from json import loads, dumps
from base64 import b64encode
from sys import version_info
from os import getenv
from os.path import abspath, basename, isfile

PY2 = version_info[0] == 2

if PY2:
    import urllib2
    from urllib import urlencode
else:
    import urllib.request as urllib2
    from urllib.parse import urlencode


def main(parser):
    args = parser.parse_args()
    api = args.picbed_url
    token = args.picbed_token
    album = args.album or ""
    if not api:
        api = getenv("picbed_cli_apiurl")
        if not api:
            print("Please enter picbed api url")
            return
    if not api.endswith("/api/upload"):
        api = "{}/api/upload".format(api.rstrip("/"))
    result = []
    style = args.style
    files = args.file
    for f in files:
        filepath = abspath(f)
        filename = basename(filepath)
        if isfile(filepath):
            with open(filepath, "rb") as fp:
                stream = fp.read()
            req = urllib2.Request(
                api,
                data=urlencode(dict(
                    picbed=b64encode(stream),
                    filename=filename,
                    album=album,
                    origin="cli/{}".format(__version__),
                )).encode("utf-8"),
                headers=dict(Authorization="LinkToken {}".format(token)),
            )
            res = urllib2.urlopen(req)
            res = loads(res.read())
            result.append(res)
    if result:
        if style == "typora":
            print("Upload Success:")
            for res in result:
                if res and isinstance(res, dict) and res.get("code") == 0:
                    print(res["src"])
        else:
            for res in result:
                print(dumps(res))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--picbed-url", required=True,
                        help="The picbed upload api url")
    parser.add_argument("-t", "--picbed-token", help="Your LinkToken")
    parser.add_argument("-a", "--album", help="Set image album")
    parser.add_argument("-s", "--style", help="upload result output style",
                        default="default", choices=["default", "typora"])
    parser.add_argument("file", nargs="+", help="Local file")
    main(parser)
