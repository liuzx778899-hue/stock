<template>
  <div class="quality-page">
    <div class="page-header">
      <h1>✅ 数据质量分析</h1>
      <div class="header-actions">
        <span class="check-time">检查时间: {{ checkTime || '-' }}</span>
        <button class="btn btn-primary" @click="triggerCheck" :disabled="checking">
          {{ checking ? '检查中...' : '开始检查' }}
        </button>
      </div>
    </div>

    <div class="quality-cards">
      <div v-for="report in reports" :key="report.data_category"
           class="quality-card" :class="getStatusClass(report.total_score)">
        <div class="card-header">
          <h3>{{ getCategoryLabel(report.data_category) }}</h3>
          <span class="status-badge" :class="report.status">
            {{ report.status }}
          </span>
        </div>
        <div class="score">{{ report.total_score?.toFixed(1) || '-' }}</div>
        <div class="dimensions">
          <div class="dimension">
            <span class="label">完整度</span>
            <span class="value" :class="getScoreClass(report.completeness_score)">
              {{ report.completeness_score?.toFixed(1) || '-' }}
            </span>
          </div>
          <div class="dimension">
            <span class="label">新鲜度</span>
            <span class="value" :class="getScoreClass(report.freshness_score)">
              {{ report.freshness_score?.toFixed(1) || '-' }}
            </span>
          </div>
          <div class="dimension">
            <span class="label">异常检测</span>
            <span class="value" :class="getScoreClass(report.anomaly_score)">
              {{ report.anomaly_score?.toFixed(1) || '-' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="anomaly-details card">
      <h3>📋 异常详情</h3>
      <div v-if="hasAnomalies">
        <div v-for="report in reports" :key="report.data_category" class="category-anomalies">
          <div v-for="anomaly in getAnomalies(report)" :key="anomaly.type" class="anomaly-item">
            <span class="anomaly-type">{{ anomaly.type }}</span>
            <span class="anomaly-count">{{ anomaly.count }}条</span>
          </div>
        </div>
      </div>
      <div v-else class="no-anomaly">✅ 暂无异常</div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { getQualityReport, triggerQualityCheck } from '../api'

export default {
  name: 'QualityPage',
  setup() {
    const reports = ref([])
    const checkTime = ref('')
    const checking = ref(false)

    const categoryLabels = {
      stock_basic: '📊 股票基础信息',
      kline_daily: '📈 K线数据',
      realtime_quote: '💹 实时行情'
    }

    const hasAnomalies = computed(() => {
      return reports.value.some(r => {
        const anomalies = r.anomaly_detail?.anomalies || []
        return anomalies.some(a => a.count > 0)
      })
    })

    const getCategoryLabel = (category) => categoryLabels[category] || category

    const getStatusClass = (score) => {
      if (score >= 80) return 'status-ok'
      if (score >= 60) return 'status-warning'
      return 'status-critical'
    }

    const getScoreClass = (score) => {
      if (score >= 80) return 'score-good'
      if (score >= 60) return 'score-mid'
      return 'score-bad'
    }

    const getAnomalies = (report) => {
      return (report.anomaly_detail?.anomalies || []).filter(a => a.count > 0)
    }

    const loadReport = async () => {
      try {
        const resp = await getQualityReport()
        if (resp.data) {
          reports.value = resp.data.reports || []
          checkTime.value = resp.data.check_time || ''
        }
      } catch (e) {
        console.error('加载质量报告失败:', e)
      }
    }

    const triggerCheck = async () => {
      checking.value = true
      try {
        const resp = await triggerQualityCheck()
        if (resp.data) {
          reports.value = resp.data.reports || []
          checkTime.value = resp.data.check_time || ''
        }
      } catch (e) {
        console.error('质量检查失败:', e)
      } finally {
        checking.value = false
      }
    }

    onMounted(() => {
      loadReport()
    })

    return {
      reports,
      checkTime,
      checking,
      hasAnomalies,
      getCategoryLabel,
      getStatusClass,
      getScoreClass,
      getAnomalies,
      triggerCheck
    }
  }
}
</script>

<style scoped>
.quality-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 20px;
  color: #333;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.check-time {
  color: #888;
  font-size: 13px;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}

.btn-primary {
  background: #667eea;
  color: white;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.quality-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.quality-card {
  background: white;
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid #667eea;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.quality-card.status-ok {
  border-left-color: #52c41a;
}

.quality-card.status-warning {
  border-left-color: #faad14;
}

.quality-card.status-critical {
  border-left-color: #f5222d;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-header h3 {
  font-size: 16px;
  color: #333;
  margin: 0;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: white;
}

.status-badge.ok {
  background: #52c41a;
}

.status-badge.warning {
  background: #faad14;
}

.status-badge.critical {
  background: #f5222d;
}

.score {
  font-size: 32px;
  font-weight: 600;
  text-align: center;
  margin: 8px 0;
  color: #333;
}

.dimensions {
  margin-top: 12px;
}

.dimension {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 6px;
}

.dimension .label {
  color: #666;
}

.dimension .value {
  font-weight: 500;
}

.value.score-good {
  color: #52c41a;
}

.value.score-mid {
  color: #faad14;
}

.value.score-bad {
  color: #f5222d;
}

.card {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.card h3 {
  font-size: 16px;
  color: #333;
  margin: 0 0 12px 0;
}

.anomaly-details {
  background: #f8f9fa;
}

.anomaly-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
}

.anomaly-type {
  color: #666;
}

.anomaly-count {
  color: #f5222d;
  font-weight: 500;
}

.no-anomaly {
  color: #52c41a;
  font-size: 14px;
}
</style>
