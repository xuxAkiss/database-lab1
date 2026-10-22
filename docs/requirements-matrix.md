# 第一阶段原要求对照

来源：2026-10-21 本轮重新提取 `大作业一.docx` 的 word/document.xml（含正文/表格文本），未渲染原 Word 排版。原件摘要见 source-provenance.json。下表测试证据文件名对应本轮实际运行输出，状态以报告与输出为准，不代表所有组合均已穷举。

|原文位置/明确要求|实现文件/入口|可复核证据|
|---|---|---|
|初始需求一：注册、登录、用户名/密码/注册时间，只看自己问卷|auth.py；/api/auth/*；surveys.py owner过滤|stage1-auth-results.txt；check_auth.py|
|初始需求二：标题说明、匿名、列表、发布、截止、关闭、固定链接、填写须登录|survey_models.py/surveys.py；/manage；/s/{token}|stage1-publish-results.txt；check_surveys.py|
|初始需求三：单选选项与必答、多选最少/最多/恰好|survey_models.py/filling_engine.py；surveys.js/fill.js|stage1-unit-results.txt、stage1-filling-results.txt|
|初始需求三：文本长度、数字上下界及整数|同上；answer_error|同上四类型边界测试|
|初始需求四：可配置单选、多选、数字跳转，不写死|rules内嵌版本；filling_engine.py|unit：完全匹配、多目标、连续、普通顺序、已访及改答来源测试；filling集成|
|初始需求五：顺序/跳转、错误提示、提交、每次保存、多人、匿名及允许重复|filling.py；草稿CAS、提交事务/幂等、历史追加|stage1-filling-results.txt，包括真实并发、回滚和发布/关闭先后|
|初始需求六：整卷/单题、单选人数及回答数、多选次数、填空内容/数字平均值|statistics.py、statistics.html/js；管理入口|stage1-statistics-results.txt；statistics-tests.md；浏览器记录|
|技术要求：MongoDB持久化、不用关系数据库/现成问卷框架|requirements.txt、backend全模块|database.md；pip check；真实接口使用MongoDB|
|MongoDB设计说明：取舍、适用性，不全部放同集合（建议）|8集合、结构内嵌/历史引用|database.md；schema字段/索引说明|
|测试要求：创建、添加、跳转、校验、提交、统计及步骤|tests/*.py|test-cases.md及原始输出|
|提交：可运行后端、schema、配置，系统/API/关键逻辑、完成报告|README、docs、源码/固定依赖|stage1-report.md、baseline-manifest.json|
|AI要求：工具、提示、结果、修改、本人贡献真实说明|ai-usage.md；只读参考总日志|source-provenance.json；模块历史记录；本轮真实日志|
|第二阶段不得重做，需保留核心/数据、记录迁移与回归|本轮仅建立基线，不预实现新需求|baseline-manifest.json；后续沿本项目演进|

## 用户选择（不是教师原文细节）

匿名后台保留账号但创建者不可见；每账号视为一人；成功提交全历史保留、统计版本内按账号最新；固定链接切不可变版本，旧草稿只读；完全匹配多选、连续跳转优先、去重、禁止循环、已访目标不自动入队、连锁撤销保留独立来源；同版重开恢复。

“每次填写保存”为教师原文，追加每次成功提交历史是用户最终接受的解释；早期覆盖方案已撤销。统计按账号最新是用户确定的口径，不能声称原文明确如此。第二阶段原文只有在现有成果上扩展的要求，没有可提前实现的新业务清单。

评分原文：MongoDB35、后端25、测试10、文档15、AI15；两阶段相同标准，总分0.3×第一阶段+0.7×第二阶段。不自行预测成绩。
