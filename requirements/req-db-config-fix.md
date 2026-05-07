# 需求文档：数据库连接配置页面修复（#157 修正）
创建时间：2026-05-07
状态：待开发
关联 Issue: #157

## 问题

当前 `/db-config` 页面返回 404，保存功能不可用。配置无法存入 `system_config` 表。

## 目标

1. `/db-config` 页面正常加载
2. 表单：host / port / username / password / database
3. 保存按钮 → API → 加密写入 `system_config` 表
4. 页面加载 → 读取已有配置 → 密码脱敏显示 `****`
5. 保存后数据确实入库，重新打开页面能回显

## 涉及文件

- `web_app.py` — 路由 + API 端点
- `static/` — 前端表单页面
- `common/db_config_store.py` — 读写逻辑

## 验收标准

- [ ] `/db-config` 返回正常 HTML 页面（非 404）
- [ ] 表单可输入 host/port/username/password/database
- [ ] 点击保存后，数据写入 `system_config` 表
- [ ] 保存后再次打开页面，已有配置回显
- [ ] 密码字段显示为 `****`
- [ ] 数据库连接按保存的配置实际生效

## 不做的事

- 不修改 system_config 表结构
- 不修改加密算法
