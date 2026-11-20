<script setup>
import { computed } from 'vue'

import { LOCALES, locale, setLocale } from '@/i18n'

const current = computed(
  () => LOCALES.find((item) => item.code === locale.value) || LOCALES[0],
)
</script>

<template>
  <el-dropdown trigger="click" @command="setLocale">
    <button type="button" class="locale-switch" :title="$t('common.language')">
      <el-icon><Switch /></el-icon>
      <span>{{ current.short }}</span>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="item in LOCALES"
          :key="item.code"
          :command="item.code"
          :disabled="item.code === current.code"
        >
          {{ item.label }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>
