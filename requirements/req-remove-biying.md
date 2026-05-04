# 需求：移除必盈 API 所有代码和配置

## 涉及 Issue
#118

## 背景
必盈 API 已不再使用，清理所有相关代码和配置。

## 涉及文件
| 文件 | 操作 |
|------|------|
| adapters/biying.py | 删除整个文件 |
| adapters/base.py | 移除非必盈相关引用 |
| adapters/akshare/eastmoney.py | 移除必盈引用 |
| models.py | 移除 BiyingLicence 等模型 |
| providers.yaml | 删除 biying 配置块 |
| services/datasource_service.py | 移除 Biying 处理逻辑 |
| web_app.py | 移除 /api/biying/* 端点 |
| templates/index.html | 移除必盈配置 UI |
| README.md | 移除必盈描述 |

## 验收标准
- [ ] 代码中无 biying/Biying/必盈 引用
- [ ] pytest tests/ -v 全部通过
- [ ] 服务启动无 import 错误
- [ ] 数据源管理页面不再显示必盈

## 不做的事
- 不删其他数据源
- 不改变数据采集逻辑
