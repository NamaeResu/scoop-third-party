# scoop-third-party

一个 Scoop bucket，收录官方 bucket（main / extras / versions）之外的第三方软件，
并由脚本持续探测上游新版本、自动更新 manifest。

仓库地址：<https://gitcode.com/NamaeResu/scoop-third-party>

## 使用

```powershell
scoop bucket add third-party https://gitcode.com/NamaeResu/scoop-third-party
scoop install third-party/<app>
```

## 目录结构

```
bucket/                      # manifest 放这里，一个软件一个 .json
scripts/update.ps1           # 探测新版本 -> 更新 manifest 的 version/url/hash -> 提交
scripts/Manifest.template.json
.gitcode/workflows/update.yml  # GitCode 流水线（定时跑 update.ps1）
```

## manifest 约定

- 每个 manifest 必须带 `checkver` 与 `autoupdate`，否则无法自动更新。
- 优先使用上游稳定的版本接口：
  - GitHub / GitCode Releases：`"checkver": { "github": "https://github.com/<owner>/<repo>" }`
  - 固定格式的网页：`"checkver": { "url": "...", "regex": "..." }`
- `autoupdate` 里的 `url` 用 `$version` 占位，`hash` 用 `"$base64"`（或保持 `"$hash"` 由脚本回填）。
- 文件名即软件名（`bucket/foo.json` → `scoop install foo`）。

## 手动更新

```powershell
# 需要本机已安装 Scoop（脚本会用 scoop 自带的 checkver）
pwsh -File scripts/update.ps1              # 检查全部
pwsh -File scripts/update.ps1 -App nekoray # 只检查一个
pwsh -File scripts/update.ps1 -DryRun      # 只报告，不落盘
pwsh -File scripts/update.ps1 -Commit      # 更新后自动 commit（不 push）
```

`scripts/update.ps1` 做的事：

1. 定位 `scoop\apps\scoop\current\bin\checkver.ps1`；
2. `checkver -Dir bucket -Update -ForceUpdate`，逐个 manifest 比对上游版本；
3. 有新版本时改写 `version`、按 `autoupdate` 模板生成新 `url` 并重新计算 `hash`；
4. 打印变更摘要，`-Commit` / `-Push` 时提交并推送。

## 自动更新

### 方式 A：本机计划任务（推荐，Windows）

```powershell
schtasks /create /tn "scoop-third-party update" /tr "pwsh -NoProfile -File C:\Users\user\scoop-third-party\scripts\update.ps1 -Commit -Push" /sc daily /st 12:00
```

### 方式 B：GitCode 流水线

`.gitcode/workflows/update.yml` 在 `schedule` 触发时运行，需要流水线环境里有
PowerShell 7 与 Scoop。若 runner 没有，请改用方式 A 或用自建 runner。

## 新增一个软件

1. 复制 `scripts/Manifest.template.json` 到 `bucket/<app>.json`；
2. 填 `version` / `description` / `homepage` / `license` / `url` / `hash` / `checkver` / `autoupdate`；
3. 本地 `scoop install .\bucket\<app>.json` 验证；
4. 提交。之后无需再手改版本，脚本会跟。

## License

MIT