# 问卷编辑、版本发布与管理（本轮实现）

本轮基于现有 FastAPI / 同步 PyMongo / 原生 HTML、CSS、JavaScript，沿用原会话、CSRF 和 MongoDB。没有新增依赖，没有实现填写草稿、答卷、运行时跳转、撤销或统计。

## 操作入口与运行

- 账号：http://127.0.0.1:8000/ ，登录后进入“管理我的问卷”。
- 管理：http://127.0.0.1:8000/manage ，仅管理当前账号拥有的问卷。
- 分享：管理页显示固定 `/s/{share_token}`；任何已登录账号可读取开放问卷的当前发布结构。本轮只有只读预览，没有填写或提交。
- 健康：http://127.0.0.1:8000/health 。

从 `D:\数据管理\work1\workspace` 运行（已有进程时不要重复启动）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\dev\mongodb\Start.ps1
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

创建问卷 → 添加题型、编辑题目和选项 → 配置限制及规则 → 保存编辑稿 → 发布已保存修订。发布后保存修改不会改变原发布版；再次发布才切换同一链接。题目可上下移动，ID 不随位置改变；删除仍被规则引用的题目或选项后，须修正规则才能保存。界面不支持直接改 ID 或改已有题型；不同题型需新增题目。编辑冲突返回 409，不自动覆盖；先复制待保留内容，再重新打开合并。离开未保存页面有提醒，请求期间禁止编辑以免覆盖新输入。

## 三集合组织与索引

| 集合 | 主要字段与职责 | 索引 |
|---|---|---|
| surveys | `_id` 固定问卷 ID、`owner_id`、随机 `share_token`、`currentVersionId`、`version_number`、`closed`、`deadline`、`state_revision`、`created_at` | `_id`；share_token 唯一；owner_id + created_at |
| survey_edits | `_id` 等于问卷 ID；owner_id；revision；structure；updated_at；内部 publish_fence | `_id` 保证每问卷一编辑稿；owner_id |
| survey_versions | `_id` 独立版本 ID；survey_id；edit_revision；number；structure 完整快照；published_at | survey_id + edit_revision 唯一；survey_id + number 唯一 |

`structure` 内嵌 title、description、anonymous、allow_repeat、questions；questions 数组顺序就是题号。每题内嵌稳定 id、type、title、required、options、约束字段、rules。选项 id 在所属题内唯一，题 id 在结构内唯一；新建页面使用 UUID。版本不可变由应用 API 保证：没有更新/删除版本接口，后续填写数据必须引用版本 ID。本轮没有设置数据库管理员不可修改的权限屏障。

匿名与重复填写开关存在编辑稿和每份版本结构中。填写入口仅返回稳定问卷 ID、当前版本 ID/号、截止时间与填写用结构，不返回 owner_id、编辑修订、内部发布栅栏、账号或会话信息。管理与历史版本接口均检查所有者。

## API

所有 `/api/surveys` 接口需要登录；所有 POST 复用 `require_mutating_user`，要求原项目 Origin、Cookie 和 X-CSRF-Token。请求额外字段拒绝。非法/他人问卷 ID 统一 404。

| 方法及路径 | 请求 / 返回 |
|---|---|
| GET /api/surveys | 仅自己的列表，含编辑标题、分享路径、状态与当前版本 |
| POST /api/surveys | Structure；201 创建固定身份和初始编辑稿，revision=1 |
| GET /api/surveys/{id}/edit | 所有者编辑结构、revision、状态、state_revision |
| POST /api/surveys/{id}/edit | `{revision, structure}`；CAS 保存并 revision+1；冲突 409 |
| POST /api/surveys/{id}/publish | `{revision}`；版本 ID/号、replayed、currentVersionId |
| GET /api/surveys/{id}/versions | 所有者读取全部历史版本结构，最新在前 |
| POST /api/surveys/{id}/state | `{revision: state_revision, action: close/reopen/deadline, deadline?: 带时区时间或null}` |
| GET /api/shared/{token} | 需登录；开放时返回当前结构；未发布/关闭/到期 409，未知链接 404 |

422 结构错误提供 `errors[].field` 和 message。语义错误字段如 `questions[1](稳定ID).rules[0].selected`；类型/长度错误如 `body.structure.questions.2.max_length`。不回显提交的密码或原始数据库错误。数据库失败沿用脱敏 503；操作失败/超时应重新读取状态后重试，不能把未知提交结果当作确定失败。

## 本轮选定的业务默认值（由 AI 按本轮授权选取，非教师额外要求）

