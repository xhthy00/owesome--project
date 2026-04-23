<script lang="ts" setup>
import { computed, ref } from 'vue'
import { Compass, DataAnalysis, Histogram, TrendCharts, Top } from '@element-plus/icons-vue'

const props = defineProps<{
  hasDatasource: boolean
}>()

const emit = defineEmits<{
  pickQuestion: [text: string]
  send: [text: string]
}>()

const recommended = computed(() => [
  { icon: DataAnalysis, label: '查看销售额最高的前 10 个产品' },
  { icon: Histogram, label: '按月份统计本年订单数量' },
  { icon: TrendCharts, label: '近 30 天活跃用户的趋势是怎样的？' },
  { icon: Compass, label: '帮我分析一下哪个地区的客户转化率最高' },
])

const onPick = (q: string) => emit('pickQuestion', q)
const quickText = ref('')
const canQuickSend = computed(() => !!quickText.value.trim())
const onQuickSend = () => {
  if (!canQuickSend.value) return
  emit('send', quickText.value.trim())
  quickText.value = ''
}
const onQuickKeydown = (evt: Event) => {
  const e = evt as KeyboardEvent
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.isComposing) {
    e.preventDefault()
    onQuickSend()
  }
}
void props
</script>

<template>
  <div class="chat-default">
    <div class="hero">
      <div class="logo-wrap">
        <div class="logo-glow" />
        <div class="logo">
          <span class="letter">A</span>
        </div>
      </div>
      <h1 class="title">{{ $t('chat.welcome_title') }}</h1>
      <p class="subtitle">{{ $t('chat.welcome_subtitle') }}</p>
    </div>

    <div class="recommend">
      <div class="quick-input">
        <el-input
          v-model="quickText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          resize="none"
          :placeholder="$t('chat.input_placeholder')"
          @keydown="onQuickKeydown"
        />
        <button class="quick-send" :disabled="!canQuickSend" @click="onQuickSend">
          <el-icon :size="16"><Top /></el-icon>
        </button>
      </div>

      <div class="recommend-title">
        <span class="dot" />
        猜你想问
      </div>
      <div class="recommend-grid">
        <button
          v-for="(q, idx) in recommended"
          :key="idx"
          class="rec-card"
          @click="onPick(q.label)"
        >
          <el-icon :size="16" class="rec-icon">
            <component :is="q.icon" />
          </el-icon>
          <span class="rec-text">{{ q.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.chat-default {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px 24px;
  min-height: 0;

  .hero {
    text-align: center;
    margin-bottom: 36px;

    .logo-wrap {
      position: relative;
      width: 64px;
      height: 64px;
      margin: 0 auto 18px;
    }

    .logo-glow {
      position: absolute;
      inset: -12px;
      background: radial-gradient(circle at center, rgba(22, 119, 255, 0.25), transparent 70%);
      filter: blur(8px);
    }

    .logo {
      position: absolute;
      inset: 0;
      border-radius: 18px;
      background: linear-gradient(135deg, #1677ff 0%, #69b1ff 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 6px 18px rgba(22, 119, 255, 0.35);

      .letter {
        font-size: 28px;
        font-weight: 800;
        color: #fff;
        letter-spacing: -1px;
      }
    }

    .title {
      font-size: 32px;
      line-height: 40px;
      font-weight: 700;
      color: #101828;
      margin: 0 0 10px;
      background: linear-gradient(135deg, #101828 0%, #1677ff 100%);
      -webkit-background-clip: text;
      background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .subtitle {
      max-width: 560px;
      margin: 0 auto;
      color: #667085;
      font-size: 14px;
      line-height: 22px;
    }
  }

  .recommend {
    width: min(1100px, 83.3333%);

    .quick-input {
      position: relative;
      margin-bottom: 16px;
      background: #fff;
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 12px 12px 52px;
      box-shadow: 0 6px 20px rgba(16, 24, 40, 0.06);

      &:focus-within {
        border-color: var(--el-color-primary);
        box-shadow: 0 0 0 4px rgba(22, 119, 255, 0.12), 0 6px 20px rgba(22, 119, 255, 0.1);
      }

      :deep(.el-textarea__inner) {
        border: none;
        box-shadow: none !important;
        padding: 0;
        background: transparent;
        font-size: 14px;
        line-height: 22px;
      }

      .quick-send {
        position: absolute;
        right: 12px;
        bottom: 12px;
        width: 34px;
        height: 34px;
        border: none;
        border-radius: 9px;
        background: #f0f3f8;
        color: #98a2b3;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.15s ease;

        &:hover:enabled {
          background: var(--el-color-primary-dark-2);
        }

        &:enabled {
          background: var(--el-color-primary);
          color: #fff;
        }

        &:disabled {
          cursor: not-allowed;
        }
      }
    }

    .recommend-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: #475467;
      font-weight: 600;
      margin-bottom: 12px;

      .dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--el-color-primary);
      }
    }

    .recommend-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }

    .rec-card {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 14px 16px;
      background: #fff;
      border: 1px solid var(--border-color);
      border-radius: 12px;
      cursor: pointer;
      text-align: left;
      transition: all 0.15s ease;
      font-size: 13.5px;
      line-height: 20px;
      color: #344054;

      .rec-icon {
        color: var(--el-color-primary);
        flex-shrink: 0;
      }

      .rec-text {
        flex: 1;
      }

      &:hover {
        border-color: var(--el-color-primary-light-5);
        background: var(--el-color-primary-light-9);
        box-shadow: 0 4px 12px rgba(22, 119, 255, 0.08);
        transform: translateY(-1px);
      }
    }
  }
}
</style>
