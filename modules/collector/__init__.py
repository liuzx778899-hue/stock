"""
collector - A股数据采集模块

职责:
  采集股票基础信息、K线、实时行情、行业/地区/概念板块
  所有后续模块（analysis/backtest/labeling）的数据基础

依赖:
  common.models（ORM 模型）
  adapters（数据源适配器）

提供给:
  analysis（股票分析） — 历史K线 + 实时行情
  backtest（回测）     — K线数据
  labeling（标签）     — 股票基础信息 + 概念板块

子目录:
  services/     — 业务逻辑（编排器、质量检查、数据源管理）
  collectors/   — 采集器（基础信息、K线、行情、行业/概念板块）
  web/          — 前端（templates + Vue SPA）
  requirements/ — 需求文档
"""
