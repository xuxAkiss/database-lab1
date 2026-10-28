# 第二阶段系统 数据库 API 与关键逻辑

## 范围与配置
本文件是第一阶段 system.md、database.md、api.md、logic.md 的增量说明。原文和证据保留。后端仍是 FastAPI/PyMongo，前端原生 HTML/JS，所有业务数据仍在 MongoDB，无关系数据库或现成问卷框架。账号、发布、填写状态机、历史提交、单卷统计继续调用原模块；未实现跨问卷统计。

依赖与 .env 不变，沿用 README 的 MongoDB 复制集与 AUTH_ORIGIN 配置。运行项目 .venv 中 Python；启动应用仍为 `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`。新增入口 `/library`，原 `/manage` 增加题库选择。部署新代码后执行 `python dev/stage2_schema.py` 安装 schema/索引；可重复执行，预检不合格时停止而不删除数据。初次 API 访问也会建立所需索引，但数据库 validator 需此脚本安装。

## 数据结构前后变化
旧结构 `survey_edits.structure.questions[]` 为 `{id,type,title,options,required,校验字段,rules}`。新结构仅可选增加 `source:{question_id,version_id}`，两个 ID 为 24 位 ObjectId 字符串。`id` 仍是本卷实例 ID，不能拿来源 ID 代替。`survey_versions` 仍按发布事务复制全卷不可变快照。无 source 的旧编辑稿、版本和填写数据正常读取，不赋予猜测的同源关系。

|集合|字段与约束|用途|
|---|---|---|
|questions|ObjectId _id/owner_id；shared_with 为用户 ObjectId 数组；number 为最新已保存序号；created_at；access_fence 为事务授权协调计数|稳定身份、所有权和共享 ACL，无可变题目内容|
|question_versions|ObjectId _id/question_id；number；definition；parent_version_id、restore_version_id；derived_from；可选 legacy_origin；created_at|保存一次即不可变；同一身份下可有不同父节点的分支|
|question_banks|ObjectId _id/owner_id；name；question_ids 字符串数组；revision|个人分类；题库成员是题身份，使用时明确选择版本|
|survey_edits / survey_versions|原字段不变，仅题实例可带 source|内容快照及确切来源同时保留，撤销共享后原快照仍可靠|

`definition` 保存原 Question 支持的 type/title/required/options/min_choices/max_choices/exact_choices/min_length/max_length/minimum/maximum/integer_only；不保存 id、rules、source。字段适用性、选项引用、数值范围仍由 `validate_structure` 检查。MongoDB validator 见 stage2-mongodb-schema.json；数据库负责基本 BSON 形状，应用负责跨字段/引用/所有权/不可变性。直连数据库的管理员仍可修改记录，应用没有版本修改和删除 API，不能把应用不可变性称为数据库防管理员篡改。

新索引：questions.owner_id、questions.shared_with；question_versions `(question_id,number)` 唯一；question_banks.owner_id；survey_edits 与 survey_versions 的 `structure.questions.source.question_id` 多键索引。所有原索引继续存在。

MongoDB 的题型可变字段天然适合文档；一次读取版本即可获得题目定义。稳定资源与不断增长的版本分开，避免无限增长的单文档历史数组。题库只引用身份避免复制完整历史。问卷快照的冗余是故意的：保证发布、填写、历史校验不依赖题库实时状态或共享 ACL。这不是另建平行问卷系统。共享列表和题库成员数组适用于本次个人题库规模；大规模组织权限/分页/容量治理未纳入本轮。

## 关键事务与权限
创建独立题和初始版本在原 SurveyStore.transaction 内提交。创建新版本先校验父版本属于同一题，在事务中原子递增 questions.number 并插入版本。并发冲突由 MongoDB with_transaction 重试，唯一索引兜底；不会覆盖父版本或丢弃分支。最新序号只是最新保存，不代表某分支必须替代另一分支。

恢复以 restore_version_id 指定的内容生成新版本，同时记录本次操作的 parent_version_id。恢复不删除后续历史。派生新身份的 derived_from 保存原题及原版本；接收者成为派生题作者，不能写原题。新版本 POST 是一次保存命令，网络结果不确定时应先查历史确认，不能保证重复发送不会生成另一个相同内容版本。

问卷创建/保存继续写原集合。新引用要求服务器读取可访问题目、版本并精确比较规范化 definition。在同一事务写入 access_fence，使并发撤销与新授权引用串行化；先完成保存的快照可以继续用，先撤销则后续保存拒绝。已有编辑稿内“相同实例 ID、来源、内容”的快照不再要求当前共享权限，可改本卷规则/标题和重新发布。换实例、换来源、改定义必须重新授权。解除来源意味着此实例成为本卷独立题，不能继续冒用旧来源；有权限时可从旧来源派生新题再替换。

