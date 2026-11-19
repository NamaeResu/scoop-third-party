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
scripts/<app>.py               # 一个软件一个更新脚本，只负责自己那个 manifest
scripts/Manifest.template.json
.gitcode/workflows/update.yml  # GitCode 流水线，每天 UTC 04:00 跑 scripts/*.py
```

## 为什么一个软件一个脚本

不同软件的上游差别太大，用一套通用规则去套只会把某个包的策略强加给所有包：

- `aoci` 发真实产物（按架构的 zip + `SHA256SUMS`），更新时要展开 `autoupdate.url`
  并按文件名从校验文件里取 sha256。
- `flutter-ohos-341` 没有可下载产物（installer 把 SDK clone 到 persist 目录再
  checkout tag），更新只需要改 `version`，没有 url/hash 可算；而且上游同一行用
  `3.41.9+ohos-1.0.2` 和 `3.41.10-ohos-1.0.0` 两种形状分在不同维护分支上，
  "最新" 得按 `created_at` 判断，不能只看版本号大小。

所以每个脚本自己决定怎么探测、改写什么。脚本之间互不依赖，一个坏了不影响其他。
公共的小工具（版本比较、占位符展开、校验文件解析）由需要的脚本自己带，
不为了复用而抽象。

## manifest 约定

- 每个 manifest 必须带 `checkver` 与 `autoupdate`，`scoop update` / 手动更新依赖它们。
  仓库的自动更新走 `scripts/<app>.py`，不解析这两个字段，但它们是 manifest 的
  标准写法，别省。
- 新增软件时照着该软件上一个 `scripts/*.py` 复制一份改。

## 手动更新

```bash
python3 scripts/aoci.py              # 只更新 aoci
python3 scripts/aoci.py --dry-run    # 只报告
python3 scripts/flutter-ohos-341.py  # 只更新 flutter-ohos-341
GH_TOKEN=xxx python3 scripts/aoci.py # 带 token，避免 GitHub API 限流
```

## 自动更新（GitCode 流水线）

`.gitcode/workflows/update.yml` 每天 UTC 04:00 遍历 `scripts/*.py` 逐个执行，
有变更就 `commit + push` 到 `main`。也可以手动触发（`workflow_dispatch`）。

某个脚本失败不会中断其他脚本，失败列表在最后一步统一报错，流水线标红。

GitCode 托管 runner 只有 Linux（`ubuntu-latest` / `euler-latest`），所以脚本刻意
不依赖 Scoop/Windows。runner 预装 Python 3，无需额外安装。

> 可选：在仓库 Secrets 里加一个 `GH_TOKEN`（GitHub PAT），可把 GitHub API 限流
> 从 60 次/小时提到 5000 次/小时。不加也能跑，`aoci.py` 会自动回退到 `releases.atom`。

## 新增一个软件

1. 复制 `scripts/Manifest.template.json` 到 `bucket/<app>.json`，填好内容；
2. 参考同类软件写 `scripts/<app>.py`：探测版本 → 判断是否更新 → 改写 manifest；
3. 本地 `python3 scripts/<app>.py --dry-run` 确认探测正常；
4. `scoop install .\bucket\<app>.json` 验证能装；
5. 提交。之后版本由流水线跟。

## License

MIT
