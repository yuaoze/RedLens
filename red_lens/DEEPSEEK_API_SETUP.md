# Deepseek API Key 设置指南

## 快速设置步骤

### 步骤1：设置API Key

您有两种方式设置：

#### 方式1：通过环境变量（推荐）✅

在终端中运行：

```bash
export DEEPSEEK_API_KEY="sk-your-actual-api-key-here"
```

**永久设置**（推荐）：

```bash
# 添加到 ~/.bashrc (或 ~/.zshrc)
echo 'export DEEPSEEK_API_KEY="sk-your-actual-api-key-here"' >> ~/.bashrc
source ~/.bashrc
```

#### 方式2：直接在配置文件中设置

编辑 `config/ai_config.py` 文件：

```python
# 找到第16行，取消注释并替换为您的API Key
DEEPSEEK_API_KEY = "sk-your-actual-api-key-here"
```

⚠️ **注意**：这种方式会将API Key提交到git，不太安全。

---

### 步骤2：启用AI功能

配置文件 `config/ai_config.py` 中的第9行已设置为：

```python
ENABLE_REAL_AI = True  # 已启用真实AI API
```

---

### 步骤3：验证设置

运行测试脚本验证配置是否正确：

```bash
python red_lens/test_ai_report.py
```

**预期输出**：
```
✓ DEEPSEEK_API_KEY configured
   Key length: XX characters
✓ OpenAI package installed
✓ OpenAI client initialization
   Base URL: https://api.deepseek.com
```

---

### 步骤4：测试真实API调用（可选）

如果想测试真实的API调用：

```bash
python red_lens/test_ai_report.py --real-api
```

这会：
1. 选择一个已采集数据的博主
2. 调用Deepseek API生成真实的AI报告
3. 显示报告内容和耗时

---

## 使用AI报告功能

### 在RedLens UI中使用

1. 启动RedLens：
   ```bash
   streamlit run red_lens/app.py
   ```

2. 进入"详细分析"页面

3. 选择一个已采集数据的博主

4. 点击"生成 AI 报告"按钮

5. 系统会：
   - 如果有缓存且未过期，立即返回缓存结果
   - 否则调用Deepseek API生成新报告
   - 生成的报告会自动缓存1小时

### 报告内容

AI报告包括：
- 📊 数据概览
- 🔥 爆款特征分析
- 💡 内容策略建议
- ⏰ 发布时间优化
- 🎬 内容形式建议
- 📈 增长建议

---

## 配置说明

所有AI相关配置在 `config/ai_config.py` 中：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_REAL_AI` | `True` | AI功能总开关 |
| `DEEPSEEK_API_KEY` | 从环境变量读取 | API密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API端点 |
| `AI_MODEL` | `deepseek-chat` | 使用的模型 |
| `AI_MAX_TOKENS` | `2000` | 最大生成token数 |
| `AI_TEMPERATURE` | `1.0` | 生成温度(0-2) |
| `AI_REQUEST_TIMEOUT` | `60` | 请求超时(秒) |
| `AI_REPORT_CACHE_ENABLED` | `True` | 是否启用缓存 |
| `AI_REPORT_CACHE_TTL` | `3600` | 缓存有效期(1小时) |

---

## 常见问题

### Q1: 如何知道API Key是否设置成功？

运行：
```bash
python red_lens/test_ai_report.py
```

如果看到：
```
✓ DEEPSEEK_API_KEY configured
   Key length: XX characters
```
说明设置成功。

### Q2: API调用失败怎么办？

可能的原因：
1. API Key 错误或过期
2. 网络问题
3. API配额用完
4. API服务故障

解决方法：
- 检查API Key是否正确
- 检查网络连接
- 查看Deepseek官网配额情况
- 暂时设置 `ENABLE_REAL_AI = False` 使用Mock模式

### Q3: 如何清除报告缓存？

方式1：在UI中点击"清除缓存"按钮

方式2：运行Python代码：
```python
from red_lens.db import AIReportDB, init_db
init_db()
AIReportDB.clear_cache()  # 清除所有缓存
# 或
AIReportDB.clear_cache(user_id)  # 清除特定用户缓存
```

### Q4: Mock模式和真实API有什么区别？

| 特性 | Mock模式 | 真实API |
|------|---------|---------|
| 需要API Key | ❌ 不需要 | ✅ 需要 |
| 费用 | 免费 | 按token计费 |
| 报告质量 | 模板化 | AI深度分析 |
| 生成速度 | 瞬间 | 3-10秒 |
| 适用场景 | 测试/演示 | 生产使用 |

---

## 费用说明

Deepseek API按token计费，非常便宜：

- **模型**：deepseek-chat
- **价格**：约 ¥0.001/1K tokens（比Claude便宜100倍）
- **单次报告**：约使用500-1000 tokens
- **单次费用**：约 ¥0.0005-0.001（不到1分钱）

**成本估算**：
- 100次报告生成 ≈ ¥0.10
- 1000次报告生成 ≈ ¥1.00

配置了缓存机制后，相同博主1小时内重复查询不会重复调用API。

---

## 安全建议

1. ✅ **使用环境变量**：避免将API Key提交到git
2. ✅ **添加到.gitignore**：如果必须在文件中设置
3. ✅ **定期轮换**：定期更换API Key
4. ✅ **监控使用量**：在Deepseek官网查看API使用情况
5. ✅ **设置配额限制**：避免意外高额费用

---

## 下一步

API Key设置完成后，您可以：

1. ✅ 运行测试验证配置
2. ✅ 启动RedLens并测试AI报告生成
3. ✅ 查看生成的报告质量
4. ✅ 根据需要调整Prompt模板（在`ai_config.py`中）

---

**当前状态**：
- ✅ AI功能已启用（`ENABLE_REAL_AI = True`）
- ⚠️ 需要设置API Key
- ✅ 所有其他配置已就绪

**设置API Key后即可使用！** 🚀