- 初始编辑稿允许零题，但发布至少一道题；保存也进行完整结构/引用/循环校验。
- 新问卷初始 `closed=false, deadline=null`，未发布仍不可访问。首次发布后，未关闭且未截止即开放；提前设置的关闭和截止状态同样保留。
- 截止时间以服务端 UTC 判定，**now >= deadline 即到期**，MongoDB 时间存为毫秒精度。浏览器用本机时区输入并转成带时区 ISO 时间。不接收无时区 API 时间。
- 关闭与到期分别保留。延长/清除截止不会擅自清除手动关闭；已关闭问卷需再点重开。已到期时重开被拒绝，必须先延长或清除截止。未发布不能重开。重新发布保持 closed 和 deadline 原值。
- 所有题型 required 独立；可选题的范围约束将来只在有答案时应用，本轮没有答案校验器。必答文本不允许 max_length=0，必答多选不允许最多/恰好0。
- 多选最少/最多可同时配置；恰好数量与最少/最多互斥。数量上限不超过选项数。文本长度范围非负、上限不小于下限；字数排除空格的具体 Unicode 范围仍留待填写模块，不默认采用某一范围。
- 数字使用有限 IEEE-754 数值，不接受布尔、字符串、NaN、Infinity；最小/最大均含边界。整数模式可使用小数边界，但范围内必须存在整数。不是任意精度小数方案。
- 单选条件恰好一个有效选项；多选是**完整集合完全匹配**（忽略选择顺序），不是逐选项触发。空条件集合不允许，同题相同集合不可重复配置。
- 数字比较支持 eq/lt/lte/gt/gte。保守地在**整个实数域**判断条件是否重叠，包括重复条件，不按题目范围或整数限制排除重叠；如 `<5` 与 `>=5` 可共存，`<=5` 与 `>=5` 因5重叠被拒绝。文本题本轮无规则条件。
- 一条规则只能选题目列表或结束；禁止混合。目标列表去重后按当前题序升序保存。所有可能的题目跳转边组成有向图，禁止自环/循环；不尝试证明某环在答案条件下不可达。结束动作不连图边，结束时必答补答属于后续运行时功能。
- 限制：100题；每题50选项/50规则；题目标题300字、问卷标题200字、说明5000字、选项文字200字、文本上限10000；主要用于课程作业的有限结构。未设计大规模分页或超大问卷上传。

完全匹配示例：题 q2 的规则 `{selected:["A","B"], action:"targets", targets:["q5","q3","q5"]}`，题序 q3 在 q5 前时保存为 `["q3","q5"]`；只选 A、不含 B 不满足此条件。连续跳转优先、已访目标不入队等已确认运行时规则没有在本轮实现。

## 一致性、并发及幂等

创建固定身份+编辑稿、发布版本+切换指针使用真实 MongoDB 事务（snapshot / majority）。发布读取指定 revision，完整重新校验，将结构复制至新版本；同时写编辑稿内部 publish_fence 和 surveys，以便并发保存/运行状态变化触发冲突重试。事务整体预算10秒，提交预算5秒；每操作沿用客户端有限超时。

保存通过 `_id + revision` 的单文档比较更新完成。两个窗口基于相同修订保存，只有一个成功，另一个409。状态操作同样要求 state_revision，避免旧窗口覆盖新状态。

本轮发布幂等标识直接采用 **(survey_id, edit_revision)**：同一修订只能有一个版本，不另建请求记录集合。相同修订重复/并发发布返回同一版本；若该修订曾发布但已不是当前版本，重试只返回历史结果，**不会回退 currentVersionId**。未发布的过期修订返回409，不发布最新编辑稿替代它。成功保存即产生新修订，即使内容完全相同也可发布成新版本；不做内容去重。

事务回调可重试，内无外部消息/文件等不可回滚副作用。实现参考 [MongoDB 官方 PyMongo 事务文档](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/transactions/)。本轮不设计填写提交顺序或答卷事务。

## 实际验证与证据

2026-10-21 执行：

```powershell
.\.venv\Scripts\python.exe tests\test_survey_validation.py
.\.venv\Scripts\python.exe tests\check_surveys.py
.\.venv\Scripts\python.exe tests\check_auth.py
```

前一条14项纯结构边界测试通过，不连接数据库。后两条使用真实 HTTP 与专用 MongoDB，创建带 test_run_id 的 QA 账号和问卷。没有清库。

最终接口原始输出见 `survey-test-results.txt`、认证回归见 `survey-auth-regression.txt`。实际包括：两账号所有权/篡改ID/CSRF；四种题型；V1发布；保存编辑稿不影响V1；并发发布V2只生成一版；同一链接读取V2且V1文档完全未变；并发保存一成功一409；旧修订重试不回滚指针；未发布旧修订拒绝；字段级校验；非法规则与非法引用；关闭、到期、重开及截止/关闭状态发布保留。

