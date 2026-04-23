<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, Download, FullScreen } from '@element-plus/icons-vue'

const props = defineProps<{
  title: string
  html: string
}>()

const showDialog = ref(false)

const safeTitle = computed(() => props.title || 'Report')

const copyHtml = async () => {
  try {
    await navigator.clipboard.writeText(props.html || '')
    ElMessage.success('HTML 已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

const downloadHtml = () => {
  const blob = new Blob([props.html || ''], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${safeTitle.value || 'report'}.html`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="report-preview">
    <div class="report-toolbar">
      <span class="report-title">{{ safeTitle }}</span>
      <div class="actions">
        <button class="tool-btn" @click="copyHtml">
          <el-icon :size="13"><CopyDocument /></el-icon>
          <span>复制HTML</span>
        </button>
        <button class="tool-btn" @click="downloadHtml">
          <el-icon :size="13"><Download /></el-icon>
          <span>下载</span>
        </button>
        <button class="tool-btn primary" @click="showDialog = true">
          <el-icon :size="13"><FullScreen /></el-icon>
          <span>展开</span>
        </button>
      </div>
    </div>
    <iframe
      class="report-iframe"
      :srcdoc="html"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
    />
    <el-dialog v-model="showDialog" :title="safeTitle" width="85%" top="5vh" append-to-body>
      <iframe
        class="report-iframe full"
        :srcdoc="html"
        sandbox="allow-scripts"
        referrerpolicy="no-referrer"
      />
    </el-dialog>
  </div>
</template>

<style scoped lang="less">
.report-preview {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.report-toolbar {
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 10px;
  border-bottom: 1px solid var(--border-color-light);
  background: #f8fafc;
}

.report-title {
  font-size: 12px;
  font-weight: 600;
  color: #344054;
}

.actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tool-btn {
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  height: 24px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #475467;
  background: #fff;
  cursor: pointer;

  &.primary {
    color: var(--el-color-primary);
  }
}

.report-iframe {
  width: 100%;
  height: 360px;
  border: 0;

  &.full {
    height: 72vh;
  }
}
</style>
