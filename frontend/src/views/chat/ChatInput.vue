<script lang="ts" setup>
import { ref, computed } from 'vue'
import { Top, Loading } from '@element-plus/icons-vue'

const props = defineProps<{
  disabled?: boolean
  placeholder?: string
  canSendExtraCheck?: boolean
}>()

const emit = defineEmits<{
  send: [text: string]
}>()

const text = ref('')
const inputRef = ref()

const canSend = computed(
  () => !!text.value.trim() && !props.disabled && (props.canSendExtraCheck ?? true)
)

const onSend = () => {
  if (!canSend.value) return
  emit('send', text.value.trim())
  text.value = ''
}

const onKeydown = (evt: Event) => {
  const e = evt as KeyboardEvent
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.isComposing) {
    e.preventDefault()
    onSend()
  }
}

const focus = () => inputRef.value?.focus?.()

defineExpose({
  setText: (v: string) => {
    text.value = v
    focus()
  },
})
</script>

<template>
  <div class="chat-input-panel">
    <div class="input-card" :class="{ disabled }" @click="focus">
      <el-input
        ref="inputRef"
        v-model="text"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        resize="none"
        class="input-area"
        :placeholder="placeholder || $t('chat.input_placeholder')"
        :disabled="disabled"
        @keydown="onKeydown"
      />

      <div class="input-toolbar">
        <div class="left">
          <span class="hint">Enter 发送 / Shift + Enter 换行</span>
        </div>
        <div class="right">
          <button
            class="send-btn"
            :class="{ enabled: canSend, loading: disabled }"
            :disabled="!canSend"
            @click.stop="onSend"
          >
            <el-icon v-if="disabled" :size="16" class="is-loading"><Loading /></el-icon>
            <el-icon v-else :size="16"><Top /></el-icon>
          </button>
        </div>
      </div>
    </div>
    <div class="footer-tip">DB-GPT 风格 · 输出可能存在错误，请核实关键数据。</div>
  </div>
</template>

<style lang="less" scoped>
.chat-input-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 6px 20px 12px;

  .input-card {
    width: min(1100px, 83.3333%);
    background: #fff;
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 10px 12px 8px;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
    box-shadow: 0 2px 8px rgba(16, 24, 40, 0.04);

    &:hover {
      border-color: var(--el-color-primary-light-5);
    }

    &:focus-within {
      border-color: var(--el-color-primary);
      box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.12), 0 2px 8px rgba(16, 24, 40, 0.04);
    }

    &.disabled {
      background: #fafbfc;
    }

    .input-area {
      :deep(.el-textarea__inner) {
        background: transparent;
        border: none;
        box-shadow: none !important;
        padding: 0 4px;
        font-size: 14px;
        line-height: 22px;
        color: #1f2329;
        resize: none;
        min-height: 44px;

        &::placeholder {
          color: #98a2b3;
        }
      }
    }

    .input-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 6px;

      .left {
        .hint {
          font-size: 11.5px;
          color: #98a2b3;
        }
      }

      .right {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .send-btn {
        width: 34px;
        height: 34px;
        border-radius: 8px;
        border: none;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #f0f3f8;
        color: #98a2b3;
        transition: all 0.15s ease;

        &.enabled {
          background: var(--el-color-primary);
          color: #fff;
          box-shadow: 0 4px 10px rgba(22, 119, 255, 0.32);

          &:hover {
            background: var(--el-color-primary-dark-2);
          }
        }

        &.loading {
          background: var(--el-color-primary);
          color: #fff;
        }

        &:disabled {
          cursor: not-allowed;
        }
      }
    }
  }

  .footer-tip {
    font-size: 11px;
    color: #98a2b3;
  }
}
</style>
