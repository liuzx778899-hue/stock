# 需求文档：数据库连接配置页面
创建时间：2026-05-07
状态：待开发
关联 Issue: #157

## 背景

#154 完成后端加密存储基础设施（crypto.py + db_config_store.py + system_config 表），
但用户只能通过命令行 bootstrap_db_config.py 配置数据库连接参数。
需要一个 Web UI 页面让用户直接在浏览器里管理。

## 目标

提供可视化数据库连接配置，替代命令行操作。

## 涉及文件

| 文件 | 改动 |
|------|------|
| web_app.py | 新增 GET/POST /api/db-config 端点 |
| common/db_config_store.py | 可能需要扩展读取接口 |
| modules/collector/web/templates/ | 新增配置页面 |
| modules/collector/web/static/ | 页面样式/JS |
| common/models.py | 可能需要调整 system_config 模型 |

## 验收标准

- [ ] Web 页面可输入 host / port / username / password / database
- [ ] 点击"保存"后配置加密存入 system_config 表
- [ ] 重新打开页面读取并显示已有配置
- [ ] 密码字段显示为 ****（脱敏）
- [ ] 保存成功/失败有提示

## 不做的事

- 不修改 bootstrap_db_config.py（保留命令行入口）
- 不修改 crypto.py 加密逻辑
