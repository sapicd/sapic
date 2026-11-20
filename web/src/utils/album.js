//: 系统相册（收纳匿名上传）在库里叫「公共相册」，管理员也改不了，它只是展示名；
//: 这里按 ``is_system`` 标记换成当前语言的名称。用户自建相册与「默认相册」的名字
//: 是用户数据，一律原样显示。
import { t } from '@/i18n'

export function albumName(album) {
  if (!album) return ''
  return album.is_system ? t('albums.systemAlbum') : album.name || ''
}
