#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
    cli.py
    ~~~~~~

    The command-line client for picbed.

    :copyright: (c) 2020 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = "0.2.0"
__author__ = "staugur <staugur@saintic.com>"

import argparse
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

allowed_style = ("default", "typora")


def style_type(value):
    if value not in allowed_style:
        try:
            if not value or "." not in value:
                raise ValueError
            mod, func = value.split(".")
            module = __import__(mod)
        except ValueError:
            raise argparse.ArgumentTypeError("invalid style type")
        except ImportError:
            raise argparse.ArgumentTypeError("not found module: " + mod)
        else:
            if not hasattr(module, func):
                raise argparse.ArgumentTypeError("not found func: " + func)
    return value


def main(parser):
    args = parser.parse_args()
    api = args.picbed_url
    token = args.picbed_token
    album = args.album or ""
    title = args.desc or ""
    expire = args.expire or 0
    if not api:
        api = getenv("picbed_cli_apiurl")
        if not api:
            print("Please enter picbed api url")
            return
    if not api.endswith("/api/upload"):
        api = "{}/api/upload".format(api.rstrip("/"))
    if not token:
        token = getenv("picbed_cli_apitoken")
        if not token:
            print("Please enter picbed api LinkToken")
            return
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
                    title=title,
                    expire=expire,
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
        elif "." in style:
            mod, func = style.split(".")
            getattr(__import__(mod), func)(result)
        else:
            print(dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="picbed cli",
        description='More docs to https://picbed.rtfd.vip/usage.html#cli-py',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-u", "--picbed-url",
                        help=(
                            "The picbed upload api url.\n"
                            "Or use environment variable: picbed_cli_apiurl"
                        ))
    parser.add_argument("-t", "--picbed-token",
                        help=(
                            "The picbed LinkToken.\n"
                            "Or use environment variable: picbed_cli_apitoken"
                        ))
    parser.add_argument("-a", "--album", help="Set image album")
    parser.add_argument("-d", "--desc", help="Set image title(description)")
    parser.add_argument("-e", "--expire", type=int,
                        help="Set image expire(seconds)")
    parser.add_argument("-s", "--style", default="default", type=style_type,
                        help=(
                            "The upload result output style: { %s }.\n"
                            "Or, allows the use of \"module.function\" to "
                            "customize the output style."
                        ) % ", ".join(allowed_style))
    parser.add_argument("file", nargs="+", help="Local file")
    main(parser)
