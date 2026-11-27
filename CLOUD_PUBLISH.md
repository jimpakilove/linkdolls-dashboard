# 云盘 → 云端生成 → 看板发布

## 当前状态

2026-11-27 已启用云端发布。云盘只读授权、主分支身份绑定、完整试运行、正式部署及线上验收均已完成。
日常更新只需上传云盘，不依赖本机开机或推送。

- [首次完整试运行成功](https://github.com/jimpakilove/linkdolls-dashboard/actions/runs/45959675064)
- [首次正式发布成功](https://github.com/jimpakilove/linkdolls-dashboard/actions/runs/45961338072)
- 首次数据：W47（2026-11-16 至 2026-11-22），10,283 个源文件。
- 线上四个页面均可访问，五个菜单入口齐全，最新分类周可选 W47，点击率报表正常加载。四周报表仍遵循既有固定周期，其最新完整周期为 W42–W45。
- 最新周所有分类记录与迁移前本地一致，类别收入文件完全一致。不能将全部历史文件描述为逐项完全相同：云端额外显示 `celebrity-sex-dolls` 的 W11–W14；本地对应目录有 ` (1)` 后缀，被分类导入器严格周名规则排除。四周 GSC 值均与对应本地原始表一致。PDP 来源列表排序不同，按来源名称对齐后内容完全一致。另有 `Other 其他` W35 跳出率显示为 12.8%，本地为 12.9%；已复算精确加权值为 12.85%，浮点求和顺序会产生 12.85 或 12.850000000000001，从而影响现有一位小数舍入。该历史舍入差异保留记录，未修改原始数据或扩大本次迁移的计算口径。

## 一次性配置

1. 确认一个云盘文件夹包含以下目录（文件名与本机一致）。上传必须是原始 CSV，而非在线表格或快捷方式：

   ```text
   数据根目录/
     config/target-2026.csv
     orders/订单明细表导出YYYY-MM-DD.csv
     landing-page-data/pageviews/*.csv
     landing-page-data/各分类/wNN_YYYY-MM-DD/*.csv
     landing-page-data/clicks/*.csv
   ```

2. 在 Google Cloud 项目启用 Drive API，创建专用服务账号。分别把 `config`、`orders`、`landing-page-data` 三个子目录以“查看者”权限共享给该账号。根目录含其他工作资料时不要共享整个根目录；不需要全域委派或云盘管理员权限。
3. 配置账号登录。优先采用 Workload Identity Federation：身份提供者必须限制为本仓库及默认分支，允许通过该服务账号读取 Drive。将提供者资源名和账号邮箱分别填入仓库变量 `GCP_WORKLOAD_IDENTITY_PROVIDER`、`GCP_SERVICE_ACCOUNT`。如暂时不设置身份联合，可把专用账号 JSON 放入仓库 Secret `GDRIVE_SERVICE_ACCOUNT_JSON`；密钥不得提交代码、粘贴聊天或放进公开云盘目录。
4. 在仓库 Actions variables 中设置 `DRIVE_FOLDER_IDS` 为三个子目录的映射：`{"config":"配置目录ID","orders":"订单目录ID","landing-page-data":"报表数据目录ID"}`。程序直接读取这三个子目录，不需要访问父目录。仅在根目录本身只包含报表数据时，才使用兼容配置 `DRIVE_FOLDER_ID`。设置 `CLOUD_PUBLISH_ENABLED=true` 后，工作流才会运行。
5. 工作流进入默认分支后，在 Actions → Cloud dashboard update → Run workflow，以默认 `dry_run=true` 先完成一次云端下载和验证。不要先切换现有网站的发布源。
6. 试运行通过后，在 Settings → Pages 将 Source 改为 GitHub Actions。再次运行工作流，关闭 `dry_run`，完成正式发布。
7. 验收原来的网站网址、五个菜单入口、观察周和收入/流量数据；确认 `.github/data-update-status.json` 成功写入。该小文件是每次成功发布的记录，不是原始数据或大型报表。
8. 在账号 Actions 通知设置中启用所需的失败通知，并检查接收邮箱；这属于账号设置，本工作流不会替用户修改通知偏好。首轮成功后，再停掉旧的本机自动推送，避免两个流程同时更新。

工作流需要 Actions 执行权限、Pages 部署权限，以及向默认分支写入一份小型发布记录的权限。若分支保护阻止机器人写记录，网站可能已部署，但记录步骤会报错；须处理权限或改用独立调度，不能忽略该失败。

## 运行规则

- 北京时间周一 21:00、周二 12:00。使用 UTC 的周一 13:00、周二 04:00 表达；调度可能延迟，不保证整点完成。
- 默认目标是最近已经结束的自然周，不能悄悄退回较老周后声称成功。
- 手动运行可以指定周一日期用于试运行；实际数据存在更新周时拒绝用旧目标覆盖网站。
- 每次从云盘重新下载，忽略仓库中历史原始 CSV，不依赖本机同步。
- 下载前后清单一致、文件大小和校验和一致才接受快照；最近 5 分钟修改的文件要求稍后重试。
- 只允许三个输入目录内的 CSV，不从云盘下载或执行代码。所有脚本和模板取自仓库。
- 检查最新周的文件、字段、可识别的导出日期、订单文件截止日期及生成结果。订单文件名的截止日期仍需上传人正确填写。
- 缺失必需文件、路径未匹配、历史周丢失、生成/回归失败均阻止部署，日志列出具体缺项。历史数据中已明确标记的缺失不改写为零。
- `config/cloud-publish-policy.json` 明确 27 个有历史数据的必需页面；从未上传周数据的 `sex-doll-videos` 不强制纳入。新增/停用页面需更新该策略。
- 网站只打包四个 HTML（主页面包含三个菜单视图）、四个报表 JSON、更新状态和首页跳转；不会打包原始订单、其他业务目录、凭据或整个仓库。
- 报表仍沿用现有公开访问模式；其中的业务汇总数据也公开。该流程不会清理旧 Git 历史中已存在的文件。
- 每次发布成功，额外提交几十 KB 的数据覆盖记录，使历史丢失检查跟随最新发布，也维持仓库活动。若长期没有成功发布，公开仓库的 60 天无活动停用限制仍需关注。
- 页面右下角显示数据截至日期及生成时间；下一轮周二 12:00 后仍没有更新时显示逾期提示。浏览器里的提示不等于已配置邮件通知。
- 当前导入器和目标表是 2026 年口径，跨年会明确停止，而不是把 2027 年数据错误归入 2026 年。

## 日常使用

1. 同事继续上传原始 CSV 到现有云盘的三个数据目录，保持目录名、周次和文件名不变。文件应在执行前至少 5 分钟上传完成。
2. 每周一 21:00、周二 12:00（北京时间），云端读取完整数据并重新生成网站。电脑可以关机，不需要运行本机推送命令。
3. 临时更新：进入仓库的 **Actions → Cloud dashboard update → Run workflow**，选择 `main`，取消 `dry_run`，周日期通常留空。运行成功后检查网页右下角的数据截至日期。
4. 仅检查数据：保持 `dry_run` 勾选；成功代表数据通过检查，不代表网站已更新。
5. 如果失败，在这次运行的失败步骤查看缺少的具体文件或字段，补齐后重新运行。上一次成功网站保留。

切换为云端发布后，`update_and_push.sh` 仍可在本机生成并提交数据，但单纯推送仓库不再立即更新网站；网站由上述云端工作流发布。模板或脚本改动推送后，需要手动运行该工作流，或等待下一次定时运行。

## 本地验证（不会推送，也不修改原始数据）

```bash
python3 -B -m unittest discover -s scripts -p 'test_cloud_dashboard.py'
python3 scripts/build_cloud_dashboard.py --source . --output /tmp/dashboard-cloud-preview
```

输出目录必须不存在。生成在临时目录完成，原始数据和本机看板不被覆盖。

## 回退

把 `CLOUD_PUBLISH_ENABLED` 改为 `false` 停止后续云端运行。若要恢复旧分支发布模式，先确认旧分支上的数据日期，再切回 Pages 的原发布源。失败构建不部署；部署后的发布记录步骤失败不代表网站没有更新，应核对 Pages 部署状态。

## 官方参考

- [Drive 文件夹只读共享](https://developers.google.com/workspace/guides/create-credentials#access-google-workspace-files-directly-with-a-service-account)
- [云端身份认证](https://github.com/google-github-actions/auth)
- [Pages 自定义部署](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [调度延迟和停用规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
