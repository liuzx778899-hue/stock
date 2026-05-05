<template>
  <div class="dashboard">
    <h2 class="page-title">Dashboard</h2>

    <!-- Data Statistics -->
    <div class="card">
      <div class="card-title">Data Statistics</div>
      <div class="stat-grid">
        <div class="stat-item">
          <div class="stat-value">{{ stats.stock_count || 0 }}</div>
          <div class="stat-label">Stocks</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ formatNumber(stats.kline_count) }}</div>
          <div class="stat-label">K-Line Records</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ formatNumber(stats.realtime_count) }}</div>
          <div class="stat-label">Realtime Quotes</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ stats.log_count || 0 }}</div>
          <div class="stat-label">Collect Logs</div>
        </div>
      </div>
    </div>

    <!-- Task Status -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">Task Status</span>
        <span :class="['badge', store.running ? 'badge-running' : 'badge-idle']">
          {{ store.running ? 'Running' : 'Idle' }}
        </span>
      </div>
      <div class="stat-grid" v-if="store.running">
        <div class="stat-item">
          <div class="stat-value">{{ store.taskType || '-' }}</div>
          <div class="stat-label">Task Type</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ store.progressPercent }}%</div>
          <div class="stat-label">Progress</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ store.progress }}</div>
          <div class="stat-label">Completed</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ store.total }}</div>
          <div class="stat-label">Total</div>
        </div>
      </div>
      <div class="progress-bar" v-if="store.running">
        <div class="progress-fill" :style="{ width: store.progressPercent + '%' }"></div>
      </div>
      <div v-if="!store.running" style="color: #888; padding: 20px 0; text-align: center;">
        No task running. Go to <router-link to="/collector">Collector</router-link> to start.
      </div>
    </div>

    <!-- Real-time Log -->
    <div class="card">
      <div class="card-title">Real-time Log</div>
      <div class="log-container">
        <div v-if="store.logs.length === 0" style="color: #666; text-align: center; padding: 20px;">
          No logs yet
        </div>
        <div v-for="(log, i) in store.logs" :key="i" :class="['log-entry', log.type]">
          [{{ log.time }}] {{ log.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useCollectorStore } from '../stores/collector'
import { getStats } from '../api'

const store = useCollectorStore()
const stats = ref({
  stock_count: 0,
  kline_count: 0,
  realtime_count: 0,
  log_count: 0
})

const formatNumber = (num) => {
  if (!num) return '0'
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

const fetchStats = async () => {
  try {
    const resp = await getStats()
    stats.value = resp.data
  } catch (e) {
    console.error('Failed to fetch stats', e)
  }
}

onMounted(() => {
  store.initWebSocket()
  store.refreshStatus()
  fetchStats()
  // Refresh stats every 30 seconds
  statsTimer = setInterval(fetchStats, 30000)
  statusTimer = setInterval(() => store.refreshStatus(), 5000)
})

let statsTimer
let statusTimer
onUnmounted(() => {
  store.closeWebSocket()
  if (statsTimer) clearInterval(statsTimer)
  if (statusTimer) clearInterval(statusTimer)
})
</script>

<style scoped>
.page-title {
  font-size: 24px;
  margin-bottom: 20px;
  color: #333;
}
</style>