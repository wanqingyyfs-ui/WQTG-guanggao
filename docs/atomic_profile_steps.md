# 账号资料维护原子步骤

账号资料维护行为已拆分为可排序、可增删的最小步骤。

- 页面交互步骤：`locator.click`、`locator.fill`、`locator.upload`，均自动创建 `workflow.<行为ID>.<步骤ID>` 定位目标，可在自动化定位设置中选择 Strategies 或绝对位置校准。
- 数据步骤：从账号资料维护配置读取头像、昵称池、用户名规则、签名和文件夹链接。
- 功能步骤：键盘操作、等待和修改结果校验，不需要网页定位。
- 旧的 `name.update`、`username.update`、`bio.update`、`folder.add` 及头像复合步骤会自动迁移为编号原子步骤。
