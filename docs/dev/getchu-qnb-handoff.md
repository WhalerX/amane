# Getchu QNB 修复与开发交接

## 工作区与分支

- 本地仓库：`D:\Amane\amane-dev`
- `origin`：`https://github.com/WhalerX/amane.git`
- 当前分支：`dev`，已跟踪 `origin/dev`
- Fork 创建时，`main` 与 `dev` 都指向 `e34da1a21ba7c7c882390e13db5cdc9fdd56ffc4`。开发修改只允许提交并推送到 `dev`，不得切换到 `main` 后写入或推送。
- 本交接涉及的源码与文档改动尚未提交。接手时先运行 `git status --short --branch`，确认在 `dev` 分支后再继续。

## 问题与修改

Getchu 商品页以 EUC-JP 编码返回正文，标题使用 `h2#soft-title`，商品字段位于当前商品表结构中。旧解析器按 UTF-8 默认解码、只匹配 `h1`，并从全页链接提取标签；这些假设导致详情页字段缺失或来源返回空结果。Cookie 不是该问题的原因。旧站点快照会跳过实时爬虫，验证解析改动时必须禁用 metadata 缓存。

当前 `src/amane/crawlers/sites/getchu.py::GetchuCrawler` 已包含以下修复：

- 搜索番号进行 URL 编码，搜索页与详情页按 EUC-JP 解码，站点使用 HTTPS。
- 兼容 `h2` 与 `h1` 标题结构；从商品字段解析品番、发行日和品牌。
- 解析封面、样例剧照、预告片、剧情和商品子类型，排除页面导航标签。
- 声明同源 Referer，满足 Getchu 图片请求的防盗链要求。

| 文件 | 修改 |
| --- | --- |
| `src/amane/crawlers/sites/getchu.py` | Getchu 请求与商品详情解析 |
| `tests/crawlers/test_getchu.py` | 商品字段、标签、封面、剧照、剧情、预告片及 Referer 回归测试 |
| `docs/dev/content-routes.md` | 记录 Getchu 图片请求的同源 Referer 契约 |
| `web/package.json` | Corepack 安装时加入 `pnpm@10.8.1` 及其完整性值，固定本工作区 pnpm 版本 |
| `AGENTS.md`、`docs/dev/index.md` | 登记本交接文档入口 |

没有创建独立测试脚本。可复现的测试位于 `tests/crawlers/test_getchu.py`。

## 验证记录

- Getchu 定向测试：`2 passed`，使用本地 Python 3.14.7。
- 定向 Ruff 检查及格式检查通过。
- `pnpm check` 通过；Oxlint 报告 4 条既有 React/Unicorn 警告，类型检查、格式检查和 i18n 检查均通过。
- Pylance 对 Getchu 源码与测试未报告错误。
- `just --list` 正常显示项目任务。
- 新仓库尚未启动前后端服务。维护者要求启动时，先设置下方的仓库内环境变量，再运行 `& "$repo\.tools\bin\just.exe" dev`；启动后检查 `http://127.0.0.1:8000/docs` 与 `http://127.0.0.1:5173/`。

再次运行定向测试：

```powershell
$repo = 'D:\Amane\amane-dev'
Set-Location $repo
& "$repo\.venv\Scripts\python.exe" -m pytest tests\crawlers\test_getchu.py -q
```

## 本地开发环境

所有本次新安装的工具、Python 运行时、Python 虚拟环境、前端依赖及缓存均位于 `D:\Amane\amane-dev`：

| 内容 | 本地路径 |
| --- | --- |
| uv 0.13.0、just 1.58.0、pnpm 10.8.1 命令 | `.tools\bin` |
| Node 22.14.0 | `.tools\node` |
| Python 3.14.7 运行时 | `.tools\python` |
| Python 虚拟环境及依赖 | `.venv` |
| Web 依赖 | `web\node_modules` |
| uv、Corepack、下载缓存 | `.cache` |
| pnpm 包存储 | `.pnpm-store` |

