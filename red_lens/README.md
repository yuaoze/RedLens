# RedLens - 小红书摄影博主分析工具

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org)

RedLens 是一个基于 MediaCrawler 的小红书摄影博主分析工具，用于自动化挖掘博主、采集数据、清洗入库，并进行 AI 洞察分析。

## ✨ 功能特性

- 🔍 **智能发现**: 通过关键词搜索自动发现优质摄影博主
  - ✅ 实时调用 MediaCrawler 爬取数据
  - ✅ 支持使用现有数据或实时爬取两种模式
  - ✅ 自动过滤低互动博主（可配置点赞阈值）
- 📥 **数据采集**: 批量采集博主的笔记数据和互动指标
  - ✅ 创作者主页数据完整抓取
  - ✅ 可配置每个博主爬取笔记数量（10-200条）
  - ✅ 自动失败重试和错误处理
- 🔥 **爆款识别**: 自动识别高互动的病毒式内容（爆款）
- 📊 **可视化分析**: 交互式 Streamlit 仪表板展示数据洞察
- 🤖 **AI 洞察**: 基于 Claude AI 生成博主内容策略建议
- 💾 **SQLite 存储**: 轻量级数据库，易于部署和维护
- 🧪 **完整测试**: 包含单元测试和集成测试套件

## 🛠️ 技术栈

- **Core Engine**: MediaCrawler（小红书数据采集）
- **Package Manager**: uv（依赖管理）
- **Database**: SQLite with Context Manager Pattern
- **Visualization**: Streamlit + Plotly
- **AI Analysis**: Anthropic Claude API
- **Language**: Python 3.8+
- **Testing**: pytest compatible test suite

## 📦 安装

### 1. 克隆仓库

```bash
cd /path/to/MediaCrawler
# RedLens 已经包含在 red_lens/ 目录中
```

### 2. 安装依赖管理器

本项目使用 `uv` 进行依赖管理，提供更好的隔离性和性能：

```bash
# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. 安装 Python 依赖

```bash
# MediaCrawler 依赖
uv sync

# RedLens 额外依赖
pip install streamlit plotly pandas requests
```

### 4. 初始化数据库

数据库会在首次运行时自动创建，也可以手动初始化：

```bash
python red_lens/db.py
```

## 🚀 快速开始

### 方式 1: 使用 Streamlit 界面（推荐）

```bash
streamlit run red_lens/app.py
```

然后在浏览器中打开 `http://localhost:8501`

### 方式 2: 使用命令行

#### Step 1: 发现博主

```python
# 使用现有数据模式（快速测试）
python -c "
from red_lens.discovery import search_and_extract_users
search_and_extract_users(
    keywords=['富士扫街', '人像摄影', '胶片色调'],
    min_likes=200,
    use_existing=True  # 使用已有 JSON 数据
)
"

# 实时爬取模式（需要浏览器交互）
python -c "
from red_lens.discovery import search_and_extract_users
search_and_extract_users(
    keywords=['富士扫街', '人像摄影', '胶片色调'],
    min_likes=200,
    max_notes=100,  # 每个关键词爬取 100 条笔记
    use_existing=False  # 启动 MediaCrawler 实时爬取
)
"
```

#### Step 2: 采集数据

```python
# 使用现有数据模式
python -c "
from red_lens.pipeline import scrape_pending_bloggers
scrape_pending_bloggers(
    limit=5,
    use_existing_data=True  # 使用已有 creator JSON 数据
)
"

# 实时爬取模式（推荐）
python -c "
from red_lens.pipeline import scrape_pending_bloggers
scrape_pending_bloggers(
    limit=5,
    max_notes=100,  # 每个博主爬取 100 条笔记
    use_existing_data=False  # 启动 MediaCrawler 实时爬取
)
"
```

#### Step 3: 分析爆款

```python
python -c "
from red_lens.analyzer import analyze_all_bloggers, download_outlier_covers
analyze_all_bloggers()
download_outlier_covers()
"
```

## 📖 使用指南

### 1. 博主发现

