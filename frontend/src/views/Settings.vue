<template>
  <div class="settings">
    <h2 class="page-title">数据库连接</h2>

    <!-- 连接状态 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">连接状态</span>
        <span :class="['badge', dbStatus.connected ? 'badge-success' : 'badge-error']">
          {{ dbStatus.connected ? '已连接' : '未连接' }}
        </span>
      </div>
      <p style="margin: 12px 0; color: #666;">{{ dbStatus.message }}</p>
      <div v-if="dbStatus.connected && dbStatus.tables.length > 0">
        <p style="font-size: 14px; color: #888;">已有表: {{ dbStatus.tables.join(', ') }}</p>
      </div>
      <div class="grid" style="margin-top: 16px;">
        <button class="btn btn-primary" @click="checkStatus">刷新状态</button>
        <button
          class="btn btn-success"
          v-if="dbStatus.connected && !dbStatus.tables_exist"
          @click="initTables"
        >
          初始化表结构
        </button>
      </div>
      <div v-if="initResult" style="margin-top: 16px;">
        <p :style="{ color: initResult.success ? '#52c41a' : '#ff4d4f' }">
          {{ initResult.message }}
        </p>
      </div>
    </div>

    <!-- 连接配置 -->
    <div class="card">
      <div class="card-title">数据库配置</div>
      <p style="color: #666; margin: 12px 0; font-size: 14px;">
        请输入数据库连接信息（配置保存在 .env 文件中）
      </p>

      <div class="form-group">
        <label>主机地址</label>
        <input type="text" v-model="form.host" placeholder="192.168.2.32">
      </div>

      <div class="form-group">
        <label>端口</label>
        <input type="number" v-model.number="form.port" placeholder="2881">
      </div>

      <div class="form-group">
        <label>用户名</label>
        <input type="text" v-model="form.username" placeholder="root@hdw">
      </div>

      <div class="form-group">
        <label>密码</label>
        <input type="password" v-model="form.password" placeholder="输入密码">
      </div>

      <div class="form-group">
        <label>数据库名</label>
        <input type="text" v-model="form.database" placeholder="astock">
      </div>

      <div class="grid" style="margin-top: 16px;">
        <button class="btn btn-primary" @click="testConnect" :disabled="testing">
          {{ testing ? '测试中...' : '测试连接' }}
        </button>
      </div>

      <div v-if="connectResult" style="margin-top: 16px;">
        <p :style="{ color: connectResult.success ? '#52c41a' : '#ff4d4f' }">
          {{ connectResult.message }}
        </p>
      </div>
    </div>

    <!-- 使用说明 -->
    <div class="card">
      <div class="card-title">使用说明</div>
      <ol style="color: #666; font-size: 14px; line-height: 1.8; padding-left: 20px;">
        <li>在项目根目录创建 <code>.env</code> 文件</li>
        <li>复制 <code>.env.example</code> 内容并修改数据库配置</li>
        <li>点击"测试连接"验证配置是否正确</li>
        <li>连接成功后点击"初始化表结构"创建数据表</li>
        <li>表结构初始化后即可开始采集任务</li>
      </ol>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { getDbStatus, dbConnect, dbInit } from '../api'

const dbStatus = reactive({
  connected: false,
  tables_exist: false,
  tables: [],
  message: '检查中...'
})

const form = reactive({
  host: '192.168.2.32',
  port: 2881,
  username: 'root@hdw',
  password: '',
  database: 'astock'
})

const testing = ref(false)
const connectResult = ref(null)
const initResult = ref(null)

const checkStatus = async () => {
  try {
    const resp = await getDbStatus()
    Object.assign(dbStatus, resp.data)
  } catch (e) {
    dbStatus.connected = false
    dbStatus.message = '获取状态失败: ' + e.message
  }
}

const testConnect = async () => {
  testing.value = true
  connectResult.value = null
  try {
    const resp = await dbConnect(form)
    connectResult.value = resp.data
    if (resp.data.success) {
      await checkStatus()
    }
  } catch (e) {
    connectResult.value = { success: false, message: e.message }
  } finally {
    testing.value = false
  }
}

const initTables = async () => {
  initResult.value = null
  try {
    const resp = await dbInit()
    initResult.value = resp.data
    if (resp.data.success) {
      await checkStatus()
    }
  } catch (e) {
    initResult.value = { success: false, message: '初始化失败: ' + e.message }
  }
}

onMounted(() => {
  checkStatus()
})
</script>

<style scoped>
.page-title {
  font-size: 24px;
  margin-bottom: 20px;
  color: #333;
}

.badge-success {
  background: #52c41a;
}

.badge-error {
  background: #ff4d4f;
}

code {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}
</style>
