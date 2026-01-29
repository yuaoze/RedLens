# RedLens v1.1.1 - 功能3: 数据采集关键词筛选

## 功能概述

在数据采集面板添加关键词筛选功能，允许用户按来源关键词标签筛选要采集的pending博主。

## 实现内容

### 1. 数据库层新增函数 (`db.py`)

#### BloggerDB类新增方法：

**`get_pending_bloggers_by_keyword(keyword, limit)`** - 按关键词筛选pending博主
- 参数：
  - `keyword`: 关键词字符串（None表示全部pending博主）
  - `limit`: 返回数量限制（默认5）
- 使用 LIKE 查询匹配 source_keyword
- 按 created_at ASC 排序（先进先出）
- 返回符合条件的pending博主列表

**`count_pending_by_keyword(keyword)`** - 统计按关键词筛选的pending博主数量
- 参数：
  - `keyword`: 关键词字符串（None表示全部pending博主）
- 返回符合条件的pending博主数量
- 用于实时显示待采集博主数量

**代码位置**: `red_lens/db.py:148-205`

### 2. 前端UI实现 (`app.py`)

#### 侧边栏数据采集部分改进

**新增元素**：

##### A. 关键词筛选下拉框
- **位置**: "📥 数据采集"部分顶部
- **功能**:
  - 自动提取所有pending博主的source_keyword
  - 生成下拉选项：["全部关键词", "城市风光", "自然风光", ...]
  - 实时更新待采集博主数量
- **代码**: `red_lens/app.py:102-123`

##### B. 动态博主计数
- 根据选中的关键词实时显示待采集博主数量
- "全部关键词" → 显示所有pending博主数量
- 特定关键词 → 显示该关键词的pending博主数量

##### C. 将要采集的博主预览
- 在点击"开始采集数据"后
- 使用 st.expander 展开显示将要采集的博主列表
- 显示博主昵称和关键词
- 默认折叠，用户可展开查看

##### D. 内联采集逻辑
- 根据筛选条件获取目标博主列表
- 使用 `get_pending_bloggers_by_keyword()` 或 `get_pending_bloggers()`
- 逐个调用 MediaCrawler 采集
- 显示实时进度：`[1/5] 正在采集: 博主名`
- 自动延迟10-30秒防止风控

**代码位置**: `red_lens/app.py:99-227`

### 3. 用户体验改进

#### 智能默认值
- 采集数量默认值自动调整为 `min(5, pending_count)`
- 避免用户输入超过实际可用博主数量

#### 实时反馈
- 选择关键词后立即显示该关键词的pending博主数量
- 采集过程中显示当前进度 `[n/total]`
- 采集完成后显示详细统计

#### 安全提示
- 展开查看将要采集的博主列表
- 避免误操作采集错误的博主

## 测试验证

### 测试脚本: `test_keyword_filter.py`

创建了完整的测试套件，包含4个测试用例：

1. **✅ Get Pending Bloggers by Keyword** - 验证关键词筛选
   - 测试关键词: "城市风光"
   - 找到10位博主
   - 验证所有博主都是pending状态
   - 验证所有博主都包含该关键词

2. **✅ Count Pending by Keyword** - 验证计数功能
   - 城市风光: 85位
   - 自然风光: 58位
   - 总计: 143位
   - 验证与手动计数一致

3. **✅ Nonexistent Keyword Handling** - 验证不存在关键词的处理
   - 测试关键词: "这个关键词绝对不存在_xyz123"
   - 正确返回0个结果
   - 正确返回计数0

4. **✅ Limit Parameter** - 验证limit参数
   - 测试 limit=1,3,5,10
   - 所有limit值都正确生效

**测试结果**: 4/4 tests passed 🎉

### 实际数据验证

#### 数据库状态
```
总pending博主: 143位
关键词分布:
  - 城市风光: 85位
  - 自然风光: 58位
```

#### 筛选测试
```
筛选"城市风光": 返回10位博主（limit=10）
✅ 所有博主都包含"城市风光"关键词
✅ 所有博主状态都是pending

示例博主:
  • clair obscur (城市风光)
  • 信 (城市风光)
  • 遁走的两轮 (城市风光)
  • 好大的雨_ (城市风光)
  • YK的城市日志 (城市风光)
```

## 功能特性

