# 第二阶段完整需求覆盖表

本表对照两份教师原文及本轮确认规则。实现完成不等同课程评分或未执行部署已验收。022 原始证据保留；本轮输出均使用 stage2-final 前缀。报告为 Markdown，不改用户 Word，不导出 PDF、不推送。

|教师要求|实现与入口/API|本轮真实证据|范围或限制|
|---|---|---|---|
|原作业一、二：在线问卷与增量演进，不得推倒重做|原 FastAPI/PyMongo、surveys/survey_edits/survey_versions/填写引擎保留；新增题资源和只读统计|stage2-final-start.json；改动摘要；旧数据校验|保留未提交022改动，不回退HEAD|
|原作业三：所有业务数据 MongoDB、不用关系库/现成问卷系统|原驱动与复制集事务；新增集合仍在同库|数据库 schema、实际 MongoDB 测试|文件仅代码/配置/测试证据，不存业务状态|
|原作业四：分集合、合理冗余、可配置逻辑、解释 MongoDB|身份/编辑稿/发布/草稿/历史/题资源分离；规则随快照；来源引用+快照|stage2-system.md、stage2-final-statistics.md、schema|不声称 MongoDB 在所有场景优于关系库|
|原作业五：真实 AI 日志及说明|stage2-final-ai-log-draft.md；报告“AI与我的贡献”|实际失败、执行与修改记录|不虚构手写代码；总日志.txt未改|
|原作业六：创建、添加题、跳转、校验、提交、统计测试|原脚本及新增专项/浏览器脚本|final-unit、check_surveys、check_filling、check_statistics、cross、browser|不是只验接口200|
|原作业七：完整代码/schema/配置/文档/测试/报告|README、原文档+增量系统说明、最终报告、final-manifest|文件清单与SHA256|排除真实.env/.local/.venv/凭据/缓存|
|原作业八：评分维度|覆盖数据库、逻辑、测试、文档和AI说明|本表与报告|不自行给出课程分数|
|初始一：注册/登录/账号字段/仅本人问卷|auth.py、/api/auth/*、/api/surveys|stage2-final-check_auth.txt、check_surveys|密码散列；会话/CSRF沿用|
|初始二：标题/说明/匿名/列表/发布/截止/关闭/固定URL/登录填写|surveys.py、/manage、/s/{token}|check_surveys、check_filling、browser|固定链接依然指向当前发布|
|初始三 单选：选项/必答|survey_models.py、filling_engine.py|27单元、check_filling|发布和填写均后端校验|
|初始三 多选：最少/最多/恰好|同上|27单元、check_filling|恰好与范围互斥|
|初始三 填空：文本长度、数字范围/整数|同上，text/number两种实际输入|27单元、check_filling、cross人工数字样本|数字0有效，空白不当0|
|初始四：单选/多选/数字跳转，规则可配置|原rules、状态机不替换|check_surveys、check_filling、unit|不支持文本条件跳转，原文未要求|
|初始五：顺序/跳转/错误提示/保存/并发/匿名/重复|fill_drafts/participations/submissions；原action/submit|check_filling、check_auth|每次成功提交追加，草稿独立|
|初始六：整卷/单题、选项计数、文本内容、数字均值|原 statistics.py /api/surveys/{sid}/statistics 与固定版单题接口|stage2-final-check_statistics.txt|原单卷每账号最新提交口径保留|
|变更一：保存独立题/选用/多卷复用|questions.py、/library、原/manage选题|check_stage2 S01/S02；cross C02；browser|旧题可显式导出，无强制转换|
|变更二：分享给其他用户复用|/api/questions/{id}/share、原问卷来源校验|check_stage2 S02/S07；cross C08|共享不授予修改原题或他人答卷权限|
|变更三：旧发布不可改，修改产生新题内容|question_versions、原survey_versions不可变|check_stage2 S03/S08；全旧数据哈希|API不可变，不声称管理员无法改库|
|变更四：修改历史/父来源/恢复|/questions/{id}/versions、parent/restore/derived来源|check_stage2 S03；browser版本切换|恢复追加新版，不删除未来历史|
|变更五：不同版本共存|source固定题版本，问卷快照不自动更新|check_stage2 S03；cross C06；browser|统计也不跨题版本混算|
|变更六：被哪些问卷使用|/questions/{id}/usage|check_stage2 S04；cross权限测试|本人详情、他人匿名引用计数，不含答卷|
|变更七：题库创建/管理/归类/选题/更新|/question-banks、版本选择与显式换版|check_stage2 S01/S07；022及本轮浏览器|移除条目不删题；无团队市场扩展|
|变更八：单题跨问卷统计与年龄分布|question_statistics.py、/question-statistics/{qid}、scope/query|cross C01–C11人工预期与并发；browser|只本人问卷，单题版本，数字频数、均值及分页|

## 本轮确认规则补充映射

|规则|校验方式|
|---|---|
|明确题ID/题版本ID，同名/派生/恢复不合并|C06及接口source匹配；无来源旧题在excluded说明|
|跨卷同账号分别贡献，卷内最新整份提交，空白不回填|C02 [0,4,8]、C04空白与草稿|
|默认当前，历史每卷仅一个替换|C05；重复survey selections返回422|
|只本人问卷，显式ID逐项归属校验|C08两账号与跨卷版本伪造404|
|撤销后本人快照可统计，不开题库访问|C08 revoked library404、own stats777|
|四题型、空值、0、分母、频数及分页|C01–C04及UI；选项比例分母为有效回答数|
|同卷重复实例只取一个|C07首个2，切换第二个6，不得计成两份；这是本轮实现默认值|
|同一请求固定结构与答案读取范围|C10真实并发发布/提交，事务快照旧2，下一HTTP新9|
|较大范围不静默截断|C11硬上限413；行分页不改变完整范围总数/均值|

真实输出引用见 stage2-final-tests.md；浏览器若失败会单独保存原失败与复测，不将待验证标为通过。
