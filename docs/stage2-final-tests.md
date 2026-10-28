# 第二阶段整体验收测试记录

日期：2026-10-23。测试使用项目原 .venv、实际 MongoDB 8.3.11 单节点复制集、HTTP 127.0.0.1:8000；没有用 mock 数据库。前端为本机 Microsoft Edge，由项目 .venv 的 Playwright 1.64.1 驱动。所有写入均为新增 qa_ 标记测试账号/问卷/题目，不清库。022输出和阶段一输出保留。

## 跨卷自动验收
执行 `python tests/check_cross_statistics.py`。实际日志：stage2-final-cross-initial.txt。每项先输出 EXPECTED 再断言 ACTUAL，C02 完整JSON记录题目ID/题版本/问卷版本/实例与频数。C10使用实际数据库并发提交，不以接口200代替数值断言。

|编号|步骤与输入|人工预期|实际|
|---|---|---|---|
|C01|创建数字题V1，在本人A/B两卷发布但无答卷|回答0、均值null、空频数|通过|
|C02|A甲先10后0，A乙4，B甲8，均经原HTTP填写/提交|[0,4,8]，回答3、均值4、频数各1|通过；跨卷甲不去重|
|C03|同三份最新整卷，单选yes/no为yes/no/yes，多选yes+no/no/yes，文本new/beta/gamma；page_size=1|单选[2,1]、多选[2,2]、文本排序beta/gamma/new；数值第二页4，完整均值仍4|通过|
|C04|A甲最新整卷各题留空，再保存数字99草稿未提交|有效[4,8]均值6，空白1，既不回填0也不计99|通过|
|C05|A发布新版并提交100；显式选A旧发布替换当前|默认[100,8]均值54；历史[4,8]均值6，响应指出旧版ID|通过|
|C06|A改用题V2回答20；恢复旧内容形成题V3；另建同名题888、派生题999、无source旧题555|V1仅B8、V2仅A20、恢复V3无回答；888/999/555均不混入|通过|
|C07|B同版重复实例n=2、n2=6|默认首个2且回答1；切第二实例6且回答1；重复选择同卷422、错误实例422|通过|
|C08|共享给乙，乙自己的私有卷答777；双方伪造对方卷或卷版本；撤销后题库访问与本人统计；伪造来源定义|甲仍2、乙777；越权404；撤销题库404但乙自己的统计777；伪造来源422；响应无身份字段|通过|
|C09|关闭并设置截止为过去|已有均值2仍可读|通过|
|C10|实际snapshot事务读结构后、聚合前，另一个HTTP流程把B切版并提交9|本次仍旧均值2；下一次HTTP均值9；不混配|通过|
|C11|将服务上限临时降为0，真实库有答案时调用统计服务|413且不返回局部总计|通过；这是上限分支测试，非1万条压力测试|

C10只在测试进程拦截 Collection.aggregate 以安排并发时点，再执行原真实聚合；没有替换数据库或返回伪造答案。其余主要统计通过HTTP完成。C11临时替换容量常量，数据库仍真实，明确区别于完整HTTP容量压测。

## 原功能与022回归
|执行|输入、预期与检查|实际输出|
|---|---|---|
|unittest discover -s tests -p test_*.py -v|原四题型校验、跳转图/状态机、边界与草稿行为|27项通过，stage2-final-unit.txt|
|tests/check_auth.py|注册/规范化/密码哈希/重复用户名/登录/会话轮换/注销/CSRF/过期及两账号|stage2-final-check_auth.txt 全部PASS|
|tests/check_surveys.py|创建旧无source问卷、添加题/规则、CAS、发布快照、事务失败回滚、截止关闭和越权|stage2-final-check_surveys.txt 全部PASS|
|tests/check_filling.py|四题型输入、跳转、必答、草稿恢复、并发、多次历史、事务回滚、切版/关闭顺序|stage2-final-check_filling.txt 全部PASS|
|tests/check_statistics.py|人工预期：3次提交/2账号，单选[1,0]、多选[1,2]、数字[0,4]均值2，旧999及被替代88排除|stage2-final-check_statistics.txt 全部PASS|
|tests/check_stage2.py|022 S01–S09：题库CRUD范围、共享/撤销、分支恢复、版本共存、并发、实例跳转与旧题导出|stage2-final-check_stage2.txt 全部PASS|
|tests/check_final_integrity.py|逐条重读原阶段一及本轮前022业务记录，比较SHA256，不计自然变化的sessions|stage2-final-integrity.txt，执行结果见该文件|

## 浏览器主路径及修复
执行 `python tests/check_cross_browser.py`，使用独立无持久用户配置的headless Edge，所有建题、建卷、填写和选择均通过真实DOM交互；没有API预置答案或直接修改前端内存。

路径：注册/登录 → 独立数字题V1 → 本人A/B两卷复用发布 → 填0、8 → 跨卷页面均值4 → A发布第二版填10 → 默认均值9 → 选择A历史发布V1均值4 → 独立题保存V2 → A显式换题版本并发布第三版填20 → 统计选择题V2均值20、纳入1卷。

初轮交互断言通过，截图人工检查发现沿用的sticky提示条在整页截图遮住范围说明、频数表列距太小。增加仅跨卷页使用的 question-statistics.css：提示条改普通流、表格边框与间距、移动端分页布局；显示时间统一UTC+8，查询提示去掉不必要内部技术词。保留 `*-initial.png` 和初测日志，再执行同一路径复测。

|检查|结果与证据|
|---|---|
|页面身份/非空|标题与h1为跨问卷题目统计，有实际结果|
|交互与数值|均值4→当前9→历史4→题V2为20，逐步断言|
|控制台|无pageerror；登录前/auth/me的预期401单独记录，不算未解释错误|
|桌面|1280×900；current/history/question-v2截图|
|移动端|390×844；未横向溢出，mobile截图|
|初测/复测|stage2-final-browser-initial.txt、stage2-final-browser-retest.txt；详细环境和QA ID在stage2-final-browser-results.json|

原022截图未覆盖。新截图位于 docs/evidence/stage2-final-browser-*.png。Firefox/Safari、生产HTTPS、负载压力测试和灾难恢复演练未执行。

## 可复现顺序
1. 按 README 启动原MongoDB复制集与后端（若已运行不重复启动）。
2. 新环境按原requirements安装运行依赖，浏览器验收另外在项目.venv安装requirements-test.txt并安装本机Edge。
3. 运行本页列出的脚本。集成脚本新增QA数据并保留，不用于生产库，不删除既有数据。
4. 检查进程退出码及每项PASS/断言，不能只看PowerShell管道退出状态。所有本轮测试启动命令保存Python退出码后再输出日志。
5. 数据哈希基线只适用于本项目当次保留的数据。克隆后空库不应运行旧数据完整性测试并声称通过，应先建立自身基线。