发布失败验证分两类：
1. 仅对 QA 问卷编辑稿临时写入自环（模拟绕过 API 的异常存储），真实发布接口422且当前V2/版本数量未变；随后恢复测试编辑稿。
2. 使用同一个发布服务、真实 MongoDB session/transaction，测试进程局部 mock 在**实际插入版本之后**抛异常；核对版本数量、surveys 完整文档、survey_edits 完整文档均未改变。没有在应用中添加故障测试接口，不是假数据库。

最终集成运行：`qa_survey_0551d69c4b`，问卷 `6ad86c6d6ebacbafc7d0f29b`，保留4个成功历史版本。早一次成功集成运行 `qa_survey_e5060badc7` 也保留（3版）。认证回归 `qa_auth_20261021_2b3af1` 两账号保留。浏览器账号 `qa_sui_mvhsr6e7`，标题显式含 QA，固定分享路径 `/s/VYVCp4EDszp-53AHqsBEMJdoBKebZkbD`。

浏览器实际完成：注册→登录→进入管理→创建问卷→添加四种题型→数量/长度/数字范围/必答配置→多选完全匹配两选项并选择两个目标→保存→发布V1→修改标题保存→另一个预览标签仍见V1→发布V2→同链接见V2→关闭后拒绝预览→重开恢复V2。稳定题ID在重开编辑稿后保持。浏览器只操作此 QA 问卷。

未覆盖：真实网络断连/主节点切换导致提交结果未知的故障、高压力、多浏览器/移动端、HTTPS部署、所有控件组合的浏览器矩阵、超大结构压力、数据库管理员直接改版防护。未实现或验证答卷、草稿、填写时跳转/撤销/必答补答、统计及对应事务。

## 本轮真实 AI 使用日志草稿

- 用户确定本轮边界与既有业务基线；AI 在原项目新增问卷模型校验、三集合管理服务、事务发布、管理与预览页面、测试和说明，没有重写认证或声称用户编写了这些代码。
- 发现此前应用和 MongoDB 未运行，使用原 Start.ps1 启动项目实例（复用旧数据），新启动本地应用；没有重置复制集、迁移原安装数据或改 MongoDB 配置。
- 第一次本机接口测试受沙箱 WinError10013 阻止；提升权限首次自动审核超时未执行，按工具允许重试后成功。不是 Python/MongoDB 兼容错误。
- AI 自查补充请求期间页面编辑保护、有限数值/布尔拒绝、必答与零上限冲突校验、事务整体超时，并将预览题型改为中文；修改后运行最终接口与认证回归。
- 实际执行发布事务成功及插入后回滚验证、权限和浏览器流程，未把复制集就绪当成事务测试结果。
- 依赖清单和虚拟环境未新增安装；没有创建答卷集合或后续业务功能。测试记录保留，不清库。

浏览器额外检查：将标题改为纯空白后保存，页面实际显示 `title: 标题不能全为空白`，原发布版不变；恢复有效标题并保存为编辑修订4，仍保持发布V2。浏览器控制台本次读取无 error/warn。截图：

- [V2 固定链接预览](evidence/survey-v2-preview.png)
- [编辑页面](evidence/survey-editor.png)

实际文件变更：新增 `backend/survey_models.py`、`backend/surveys.py`；修改 `backend/main.py` 接入路由、Store 和问卷字段错误处理；新增 `frontend/surveys.html`、`surveys.js`、`surveys.css`、`preview.html`、`preview.js`；修改 `frontend/auth.html` 增加管理入口；新增 `tests/check_surveys.py`、`tests/test_survey_validation.py`；新增本说明、两份原始测试输出和两张截图；更新 README。忽略目录 `.local` 中应用进程记录、应用/MongoDB日志及数据库文件随真实运行更新。`backend/auth.py`、依赖清单、.env、MongoDB脚本及配置没有修改。

工作区没有 Git 仓库，`git status` 实际返回 not a git repository；没有初始化仓库或执行提交，文件清单以本轮实际读写为据。

收尾真实检查：浏览器测试账号与对应问卷已补 `test_run_id=qa_sui_mvhsr6e7`；测试问卷 V2、closed=false。最终集成问卷实际保留4个版本。三个集合的预期索引已实际读取确认。MongoDB ping=1；监听为 `127.0.0.1:27018`（PID 27276）和 `127.0.0.1:8000`（PID 4772）。应用与 MongoDB 保持运行；这些是本轮收尾观测，不是未来持续运行保证。
