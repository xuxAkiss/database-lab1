# 跨问卷统计 系统 数据库 API 与关键逻辑

本说明补充原 system.md/database.md/api.md/logic.md 与022的 stage2-system.md。核心问卷、发布、填写、提交和原单卷统计不变。新增 backend/question_statistics.py 和 frontend/question-statistics.html/js，原 main.py 注册路由、survey_store 增加索引；题库页与原问卷题实例提供跨卷入口。

## 配置与依赖
业务运行环境/.env不变，仍需 MongoDB 复制集事务。原启动命令不变；此功能无新增运行时Python依赖。浏览器测试专用 Playwright 安装在项目 .venv，版本见 requirements-test.txt；复现使用本机 Edge，无下载浏览器或重建环境。原 requirements.txt 不混入测试工具。

新增 MongoDB 索引 submissions `(survey_id:1,version_id:1,user_id:1,sequence:-1)`，名字 cross_statistics_latest，原 SurveyStore.ensure_indexes 幂等安装。新增统计无需集合或业务字段；022的 source、题版本、问卷快照和历史答卷足够。原 schema 与022 validator 不变。

## 已确定业务口径
精确匹配 question_id + question_version_id。派生题属于新身份，恢复产生新版，两者均不因文字相同合并。题目整体页可切换版本，每次统计一个明确题版本。自己卷内同一题版本多个实例默认选择问卷顺序首个，响应列出所有可选实例并提示，页面可切换；这是本轮实现默认值。

每个纳入问卷发布版本，按账号取 sequence 最大的最新成功整份 submission，然后读取所选实例的答案。先选整份最新记录再看答案，不能先过滤空白；因此最新留空不回填旧值。草稿不进查询，数字0有效，空白不作0。跨卷不按账号去重，UI称回答数而不是独立人数。每卷只选一个发布版本，历史选择替换该卷当前版本；关闭/截止不影响已收集统计。

无当前发布、不含该题版本、缺乏可靠source的旧题不纳入，并报告excluded原因。no_reliable_source表示当前版没有匹配来源且包含未知来源旧题，不代表推断这些旧题同源。历史数据不回写。

## 授权与撤销
统计只扫 owner_id 等于当前用户的 surveys，所有显式 survey_id/survey_version_id 校验绑定关系；其他人资源一律404，不能利用共享题查看作者私有问卷。题库有权限时可以查看该题版本的空结果；撤销后，仅当自己已保存编辑稿/发布快照确有该题版本，才允许从快照获取必要题定义和统计。不会返回原作者身份、父来源或其他不可访问题版本。原题库接口仍404。

统计响应不含user_id、owner_id、username、session、submission_id等身份/答卷关联字段；文本内容是答案本身，可能由填写者主动输入身份信息，系统并不声称文本自动脱敏。数字/文本逐题独立排序，不提供跨题关联。

## 一致性和聚合步骤
1. 使用原 SurveyStore.transaction，readConcern=snapshot、writeConcern=majority，固定本人问卷列表、当前指针、所有读取到的发布快照。
2. 校验题目版本和权限，再将每卷当前指针替换为可选的一个显式历史版本；同卷重复选择拒绝422。
3. 在同一事务里按精确source匹配实例，校验快照定义一致，默认首个或用户明确实例。
4. submissions 聚合 match(survey_id,version_id)，sort(user_id,sequence降序)，group按user_id取first整份answers，project移除身份。随后只取本次选定实例，空白/无效值单列，有效值聚合。
5. 同一快照返回纳入问卷/发布版本/实例、各卷最新答卷数及有效/空白/无效总数。并发切版或提交不会使本次结构与答案混配；下次查询可看到新数据。只读请求可能被事务机制重试，成功结果仍来自一次完整快照。

数字用 Decimal 累加/平均（精度40）后转JSON数值；频数按数值归一，0/0.0同一数值；不是按文字归类。单选/多选计数，分母为有效回答数，多选比例和可超过100%。文本按内容排序分页。无需把聚合结果写为业务集合，避免缓存与答案不一致。

MongoDB适合保留题型多样的嵌入答案和不可变结构快照。新增索引服务精确版本的最新记录读取，source引用用于同源识别，快照冗余保障撤销后可用和历史不变；不迁移到关系库，不增加平行问卷系统。

## 明确容量边界和分页
单次最多本人200份问卷、1000个发布版本、所纳入10000份最新整份提交、2000000字符有效内容；超过返回413 statistics_limit，不返回局部统计。不静默截断其他人的数据也不列出其他人问卷。数据库聚合 maxTimeMS=5000、原事务10秒超时仍有效，超时错误不视为零结果。

page_size为1–100，默认50；page从1开始。数字rows为频数行，文本rows为回答内容；rows_total是全量行数、page_count明确页数。answered_count/average/options始终来自完整范围，非当前页。每次翻页是新快照，computed_at和全量计数同时更新；未承诺跨多次HTTP翻页冻结答案，页面明确说明。后续若需要不可变导出，应增加显式报告快照机制，当前不伪称已具备。

## API
- GET `/api/question-statistics/{qid}/scope`：会话鉴权，返回可用题目版本（本人快照或当前题库权限）、本人含该题的发布版本/实例选择，current_survey_version_id标明当前版。不返回他人范围。
- POST `/api/question-statistics/{qid}/query`：只读结构化查询，仍要求现有Origin和X-CSRF-Token。请求 `{question_version_id, selections:[{survey_id,survey_version_id,instance_id:null}],page:1,page_size:50}`。selections仅覆盖所列卷，其余本人问卷默认当前；显式无匹配题版本的卷列入excluded，若同时指定不匹配实例则422。
- 响应包含 question_id/question_version_id/question_version_number/title/type、included_survey_count、included（明确问卷发布版本与实例）、excluded、latest_submission_count、answered_count、empty_count、invalid_count、computed_at、scope、limits、分页信息。数字附average/distribution_total/频数rows；文本rows；选择题options和proportion_denominator。
- 401未登录，403 CSRF，404无权/不存在，409来源快照不一致，422非法选择或输入，413明确容量上限。旧接口保持原行为。

入口 `/question-statistics/{qid}?version={question_version_id}`；从 `/library` 选定版本可进入，原 `/manage` 已引用题实例的统计链接在撤销共享后仍能使用本人快照。

## 兼容与恢复
纯增量索引和读接口，不改历史结构/校验值/答卷。022数据不强制转换，旧无来源数据仍可用原单卷统计。当前代码兼容旧数据不等于可无条件降级到第一阶段：旧模型拒绝source。需先停写、完整备份，在副本验证兼容补丁和回退路径，保留所有新历史；没有清库式回退方案。本轮验证旧记录哈希和真实事务行为，未进行生产备份恢复演练。
