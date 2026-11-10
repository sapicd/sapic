# -*- coding: utf-8 -*-
"""
    utils._compat
    ~~~~~~~~~~~~~

    A module providing tools for cross-version compatibility.

    :copyright: (c) 2019 by staugur.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

from sys import version_info
from os import getenv


def iteritems(d):
    return iter(d.items())


def itervalues(d):
    return iter(d.values())


text_type = str
string_types = (str,)
integer_types = (int,)
from urllib.parse import urlencode, urlparse, urlsplit, parse_qs
from urllib.request import Request, urlopen
import configparser as ConfigParser
import _thread as thread


def is_true(value):
    if value and value in (True, "True", "true", "on", 1, "1", "yes"):
        return True
    return False


class Properties(object):
    def __init__(self, filename, from_env=False):
        #: 读取配置文件
        self.filename = filename
        #: 使用get方法查询无果时，是否从环境变量读取
        self.from_env = from_env
        self.properties = {}
        self._getProperties()

    def __getDict(self, str_name, dict_name, value):

        if str_name.find(".") > 0:
            k = str_name.split(".")[0]
            dict_name.setdefault(k, {})
            return self.__getDict(str_name[len(k) + 1 :], dict_name[k], value)
        else:
            dict_name[str_name] = value
            return

    def _getProperties(self):
        try:
            pro_file = open(self.filename, "r")
            for line in pro_file.readlines():
                line = line.strip().replace("\n", "")
                if line.find("#") != -1:
                    line = line[0 : line.find("#")]
                if line.find("=") > 0:
                    strs = line.split("=")
                    strs[1] = line[len(strs[0]) + 1 :]
                    self.__getDict(
                        strs[0].strip(), self.properties, strs[1].strip()
                    )
        except IOError:
            pass
        else:
            pro_file.close()
        return self.properties

    def get(self, k, default_value=None):
        if not self.properties:
            self._getProperties()
        v = self.properties.get(k)
        if self.from_env is True:
            if not v:
                v = getenv(k)
        return v or default_value