在 Streamlit 侧边栏中：
1. 输入搜索关键词（逗号分隔），例如：`富士扫街,人像摄影,胶片色调`
2. 设置最低点赞数过滤阈值（推荐 200+）
3. **选择运行模式**：
   - **使用现有数据**: 快速分析已有的 JSON 文件（无需浏览器交互）
   - **运行 MediaCrawler 爬取**: 实时启动爬虫获取最新数据（需要登录）
4. 点击 "🚀 开始发现博主"

**实时爬取模式说明**：
- 会弹出浏览器窗口
- 需要扫码登录小红书
- 可能需要手动完成滑动验证
- 首次运行时间较长（3-10分钟）
- 自动禁用评论爬取以提升速度

系统会自动：
- 调用 MediaCrawler 搜索包含关键词的笔记
- 提取点赞数超过阈值的博主
- 去重并保存到数据库，状态设为 `pending`

### 2. 数据采集

在侧边栏中：
1. 设置每次采集的博主数量（建议 5 位）
2. **配置爬取笔记数量**（新增）：使用滑动条设置每个博主爬取 10-200 条笔记（默认 100）
3. 点击 "📊 开始采集数据"

系统会：
- 从数据库读取 `pending` 状态的博主
- 逐个调用 MediaCrawler 创作者模式爬取
- 自动修改并恢复 `config/base_config.py` 和 `config/xhs_config.py`
- 解析 JSON 数据并清洗
- 存入 `notes` 表
- 更新博主状态为 `scraped` 或 `error`
- 随机延迟 10-30 秒（防风控）

**技术细节**：
- 使用纯 user_id 格式（24位十六进制字符）
- 自动禁用评论爬取以提升速度
- 配置文件采用备份-修改-恢复机制
- 支持失败重试和错误记录

### 3. 爆款分析

点击 "🔥 识别所有爆款"：
- 计算每位博主的平均点赞数
- 标记点赞数 > 3x 平均值 且 > 500 的笔记为爆款
- 在数据库中设置 `is_outlier=True`

点击 "📥 下载爆款封面"：
- 下载所有爆款笔记的封面图
- 保存到 `red_lens/assets/covers/`
- 更新数据库中的本地路径

### 4. 查看分析结果

#### 📊 博主排行榜

- 展示所有已采集博主
- 按爆款率排序
- 可视化对比：
  - Top 10 博主爆款率
  - Top 10 博主平均点赞
  - 笔记数量 vs 爆款率散点图

#### 🔥 爆款画廊

- 瀑布流展示所有爆款内容
- 支持筛选：最低点赞数、指定博主
- 显示封面图、互动数据、发布时间

#### 📈 详细分析

选择特定博主查看：
- 数据概览（笔记数、平均点赞、爆款率等）
- 内容分布（图文 vs 视频、爆款 vs 普通）
- 点赞数时间趋势图
- Top 10 热门笔记列表
- 🤖 AI 洞察报告（点击生成）

## 📁 项目结构

```
red_lens/
├── __init__.py              # 包初始化
├── db.py                    # 数据库模块（SQLite + Context Manager）
├── discovery.py             # 博主发现模块（MediaCrawler 搜索模式）
├── pipeline.py              # 数据采集与清洗（MediaCrawler 创作者模式）
├── analyzer.py              # 爆款分析与 AI 洞察
├── app.py                   # Streamlit 可视化界面
├── test_discovery.py        # 发现模块测试套件（8个测试用例）
├── test_pipeline.py         # 管道模块集成测试
├── test_integration.py      # 端到端集成测试
├── red_lens.db              # SQLite 数据库文件（~960KB）
├── assets/
│   └── covers/              # 爆款封面图存储目录
└── README.md                # 本文档
```

## 🗃️ 数据库架构

### bloggers 表

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT (PK) | 用户 ID |
| nickname | TEXT | 昵称 |
| avatar_url | TEXT | 头像 URL |
| initial_fans | INTEGER | 入库时粉丝数 |
| current_fans | INTEGER | 最新粉丝数 |
| source_keyword | TEXT | 来源关键词 |
| status | TEXT | 状态 (pending/scraped/error) |
| last_update | TIMESTAMP | 最后更新时间 |

