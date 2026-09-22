# AI 趋势日报 · AI Daily Digest

每日自动生成、静态沉淀、可检索的全球 AI 行业日报。整条链路零第三方依赖，只用 Python 标准库 + 原生 HTML/CSS/JS。

```
ai-daily-digest/
├── index.html                 # 始终展示最新一期日报
├── archive.html               # 历史档案总览（日期 / 标签 / 关键词筛选）
├── assets/
│   ├── style.css              # 由 templates/partials.css 生成
│   └── app.js                 # 由 templates/partials.js 生成
├── data/
│   ├── index.json             # 历期元数据（前端检索索引，由 build_site.py 重建）
│   └── 2026-09-17.json        # 当日清洗后的结构化数据
├── archive/
│   └── 2026-09-17.html        # 历史静态快照（自包含，可单独分发）
├── templates/
│   ├── daily.html             # 日报模板
│   ├── archive.html           # 归档页模板
│   ├── partials.css
│   └── partials.js
├── scripts/
│   ├── template_engine.py     # 零依赖模板引擎（{{TOKEN}} + BEGIN/END 嵌套循环）
│   ├── fetch_sources.py       # 06:00-07:30 数据抓取
│   ├── dedupe.py              # 07:00-07:30 Embedding 聚类去重
│   ├── summarize.py           # 07:30-08:15 LLM 结构化提炼
│   ├── build_site.py          # 08:15-08:45 静态站点生成
│   ├── notify.py              # 09:00 Webhook 推送
│   └── run_pipeline.py        # 编排
├── config.json                # 监控源、模块定义、标签词表、模型与推送配置
└── requirements.txt
```

## 一、流水线

| 时间 | 阶段 | 脚本 | 产物 |
| --- | --- | --- | --- |
| 06:00-07:30 | 数据抓取 | `fetch_sources.py` | `data/raw/<date>.json` |
| 07:00-07:30 | 清洗去重 | `dedupe.py` | `data/clean/<date>.json` |
| 07:30-08:15 | 结构化提炼 | `summarize.py` | `data/<date>.json` |
| 08:15-08:45 | 静态渲染 | `build_site.py` | `index.html` / `archive.html` / `archive/<date>.html` |
| 09:00 | 发布分发 | `notify.py` | 飞书 / 企业微信 / 邮件 |

一键运行：

```bash
python3 scripts/run_pipeline.py                      # 全流程
python3 scripts/run_pipeline.py --from-stage render   # 已有数据，只重渲染
python3 scripts/run_pipeline.py --skip-push --push-git
```

只重渲染（改样式或改数据后）：

```bash
python3 scripts/build_site.py              # 全部期次
python3 scripts/build_site.py --latest     # 只渲染最新一期
```

### 抓取源

`config.json → sources` 可增删，支持四类：

- `rss` —— Techmeme、OpenAI、DeepMind、NVIDIA、量子位、机器之心、Reuters、FT 等
- `hn_api` —— Hacker News Algolia API（按 `points>40` 过滤）
- `github_trending` —— GitHub Trending 日榜
- `hf_papers` —— Hugging Face Daily Papers

单个源失败不会中断流水线，只会在日志里打 `!`。

### 去重

默认用 `text-embedding-3-large`（OpenAI 兼容接口）对「标题 + 摘要」做向量化，再做贪心聚类，
把同一新闻的多源转载折叠成一个簇（代表报道 = 权重最高的一条，其余保留在 `sources` 里）。
未配置 `OPENAI_API_KEY` 时自动退化为本地字符 n-gram TF-IDF 余弦相似度，链路依然可跑通。
注意：TF-IDF 只能识别字面重合，跨源改写标题的同一条新闻基本不会被合并（实测多源重复率 ~1%）；
真正消除多源重复需要打开 Embedding 模式。

### 提炼

`summarize.py` 的 Prompt 强制输出：

```json
{ "标题", "分类", "核心事实", "深度洞察", "关联标的/企业", "引用来源" }
```

并做了三重校验：模块 ID 必须来自 `config.json`、标签必须命中词表、来源链接必须来自候选素材。
**没有 API Key 时脚本直接退出，绝不生成占位内容。**

## 二、内容知识体系

四个固定模块（见 `config.json → modules`）：

1. **全球 AI 宏观与政经脉搏** —— 测试时计算扩展、长程自主 Agent Harness、多模态全双工语音、端侧轻量化；货币政策、算力芯片供应链、AI 安全与主权监管
2. **AI 浏览器与端侧工作流** —— Chrome/Gemini、Edge/Copilot、夸克、QQ 浏览器 vs Tabbit、Comet、Dia、Ego Lite
3. **国内三巨头与本土生态** —— 腾讯（混元 + 微信/QQ 入口）、字节（豆包矩阵 + 扣子 + 火山引擎）、阿里（Qwen 开源 + 阿里云变现）
4. **前沿模型与落地产品** —— 海外 Claude / ChatGPT / Gemini / Copilot，国内豆包 / 元宝 / 通义千问 / Kimi
5. **AI 视觉 UI 设计趋势** —— Chrome / Edge、夸克 / QQ 浏览器、Comet / Tabbit / Dia / Ego Lite 的设计竞品分析：交互设计、UI 质感、颜色、图标、概念表达与创新体验，**配图只采用厂商官网或第三方真实截图，禁止 AI 生成图**；数据结构为 `item.images[] = {url, caption, credit, link}`

