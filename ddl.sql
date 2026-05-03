-- A股历史数据分析系统 数据库表结构 DDL
-- 数据库：OceanBase / MySQL
-- 创建日期：2026-05-02

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS astock DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE astock;

-- ============================================
-- 1. 股票基础信息表
-- ============================================
CREATE TABLE IF NOT EXISTS stock_basic (
    ts_code VARCHAR(20) NOT NULL COMMENT 'TS代码（如 000001.SZ）',
    symbol VARCHAR(10) NOT NULL COMMENT '股票代码',
    name VARCHAR(50) NOT NULL COMMENT '股票名称',
    area VARCHAR(20) COMMENT '地域',
    industry VARCHAR(50) COMMENT '所属行业',
    market VARCHAR(10) COMMENT '市场类型（主板/创业板/科创板等）',
    list_date DATE COMMENT '上市日期',
    list_status VARCHAR(2) DEFAULT 'L' COMMENT '上市状态：L上市 D退市 P暂停上市',
    delist_date DATE COMMENT '退市日期',
    is_hs VARCHAR(2) COMMENT '是否沪深港通标的：H沪股通 S深股通 N否',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (ts_code),
    INDEX idx_stock_basic_symbol (symbol),
    INDEX idx_stock_basic_list_status (list_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='A股股票基础信息表';

-- ============================================
-- 2. 股票日K线数据表（前复权）
-- ============================================
CREATE TABLE IF NOT EXISTS stock_daily_kline (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    ts_code VARCHAR(20) NOT NULL COMMENT 'TS代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    `open` DECIMAL(12, 4) COMMENT '开盘价',
    high DECIMAL(12, 4) COMMENT '最高价',
    low DECIMAL(12, 4) COMMENT '最低价',
    `close` DECIMAL(12, 4) COMMENT '收盘价',
    pre_close DECIMAL(12, 4) COMMENT '昨收价',
    volume BIGINT COMMENT '成交量（手）',
    amount DECIMAL(20, 4) COMMENT '成交额（千元）',
    turnover_rate DECIMAL(10, 4) COMMENT '换手率（%）',
    pct_chg DECIMAL(10, 4) COMMENT '涨跌幅（%）',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_kline_code_date (ts_code, trade_date),
    INDEX idx_kline_trade_date (trade_date),
    INDEX idx_kline_code_date (ts_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='A股股票日K线数据表（前复权）';

-- ============================================
-- 3. 股票实时行情表
-- ============================================
CREATE TABLE IF NOT EXISTS stock_realtime_quote (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    symbol VARCHAR(10) NOT NULL COMMENT '股票代码',
    name VARCHAR(50) COMMENT '股票名称',
    price DECIMAL(12, 4) COMMENT '当前价格',
    `open` DECIMAL(12, 4) COMMENT '开盘价',
    high DECIMAL(12, 4) COMMENT '最高价',
    low DECIMAL(12, 4) COMMENT '最低价',
    pre_close DECIMAL(12, 4) COMMENT '昨收价',
    volume BIGINT COMMENT '成交量（手）',
    amount DECIMAL(20, 4) COMMENT '成交额（千元）',
    bid_price1 DECIMAL(12, 4) COMMENT '买一价',
    bid_volume1 BIGINT COMMENT '买一量',
    ask_price1 DECIMAL(12, 4) COMMENT '卖一价',
    ask_volume1 BIGINT COMMENT '卖一量',
    update_time DATETIME COMMENT '行情更新时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    INDEX idx_realtime_symbol (symbol),
    INDEX idx_realtime_time (update_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='A股股票实时行情表';

-- ============================================
-- 4. 数据采集日志表
-- ============================================
CREATE TABLE IF NOT EXISTS collect_log (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    task_name VARCHAR(50) NOT NULL COMMENT '任务名称',
    task_type VARCHAR(20) NOT NULL COMMENT '任务类型（basic/kline/realtime）',
    start_time DATETIME NOT NULL COMMENT '开始时间',
    end_time DATETIME COMMENT '结束时间',
    total_count INT DEFAULT 0 COMMENT '总数量',
    success_count INT DEFAULT 0 COMMENT '成功数量',
    failed_count INT DEFAULT 0 COMMENT '失败数量',
    status VARCHAR(10) DEFAULT 'running' COMMENT '状态（running/success/failed）',
    error_msg TEXT COMMENT '错误信息',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    INDEX idx_collect_log_task_type (task_type),
    INDEX idx_collect_log_start_time (start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据采集日志表';

-- ============================================
-- 5. 数据源配置表
-- ============================================
CREATE TABLE IF NOT EXISTS datasource_config (
    id VARCHAR(50) NOT NULL COMMENT '数据源ID',
    name VARCHAR(100) NOT NULL COMMENT '数据源名称',
    type VARCHAR(20) NOT NULL COMMENT '类型',
    api_url VARCHAR(500) COMMENT 'API地址',
    api_key VARCHAR(500) COMMENT 'API密钥（加密存储）',
    auth_type VARCHAR(20) DEFAULT 'none' COMMENT '认证类型',
    priority INT DEFAULT 99 COMMENT '优先级（数字越小越优先）',
    enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    is_builtin TINYINT(1) DEFAULT 0 COMMENT '是否内置数据源',
    description VARCHAR(500) COMMENT '描述',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    INDEX idx_datasource_priority (priority),
    INDEX idx_datasource_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源配置表';

-- ============================================
-- 6. 必盈API Licence池表
-- ============================================
CREATE TABLE IF NOT EXISTS biying_licence (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    licence VARCHAR(100) NOT NULL COMMENT 'Licence密钥',
    usage_count INT DEFAULT 0 COMMENT '使用次数',
    error_count INT DEFAULT 0 COMMENT '错误次数',
    is_current TINYINT(1) DEFAULT 0 COMMENT '是否当前使用',
    is_available TINYINT(1) DEFAULT 1 COMMENT '是否可用',
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '添加时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_biying_licence (licence),
    INDEX idx_biying_current (is_current)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='必盈API Licence池表';

-- 初始化内置数据源配置
INSERT INTO datasource_config (id, name, type, priority, enabled, is_builtin, description) VALUES
('akshare_em', '东方财富', 'akshare', 1, 1, 1, 'AkShare东方财富数据源'),
('akshare_sina', '新浪', 'akshare', 2, 1, 1, 'AkShare新浪数据源'),
('akshare_tencent', '腾讯', 'akshare', 3, 1, 1, 'AkShare腾讯数据源'),
('biying', '必盈API', 'http', 4, 1, 1, '必盈API付费数据源，需配置Licence')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- ============================================
-- 7. 数据质量检查报告表
-- ============================================
CREATE TABLE IF NOT EXISTS data_quality_report (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    check_time DATETIME NOT NULL COMMENT '检查时间',
    data_category VARCHAR(32) NOT NULL COMMENT '数据类别(stock_basic|kline_daily|realtime_quote)',
    total_score DECIMAL(5,1) NOT NULL COMMENT '总分(0-100)',
    completeness_score DECIMAL(5,1) NOT NULL COMMENT '完整度分数',
    freshness_score DECIMAL(5,1) NOT NULL COMMENT '新鲜度分数',
    anomaly_score DECIMAL(5,1) NOT NULL COMMENT '异常检测分数(100=无异常)',
    completeness_detail JSON COMMENT '各字段覆盖率明细',
    freshness_detail JSON COMMENT '新鲜度明细(last_update/days_lag)',
    anomaly_detail JSON COMMENT '异常明细列表',
    status VARCHAR(16) DEFAULT 'ok' COMMENT '状态(ok|warning|critical)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    INDEX idx_quality_category_time (data_category, check_time DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据质量检查报告表';