### 精确筛选
- 支持按关键词精确筛选pending博主
- 支持"全部关键词"选项查看所有pending博主
- LIKE查询支持模糊匹配

### 实时统计
- 动态显示当前筛选条件下的博主数量
- 自动调整采集数量的合理默认值

### 采集控制
- 只采集符合筛选条件的博主
- 展开查看将要采集的博主列表
- 避免误操作

### 性能优化
- 关键词列表自动去重和排序
- 使用索引优化的SQL查询
- 限制pending博主查询数量（最多1000位）

## 使用场景

### 场景1: 分关键词采集
**问题**: 用户从多个关键词发现了博主，想先采集特定关键词的博主

**解决方案**:
1. 在数据采集面板选择"筛选待采集博主"
2. 选择特定关键词（如"城市风光"）
3. 系统显示该关键词下有85位待采集博主
4. 设置采集数量（如5位）
5. 开始采集，只会采集"城市风光"关键词的博主

### 场景2: 查看采集进度
**问题**: 用户想知道每个关键词还有多少博主未采集

**解决方案**:
1. 在下拉框中切换不同关键词
2. 实时查看每个关键词的pending数量
3. 规划采集顺序

### 场景3: 避免重复采集
**问题**: 用户想确保只采集指定关键词的博主

**解决方案**:
1. 选择关键词后，点击"开始采集数据"
2. 展开"📋 将要采集的博主"查看列表
3. 确认无误后等待采集完成

## 文件变更

**修改的文件**:
- `red_lens/db.py` - 新增2个关键词筛选函数
- `red_lens/app.py` - 侧边栏添加关键词筛选和内联采集逻辑

**新增的文件**:
- `red_lens/test_keyword_filter.py` - 功能测试脚本
- `red_lens/FEATURE_V1.1.1_KEYWORD_FILTER.md` - 本文档

## 技术细节

### SQL查询优化
使用参数化查询和LIKE匹配：
```sql
SELECT * FROM bloggers
WHERE status = 'pending' AND source_keyword LIKE '%keyword%'
ORDER BY created_at ASC
LIMIT ?
```

### 关键词提取
从pending博主中提取唯一关键词：
```python
all_pending = BloggerDB.get_pending_bloggers(limit=1000)
pending_keywords = set()
for blogger in all_pending:
    if blogger.get("source_keyword"):
        pending_keywords.add(blogger["source_keyword"])
```

### 条件分支
根据筛选条件选择不同的查询方法：
```python
if filter_keyword:
    target_bloggers = BloggerDB.get_pending_bloggers_by_keyword(
        keyword=filter_keyword,
        limit=scrape_limit
    )
else:
    target_bloggers = BloggerDB.get_pending_bloggers(limit=scrape_limit)
```

## 验证清单

- [x] 数据库函数实现完整（2个新函数）
- [x] 关键词下拉框显示正常
- [x] 关键词切换时博主数量正确更新
- [x] 采集时只处理选中关键词的博主
- [x] 将要采集的博主列表显示正确
- [x] 采集进度实时显示
- [x] 不存在的关键词正确处理
- [x] Limit参数功能正常
- [x] 所有测试通过 (4/4)

## 状态

✅ **功能3完成** - 数据采集关键词筛选功能已全部实现并测试通过

## v1.1.1版本总结

### 三个功能全部完成：

1. ✅ **功能1: 笔记URL链接**
   - 数据库添加note_url字段
   - 前端爆款画廊和详细分析页面添加跳转链接
   - 1032条现有笔记URL已更新

2. ✅ **功能2: 数据库清理功能**
   - 单个博主数据清空（详细分析页面）
   - 博主管理页面（筛选+批量删除/重置）
   - 二次确认和进度显示

3. ✅ **功能3: 采集关键词筛选**
   - 按关键词筛选pending博主
   - 实时统计和采集控制
   - 支持"全部关键词"选项

### 测试统计
- 功能1: 3/3 tests passed
- 功能2: 5/5 tests passed
- 功能3: 4/4 tests passed
- **总计: 12/12 tests passed 🎉**

### 代码变更
- 修改文件: 2个 (db.py, app.py)
- 新增测试: 3个
- 新增代码: ~800行
- 新增功能文档: 3个

**v1.1.1版本开发完成！** 🚀
