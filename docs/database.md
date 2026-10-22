# MongoDB 数据设计与 schema 说明

以下是实际应用结构说明；约束由 Pydantic/服务端和索引共同保证，不冒称安装了 MongoDB JSON Schema validator。结构字段定义见 `backend/survey_models.py`，索引建立见 AuthStore/SurveyStore.ensure_indexes。

|集合|主要字段与职责|约束/索引|
|---|---|---|
|users|_id、username、password_hash、created_at；测试账号可含 test_run_id|username 唯一|
|sessions|令牌摘要 _id、user_id、csrf_token、expires_at；不存原令牌|expires_at TTL，应用主动过期检查|
|surveys|固定 _id、owner_id、share_token、currentVersionId、version_number、closed、deadline、state_revision、fill_fence|share_token 唯一；owner_id/created_at|
|survey_edits|_id=survey_id、owner_id、revision、structure、updated_at、publish_fence|_id唯一；修订号条件更新|
|survey_versions|_id、survey_id、number、edit_revision、structure、published_at|survey_id+number 唯一；survey_id+edit_revision 唯一|
|fill_drafts|survey_id、version_id、user_id、attempt_id、revision、status、state|survey_id+version_id+user_id 唯一|
|participations|同上作用域、submission_count、latest_submission_id|survey_id+version_id+user_id 唯一|
|submissions|survey_id、version_id、user_id、sequence、answers、attempt_id、draft_revision、request_key/hash、submitted_at|version_id+user_id+sequence 唯一；version_id+user_id+request_key 唯一|

`structure` 内嵌 title/description/anonymous/allow_repeat/questions；每题有稳定 id、type、title、required、options、限制、rules。选项和规则也有稳定 id。题序由数组顺序定义，移动不更换标识。answers 以题目 id 为键；数字以原始字符串保存（含零），提交前验证完整有限值。普通题目 ID 无填写者身份含义。

## 嵌入与引用取舍

完整问卷读取与规则校验需要题、选项、规则一起出现，嵌入版本文档可保留一致结构，不需要按题连接集合。版本是有界结构（配置限制题量），编辑稿独立可变。历史版本、草稿、提交无限增长部分独立集合引用稳定问卷和版本；不追加到单一巨大文档。账号/会话/参与状态生命周期不同，独立存储。虽使用引用，但不将每个选项拆为关系表，避免为一次整卷读取进行大量连接。

发布事务创建版本并更新指针；旧版本只读无修改接口。保存编辑稿不会修改已发布结构。匿名/重复开关绑定版本。每个版本独立填写资格，旧草稿只读、新版空白。数据兼容以版本引用保证；第二阶段需基于该结构迁移/扩展，保留现有历史，不能推倒重做。

## 一致性

草稿 CAS 及 attempt_id 防止多窗口覆盖、迟到保存复活和污染新尝试。提交事务原子追加历史、递增序号、更新最新引用、消费草稿。序号按账号+版本递增，比毫秒时间更明确；同一时间仍由序号决定最新。幂等键按账号+版本唯一，同键不同尝试/修订拒绝。参与引用是受事务维护的冗余，可由历史重建；本轮统计直接读取历史，不依赖引用无误。

发布/关闭与提交共同写 surveys，事务冲突重试后重新检查状态与版本。截止以提交事务协调写后服务器 UTC 判定点为准，不声称网络响应时仍未过期。索引不能代替权限、无环检查、必答校验、运行状态检查或多个集合的原子提交。

## 统计查询

在只读 snapshot 事务中：读取自己拥有的 surveys → 固定版本 → 读取属于该问卷的版本 → submissions 按 survey_id/version_id 匹配 → facet 一支 count 全部成功提交，另一支按 user_id 升序/sequence 降序排序并 group user_id 取 first answers，随后投影掉 user_id。Python 按该版本每题汇总已选最新答案。先选整份最新答卷，再逐题过滤空值，不能先过滤非空再选最新。

每题有效非空答案复用填写校验。单选计人数、多选计选择次数；文本独立排序保留原文；数字转有限值后用 Decimal 求平均再返回浮点数，避免直接浮点累加溢出。零有效记录平均值 null。没有百分比。两次独立请求之间数据可更新；单次请求内总数/参与数/题目均来自同一快照。单题 API 必须再次验证所有权及版本属于该问卷，不提供历史切换界面。
