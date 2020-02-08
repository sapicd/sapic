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


class Properties(object):

    def __init__(self, fileName):
        self.fileName = fileName
        self.properties = {}

    def __getDict(self, strName, dictName, value):

        if(strName.find('.') > 0):
            k = strName.split('.')[0]
            dictName.setdefault(k, {})
            return self.__getDict(strName[len(k)+1:], dictName[k], value)
        else:
            dictName[strName] = value
            return

    def getProperties(self):
        try:
            pro_file = open(self.fileName, 'Ur')
            for line in pro_file.readlines():
                line = line.strip().replace('\n', '')
                if line.find("#") != -1:
                    line = line[0:line.find('#')]
                if line.find('=') > 0:
                    strs = line.split('=')
                    strs[1] = line[len(strs[0])+1:]
                    self.__getDict(
                        strs[0].strip(),
                        self.properties, strs[1].strip()
                    )
        except Exception, e:
            raise e
        else:
            pro_file.close()
        return self.properties
