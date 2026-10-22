# 本轮文件变更

新增：backend/statistics.py（版本快照/聚合/权限），frontend/statistics.html与statistics.js（整卷/单题），tests/check_statistics.py（真实已知数据），dev/make_manifest.py（白名单文件与哈希）。

修改：backend/main.py（统计路由/页面），frontend/surveys.html与surveys.js（管理入口），README.md（统一当前阶段操作及交付）。

新增文档：system.md、database.md、api.md、logic.md、requirements-matrix.md、statistics-tests.md、test-cases.md、browser-statistics.md、stage1-report.md、ai-usage.md、source-provenance.json、stage1-final-checks.txt、changes-stage1.md、baseline-manifest.json；stage1-*-results.txt原始输出及初次失败输出；evidence/statistics-browser.png。

未修改：总日志、认证实现、原问卷/填写逻辑、依赖清单、真实.env、MongoDB配置/启停脚本。运行目录.local中的进程/日志/数据库内部及本轮QA数据随运行更新，非交付源码，不删除或重置。

真实问题与AI修复见ai-usage.md。启动命令和测试复现见README。清单只记录受控交付文件，不包含本机环境或凭据。工作区无Git仓库，无提交号或已提交改动声明。