每个模块底部挂一块 **Watchlist（长期观察）**：不随当日新闻变化，用来沉淀竞争格局框架，和上面的「当日条目」区分开。

每条资讯绑定语义化标签（`#AI安全` `#AI浏览器` `#大厂战略` `#投融资` …），标签词表在 `config.json → tags` 里收敛，避免无限膨胀。

## 三、页面交互

- **桌面双栏**：左侧粘性锚点导航（自动高亮当前模块）+ 标签过滤，右侧正文流
- **移动端单栏**：锚点降级为横向 chip，字段由两栏变上下堆叠
- **右上角常驻**：日期快速跳转器（`<select>`）+ 归档抽屉（右侧滑出，Esc / 点遮罩关闭）
- **归档页**：关键词 + 月份 + 标签三重筛选，实时过滤
- **视觉**：编辑风衬线标题、单个超大弥散光斑（跟随指针缓慢漂移）、发丝级分隔线、硬边组件（圆角全为 0）、细噪点质感

## 四、部署

纯静态产物，任选其一：

```bash
# GitHub Pages：仓库 Settings → Pages → 根目录
python3 scripts/run_pipeline.py --push-git

# Cloudflare Pages
npx wrangler pages deploy . --project-name ai-daily-digest

# Vercel
npx vercel deploy --prod
```

定时任务（以本机 launchd / crontab 为例，每天 06:00 触发）：

```cron
0 6 * * * cd /path/to/ai-daily-digest && /usr/bin/python3 scripts/run_pipeline.py --push-git >> logs/pipeline.log 2>&1
```

推送渠道通过环境变量注入，不要写进仓库：

```bash
export OPENAI_API_KEY=sk-...
export FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/...
export WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
python3 scripts/notify.py --date 2026-09-17 --dry-run   # 先看内容再发
```

## 五、固定访问地址

**内容每天更新，地址永远不变。**

### 本机固定地址（已启用，零依赖）

```
http://localhost:8080/index.html      # 最新一期
http://localhost:8080/archive.html    # 历史归档
```

已注册为 launchd 常驻服务（`com.ai-daily-digest.server`，开机自启、崩溃自动重启）：

```bash
# 安装 / 重装
cp deploy/com.ai-daily-digest.server.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.ai-daily-digest.server.plist

# 一键打开固定地址（已在运行则直接打开）
./scripts/serve.sh
```

因为服务直接读磁盘，每天 `build_site.py` 覆盖 `index.html` 后**无需重启**，刷新浏览器即是最新一期。

### 手机 / 局域网访问

`localhost` 在手机上指向手机自己，所以手机要用下面两个地址之一（服务已监听 `0.0.0.0`，只要手机和 Mac 在同一个 Wi-Fi）：

```
http://delias-MacBook-Pro.local:8080/index.html   ← 推荐：mDNS，IP 变了也能用
http://10.64.38.105:8080/index.html               ← 备用：当前局域网 IP
```

- 扫码打开：见 `deploy/qrcode-lan.png`（`./scripts/serve.sh` 会自动重新生成）
- 首次从手机访问时，macOS 可能弹出「是否允许 python3 接收传入网络连接」，点**允许**
- 页面本身是响应式的：手机自动切单栏，锚点导航降级为横向 chip，归档抽屉可全屏滑出

> 若手机和 Mac 不在同一网络，请用下面的公网方案。

### 公网固定地址（任选其一，一次配置终身不变）

| 方案 | 固定地址形态 | 配置命令 |
| --- | --- | --- |
| GitHub Pages | `https://<owner>.github.io/<repo>/` | 仓库 Settings → Pages → GitHub Actions；已内置 `.github/workflows/daily-pages.yml`（每天 09:00 自动跑流水线 + 发布） |
| Cloudflare Pages | `https://ai-daily-digest.pages.dev` | `npx wrangler pages deploy . --project-name ai-daily-digest`（配置见 `wrangler.toml`），支持绑定自定义域名 |
| Vercel | `https://<project>.vercel.app` | `npx vercel deploy --prod` |

> 不要用「每次新建沙箱」的临时托管做长期入口——那类地址每次发布都会变。

### 首页与归档的自动更新机制

`assets/app.js` 在加载时拉取 `data/index.json`：

- 首页自动对齐最新一期（标题、日期、正文、目录、标签云全部重渲染），**新增 `data/<date>.json` 后无需重新构建**；
- 归档页自动重建列表，并会探测索引之后最多 7 天的新 JSON 自动补录；
- 历史快照 `archive/<date>.html` 内容保持不变，只同步跳转器与抽屉。
