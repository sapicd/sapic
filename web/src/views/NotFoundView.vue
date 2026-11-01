<template>
  <div class="auth">
    <el-card class="auth__card" style="text-align: center">
      <el-result icon="warning" title="404" sub-title="页面不存在">
        <template #extra>
          <router-link :to="{ name: 'upload' }">
            <el-button type="primary">返回首页</el-button>
          </router-link>
        </template>
      </el-result>
    </el-card>
  </div>
</template>
