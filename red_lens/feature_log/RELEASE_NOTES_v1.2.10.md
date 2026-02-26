# RedLens v1.2.10 更新说明

## 版本信息
- **版本号**: v1.2.10
- **发布日期**: 2026-02-25
- **更新类型**: 功能增强

---

## ✨ 新增功能

### 1. 历史报告下拉选择器

**问题**: 之前的报告展示使用expander列表，当报告数量多时滚动查看不便。

**改进**: 改为下拉选择器(selectbox)模式

**效果**:
- 更紧凑的UI布局
- 在不同报告之间快速切换
- 清晰显示报告总数
- 只显示当前选中的报告，减少页面长度

**位置**: `red_lens/app.py` (line 994-1030)

**使用方法**:
1. 在"详细分析"页面查看已生成报告
2. 使用下拉框选择要查看的报告
3. 下拉框格式：`{模式} | {提供商}-{模型} | {生成时间}`
4. 报告内容实时切换

---

### 2. 笔记封面自动下载与本地缓存

**功能**: 支持下载和本地存储笔记封面，用于AI多模态分析

#### 2.1 自动下载（新增）

**功能**: 博主采集完成后自动下载封面，无需手动操作

**位置**:
- `red_lens/pipeline.py` (line 987-1035) - `scrape_pending_bloggers()`
- `red_lens/pipeline.py` (line 1379-1427) - `scrape_specific_bloggers()`
- `red_lens/pipeline.py` (line 1706-1715) - `collect_blogger_by_manual_id()`

**触发时机**:
1. **批量采集**: `scrape_pending_bloggers()` 完成后
2. **指定采集**: `scrape_specific_bloggers()` 完成后
3. **手动采集**: `collect_blogger_by_manual_id()` 完成后

**工作流程**:
```
博主采集 → 保存笔记到数据库 → 自动下载封面 → 显示统计
```

**输出示例**:
```
============================================================
📥 Auto-downloading note covers
============================================================

📥 Downloading covers for: 上五楼的快活
  ✓ Downloaded: 10 Top + 5 Bottom covers

📥 Downloading covers for: 摄影师小李
  ✓ Downloaded: 10 Top + 5 Bottom covers
  ⚠ Failed: 2 covers

============================================================
Cover Download Summary
============================================================
✓ Bloggers processed: 2
✓ Total Top covers: 20
✓ Total Bottom covers: 10
✗ Failed: 2
============================================================
```

#### 2.2 手动下载（保留）

**功能**: 提供UI按钮手动触发下载（用于重新下载或更新封面）

**位置**: `red_lens/app.py` (line 893-928)

**重要改进**: 使用精准爬取模式，只爬取15条笔记

**工作流程**:
```
用户点击"下载封面"
  ↓
步骤 1/2: 刷新封面URL
  - 调用 refresh_note_cover_urls()
  - 使用 XHS_SPECIFIED_NOTE_URL_LIST 精准爬取15条笔记
  - 使用 detail 模式（指定笔记详情模式）
  - 更新数据库中的封面URL（原URL可能已失效）
  - 显示更新的笔记数量
  ↓
步骤 2/2: 下载封面
  - 使用最新的封面URL下载图片
  - 保存到本地目录
  - 显示下载统计
```

**为什么需要两步**:
- 小红书的封面URL是临时链接（如 `http://sns-webpic-qc.xhscdn.com/...`）
- 时间久了会失效，无法直接下载
- 必须先重新爬取获取新鲜的URL

**精准爬取优势**:
- ✅ **高效**: 只爬取15条笔记，不是整个博主的所有笔记
- ✅ **精准**: 使用 `XHS_SPECIFIED_NOTE_URL_LIST` 指定笔记URL列表
- ✅ **快速**: 约1-2分钟完成（vs 重新爬取整个博主需5-10分钟）
- ✅ **无干扰**: 不会被智能过滤（exclude_note_ids_map）影响

**技术实现**:
- 函数: `refresh_note_cover_urls(user_id)` - `red_lens/pipeline.py` (line 25-142)
- MediaCrawler: detail 模式 + `XHS_SPECIFIED_NOTE_URL_LIST`
- 数据库: `NoteDB.update_cover_url()` 更新封面URL

**功能**:
- 📥 下载封面按钮（手动触发）
- 🎯 精准爬取15条笔记（Top 10 + Bottom 5）
- 🔄 自动处理URL失效问题（刷新+下载）
- 📊 显示已下载封面统计（Top封面数 + Bottom封面数）
- 📁 显示存储路径：`red_lens/covers/{user_id}/`
- ⚠️ 多模态模型提示（提醒用户下载封面以获得更好分析效果）

#### 2.3 封面下载逻辑

**位置**: `red_lens/analyzer.py` (line 381-488)

**函数**: `download_note_covers(user_id: str, force_redownload: bool = False)`

**功能**:
- 自动获取博主的Top 10和Bottom 5笔记
- 下载封面图片并转换为JPEG格式
- 统一命名格式：`top_01_{note_id}.jpg`, `bottom_01_{note_id}.jpg`
- 存储路径：`red_lens/covers/{user_id}/`
- 支持强制重新下载
- 返回下载统计：`{'top': count, 'bottom': count, 'failed': count}`

**文件命名规则**:
```
top_01_5d4d634f000000001102f282.jpg   # Top 1笔记封面
top_02_5d4d634f000000001102f283.jpg   # Top 2笔记封面
...
top_10_5d4d634f000000001102f28b.jpg   # Top 10笔记封面
bottom_01_5d4d634f000000001102f28c.jpg # Bottom 1笔记封面
...
bottom_05_5d4d634f000000001102f290.jpg # Bottom 5笔记封面
```