导入创建新的实例 ID、清空规则；换版保留原实例 ID 和本卷 rules。保存与发布仍全量校验规则选项、目标存在、自引用、循环、类型和数字条件重叠。失效时返回 422，不静默删除规则。编辑稿换版不会改变线上，必须发布明确修订。

共享指定规范化注册用户名，仅作者可授予/撤销，接收者获得读取版本与在自己问卷中使用权限。所有写 API 沿用会话、精确 Origin 与 X-CSRF-Token 校验。无权资源统一 404；未登录 401；CSRF 403；修订冲突 409；输入/结构错误 422。

使用查询从原编辑稿及发布集合实时查询 source，不维护可能失步的计数表。自己的引用返回问卷 ID、标题、实例、题版本和编辑/当前/历史类别；他人只返回每类别的引用次数，不含私有问卷 ID、标题、账号、分享链接、答卷或参与者。次数不是问卷去重数或人数。同卷多个实例分别计数，历史每次发布分别计数。这是本轮选择的最小匿名使用信息授权，不授予统计权限。题目作者/当前接收者可查；共享撤销后接收者不能查题资源用量，但自己的问卷仍可在原管理页访问。

## 旧题关联与恢复方案
`POST /api/surveys/{sid}/questions/{instance_id}/export` 只从自己已保存编辑稿导出，revision 必须匹配。事务创建新题及 V1，记录 `legacy_origin:{survey_id,edit_revision,instance_id}`，并给原编辑稿实例绑定 source、递增编辑修订。保留本卷规则，不带入独立 definition。相同请求重复执行返回已建立的来源；不是全库迁移，不按标题合并。legacy_origin 仅对题目作者返回，避免共享泄露私有问卷 ID。

旧发布、旧答卷及其校验值完全不更新。可以证明此次导出来自哪个编辑修订，不能证明更早的相同文字历史题属于同一家族；旧发布无 source 就继续表示未知。数据库不需要批量迁移，也不要求先转换全部旧题。新集合/索引安装是增量、幂等、先校验。

故障时事务回滚，不会出现已关联但没有版本的半成品。保留 stage2-baseline.json 与测试前备份；只读运行 check_stage2_baseline.py 核对原记录。需要撤回关联时，保留新集合和历史，使用当前应用编辑稿显式解除 source 后另存（保留发布历史）。不要直接部署第一阶段代码覆盖新增数据：旧 Pydantic extra=forbid 不能解释 source。生产回退应先停写、备份全库，在副本验证向前兼容补丁；本轮没有进行灾难恢复演练，不承诺未测试的全库还原。

## API
下表路径均在 `/api` 下；GET 不需 CSRF，POST 沿用原会话+Origin+CSRF。具体完整请求模型同时可在 `/docs` 查看。

|方法 路径|输入|输出/行为|
|---|---|---|
|GET /questions|无|questions 数组：id、owned、latest|
|POST /questions|definition 为原 Question 形状，含占位 id、空 rules；可选 derived_question_id/derived_version_id（必须成对）|201，新版本 `_id,question_id,number,definition,parent_version_id,restore_version_id,derived_from,created_at`|
|GET /questions/{id}/versions|无|按序号升序全部可访问版本；作者可见 legacy_origin|
|POST /questions/{id}/versions|parent_version_id；definition 与 restore_version_id 二选一|201，不可变新版本；只有作者可调用|
|POST /questions/{id}/share|username、enabled 布尔|shared 布尔；true 授予，false 撤销|
|GET /questions/{id}/shares|无|仅作者可读用户名列表|
|GET /questions/{id}/usage|可选 version_id 查询参数|own_references 与 other_reference_counts|
|POST /question-banks|name|201，id/revision|
|GET /question-banks|无|banks：id/name/question_ids/revision，仅自己的题库|
|POST /question-banks/{id}/rename|name/revision|新 revision，冲突 409|
|POST /question-banks/{id}/members|question_id/present/revision|新 revision；加入检查访问，移除不删题|
|POST /surveys/{id}/questions/{instance}/export|revision|201，source/revision/replayed；原子旧题关联|
|POST /surveys 与 /surveys/{id}/edit|沿用原结构；question 可附 source|服务器验证来源、快照和原结构；edit 继续 CAS|

选题本身是客户端读取题库成员、读取题版本、构造本卷实例；实际引用在原问卷保存接口提交成功时建立，无第二套问卷创建 API。

示例：`{"id":"instance-1","type":"number","title":"年龄","required":false,"options":[],"minimum":0,"maximum":120,"integer_only":true,"rules":[],"source":{"question_id":"题资源的24位ID","version_id":"固定版本的24位ID"}}`。快照须采用版本 definition 的全部规范化字段；前端会直接复制版本数据。示例中的 ID 为说明占位符，不能直接提交。
