import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getStatus, stopTask } from '../api'

export const useCollectorStore = defineStore('collector', () => {
  // 任务状态
  const running = ref(false)
  const taskType = ref(null)
  const progress = ref(0)
  const total = ref(0)
  const stats = ref(null)
  const error = ref(null)
  const logs = ref([])

  // WebSocket 连接
  let ws = null
  let reconnectTimer = null
  let isUnmounted = false

  // 计算属性
  const progressPercent = computed(() => {
    if (total.value === 0) return 0
    return Math.round(progress.value * 100 / total.value)
  })

  // 添加日志
  const addLog = (type, message) => {
    const time = new Date().toLocaleTimeString()
    logs.value.push({ type, message, time })
    if (logs.value.length > 100) {
      logs.value.shift()
    }
  }

  // 更新状态
  const updateStatus = (data) => {
    running.value = data.running
    taskType.value = data.task_type
    progress.value = data.progress
    total.value = data.total
    stats.value = data.stats
    error.value = data.error
  }

  // 初始化 WebSocket
  const initWebSocket = () => {
    // 重置标志，允许重新连接
    isUnmounted = false

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(protocol + '//' + location.host + '/ws/progress')

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'progress') {
          progress.value = data.completed
          total.value = data.total
          addLog('info', `进度: ${data.completed}/${data.total} (${data.percent || 0}%)`)
        } else if (data.type === 'completed') {
          addLog('success', data.message)
          running.value = false
          refreshStatus()
        } else if (data.type === 'error') {
          addLog('error', data.message)
          running.value = false
          error.value = data.message
        } else if (data.type === 'stopped') {
          // 处理停止消息（修复 BUG-067）
          addLog('warning', data.message)
          running.value = false
          refreshStatus()
        }
      } catch (e) {
        console.error('WebSocket message parse error:', e)
        addLog('error', 'WebSocket message parse error')
      }
    }

    ws.onclose = () => {
      if (!isUnmounted) {
        // 防抖重连
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
        }
        reconnectTimer = setTimeout(() => {
          initWebSocket()
        }, 3000)
      }
    }
  }

  // 关闭 WebSocket
  const closeWebSocket = () => {
    isUnmounted = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
  }

  // 刷新状态
  const refreshStatus = async () => {
    try {
      const resp = await getStatus()
      updateStatus(resp.data)
    } catch (e) {
      console.error('获取状态失败', e)
    }
  }

  // 开始任务
  const startTask = (type) => {
    running.value = true
    taskType.value = type
    progress.value = 0
    total.value = 0
    error.value = null
    addLog('info', `启动 ${type} 采集任务`)
  }

  // 停止任务（修复 BUG-066）
  const stopRunningTask = async () => {
    try {
      const resp = await stopTask()
      if (resp.data.success) {
        addLog('warning', resp.data.message)
        // 1秒后刷新状态
        setTimeout(refreshStatus, 1000)
      } else {
        addLog('error', resp.data.error || resp.data.message)
      }
    } catch (e) {
      addLog('error', '停止请求失败: ' + e.message)
    }
  }

  return {
    running,
    taskType,
    progress,
    total,
    stats,
    error,
    logs,
    progressPercent,
    addLog,
    updateStatus,
    initWebSocket,
    closeWebSocket,
    refreshStatus,
    startTask,
    stopRunningTask
  }
})