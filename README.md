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
bucket/                        # manifest 放这里，一个软件一个 .json
scripts/update.py              # 探测新版本 -> 改写 version/url/hash（Python 3，仅标准库）
scripts/Manifest.template.json
.gitcode/workflows/update.yml  # GitCode 流水线，每天 UTC 04:00 自动跑
```

## manifest 约定

- 每个 manifest 必须带 `checkver` 与 `autoupdate`，否则无法自动更新。
- `checkver` 支持两种写法：
  - `{"github": "https://github.com/<owner>/<repo>"}` —— 走 GitHub API，失败自动回退到 `releases.atom`
  - `{"url": "...", "regex": "..."}` —— 任意页面 + 正则，第一个捕获组即版本号
- `autoupdate` 的 `url` 用 `$version` 等占位符；`hash` 可以是：
  - `{"url": "$baseurl/SHA256SUMS"}` —— 从校验文件里按文件名提取
  - `{"url": "...", "regex": "..."}` —— 自定义提取
  - 不写 —— 直接下载产物自己算 sha256

## 手动更新

```bash
python3 scripts/update.py              # 检查并写入
python3 scripts/update.py --dry-run    # 只报告
python3 scripts/update.py --app aoci   # 只检查一个
GH_TOKEN=xxx python3 scripts/update.py # 带 token，避免 GitHub API 限流
```

脚本做的事：

1. 读取每个 manifest 的 `checkver`，拿到上游最新版本；
2. 用版本比较判断是否更新（`0.2.0` > `0.2.0-rc2`，`rc10` > `rc2`，`1.2` == `1.2.0`）；
3. 按 `autoupdate` 模板展开 `url`，解析或下载计算 `hash`；
4. 写回 manifest。

Windows 上没装 Python 也可以用 `scoop install python`，或者在 Git Bash 里跑。

## 自动更新（GitCode 流水线）

`.gitcode/workflows/update.yml` 每天 UTC 04:00 跑一次 `scripts/update.py`，
有变更就 `commit + push` 到 `main`。也可以手动触发（`workflow_dispatch`）。

GitCode 托管 runner 只有 Linux（`ubuntu-latest` / `euler-latest`），所以脚本刻意
不依赖 Scoop/Windows。runner 预装 Python 3，无需额外安装。

> 可选：在仓库 Secrets 里加一个 `GH_TOKEN`（GitHub PAT），可把 GitHub API 限流
> 从 60 次/小时提到 5000 次/小时。不加也能跑，会自动回退到 `releases.atom`。

## 新增一个软件

1. 复制 `scripts/Manifest.template.json` 到 `bucket/<app>.json`；
2. 填 `version` / `description` / `homepage` / `license` / `url` / `hash` / `checkver` / `autoupdate`；
3. 本地 `python3 scripts/update.py --app <app> --dry-run` 确认探测正常；
4. `scoop install .\bucket\<app>.json` 验证能装；
5. 提交。之后版本由流水线跟。

## License

MIT