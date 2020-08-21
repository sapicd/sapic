.. _picbed-modules:

==============
Picbed Modules
==============

钩子管理类
------------

.. autoclass:: libs.hook.HookManager
    :members:
    :undoc-members:

本地存储类
----------

.. autoclass:: libs.storage.RedisStorage
    :members:
    :undoc-members:

通用方法
---------

.. currentmodule:: utils.tool

.. data:: logger

.. autofunction:: rsp

.. autofunction:: get_current_timestamp

.. autofunction:: parse_valid_comma

.. autofunction:: parse_valid_verticaline

.. autofunction:: parse_valid_colon

.. autofunction:: is_true

.. autofunction:: generate_random

.. autofunction:: check_url

.. autofunction:: check_ip

.. autofunction:: slash_join

.. autofunction:: gen_ua

.. autofunction:: try_request

.. autofunction:: is_all_fail

.. autofunction:: bleach_html

.. autofunction:: is_valid_verion

.. autoclass:: Mailbox

适用Web环境的方法
-----------------

.. automodule:: utils.web
    :members:
    :undoc-members:

异常
--------

.. currentmodule:: utils.exceptions

.. autoexception:: PicbedError

.. autoexception:: ApiError

.. autoexception:: PageError
