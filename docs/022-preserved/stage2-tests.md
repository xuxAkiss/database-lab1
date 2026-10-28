# 第二阶段第一个功能块测试与需求覆盖

日期：2026-10-23。实际本地 MongoDB 8.3.11 复制集，项目既有 .venv 与 FastAPI HTTP 服务。无 mock 数据库替代验收。所有脚本创建 qa_ 前缀账号/问卷并保留数据；不清库。测试脚本断言失败会终止；PowerShell Tee 管道本身退出码不能代替逐条输出判断。

## 自动验收用例
执行：`.\.venv\Scripts\python.exe tests/check_stage2.py`。最终脚本在安装 MongoDB validator 后亦须运行；见 stage2-integration-schema.txt。初轮及中间通过输出另存，不覆盖第一阶段证据。

|编号/教师需求|步骤与输入|预期输出|实际结果|
|---|---|---|---|
|S01 一、七|账号 A 创建单选题 A/B、建库、加入、改名；旧 revision 重命名；B 越权|201/200；409；404|通过，题库归类与 CAS 生效|
|S02 一、二、三|A 共享给 B；同一 V1 各创建一卷并发布；原填写接口选 A 提交|两卷 source 同 V1；真实 submission 生成|通过|
|S03 三、四、五|从 V1 创建 V2、另从 V1 创建 V3；以 V3 为父恢复 V1；本卷换 V2 再发布|父版本/恢复来源可查；旧发布和答卷原样；另一卷继续 V1|通过，直接比较旧 Mongo 文档；接收者派生来源保留|
|S04 六|作者查全题及 V1 使用；B 问卷标题含 PRIVATE_TITLE|自己有 edit/current/historical；他人仅匿名计数；V1 筛选正确|通过，私有标题、问卷 ID、用户 ID 不在输出中|
|S05 推荐并发规则|6 线程从 V1 创建版本；2 线程保存同问卷修订|6 个连续唯一序号全部保留；保存 200/409 各一次|通过|
|S06 原跳转要求及推荐实例边界|伪造 source 内容、外卷目标；合法本卷 target；新版移除 A/B 仍带旧规则|伪造与失效规则 422；合法结构保存并发布|通过，不静默改规则|
|S07 二及推荐撤销规则|撤销 B；B 读/新增引用/派生；B 对已保存实例仅改问卷标题并发布；同卷加新实例；移除题库成员|后续访问和新引用 404；旧实例可发布；历史仍在|通过|
|S08 三|新版操作和撤销后再次比较旧发布及答卷|完全不变|通过|
|S09 原作业兼容要求|无 source 旧题发布；按修订导出；重复导出；B 越权与共享读取|原子关联；重放复用；旧发布不变；legacy_origin 不泄露|通过|

测试输入、所有断言及实际记录 ID 保存在 tests/check_stage2.py 和对应输出。测试中的 q 为可选单选题；S02 真实提交走 start/save/next/submit，不直接伪造答卷。并发版本测试验证全部保存，不代表实现通用 HTTP 幂等请求键。

## 第一阶段受影响回归
|脚本|步骤/输入/预期|实际证据|
|---|---|---|
|unittest discover test_*.py|四题型、必答、数量、范围、整数、跳转目标/循环/条件与填写引擎状态|27 项通过：stage2-unit-results.txt|
|check_surveys.py|旧无 source 问卷创建/编辑/发布、并发、发布失败注入回滚、固定链接、截止关闭、越权|全部 PASS：stage2-regression-surveys.txt|
|check_filling.py|旧四题型答卷、草稿恢复、历史/latest、重复/并发、真实事务回滚、发布与提交顺序、关闭/截止|全部 PASS：stage2-regression-filling.txt|
|check_statistics.py|3 次提交/2 账号，单选 [1,0]，多选 [1,2]，数字 [0,4] 平均 2；排除旧版 999 和被替代 88；匿名与所有权|实际等于人工预期：stage2-regression-statistics.txt|
|check_stage2_baseline.py|按基线逐 ID 重读旧记录并 SHA256 比较|525 条旧业务记录全部存在且不变：stage2-data-integrity.txt|
|stage2_schema.py 连续两次|校验已有新集合文档，安装 validator/index，重复运行|均 PASS：stage2-schema-results.txt 与 stage2-schema-repeat-results.txt|

## 浏览器真实路径
本机 IAB 打开 127.0.0.1:8000；明确测试账号 qa_stage2_browser_1023。浏览器通过 UI 注册登录，建“QA 浏览器题库”，创建“QA 您是否参加”单选题并加入题库，创建“QA 第二阶段浏览器问卷”，选择指定题库及 V1，加入本卷、保存修订 2、发布 V1。通过固定链接开始填写，选“参加”，下一题、确认提交；结果提交记录 6adad9b432a08c9b3bfa79ca。原统计页显示提交 1、参与账号 1、参加 1、不参加 0。

随后 UI 修改题目生成 V2，选择 V1 查询使用，显示原卷 edit 与 current 两条引用；恢复 V1 生成 V3，父版本 V2、恢复来源 V1，V2 仍列在历史。截图见 evidence/stage2-browser-submitted.png、stage2-browser-statistics.png、stage2-browser-history.png。共享/撤销/越权由双账号 HTTP 测试覆盖，不冒称全部权限案例均在浏览器手测。

浏览器自动化有一次输入时页面刚刷新导致焦点目标失效；重新读取页面状态后填入并保存成功。这是测试控制时序问题，无代码绕过。展示旧报告时控制台曾有编码乱码，真实文件/JSON 内容未据此更改；新测试显式设置 PYTHONIOENCODING=utf-8。

## 未纳入及限制
教师变更第八节跨问卷统计按本轮指令延期；团队组织、公开市场、性能压测、生产 HTTPS 部署、灾难恢复演练未做。本轮不宣称整份第二阶段需求全部完成。原作业要求的完整代码、schema、配置、系统/API/逻辑、测试、报告、真实 AI 说明均有本功能块对应交付；最终课程平台 PDF 与 GitHub 推送未执行。
