# MongoDB 问卷系统 · 第一阶段与第二阶段

代码仓库：https://github.com/xuxAkiss/database-lab1


## 第二阶段提交材料

第二阶段在第一阶段代码上增量实现，包含题库、题目版本、共享及跨问卷统计。

- [最终报告 PDF](docs/reports/2026_ECNU_PJ1_2_徐健.pdf)
- [可编辑报告 Markdown](docs/reports/2026_ECNU_PJ1_2_徐健.md)
- [完整开发提示词与结果日志](docs/ai-development-log-stage2.txt)
- [需求覆盖](docs/stage2-final-coverage.md)与[测试记录](docs/stage2-final-tests.md)

下方及历史报告中的“未推送”“跨卷统计延期”等表述是当轮记录，当前功能见“第二阶段完整实现与验收”。第一阶段及022原始证据和清单继续保留；本次上传清单另存 `docs/stage2-upload-manifest.json`。数据库文件、虚拟环境和真实配置不交付。课程平台仍需单独提交 PDF。

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


## 第二阶段第一个功能块
独立题目、不可变版本/分支/恢复、题库、指定账号共享与撤销、原问卷固定版本选题及使用查询已实现。入口 `/library`；原 `/manage` 保留。跨问卷统计延期。

配置与依赖沿用上文。安装新增 MongoDB schema/索引：`.\.venv\Scripts\python.exe dev/stage2_schema.py`，可重复执行，不清库。

[第二阶段报告](docs/stage2-report.md) · [演进记录](docs/stage2-evolution.md) · [系统/数据库/API/逻辑](docs/stage2-system.md) · [测试与需求覆盖](docs/stage2-tests.md) · [真实 AI 日志草稿](docs/stage2-ai-log-draft.md)。

专项复测：`.\.venv\Scripts\python.exe tests/check_stage2.py`；旧数据核验：`.\.venv\Scripts\python.exe tests/check_stage2_baseline.py`。阶段二交付另见 docs/stage2-manifest.json，阶段一清单和证据保留。未提交或推送 GitHub。

## 第二阶段完整实现与验收
跨问卷题目统计已在022基础上实现，上文“延期”描述022当时范围。先登录，进入 `/library` 选题版本，点击“统计我拥有的问卷中的此题版本”；也可在原 `/manage` 已引用题实例上点击跨卷统计链接。题库共享撤销后，该问卷实例入口仍可查询自己的快照统计。

口径：精确题目版本，只本人问卷，默认每卷当前发布、可用一个历史版替换。每卷取每账号最新成功整份提交，跨卷不去重，最新空白不回填；重复实例默认首个可切换。数字含频数和均值，详情分页，总计不受页数影响。范围超限明确报错，不静默截断。

[完整报告](docs/stage2-report.md) · [教师需求覆盖](docs/stage2-final-coverage.md) · [跨卷API/数据库索引/关键逻辑/限制](docs/stage2-final-statistics.md) · [整体验收与复现](docs/stage2-final-tests.md) · [本轮AI日志草稿](docs/stage2-final-ai-log-draft.md) · [改动摘要](docs/stage2-final-changes.md)。

运行时依赖和.env不变。新增索引由原SurveyStore自动幂等安装；022集合schema仍使用dev/stage2_schema.py。浏览器测试可选依赖只在项目.venv安装：`.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt`，使用本机Microsoft Edge。

本轮复现：`tests/check_cross_statistics.py`（真实HTTP/MongoDB）、`tests/check_cross_browser.py`（浏览器）、`tests/check_final_integrity.py`（保留数据库的双基线只读核验），均用项目.venv Python运行。完整本地交付清单为docs/stage2-final-manifest.json；第一阶段与022旧清单保留，不用旧清单代替当前交付。
