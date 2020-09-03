.. _picbed-modules:

==============
Picbed Modules
==============

下面仅列出可能有用的部分

钩子管理类
-------------

.. autoclass:: libs.hook.HookManager
    :members:
    :undoc-members:

通用方法
----------

.. currentmodule:: utils.tool

.. data:: logger

.. data:: err_logger

.. data:: ALLOWED_EXTS

    默认允许上传的图片后缀

.. autofunction:: rsp

.. autofunction:: md5

.. autofunction:: sha1

.. autofunction:: sha256

.. autofunction:: hmac_sha256

.. autofunction:: get_current_timestamp

.. autofunction:: create_redis_engine

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
    :members:

适用Web环境的方法
-----------------

.. currentmodule:: utils.web

.. data:: rc

    redis连接实例

    .. versionadded:: 1.9.0

.. autodecorator:: login_required

.. autodecorator:: anonymous_required

.. autodecorator:: apilogin_required

.. autodecorator:: admin_apilogin_required

.. autofunction:: get_site_config

.. autofunction:: set_site_config

.. autofunction:: sendmail

.. autofunction:: make_email_tpl

.. autofunction:: try_proxy_request

.. autofunction:: set_page_msg

.. autofunction:: get_page_msg

.. autofunction:: push_user_msg

.. autofunction:: get_push_msg

.. autofunction:: get_user_ip

.. autofunction:: has_image

.. autofunction:: guess_filename_from_url

.. autofunction:: allowed_suffix

.. autoclass:: Base64FileStorage
    :members:
    :undoc-members:

.. autoclass:: ImgUrlFileStorage
    :members:
    :undoc-members:

异常类
--------

.. currentmodule:: utils.exceptions

.. autoexception:: PicbedError

.. autoexception:: ApiError

.. autoexception:: PageError
