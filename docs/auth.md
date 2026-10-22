# 注册登录与权限基础

## 范围和启动

本轮实现注册、登录、退出、当前用户、可复用身份依赖，以及同源页面。
没有实现问卷，也没有验证问卷归属隔离。原 MongoDB 管理脚本、配置和数据保留。

项目根目录：`D:\数据管理\work1\workspace`。

```powershell
Set-Location -LiteralPath 'D:\数据管理\work1\workspace'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

如果应用已经运行，不要重复启动。本轮重启仅针对经身份核实的项目应用，未重启数据库。
账号页面 `/`；运行检查页面 `/health`；原 `/api/health/live` 和 `/api/health/database` 不变。

本轮仅新增直接依赖 `argon2-cffi==25.1.0`，完整依赖锁定于 `requirements.txt`。
安装使用项目 `.venv`，未向 Miniconda 基础环境安装。

## 安全与普通实现默认值

- 用户名：Unicode NFKC 规范化、去首尾空白、casefold；最终只接受 3–32 个 ASCII 小写字母、数字或下划线。
  ` Alice ` 与 `alice` 为同一用户名，规范化后的值也是页面显示名。
- 密码：12–128 个字符，不去空白、不做 Unicode 规范化、不截断。服务器严格校验，前端提示只作辅助。
- 密码使用 argon2-cffi 的 Argon2id 默认参数及随机盐；不自制哈希算法。登录成功时如库判断需更新参数，则重新哈希。
- 不返回密码哈希。输入校验错误采用固定文案，不沿用可能回显原密码的默认错误详情。
- 用户名不存在和密码错误均返回相同的 401 文案；不存在的用户也执行一次虚拟哈希验证。
- 会话采用标准的服务端不透明令牌模式：32 字节随机值放入 HttpOnly Cookie，数据库只存其 SHA-256 摘要作为 `_id`。
  会话逻辑由本项目实现，使用 Python secrets、Starlette Cookie API 和 MongoDB，不声称引入了第三方完整账号框架。
- 登录会话默认绝对有效期 8 小时，不滑动续期。未登录 CSRF 会话有效期 20 分钟。
- 登录消耗旧会话，再发新会话和 CSRF token，避免固定会话；退出删除当前会话并清除 Cookie，不退出其他浏览器会话。
- 每次身份验证检查 `expires_at > 当前 UTC 时间`。MongoDB TTL 后台清理可能延迟，不能替代到期判断。
- 所有 auth 修改请求必须具备精确匹配的 Origin 和会话绑定的 `X-CSRF-Token`，注册和登录也检查。
  不启用跨域 CORS。SameSite 只是附加防线，不代替 CSRF token。
- CSRF token 由同源 `/api/auth/csrf` 获取，只保存在前端内存；不在 localStorage 保存登录令牌。
- 接口响应 `Cache-Control: no-store`；提供 CSP、nosniff、frame-ancestors 等基础响应头。
- 数据库错误返回脱敏 503，不伪装成功；写入应答丢失时也不承诺“一定没有写入”。

参考：
[Argon2 官方 API](https://argon2-cffi.readthedocs.io/en/stable/api.html)、
[OWASP 会话管理](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)、
[OWASP CSRF 防护](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。

## 本地 HTTP 与部署 HTTPS

本地默认（当前 `.env` 没有这些项时自动采用）：

```dotenv
AUTH_ORIGIN=http://127.0.0.1:8000
SESSION_COOKIE_SECURE=false
SESSION_TTL_SECONDS=28800
```

本地 Cookie：`work1_session`，HttpOnly，SameSite=Lax，Path=/，无 Domain，Max-Age 对应会话时长。
HTTP 不设 Secure 仅允许用于回环地址；访问 `localhost` 与 `127.0.0.1` 不是同一个 Origin，应使用配置中的地址。

部署 HTTPS 时使用实际公开地址并启用 Secure，例如：

```dotenv
AUTH_ORIGIN=https://your-project.example
SESSION_COOKIE_SECURE=true
SESSION_TTL_SECONDS=28800
```

Cookie 改名为 `__Host-work1_session`，设置 Secure，继续保持 HttpOnly、SameSite=Lax、Path=/，不设置 Domain。
HTTPS 模式未启用 Secure 会拒绝启动。配置改变后重启应用。
实际 TLS、反向代理、HTTPS 浏览器行为未在本轮部署验证。当前没有登录限流、验证码、密码重置或多因素认证；
本轮不声称具备完整公网账号系统的防护能力。

## MongoDB 数据和索引

所有持久化账号与会话数据位于既有 `work1` 数据库。索引在首次 auth 请求时创建；已有索引可重复使用，
若创建唯一索引失败则返回错误，不删除或修复已有数据。

| 集合 | 字段 | 索引与职责 |
|---|---|---|
| users | `_id`、规范化 `username`、`password_hash`、UTC `created_at` | `username_unique` 唯一索引保证并发下不重复 |
| sessions | `_id` 为令牌摘要、`user_id` 或 null、`csrf_token`、`created_at`、`expires_at` | `_id` 默认唯一；`expires_ttl` 对 `expires_at` 设置 expireAfterSeconds=0 |

测试账号额外带 `test_run_id` 和 `test_purpose`；正常注册不接受这些额外字段。
密码明文和 Cookie 原始令牌不入库。CSRF token 可以存在服务端会话中；它不是单独的登录凭据。
用户 API 只返回 `id`、`username`、`created_at`。示例、日志不保存测试密码或 Cookie 原始值。

## API

修改接口要求 JSON、`Origin` 与 `X-CSRF-Token`；Cookie 由浏览器同源请求自动携带。
前端注册成功后要求登录，不自动登录。

| 方法与路径 | 输入 | 成功 | 主要失败 |
|---|---|---|---|
| GET `/api/auth/csrf` | 当前 Cookie（可无） | 200，csrf_token；必要时设置未登录 Cookie | 403 跨站；503 数据库不可用 |
| POST `/api/auth/register` | username、password | 201，公开用户资料 | 409 重名；422 输入非法；403 CSRF；503 数据库 |
| POST `/api/auth/login` | username、password | 200，公开用户、csrf_token，并轮换 Cookie | 401 用户名或密码错误；403/422/503 |
| GET `/api/auth/me` | 服务器会话 Cookie | 200，公开用户资料 | 401 未登录/过期/失效；503 数据库 |
| POST `/api/auth/logout` | 空 JSON | 200，删除当前会话并清 Cookie | 401/403 无效身份或 CSRF；503 数据库 |

不接受 register/login 额外字段。`/me?userId=其他用户` 不会改变身份；身份始终取自会话。
`GET /` 返回不含私人数据的页面外壳，私人身份来自受保护接口，不靠前端隐藏按钮授权。

复用方式：

- 受保护读取：FastAPI `Depends(require_user)`，从 `backend.auth` 导入。
- 受保护修改：`Depends(require_mutating_user)`，同时要求身份和 CSRF。
- 未来资源归属检查还需用返回用户 `_id` 检查资源所有者；本轮没有资源模型，未声称已经完成问卷隔离。

## 验证与复现

运行中的正常应用：

```powershell
.\.venv\Scripts\python.exe tests\check_auth.py
.\.venv\Scripts\python.exe tests\check_http.py --base http://127.0.0.1:8000 --database up
```

`check_auth.py` 每次生成独立 `qa_auth_日期_随机后缀_a/b` 账号并标记用途，保留用户记录，不清库。
只使本次创建账号的测试会话失效。过期用例把自己的测试会话到期时间改为过去，
通过真实 HTTP 验证 401；不是实际等待 8 小时，也没有修改系统时间或真实用户会话。

数据库故障复现：确认 27019 未监听，在另一个 PowerShell 窗口使用临时配置启动 8001：

```powershell
$savedUri = [Environment]::GetEnvironmentVariable('MONGODB_URI', 'Process')
$savedOrigin = [Environment]::GetEnvironmentVariable('AUTH_ORIGIN', 'Process')
try {
    $env:MONGODB_URI='mongodb://127.0.0.1:27019/work1?replicaSet=work1DevRs&serverSelectionTimeoutMS=5000'
    $env:AUTH_ORIGIN='http://127.0.0.1:8001'
    .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
} finally {
    [Environment]::SetEnvironmentVariable('MONGODB_URI', $savedUri, 'Process')
    [Environment]::SetEnvironmentVariable('AUTH_ORIGIN', $savedOrigin, 'Process')
}
```

另一窗口运行 ` .\.venv\Scripts\python.exe tests\check_auth_unavailable.py `。
完成后 Ctrl+C 停止临时应用；不停止正常 MongoDB、不修改 `.env`。

### 2026-10-21 实际结果

- 两个账号注册成功；用户名大小写及空白规范化后重复注册返回 409。
- 输入限制、额外 userId 拒绝，错误响应不回显密码；数据库实际存储 Argon2id 哈希，无明文密码字段。
- 正确密码登录成功，错误密码和不存在用户名返回相同 401。
- 未登录 `/me` 返回 401；两个独立客户端分别得到自己的身份；伪造 userId 查询参数不改变身份。
- 缺 CSRF token、跨站 Origin、缺 Origin、错误 token 被拒绝。
- 登录轮换 Cookie，旧匿名会话不可继续使用。
- 退出后会话记录删除，重放旧 Cookie 返回 401；另一账号会话仍有效。
- 本轮专用测试会话设为已过期后，受保护接口返回 401。
- 用户唯一索引和会话 TTL 索引实际存在。
- 内置浏览器 1280×720 实际完成注册→登录→显示用户名→退出→刷新仍未登录。
- 浏览器访问 `/health` 两项正常；工具返回的浏览器 error/warn 日志为空。
- 不可达数据库下 csrf、me、login 分别在约 5.159、5.524、5.529 秒返回脱敏 503；页面和后端存活正常。
- 浏览器数据库故障页真实显示错误而不是注册或登录成功。
- 原健康接口回归通过，正常 ping 约 0.005 秒。

本轮自动化测试标记：`qa_auth_20261021_d320c7`。
浏览器测试账号：`qa_browser_20261021_545960`，已标记用途并退出。
保留这些明确标识的测试用户；会话由退出和 TTL 按设计失效，不清理其他用户数据。

未验证：实际 HTTPS/代理部署、多浏览器、移动端、长期自然过期、TTL 清理时刻、压力与暴力破解防护，
以及未实现的问卷归属隔离。未进行事务写入测试。

## AI 使用日志草稿

- 用户授权直接实现注册、登录、退出、权限基础，允许本轮用户/会话集合、索引和标识测试数据。
- AI 选择 Argon2id 和 MongoDB 服务端会话，编写后端、页面、自动化验证和说明。
- 依赖下载首次被沙箱网络限制阻止，AI 按流程申请后仅向 `.venv` 安装；没有兼容性错误。
- AI 实际执行真实 MongoDB/HTTP 验证及浏览器注册、登录、退出流程，没有模拟成功。
- AI 在截图检查中发现次要按钮 hover 样式造成深色文字叠加深色背景，原因是基础 hover 规则优先级；
  AI 增加专用 hover 样式并重新查看截图。用户未被记作该修复的实施者。
- AI 同时修正了登录后仍显示登录引导文案、缺少 CSRF token 时定时器未及时清理、
  退出失败时仍展示旧登录成功区域的问题；均为实现过程中的 AI 修改，不虚构用户贡献。
- 本轮只重启项目应用，保留原 MongoDB 实例、配置和数据。临时故障应用验证后停止。
- 未实现账号以外业务，没有声称完成问卷隔离或生产安全认证。
