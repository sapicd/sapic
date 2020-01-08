# -*- coding: utf-8 -*-
"""
    utils._compat
    ~~~~~~~~~~~~~

    A module providing tools for cross-version compatibility.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from sys import version_info

PY2 = version_info[0] == 2

if PY2:  # pragma: nocover

    def iteritems(d):
        return d.iteritems()

    def itervalues(d):
        return d.itervalues()

    text_type = unicode
    string_types = (str, unicode)
    integer_types = (int, long)
    from urllib import urlencode
    from urllib2 import Request, urlopen

else:  # pragma: nocover

    def iteritems(d):
        return iter(d.items())

    def itervalues(d):
        return iter(d.values())

    text_type = str
    string_types = (str,)
    integer_types = (int, )
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
