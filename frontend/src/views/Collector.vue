<template>
  <div class="collector">
    <h2 class="page-title">数据采集</h2>

    <div class="grid">
      <!-- 股票基础信息 -->
      <div class="card">
        <div class="card-title">股票基础信息</div>
        <p style="color: #666; margin: 12px 0; font-size: 14px;">采集A股所有股票基础信息列表</p>
        <button class="btn btn-primary" :disabled="store.running" @click="startBasic">
          开始采集
        </button>
      </div>

      <!-- 实时行情 -->
      <div class="card">
        <div class="card-title">实时行情</div>
        <p style="color: #666; margin: 12px 0; font-size: 14px;">采集当日盘口实时数据</p>
        <button class="btn btn-primary" :disabled="store.running" @click="startRealtime">
          开始采集
        </button>
      </div>
    </div>

    <!-- 历史K线 -->
    <div class="card">
      <div class="card-title">历史K线数据</div>
      <div class="grid" style="margin-top: 16px;">
        <div class="form-group">
          <label>开始日期</label>
          <input type="date" v-model="klineForm.start_date">
        </div>
        <div class="form-group">
          <label>结束日期</label>
          <input type="date" v-model="klineForm.end_date">
        </div>
        <div class="form-group">
          <label>并发线程</label>
          <input type="number" v-model.number="klineForm.threads" min="1" max="50">
        </div>
      </div>
      <button class="btn btn-primary" :disabled="store.running" @click="startKline">
        开始采集
      </button>
    </div>

    <!-- 增量采集 -->
    <div class="card">
      <div class="card-title">增量采集</div>
      <div class="grid" style="margin-top: 16px;">
        <div class="form-group">
          <label>采集最近N天</label>
          <input type="number" v-model.number="incrementalForm.days" min="1" max="365">
        </div>
      </div>
      <button class="btn btn-primary" :disabled="store.running" @click="startIncremental">
        开始采集
      </button>
    </div>

    <!-- 进度 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">采集进度</span>
        <span :class="['badge', store.running ? 'badge-running' : 'badge-idle']">
          {{ store.running ? '运行中' : '空闲' }}
        </span>
      </div>
      <!-- 停止按钮（修复 BUG-066） -->
      <button v-if="store.running" class="btn btn-danger" @click="stopTask" style="margin-bottom: 12px;">
        停止任务
      </button>
      <div class="progress-bar" style="margin: 16px 0;">
        <div class="progress-fill" :style="{ width: store.progressPercent + '%' }"></div>
      </div>
      <div class="log-container">
        <div v-for="(log, i) in store.logs" :key="i" :class="['log-entry', log.type]">
          [{{ log.time }}] {{ log.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, onMounted, onUnmounted } from 'vue'
import { useCollectorStore } from '../stores/collector'
import { collectBasic, collectKline, collectIncremental, collectRealtime } from '../api'

const store = useCollectorStore()

const klineForm = reactive({
  start_date: '2024-01-01',
  end_date: '2024-12-31',
  threads: 10
})

const incrementalForm = reactive({
  days: 30
})

let statusTimer = null

onMounted(() => {
  store.initWebSocket()
  store.refreshStatus()
  // 每 3 秒刷新一次状态，确保 UI 同步
  statusTimer = setInterval(() => store.refreshStatus(), 3000)
})

onUnmounted(() => {
  store.closeWebSocket()
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
})

const startBasic = async () => {
  try {
    const resp = await collectBasic()
    if (resp.data.success) {
      store.startTask('basic')
    }
  } catch (e) {
    store.addLog('error', '启动失败: ' + e.message)
  }
}

const startKline = async () => {
  try {
    const resp = await collectKline(klineForm)
    if (resp.data.success) {
      store.startTask('kline')
    }
  } catch (e) {
    store.addLog('error', '启动失败: ' + e.message)
  }
}

const startIncremental = async () => {
  try {
    const resp = await collectIncremental(incrementalForm)
    if (resp.data.success) {
      store.startTask('incremental')
    }
  } catch (e) {
    store.addLog('error', '启动失败: ' + e.message)
  }
}

const startRealtime = async () => {
  try {
    const resp = await collectRealtime()
    if (resp.data.success) {
      store.startTask('realtime')
    }
  } catch (e) {
    store.addLog('error', '启动失败: ' + e.message)
  }
}

// 停止任务（修复 BUG-066）
const stopTask = () => {
  store.stopRunningTask()
}
</script>

<style scoped>
.page-title {
  font-size: 24px;
  margin-bottom: 20px;
  color: #333;
}
.btn-danger {
  background: #e74c3c;
  color: white;
}
.btn-danger:hover {
  background: #c0392b;
}
.log-entry.warning {
  color: #f39c12;
}
</style>