### notes 表

| 字段 | 类型 | 说明 |
|------|------|------|
| note_id | TEXT (PK) | 笔记 ID |
| user_id | TEXT (FK) | 用户 ID |
| title | TEXT | 标题 |
| desc | TEXT | 描述 |
| type | TEXT | 类型 (video/image) |
| likes | INTEGER | 点赞数 |
| collects | INTEGER | 收藏数 |
| comments | INTEGER | 评论数 |
| create_time | TIMESTAMP | 发布时间 |
| crawled_time | TIMESTAMP | 爬取时间 |
| cover_url | TEXT | 封面 URL |
| local_cover_path | TEXT | 本地封面路径 |
| is_outlier | BOOLEAN | 是否为爆款 |

## 🔬 爆款算法

一篇笔记被标记为爆款需满足：
1. `likes > avg_likes × 3` (点赞数超过该博主平均值的 3 倍)
2. `likes > 500` (绝对点赞数超过 500)

可在 `analyzer.py` 中调整参数：
```python
identify_outliers(user_id, multiplier=3.0, min_likes=500)
```

## 🤖 AI 洞察

目前使用 Mock 报告。如需接入真实 Claude API：

1. 安装 Anthropic SDK：
```bash
pip install anthropic
```

2. 设置 API Key：
```bash
export ANTHROPIC_API_KEY="your-api-key"
```

3. 修改 `analyzer.py` 中的 `generate_ai_report()` 函数，将 `use_mock=False`

## 🧪 测试

项目包含完整的测试套件：

### 运行发现模块测试

```bash
python red_lens/test_discovery.py
```

**测试用例包括**：
- ✅ 函数参数验证
- ✅ 使用现有数据模式
- ✅ 禁用爬虫模式
- ✅ MediaCrawler 函数存在性检查
- ✅ 配置备份恢复机制
- ✅ JSON 文件回退逻辑
- ✅ 模式显示信息
- ✅ MediaCrawler 实际运行（Live 测试）

### 运行管道模块测试

```bash
python red_lens/test_pipeline.py
```

**测试验证**：
- MediaCrawler 创作者模式成功启动
- JSON 数据文件生成/更新
- 笔记数据正确解析并存入数据库
- 配置文件正确修改和恢复

### 运行集成测试

```bash
python red_lens/test_integration.py
```

## ⚠️ 注意事项

1. **遵守平台规则**: 本工具仅供学习研究使用，请遵守小红书使用条款
2. **请求频率控制**: 采集时自动添加 10-30 秒随机延迟
3. **数据存储**: 数据库文件在 `red_lens/red_lens.db`（约 960KB），请定期备份
4. **浏览器交互**: 实时爬取需要扫码登录和滑动验证
5. **环境要求**: 必须使用 `uv` 运行 MediaCrawler，否则会出现依赖错误
6. **配置管理**: 系统会自动备份和恢复配置文件，请勿手动修改正在运行的配置

## 🐛 故障排除

### 问题 1: `ModuleNotFoundError: No module named 'playwright'`

**原因**: 直接使用 `python` 运行，未使用 `uv` 管理依赖

**解决方案**:
```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 使用 uv run 运行
uv run main.py --platform xhs --lt qrcode --type search
```

### 问题 2: 爬取笔记数量少于预期

**原因**: `max_notes` 参数未正确传递或配置文件未更新

**解决方案**:
- 检查 Streamlit 滑动条设置（10-200）
- 确认命令行参数: `scrape_pending_bloggers(max_notes=100)`
- 验证 `config/base_config.py` 中的 `CRAWLER_MAX_NOTES_COUNT` 值

### 问题 3: MediaCrawler 配置错误

**原因**: 配置文件备份/恢复机制失败

**解决方案**:
```bash
# 检查是否有残留的备份文件
ls config/*.redlens_backup

# 手动恢复配置
cp config/base_config.py.redlens_backup config/base_config.py
```

### 问题 4: 创作者 URL 格式错误

**原因**: 使用了带参数的完整 URL 而非纯 user_id

