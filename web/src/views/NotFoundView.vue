<template>
  <div class="auth">
    <el-card class="auth__card" style="text-align: center">
      <el-result icon="warning" title="404" :sub-title="$t('notFound.title')">
        <template #extra>
          <router-link :to="{ name: 'upload' }">
            <el-button type="primary">{{ $t('notFound.backHome') }}</el-button>
          </router-link>
        </template>
      </el-result>
    </el-card>
  </div>
</template>
