# RedLens v1.2.3 - 功能总结

**版本**: v1.2.3
**日期**: 2026-02-12
**核心功能**: 关键词过滤增强 + 粉丝数获取逻辑优化

---

## 🎯 功能概述

本次更新主要解决了两个关键问题：
1. **关键词过滤传递问题** - 修复了正常采集模式下关键词过滤参数未传递的bug
2. **粉丝数获取稳定性** - 大幅优化博主粉丝数获取逻辑，支持多文件搜索和异常处理

---

## 📝 功能详情

### 功能1: 关键词过滤参数传递修复

#### 问题背景

在 v1.2.2 版本中，关键词过滤功能存在于数据库查询层面，但在正常采集模式下，`source_keyword` 参数未传递到 `scrape_pending_bloggers()` 函数，导致采集时无法按关键词过滤博主。

#### 解决方案

**文件**: `red_lens/app.py:220`

```python
stats = scrape_pending_bloggers(
    use_existing_data=False,
    limit=max_bloggers,
    max_notes=max_notes_per_blogger,
    min_fans=min_fans,
    resume_partial=False,
    batch_size=batch_size,
    source_keyword=filter_keyword  # ✅ 新增：传递关键词过滤参数
)
```

#### 影响

- ✅ 正常采集模式下支持按关键词过滤博主
- ✅ 与断点续采模式保持一致的过滤逻辑
- ✅ 避免采集不相关的博主

---

### 功能2: 粉丝数获取逻辑大幅优化

#### 问题背景

之前的粉丝数获取逻辑存在以下问题：
1. **只查找最新的一个 JSON 文件** - 如果目标博主不在最新文件中则丢失
2. **MediaCrawler 多批次生成文件** - 每次运行可能生成新文件，导致历史数据遗漏
3. **缺少 Fallback 机制** - HTML 解析失败时无法诊断原因
4. **错误处理不足** - JSON 读取失败时直接中断

#### 优化方案

**文件**: `red_lens/pipeline.py:46-139`

##### 1. 多文件搜索机制

```python
# ✅ 搜索所有最近的 creator 文件（按时间倒序）
creator_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

found_count = 0
remaining_ids = set(user_ids)

for json_file in creator_files:
    if not remaining_ids:
        break  # 所有用户已找到

    # 从当前文件中查找剩余的用户
    for creator in creators:
        if user_id in remaining_ids:
            result[user_id] = fans
            remaining_ids.remove(user_id)
            print(f"✓ {nickname}: {fans:,} fans (from {json_file.name})")
```

##### 2. Fallback 到 content 文件

```python
# ✅ 如果 creator_creators 文件中找不到，尝试 creator_contents 文件
if remaining_ids:
    print(f"ℹ️  Some user_ids not found in creator_creators files, checking creator_contents...")
    content_files = list(json_dir.glob("creator_contents_*.json"))

    for content in contents:
        if user_id in remaining_ids:
            result[user_id] = 0  # ⚠ content 文件不包含粉丝数
            print(f"⚠ {nickname}: found in content file but fans count not available")
```

##### 3. MediaCrawler HTML 解析失败诊断

```python
# ✅ 检测 MediaCrawler 的 get_creator_info() 是否失败
if remaining_ids and len(creator_files) > 0:
    latest_creator_file = creator_files[0]
    file_age_seconds = (datetime.now().timestamp() - latest_creator_file.stat().st_mtime)

    if file_age_seconds < 60:  # 文件很新但没有数据
        print(f"⚠️  Warning: Latest creator_creators file exists but doesn't contain requested user_ids.")
        print(f"⚠️  This typically means MediaCrawler's get_creator_info() failed to parse HTML.")
```

##### 4. 异常处理增强

```python
try:
    with open(json_file, 'r', encoding='utf-8') as f:
        creators = json.load(f)
    # ... 处理逻辑
except Exception as e:
    print(f"⚠ Warning: Failed to read {json_file.name}: {e}")
    continue  # ✅ 跳过损坏的文件，继续处理其他文件
```

#### 优化效果

| 优化前 | 优化后 |
|--------|--------|
| 只查找最新 1 个文件 | 查找所有最近的文件（多个批次） |
| 找不到用户直接返回 0 | 尝试 Fallback 到 content 文件 |
| 无法诊断 MediaCrawler 失败 | 检测并提示 HTML 解析失败 |
| JSON 错误直接中断 | 跳过损坏文件继续处理 |
| 无详细日志 | 输出每个用户的来源文件和状态 |

---

### 功能3: 关键词过滤逻辑增强

#### 新增功能

**文件**: `red_lens/pipeline.py:609-646`

支持在采集前按 `source_keyword` 过滤博主列表：

```python
def scrape_pending_bloggers(
    ...
    source_keyword: Optional[str] = None  # ✅ 新参数
):
    # 打印过滤信息
    if source_keyword:
        print(f"Source keyword filter: {source_keyword}")

    # 从数据库中获取匹配关键词的博主
    all_pending_by_keyword = BloggerDB.get_pending_bloggers_by_keyword(source_keyword, limit=1000)
    all_resumable_by_keyword = [
        b for b in all_resumable
        if b.get('source_keyword', '').find(source_keyword) != -1
    ]

    # 去重并限制数量
    keyword_matched = all_pending_by_keyword + all_resumable_by_keyword
    target_bloggers = keyword_matchers[:limit]
```

