# -*- coding: utf-8 -*-
"""
    hooks.pic2webp
    ~~~~~~~~~~~~~~

    Transfer jpg/png picture to webp

    :copyright: (c) 2023 by blunt.
    :license: BSD 3-Clause, see LICENSE for more details.
"""

__version__ = "0.0.1"
__author__ = "blunt"
__description__ = "将JPG/PNG图片转为webp格式"
__state__ = 'disabled'
__catalog__ = "processor"

from PIL import Image
from io import BytesIO

from utils.tool import logger

def upimg_stream_processor(stream, suffix):
    if suffix != ".jpg" and suffix != ".png":
        return

    logger.debug("pic2webp start, suffix is %s" % suffix)
    webp_stream = BytesIO()
    pic = Image.open(BytesIO(stream))
    pic = pic.convert('RGB')
    pic.save(webp_stream, 'webp', optimize=True, quality=75)
    logger.info("pic2webp transfer success! new suffix is .webp")

    return {'code': 0,
            'data': {'stream': webp_stream.getvalue()},
            'suffix': '.webp'
            }