本地运行时版本已验证：Python 3.14.7、Node 22.14.0、uv 0.13.0、just 1.58.0、pnpm 10.8.1。`web/package.json` 的 `packageManager` 字段供 Corepack 选择已验证的 pnpm 版本。

PowerShell 中运行项目命令前，使用以下仓库内路径；此设置仅作用于当前 PowerShell 进程，不修改系统或用户 PATH：

```powershell
$repo = 'D:\Amane\amane-dev'
Set-Location $repo
$env:PATH = "$repo\.tools\bin;$repo\.tools\node;$env:PATH"
$env:UV_CACHE_DIR = "$repo\.cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$repo\.tools\python"
$env:UV_PROJECT_ENVIRONMENT = "$repo\.venv"
$env:COREPACK_HOME = "$repo\.cache\corepack"
$env:PNPM_HOME = "$repo\.tools\bin"
$env:npm_config_store_dir = "$repo\.pnpm-store"
```

`.git/info/exclude` 本地排除了 `.tools`、`.cache` 与 `.pnpm-store`；这些目录不会提交到远程。Python 虚拟环境和 `web\node_modules` 由仓库 `.gitignore` 排除。系统已有的 `D:\Node_js`、用户目录下的 Python 及工具未用于新仓库安装。维护者要求移除的 `D:\.pnpm-store` 已删除；后续不得在该路径重建项目缓存。

## 先前真实刮削结果与未完成事项

前一工作区对九条 QNB 记录提交了无缓存刮削，任务 #72–80 均完成且 Getchu 来源成功。九条记录均获取剧情、封面和 14–15 张样例剧照；剧照资源已下载到前一工作区的 Resource 缓存。先前的任务日志与 SQLite 数据库没有复制到本仓库，因此新克隆中的 UI 不会自动包含这些任务、记录或资源。

| 任务 | 番号 | Metadata ID |
| --- | --- | ---: |
| 72 | QNB-M185 | 25 |
| 73 | QNB-M163 | 26 |
| 74 | QNB-M165 | 27 |
| 75 | QNB-M181 | 28 |
| 76 | QNB-M180 | 29 |
| 77 | QNB-M183 | 31 |
| 78 | QNB-M184 | 32 |
| 79 | QNB-M190 | 33 |
| 80 | QNB-M182 | 30 |

单独刮削不会写入 NFO，也不会把 Resource 缓存中的剧照复制到媒体库目录；这些操作由 ORGANIZE 执行。前一工作区的媒体库根目录 `F:\动漫区` 在当时后端环境不可访问，故未运行整理。若后续需要处理 NFO 或媒体库图片，先在当前运行环境确认媒体库挂载和每个视频文件均可访问，再查询当前数据库中的 MediaFile ID，仅对目标记录提交定向 ORGANIZE。不得对整个媒体库提交整理来替代范围确认，因为 ORGANIZE 没有只读预览且可能移动视频。

## 后续 Git 操作

所有提交与推送仅限 `dev`：

```powershell
git status --short --branch
git diff --check
git add AGENTS.md docs/dev/index.md docs/dev/content-routes.md docs/dev/getchu-qnb-handoff.md src/amane/crawlers/sites/getchu.py tests/crawlers/test_getchu.py web/package.json
git commit -m "fix: improve Getchu scraping" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push origin dev
```

推送前再次确认当前分支是 `dev`，并确认 staged diff 不含环境目录、缓存、数据库或其它运行产物。不得推送 `main`。

## 代码入口

- Getchu 解析：`src/amane/crawlers/sites/getchu.py::GetchuCrawler`
- 回归测试：`tests/crawlers/test_getchu.py`
- 缓存与刮削后处理：`src/amane/handlers/scrape.py::ScrapeHandler`、`src/amane/aggregate/engine.py`
- 图片资源缓存：`src/amane/media/pipeline.py::materialize_images`、`src/amane/media/resource_store.py::ResourceStore.acquire_extrafanart`
- NFO 与整理：`src/amane/handlers/file.py::OrganizeHandler`、`src/amane/media/nfo.py::write_nfo`
- 站点路由说明：`docs/dev/content-routes.md`