#### 应用场景

- ✅ 正常采集时按关键词过滤博主（如只采集"风光摄影"关键词的博主）
- ✅ 断点续采时仅恢复特定关键词的博主
- ✅ 避免不相关博主消耗采集配额

---

## 🔧 配置调整

### 1. Headless 模式切换

**文件**: `config/base_config.py:39`

```python
# 优化前
HEADLESS = False  # 打开浏览器调试模式

# 优化后
HEADLESS = True  # ✅ 生产环境使用无头模式
```

**影响**:
- ✅ 减少资源占用
- ✅ 适合服务器环境运行
- ✅ 提升采集效率

### 2. AI API 配置调整

**文件**: `config/ai_config.py:13-16`

```python
# 优化前（从环境变量读取）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# 优化后（直接配置）
DEEPSEEK_API_KEY = ""
```

⚠️ **注意**: 此配置包含敏感信息，建议在提交前恢复为环境变量读取方式

---

## 📊 代码变更统计

| 文件 | 插入 | 删除 | 净增 | 说明 |
|------|------|------|------|------|
| `red_lens/pipeline.py` | +83 | -18 | +65 | 粉丝数获取逻辑优化 + 关键词过滤 |
| `red_lens/app.py` | +2 | -1 | +1 | 传递 source_keyword 参数 |
| `config/base_config.py` | +1 | -1 | 0 | HEADLESS 模式切换 |
| `config/ai_config.py` | +1 | -1 | 0 | API Key 配置调整 |
| `red_lens/red_lens.db` | - | - | - | 数据更新 |
| **总计** | **+87** | **-21** | **+66** | **净增66行** |

---

## 🐛 Bug修复

### Bug 1: 关键词过滤参数未传递

**问题**: 正常采集模式下，`source_keyword` 参数未传递到 `scrape_pending_bloggers()`

**影响**: 无法按关键词过滤博主，导致采集不相关的博主

**修复**: `red_lens/app.py:220` - 添加 `source_keyword=filter_keyword` 参数传递

---

### Bug 2: 粉丝数获取不稳定

**问题**: 只查找最新的 JSON 文件，导致多批次采集时丢失历史数据

**影响**:
- 部分博主的粉丝数返回 0
- 无法判断是真的 0 粉丝还是数据丢失
- MediaCrawler 解析失败时无法诊断

**修复**: `red_lens/pipeline.py:46-139`
- ✅ 多文件搜索机制（按时间倒序）
- ✅ Fallback 到 creator_contents 文件
- ✅ 增加 MediaCrawler HTML 解析失败诊断
- ✅ 异常处理增强（跳过损坏文件）
- ✅ 详细日志输出（来源文件、状态）

---

## 🎁 用户价值

### 关键词过滤增强

✅ **精准采集**: 只采集符合关键词的博主，节省配额
✅ **逻辑一致**: 正常采集和断点续采的过滤逻辑统一
✅ **参数透明**: UI 层面的关键词过滤正确传递到采集层

### 粉丝数获取优化

✅ **数据完整性**: 支持多批次文件搜索，不遗漏历史数据
✅ **稳定性提升**: 异常处理增强，单个文件损坏不影响整体
✅ **可诊断性**: 清晰的日志输出，快速定位问题
✅ **Fallback 机制**: creator 文件找不到时尝试 content 文件
✅ **MediaCrawler 诊断**: 检测并提示 HTML 解析失败

---

## 🔄 兼容性

- ✅ **数据库 Schema**: 无需迁移
- ✅ **已有数据**: 不受影响
- ✅ **API 接口**: 无变化
- ✅ **其他功能**: AI 报告、数据管理功能正常

---

## 📚 相关文档

- `red_lens/feature_log/FEATURE_V1.2.0_SUMMARY.md` - v1.2.0 功能总结（AI 洞察报告 + 断点续采）
- `red_lens/feature_log/FEATURE_V1.2.1_SUMMARY.md` - v1.2.1 功能总结（手动采集 + 逻辑优化）
- `red_lens/feature_log/FEATURE_V1.2.2_SUMMARY.md` - v1.2.2 功能总结（双模式 AI 报告）

---

## ⚠️ 待处理事项

### 安全建议

1. **API Key 配置** (`config/ai_config.py`)
   - 当前直接配置了 API Key（不推荐）
   - 建议恢复为环境变量读取方式：
     ```python
     DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
     ```
   - 或在 `.gitignore` 中排除 `config/ai_config.py`

### 功能增强建议

1. **粉丝数缓存**
   - 可考虑缓存已获取的粉丝数，避免重复调用 MediaCrawler
   - 定期刷新缓存（如 24 小时后过期）

2. **关键词模糊匹配**
   - 当前使用 `str.find()` 进行包含匹配
   - 可考虑支持正则表达式或多关键词匹配

---

**版本**: v1.2.3
**更新时间**: 2026-02-12
**核心价值**: 提升关键词过滤准确性和粉丝数获取稳定性，优化采集体验
