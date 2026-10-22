# 第一阶段测试复现与证据

先按 README 启动项目数据库和应用。项目根目录使用 `.venv\Scripts\python.exe`。集成脚本会新增明确QA数据，禁止拿生产库运行，不清空数据。

|命令（python后参数）|输入/操作与预期|原始结果|
|---|---|---|
|-m unittest discover -s tests -p "test_*.py" -v|27项结构及纯状态机：非法数量/引用/环/数字；完全匹配；队列与来源撤销；预期断言通过|stage1-unit-results.txt|
|tests/check_auth.py|两个QA账号、重复注册、错误密码、伪造身份、CSRF、退出和过期；预期对应401/409/422及身份正确|stage1-auth-results.txt|
|tests/check_surveys.py|四题型、CAS并发、发布V1/V2、旧版不变、非法规则、实际插入后故障回滚、关闭/截止；预期版本/状态断言|stage1-publish-results.txt|
|tests/check_filling.py|四类型、草稿恢复、提交重复/幂等、并发CAS、回滚、旧版本、结束补答、发布/关闭顺序；预期只有合法历史生效|stage1-filling-results.txt|
|tests/check_statistics.py|见statistics-tests.md逐行输入和人工值；统计权限/隐私|stage1-statistics-results.txt|

纯状态机测试不替代真实数据库；事务故障测试在实际写入后由测试进程局部注入异常，检查事务回滚，非模拟Mongo成功。发布/关闭与提交先后由测试线程闸门控制并确认第二事务读过旧快照，再释放第一事务，证明冲突重试而非仅串行请求。

历史模块文档里的“尚未实现”只描述当时范围；当前以 stage1-report.md 和本轮 stage1-* 输出为准。真实浏览器步骤和截图见 browser-statistics.md。未执行负载、故障切主、HTTPS/移动端/多浏览器矩阵；不以单节点部署就绪代替业务事务测试。
