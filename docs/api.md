# 第一阶段 API 索引

均同源 JSON；POST 除指定认证初始化外要求有效会话、精确 Origin、X-CSRF-Token。身份不接受客户端 userId。401未登录，404资源不存在/非本人，409状态/修订/幂等冲突，422定位输入错误，503数据库不可用且脱敏。细节及字段示例见 [认证](auth.md)、[管理](surveys.md)、[填写](filling.md)。在线 `/docs` 为 FastAPI 生成定义。

|方法/路径|用途|
|---|---|
|GET /api/auth/csrf|初始化/获取会话 CSRF|
|POST /api/auth/register、/login、/logout|注册、登录、退出|
|GET /api/auth/me|当前服务器会话身份|
|GET/POST /api/surveys|本人列表/创建|
|GET/POST /api/surveys/{sid}/edit|编辑稿/带 revision 保存|
|POST /api/surveys/{sid}/publish|发布指定 revision；重复发布不新增版本|
|GET /api/surveys/{sid}/versions|本人不可变版本列表|
|POST /api/surveys/{sid}/state|revision + action close/reopen/deadline|
|GET /api/shared/{token}|登录后当前开放结构，兼容预览接口|
|GET /api/fill/{token}|当前结构、自己的草稿及填写状态|
|POST /api/fill/{token}/start|开始/恢复，显式 repeat/new_attempt|
|GET /api/fill/{token}/drafts/{vid}|自己的草稿，旧版只读|
|POST /api/fill/{token}/drafts/{vid}/action|attempt_id/revision，save/next/goto/finish|
|POST /api/fill/{token}/drafts/{vid}/submit|attempt_id/revision/request_key，原子提交或幂等重放|
|GET /api/surveys/{sid}/statistics|本人当前发布版整卷统计|
|GET /api/surveys/{sid}/versions/{vid}/statistics/questions/{qid}|本人指定已固定版本单题统计|
|GET /api/health/live、/database|独立存活、真实只读 ping|

统计返回 survey_id/version_id/version_number/title/anonymous/submission_count/participant_count/questions；每题 question_id/title/type/answered_count。选择题 options=[{id,label,count}]；填空 values；数字另有 valid_count/average(null表示无数据)。没有填写者、会话、参与状态、答卷标识、提交时间或序号。问卷/题目结构 ID 不属于用户身份字段。未发布整卷统计409，错误版本或题目404；关闭/到期不限制创建者读取统计。


## 第二阶段最终增量说明

原说明保留。题库/不可变题版本/共享见 [stage2-system.md](stage2-system.md)；跨问卷统计的系统、MongoDB索引与schema兼容、配置、API、快照聚合与权限见 [stage2-final-statistics.md](stage2-final-statistics.md)。最终需求覆盖及真实验收见 [stage2-final-coverage.md](stage2-final-coverage.md) 和 [stage2-final-tests.md](stage2-final-tests.md)。
