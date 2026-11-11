<script setup>
import { computed, reactive, ref, watch } from 'vue'

import { api, errorMessage } from '@/api/client'

defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'uploaded'])

//: 预览窗口与导出尺寸；两者比例一致，裁剪结果与预览所见即所得。
const VIEW = 240
const OUTPUT = 320
const MAX_ZOOM = 3

const fileInput = ref(null)
const picture = ref(null)
const imageUrl = ref('')
const zoom = ref(1)
const offset = reactive({ x: 0, y: 0 })
const dragging = ref(null)
const uploading = ref(false)

const baseScale = computed(() => {
  if (!picture.value) return 1
  return Math.max(
    VIEW / picture.value.naturalWidth,
    VIEW / picture.value.naturalHeight,
  )
})

//: 图片按「铺满裁剪框」的比例定位，拖拽与缩放都叠加在中心对齐之上。
const display = computed(() => {
  if (!picture.value) return { width: VIEW, height: VIEW, left: 0, top: 0 }
  const scale = baseScale.value * zoom.value
  const width = picture.value.naturalWidth * scale
  const height = picture.value.naturalHeight * scale
  return {
    width,
    height,
    left: (VIEW - width) / 2 + offset.x,
    top: (VIEW - height) / 2 + offset.y,
  }
})

function clampOffsets() {
  const maxX = Math.max(0, (display.value.width - VIEW) / 2)
  const maxY = Math.max(0, (display.value.height - VIEW) / 2)
  offset.x = Math.min(maxX, Math.max(-maxX, offset.x))
  offset.y = Math.min(maxY, Math.max(-maxY, offset.y))
}

watch(zoom, clampOffsets)

function pickFile() {
  fileInput.value?.click()
}

function onFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件')
    return
  }
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = URL.createObjectURL(file)
  const next = new Image()
  next.onload = () => {
    picture.value = next
    zoom.value = 1
    offset.x = 0
    offset.y = 0
  }
  next.src = imageUrl.value
}

function onPointerDown(event) {
  if (!picture.value) return
  dragging.value = {
    x: event.clientX,
    y: event.clientY,
    offsetX: offset.x,
    offsetY: offset.y,
  }
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function onPointerMove(event) {
  if (!dragging.value) return
  offset.x = dragging.value.offsetX + (event.clientX - dragging.value.x)
  offset.y = dragging.value.offsetY + (event.clientY - dragging.value.y)
  clampOffsets()
}

function onPointerUp() {
  dragging.value = null
}

function reset() {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = ''
  picture.value = null
  zoom.value = 1
  offset.x = 0
  offset.y = 0
}

function close() {
  emit('update:modelValue', false)
}

async function confirm() {
  if (!picture.value) {
    ElMessage.warning('请先选择图片')
    return
  }
  const canvas = document.createElement('canvas')
  canvas.width = OUTPUT
  canvas.height = OUTPUT
  const context = canvas.getContext('2d')
  const ratio = OUTPUT / VIEW
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, OUTPUT, OUTPUT)
  context.drawImage(
    picture.value,
    display.value.left * ratio,
    display.value.top * ratio,
    display.value.width * ratio,
    display.value.height * ratio,
  )

  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, 'image/png'),
  )
  if (!blob) {
    ElMessage.error('裁剪失败，请重试')
    return
  }

  const form = new FormData()
  form.append('file', new File([blob], 'avatar.png', { type: 'image/png' }))
  uploading.value = true
  try {
    const data = await api.post('/auth/avatar', { form })
    emit('uploaded', data)
    close()
  } catch (error) {
    ElMessage.error(errorMessage(error, '头像上传失败'))
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="上传头像"
    width="360px"
    :close-on-click-modal="false"
    @update:model-value="close"
    @closed="reset"
  >
    <div class="avatar-crop">
      <div
        class="avatar-crop__viewport"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      >
        <img
          v-if="imageUrl"
          class="avatar-crop__image"
          :src="imageUrl"
          :style="{
            width: `${display.width}px`,
            height: `${display.height}px`,
            left: `${display.left}px`,
            top: `${display.top}px`,
          }"
          alt=""
          draggable="false"
        />
        <button v-else type="button" class="avatar-crop__empty" @click="pickFile">
          点击选择图片
        </button>
      </div>

      <el-slider
        v-model="zoom"
        :min="1"
        :max="MAX_ZOOM"
        :step="0.05"
        :disabled="!imageUrl"
      />

      <input
        ref="fileInput"
        type="file"
        accept="image/*"
        class="avatar-crop__input"
        @change="onFileChange"
      />

      <div class="form-actions">
        <el-button size="small" @click="pickFile">
          {{ imageUrl ? '重新选择' : '选择图片' }}
        </el-button>
        <span class="form-actions__meta">拖动调整位置，滑块缩放</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button
        type="primary"
        :loading="uploading"
        :disabled="!imageUrl"
        @click="confirm"
      >
        保存头像
      </el-button>
    </template>
  </el-dialog>
</template>
