import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// 获取任务状态
export const getStatus = () => api.get('/status')

// 获取数据统计
export const getStats = () => api.get('/stats')

// 获取股票列表
export const getStocks = () => api.get('/stocks')

// 数据库连接状态
export const getDbStatus = () => api.get('/db/status')

// 测试数据库连接
export const dbConnect = (params) => api.post('/db/connect', params)

// 初始化数据库表结构
export const dbInit = () => api.post('/db/init')

// 采集股票基础信息
export const collectBasic = () => api.post('/collect/basic')

// 采集历史K线
export const collectKline = (params) => api.post('/collect/kline', params)

// 增量采集
export const collectIncremental = (params) => api.post('/collect/incremental', params)

// 实时行情采集
export const collectRealtime = () => api.post('/collect/realtime')

// 智能实时行情采集（判断开盘）
export const collectRealtimeAuto = () => api.post('/collect/realtime-auto')

// 停止任务
export const stopTask = () => api.post('/stop')

// 获取市场状态
export const getMarketStatus = () => api.get('/market/status')

// 数据源列表
export const getDatasources = () => api.get('/datasource/list')

// T7-1: Provider 能力声明
export const getProviders = () => api.get('/datasource/providers')

// T7-2: 字段覆盖率报告
export const getFieldReport = () => api.get('/collect/field-report')

// 添加数据源
export const addDatasource = (params) => api.post('/datasource/add', params)

// 更新数据源
export const updateDatasource = (id, params) => api.put(`/datasource/${id}`, params)

// 删除数据源
export const removeDatasource = (id) => api.delete(`/datasource/${id}`)

// 测试数据源连通性
export const testDatasource = (params) => api.post('/datasource/test', params)

// 数据质量 API (Q-5)
export const getQualityReport = (category) => api.get('/quality/report', { params: { category } })
export const triggerQualityCheck = () => api.post('/quality/check')
export const getQualityHistory = (category, limit = 20) => api.get('/quality/history', { params: { category, limit } })

export default api
