# 本轮改动摘要与交付检查

基于本轮开始时含022未提交成果的实际工作区，而非假设HEAD就是022。HEAD仍为e0b3391。保留全部原数据；没有提交或推送。

## 主要变化
- 新增只读跨卷统计后端与页面；固定题版本、本人问卷、历史发布替换、同卷实例选择、最新整份提交、频数与分页。
- 在原main.py注册入口，原surveys.py增加submissions索引，题库与原问卷前端加统计链接。
- 原认证/填写/单卷统计代码未改；022题身份、版本、共享、快照保存机制沿用。
- 完善报告、八项演进、完整需求覆盖、API/数据库/逻辑、测试和AI日志；022需更新文档先保存在022-preserved。
- 新增测试工具依赖仅在项目.venv，业务依赖与.env不变。未触碰日志.txt或用户Word。

## 检查结果
真实跨卷C01–C11、022 S01–S09、原认证/发布/填写/统计、27项单元及浏览器复测通过。阶段一525条、本轮前762条业务记录哈希不变。浏览器修复提示遮挡和表格间距后复测；pip check通过，git diff空白检查通过（保留CRLF）。

旧阶段一/022测试输出和清单的哈希与本轮起始文件快照比较通过，共检查 19 个证据文件。最终清单排除自身，以避免自引用；交付清单内文件加清单本身。排除.venv/.local/真实.env/凭据/缓存/数据库目录。

## 相对起始文件快照发生变化的文件
- backend/main.py
- backend/surveys.py
- docs/api.md
- docs/database.md
- docs/logic.md
- docs/stage2-evolution.md
- docs/stage2-report.md
- docs/stage2-system.md
- docs/stage2-tests.md
- docs/system.md
- frontend/library.js
- frontend/surveys.js

## 当前新增文件
- .env.example
- .gitattributes
- .gitignore
- README.md
- backend/question_statistics.py
- dev/capture_stage2_final_baseline.py
- dev/make_stage2_final_manifest.py
- docs/022-preserved/README.md
- docs/022-preserved/api.md
- docs/022-preserved/database.md
- docs/022-preserved/logic.md
- docs/022-preserved/stage2-evolution.md
- docs/022-preserved/stage2-manifest.json
- docs/022-preserved/stage2-report.md
- docs/022-preserved/stage2-system.md
- docs/022-preserved/stage2-tests.md
- docs/022-preserved/system.md
- docs/evidence/stage2-final-browser-current-initial.png
- docs/evidence/stage2-final-browser-current.png
- docs/evidence/stage2-final-browser-history-initial.png
- docs/evidence/stage2-final-browser-history.png
- docs/evidence/stage2-final-browser-mobile-initial.png
- docs/evidence/stage2-final-browser-mobile.png
- docs/evidence/stage2-final-browser-question-v2-initial.png
- docs/evidence/stage2-final-browser-question-v2.png
- docs/stage2-final-ai-log-draft.md
- docs/stage2-final-browser-initial.txt
- docs/stage2-final-browser-results.json
- docs/stage2-final-browser-retest.txt
- docs/stage2-final-check_auth.txt
- docs/stage2-final-check_filling.txt
- docs/stage2-final-check_stage2.txt
- docs/stage2-final-check_statistics.txt
- docs/stage2-final-check_surveys.txt
- docs/stage2-final-coverage.md
- docs/stage2-final-cross-initial.txt
- docs/stage2-final-data-baseline.json
- docs/stage2-final-integrity.txt
- docs/stage2-final-start.json
- docs/stage2-final-statistics.md
- docs/stage2-final-tests.md
- docs/stage2-final-unit.txt
- frontend/question-statistics.css
- frontend/question-statistics.html
- frontend/question-statistics.js
- requirements-test.txt
- requirements.in
- requirements.txt
- stage2_baseline.py
- tests/check_cross_browser.py
- tests/check_cross_statistics.py
- tests/check_final_integrity.py

列表只表示文件变化，不表示用户手写贡献。README未包含在起始files映射中，但已作为022-preserved/README.md保留；应将它理解为更新文件。新增列表包含本轮保存的022副本。