#### 2.4 AI分析优先使用本地封面

**位置**: `red_lens/analyzer.py` (line 491-614)

**修改**: `prepare_images_for_ai()` 函数

**新增参数**:
- `user_id: str = None` - 博主ID，用于查找本地封面

**逻辑优化**:
1. **优先本地**: 如果传入`user_id`，先尝试从本地加载封面
2. **降级下载**: 本地不存在时才从URL下载
3. **性能提升**: 避免重复下载，减少API调用时间
4. **日志输出**:
   - `✓ Loaded from local: filename` - 成功从本地加载
   - `• Downloading image...` - 从URL下载

**调用示例**:
```python
# analyzer.py line 864
images = prepare_images_for_ai(
    top_notes,
    max_images=config.AI_MAX_IMAGES_PER_REPORT,
    use_base64=use_base64,
    user_id=user_id  # 传入user_id以启用本地加载
)
```

---

## 📊 效果对比

### 历史报告UI对比

**修复前 (Expander)**:
```
已生成的报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
▼ 流量拆解 | deepseek-reasoner | 2026-02-20 10:30:15
  [完整报告内容，占据大量页面空间]

▼ 个人复盘 | kimi-k2.5 | 2026-02-21 15:45:20
  [完整报告内容]

▼ 流量拆解 | kimi-k2.5 | 2026-02-22 09:10:30
  [完整报告内容]
```

**修复后 (Selectbox)**:
```
已生成报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
选择报告: [流量拆解 | deepseek-reasoner | 2026-02-20 10:30:15 ▼]
          共有 3 个报告

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[仅显示选中的报告内容]

[删除报告] [导出报告]
```

### 封面下载流程

```
笔记封面管理
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ 已下载: 10 个Top封面 + 5 个Bottom封面

[🔄 重新下载]

✅ 该模型支持图像分析，将优先使用本地封面图片
```

---

## 🔧 技术细节

### 封面存储结构

```
red_lens/
├── covers/
│   ├── 5d4d634f000000001102f282/    # 博主1
│   │   ├── top_01_note123.jpg
│   │   ├── top_02_note124.jpg
│   │   ├── ...
│   │   ├── bottom_01_note456.jpg
│   │   └── bottom_05_note460.jpg
│   ├── 6e5e745g000000002203g393/    # 博主2
│   │   └── ...
```

### 图片处理流程

1. **下载**: 从笔记的`cover_url`字段获取图片
2. **转换**: 使用PIL转换为JPEG格式
3. **命名**: `{rank}_{index:02d}_{note_id}.jpg`
4. **保存**: 存储到`covers/{user_id}/`目录

### AI分析加载流程

```python
# 1. 尝试本地加载
covers_dir = Path(__file__).parent / 'covers' / user_id
matching_files = list(covers_dir.glob(f"*_{note_id}.jpg"))

if matching_files:
    # 使用本地文件
    with open(matching_files[0], 'rb') as f:
        img_data = f.read()
    print(f"✓ Loaded from local: {matching_files[0].name}")
else:
    # 降级：从URL下载
    response = requests.get(note['cover_url'])
    img_data = response.content
    print("• Downloading image...")
```

---

## 🎯 使用指南

### 对于新用户

1. 采集博主数据后，进入"详细分析"页面
2. 点击"📥 下载封面"按钮
3. 等待下载完成（约5-15秒）
4. 选择支持视觉的AI模型（如KIMI k2.5）
5. 生成报告时会自动使用本地封面

### 对于已有用户

**重新下载封面**:
- 如果笔记数据已更新（爬取了新数据）
- 点击"🔄 重新下载"按钮更新封面

**检查封面状态**:
```bash
ls -lh red_lens/covers/{user_id}/
```

---

## 📝 修改文件

### 修改
- `red_lens/app.py` (line 873-920, 994-1030)
  - 新增封面管理UI
  - 修改历史报告展示为下拉选择器

- `red_lens/analyzer.py` (line 381-488, 491-614, 864)
  - 新增`download_note_covers()`函数
  - 修改`prepare_images_for_ai()`支持本地加载
  - 调用时传入`user_id`参数

---

## 🔄 向后兼容性

✅ **完全兼容**

- **不传user_id**: `prepare_images_for_ai()`仍然从URL下载，行为与v1.2.9一致
- **旧报告**: 历史报告仍然可以正常查看
- **无封面**: 未下载封面时，AI分析自动降级到URL下载

---

## 🐛 已知问题

### 封面下载失败

**原因**: 部分笔记的`cover_url`可能为空或无法访问

**表现**: 下载统计显示`失败: X 张`

**影响**: 不影响其他封面下载和AI分析（会跳过失败的图片）

**解决方案**: 无需处理，AI分析时会自动忽略失败的封面

---

## 📚 相关文档

- 多AI模型支持: `RELEASE_NOTES_v1.2.4.md`
- KIMI base64修复: `RELEASE_NOTES_v1.2.7.md`
- KIMI超时修复: `RELEASE_NOTES_v1.2.8.md`
- KIMI markdown修复: `RELEASE_NOTES_v1.2.9.md`

---

**开发者**: Claude (Anthropic)
**发布日期**: 2026-02-25
**状态**: ✅ 已完成并测试
**影响范围**: UI增强 + 封面管理
**向后兼容**: ✅ 完全兼容
