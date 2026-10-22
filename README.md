# MongoDB 问卷系统 · 第一阶段

代码仓库：https://github.com/xuxAkiss/database-lab1

首次获取：`git clone https://github.com/xuxAkiss/database-lab1.git`，然后 `cd database-lab1`。下文 `D:\数据管理\work1\workspace` 是原开发目录，克隆后请使用自己的仓库目录；Python 路径也应替换为本机解释器。数据库启动脚本中的安装路径见 `dev/mongodb/Common.ps1`，默认使用 `D:\Mongodb\bin`，其他机器应先按实际安装位置调整。

已实现账号、问卷编辑/版本发布、草稿/跳转/提交、创建者整卷与单题统计。第一阶段报告：[docs/stage1-report.md](docs/stage1-report.md)；要求对照：[docs/requirements-matrix.md](docs/requirements-matrix.md)。历史模块文档里的“本轮尚未实现”仅表示当时范围。

## 环境与首次准备

Windows；实际项目Python3.14.7，独立.venv；MongoDB8.3.11单节点复制集work1DevRs。直接依赖版本在requirements.in，完整固定版本在requirements.txt；本轮无新增依赖，pip check通过。Miniconda只提供解释器，不向基础环境安装项目依赖。

```powershell
Set-Location -LiteralPath 'D:\数据管理\work1\workspace'
# 仅新环境需要创建；现有.venv不要覆盖
& 'D:\miniconda3\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
.\.venv\Scripts\python.exe -m pip check
```

已有环境直接使用。首次安装需网络。不同机器需安装自己的Python/MongoDB并审阅配置路径；没有将本机安装程序打包进源码。

## 数据库与应用启动

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\dev\mongodb\Start.ps1
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

应用前台Ctrl+C停止；端口已有项目应用时无需重复启动。Mongo检查/停止分别用dev/mongodb/Check.ps1、Stop.ps1；只针对本项目实例，详见[数据库脚本说明](dev/mongodb/README.md)。复用D:\Mongodb安装程序，项目数据在.local/mongodb，不碰原安装配置和原数据目录。

配置示例（真实.env不交付）：

```dotenv
MONGODB_URI=mongodb://127.0.0.1:27018/work1?replicaSet=work1DevRs&serverSelectionTimeoutMS=5000
MONGODB_DB=work1
DB_CHECK_TIMEOUT_MS=5000
AUTH_ORIGIN=http://127.0.0.1:8000
SESSION_COOKIE_SECURE=false
SESSION_TTL_SECONDS=28800
```

本机HTTP只绑定回环。部署HTTPS须设置真实精确AUTH_ORIGIN、SESSION_COOKIE_SECURE=true并配置HTTPS代理；本轮未验收该部署。事务需要复制集；不能用未配置的standalone替代。本地开发库无公网安全承诺。

## 操作入口

- [账号](http://127.0.0.1:8000/) → [问卷管理](http://127.0.0.1:8000/manage)。
- 创建、添加题目/规则、保存、发布；管理区打开固定分享链接填写。
- 同一编辑区“查看当前发布版本统计”进入整卷，选择下拉题目查看单题。默认当前版，点击刷新重新固定版本。仅创建者有权访问。
- [运行健康检查](http://127.0.0.1:8000/health)，[API交互定义](http://127.0.0.1:8000/docs)。

## 验收复现

先启动应用与数据库；下列集成脚本新增QA账号/问卷/提交，不清库，不要用于生产库。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
.\.venv\Scripts\python.exe tests\check_auth.py
.\.venv\Scripts\python.exe tests\check_surveys.py
.\.venv\Scripts\python.exe tests\check_filling.py
.\.venv\Scripts\python.exe tests\check_statistics.py
```

输入/预期/实际：[测试目录说明](docs/test-cases.md)、[统计人工预期](docs/statistics-tests.md)、docs/stage1-*-results.txt、[浏览器记录](docs/browser-statistics.md)。输出不能用部署就绪替代事务测试。

## 文档与交付

[系统](docs/system.md) · [数据/schema/索引](docs/database.md) · [API](docs/api.md) · [跳转/校验](docs/logic.md) · [AI真实使用说明](docs/ai-usage.md)。

交付采用docs/baseline-manifest.json列出的文件及该清单本身；包含源码、固定依赖、示例配置、脚本、文档/截图。不交付.venv/.local/.env/凭据/运行数据/缓存；不删除这些本地文件。清单重建：`.\.venv\Scripts\python.exe dev\make_manifest.py`。第二阶段沿此基线增量演进。


