# 本项目 MongoDB 开发复制集

仅复用 `D:\Mongodb\bin\mongod.exe` 和 `mongosh.exe`。
不修改原 `D:\Mongodb\bin\mongod.cfg`，不使用原 `D:\Mongodb\data`。
本实例不安装为 Windows 服务，不自动随系统启动。

## 实际配置

| 项目 | 值 |
|---|---|
| 工作目录 | `D:\数据管理\work1\workspace` |
| 配置 | `dev\mongodb\mongod.cfg` |
| 数据目录 | `.local\mongodb\data` |
| 日志目录 | `.local\mongodb\logs` |
| mongosh 本地配置及日志 | `.local\mongodb\client-profile` |
| 所有权记录 | `.local\mongodb\owner.json` |
| 进程记录 | `.local\mongodb\process.json` |
| 监听 | `127.0.0.1:27018` |
| 复制集 | `work1DevRs` |
| 成员 | `127.0.0.1:27018` |

这是只绑定回环地址、未配置认证的本机开发实例，仅供本项目开发使用。
不要将绑定地址改为公网地址。整个 `.local/` 已纳入 Git 忽略规则。
运行目录内包含 MongoDB 自动产生的存储、复制集内部数据与日志，不应提交到版本库。

## 启动、检查、停止

在 PowerShell 中先切换到项目目录：

```powershell
Set-Location -LiteralPath 'D:\数据管理\work1\workspace'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\dev\mongodb\Start.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\dev\mongodb\Check.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\dev\mongodb\Stop.ps1
```

`ExecutionPolicy Bypass` 仅作用于这次 PowerShell 进程，不修改系统执行策略。
在受限执行环境中，端口和进程查询可能需要运行权限；失败时应申请权限，不跳过所有权检查。

- `Start.ps1` 检查端口、目录所有权及进程记录，以隐藏窗口启动。
  只有全新项目目录的初始化标记允许初始化；已有正确复制集不会被重置。
  已运行时只检查，不启动第二个实例。
- `Check.ps1` 核对 PID、启动时间、程序、配置参数、监听端口和服务器实际参数，
  使用应用复制集连接地址执行只读 `ping`、`hello`、`buildInfo`、
  `replSetGetStatus`、`replSetGetConfig` 等检查。
- `Stop.ps1` 核实项目进程后，通过该实例请求正常关闭，再确认进程退出及端口释放。
  不按名称批量停止，不强制杀进程，不删除数据。
- 配置在项目工作目录下通过相对路径传给 mongod，避免首次启动遇到的中文绝对路径问题。
  数据与日志在配置中仍明确使用项目绝对路径。

端口被其他进程占用、PID 被复用、目录存在但缺少所有权记录或复制集配置不符时，
脚本会报错停止，不清空数据、不重新配置、不终止占用者。
如需变更目录、端口或复制集名，应单独检查并调整整套配置，不要只改其中一个字段。

## 下一轮应用连接

```text
MONGODB_URI=mongodb://127.0.0.1:27018/work1?replicaSet=work1DevRs&serverSelectionTimeoutMS=5000
MONGODB_DB=work1
```

连接串中的 `work1` 是下一轮拟使用的业务数据库名称。
本轮未创建该业务数据库、业务集合或种子数据。
`directConnection=true` 仅供初始化/停止时的管理连接使用；应用使用上述复制集地址。

## 本轮验证记录

1. 工作目录初始为空；27018 未发现占用。
2. 首次受限执行被拒绝进行端口查询，获准后重试。
3. 首次 mongod 启动报 `Error opening config file: no such file or directory`。
   改为指定项目工作目录、传入相对配置路径后启动成功。
4. 初始化新复制集一次；首次运行 PID 为 `23408`。
5. 重复执行启动脚本，仍使用 PID `23408`，未启动第二个实例或重新初始化。
6. 正常停止 PID `23408`，脚本确认退出和端口释放，保留原项目数据目录。
7. 同一项目数据目录重新启动，PID 为 `6116`，无需再次初始化。
8. 重启后只读检查：服务端 `8.3.11`，复制集 `work1DevRs`，
   单成员 `127.0.0.1:27018`，`PRIMARY`，`health=1`，`isWritablePrimary=true`，`ping=1`。

PID 是本次执行记录，未来以 `process.json` 和脚本核查结果为准。
正常停止、重启已实际验证；异常断电恢复、并发业务、事务写入及应用功能未测试。
复制集就绪仅表示具备相应部署前提，不表示业务事务或并发测试通过。

## AI 使用日志草稿

- 用户授权复用原安装程序，为项目新建本地单节点复制集，明确禁止使用原数据目录、
  修改原配置、安装系统服务和停止其他实例。
- AI 创建了专用配置、启停检查脚本、管理脚本、使用说明和忽略规则。
- 实际完成首次初始化、只读主节点检查、重复启动检查、正常停止及同目录重启。
- 首次启动错误如上记录，未编造失败或验证结果。
- MongoDB 初始化及运行产生了内部数据库、复制集元数据、oplog、存储文件和日志；
  未创建业务集合、种子数据或执行事务写入测试。
- 未创建前后端骨架、安装 Python 依赖或编写业务代码。
- 此次准备的是新建项目专用实例，不是“修复或改好了原来的实例”。