**解决方案**: 系统已自动处理，使用 24 位十六进制 user_id 格式（无需手动修改）

### 问题 5: 扫码登录失败

**原因**: 小红书验证码或滑动验证

**解决方案**:
- 关闭无头模式: 在 `config/base_config.py` 设置 `HEADLESS = False`
- 手动完成浏览器中的验证步骤
- 确保登录状态已保存: `SAVE_LOGIN_STATE = True`

## 🔧 技术实现细节

### Context Manager 数据库模式

```python
@contextmanager
def get_connection():
    """自动处理事务和连接关闭"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()  # 成功则提交
    except Exception:
        conn.rollback()  # 失败则回滚
        raise
    finally:
        conn.close()  # 保证关闭
```

### 配置文件管理策略

1. 备份原始配置到 `.redlens_backup`
2. 使用正则表达式修改目标参数
3. 执行 MediaCrawler
4. 在 `finally` 块中恢复配置
5. 删除备份文件

### MediaCrawler 集成方式

**发现模式** (discovery.py):
- 修改 `base_config.py`: `CRAWLER_TYPE = "search"`
- 设置关键词: `KEYWORDS = "富士扫街,人像摄影"`
- 禁用评论: `ENABLE_GET_COMMENTS = False`
- 执行: `uv run main.py --platform xhs --lt qrcode --type search`

**创作者模式** (pipeline.py):
- 修改 `base_config.py`: `CRAWLER_TYPE = "creator"`
- 修改 `xhs_config.py`: `XHS_CREATOR_ID_LIST = ["user_id_here"]`
- 设置笔记数: `CRAWLER_MAX_NOTES_COUNT = 100`
- 执行: `uv run main.py --platform xhs --lt qrcode --type creator`

## 📝 更新日志

### v1.1.0 (2026-01-28)

**重大更新**：
- ✅ 实现 MediaCrawler 实时集成（discovery.py 和 pipeline.py）
- ✅ 新增运行模式选择（使用现有数据 vs 实时爬取）
- ✅ 新增笔记数量配置滑动条（10-200，默认 100）
- ✅ 自动配置文件管理（备份-修改-恢复）
- ✅ 支持 uv 包管理器（自动检测和回退）
- ✅ 禁用评论爬取以提升速度

**测试覆盖**：
- ✅ 新增 test_discovery.py（8个测试用例）
- ✅ 新增 test_pipeline.py（集成测试）
- ✅ 验证 MediaCrawler 实际运行
- ✅ 验证笔记数量正确性（修复了低计数 bug）

**Bug 修复**：
- 🐛 修复发现模块未调用 MediaCrawler
- 🐛 修复创作者配置在错误的文件中
- 🐛 修复 `ENABLE_GET_COMMENTS` 正则表达式错误
- 🐛 修复笔记数量低于预期（缺少 `CRAWLER_MAX_NOTES_COUNT` 设置）
- 🐛 修复 Python 依赖路径问题（使用 uv）

**文件变更统计**：
- 修改文件: 5 个
- 新增文件: 2 个
- 新增代码: +852 行
- 删除代码: -35 行

## 📝 开发计划

- [x] 支持实时运行 MediaCrawler ✅ v1.1.0
- [x] 配置化笔记数量控制 ✅ v1.1.0
- [x] 完整测试套件 ✅ v1.1.0
- [ ] 接入真实 Claude API 进行 AI 分析
- [ ] 支持更多平台（抖音、B站等）
- [ ] 导出分析报告（PDF/Excel）
- [ ] 粉丝增长追踪
- [ ] 内容标签云分析

## 📄 许可证

本项目基于 MediaCrawler 开发，继承其非商业学习许可证。仅供学习研究使用。

## 🙏 致谢

- [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) - 提供核心爬虫引擎
- [Streamlit](https://streamlit.io/) - 提供可视化框架
- [Anthropic Claude](https://www.anthropic.com/) - AI 分析能力

## 📞 联系方式

如有问题或建议，欢迎提交 Issue。

---

**Happy Analyzing! 📸✨**
