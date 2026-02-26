# KIMI (Moonshot AI) API 配置指南

## 1. 获取API Key

1. 访问 [Moonshot AI Platform](https://platform.moonshot.cn)
2. 注册/登录账号
3. 进入"API密钥"页面
4. 创建新的API Key并复制（只显示一次，请妥善保管）

## 2. 配置环境变量

### 方法一：环境变量（推荐）

在终端中设置环境变量：

```bash
export KIMI_API_KEY="your_kimi_api_key_here"
```

或者在 `~/.bashrc` 或 `~/.zshrc` 中添加：

```bash
# KIMI API配置
export KIMI_API_KEY="your_kimi_api_key_here"
```

### 方法二：直接修改配置文件

编辑 `config/ai_config.py`：

```python
AI_PROVIDERS = {
    "kimi": {
        "api_key": "your_kimi_api_key_here",  # 直接填入API Key
        "base_url": "https://api.moonshot.cn/v1",
        ...
    }
}
```

**注意**：方法二不建议用于生产环境或公开代码，因为会将API Key暴露在代码中。

## 3. 支持的模型

### moonshot-v1-vision (推荐用于RedLens)
- **特性**：多模态模型，支持图文混合分析
- **上下文**：4K tokens
- **适用场景**：分析笔记封面图片 + 标题数据，提供视觉洞察
- **费用**：输入约 ¥0.03/1K tokens，输出约 ¥0.1/1K tokens
- **图片处理**：每张图片约消耗 500-1000 tokens（取决于分辨率）

### moonshot-v1-8k
- **特性**：纯文本模型
- **上下文**：8K tokens
- **适用场景**：不需要视觉分析的场景

### moonshot-v1-32k
- **特性**：纯文本模型
- **上下文**：32K tokens
- **适用场景**：需要处理大量文本数据的场景

### moonshot-v1-128k
- **特性**：纯文本模型
- **上下文**：128K tokens
- **适用场景**：超长上下文分析

## 4. 在RedLens中使用

### 启动RedLens

```bash
cd red_lens
streamlit run app.py
```

### 生成AI报告

1. 在左侧边栏选择已爬取的博主
2. 进入"详细分析"标签页
3. 在"AI模型配置"区域：
   - **AI服务提供商**：选择"🌙 KIMI (Moonshot)"
   - **AI模型**：选择"KIMI Vision (多模态)"（推荐）
4. 选择报告模式（流量拆解 / 个人复盘）
5. 点击"🚀 生成AI报告"

### 视觉分析功能

当使用 `moonshot-v1-vision` 模型时，RedLens会：

- 自动提取Top 5笔记的封面图片
- 将图片和标题数据一起发送给AI
- 生成包含视觉分析的报告（色调、构图、视觉风格等）

**示例报告特性**：
- 视觉风格识别（日系、赛博朋克、极简等）
- 封面与标题的协同效果分析
- 视觉吸引力评估
- 封面优化建议

## 5. 费用估算

### 单次报告成本（使用Vision模型）

- **输入数据**：
  - 系统Prompt：约 500 tokens
  - 用户Prompt（博主数据）：约 1000 tokens
  - 封面图片（5张）：约 5000 tokens (1000 tokens/张)
  - **总计输入**：约 6500 tokens → ¥0.20

- **输出数据**：
  - AI报告：约 2000 tokens
  - **总计输出**：约 2000 tokens → ¥0.20

- **单次报告费用**：约 ¥0.40 - ¥0.50

### 节省成本的方法

1. **使用纯文本模型**：如果不需要视觉分析，选择 `moonshot-v1-8k`，成本降低约60%
2. **减少图片数量**：在 `config/ai_config.py` 中调整：
   ```python
   AI_MAX_IMAGES_PER_REPORT = 3  # 默认5张，可改为3张
   ```
3. **缓存报告**：避免重复生成相同的报告

## 6. API限流说明

### 免费账户
- **并发限制**：3 RPM (Requests Per Minute)
- **每日限额**：根据账户等级不同

### 付费账户
- 更高的并发限制和额度
- 详见 [Moonshot AI 定价页面](https://platform.moonshot.cn/pricing)

### 应对限流

如果遇到 `429 Too Many Requests` 错误：

1. 等待1分钟后重试
2. 减少并发请求
3. 升级到付费账户

## 7. 常见问题

### Q: KIMI API Key配置了但提示未配置？

**A**: 检查以下几点：
1. 环境变量是否正确设置：`echo $KIMI_API_KEY`
2. 重启终端或IDE以加载新的环境变量
3. 确认API Key没有多余的空格或引号

### Q: 报告生成失败，提示"403 Forbidden"？

**A**:
- 检查API Key是否正确
- 确认账户是否欠费
- 登录 [Moonshot Platform](https://platform.moonshot.cn) 查看账户状态

### Q: 视觉分析没有生效？

**A**: 确认以下几点：
1. 选择的模型是 `moonshot-v1-vision`（而非8k/32k）
2. 笔记有封面图片（`cover_url`字段不为空）
3. 查看控制台输出，确认"Prepared X cover images for analysis"

### Q: 图片无法加载？

**A**:
- KIMI支持通过URL直接传递图片
- 确保小红书的图片CDN可访问
- 如果图片URL失效，KIMI会跳过该图片

### Q: 对比Deepseek和KIMI怎么选？

**A**:

| 特性 | Deepseek | KIMI |
|------|----------|------|
| **推理能力** | 强（Reasoner模式） | 中 |
| **视觉分析** | 不支持 | 支持 (Vision模型) |
| **上下文长度** | 5K | 4K/8K/32K/128K |
| **成本** | 较低 | 中等 |
| **适用场景** | 纯文本深度分析 | 需要视觉分析的场景 |

**推荐方案**：
- **流量拆解 + 视觉分析**：KIMI Vision
- **深度文本推理**：Deepseek Reasoner
- **可以两者都生成，对比分析结果**

## 8. 技术细节

### API兼容性

KIMI API兼容OpenAI SDK，RedLens使用以下方式调用：

```python
from openai import OpenAI

client = OpenAI(
    api_key="your_kimi_api_key",
    base_url="https://api.moonshot.cn/v1"
)

response = client.chat.completions.create(
    model="moonshot-v1-vision",
    messages=[
        {"role": "system", "content": "..."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "..."},
                {"type": "image_url", "image_url": {"url": "https://..."}}
            ]
        }
    ]
)
```

### 图片格式支持

- **支持格式**：JPG, PNG, WebP
- **URL要求**：公开可访问的HTTP/HTTPS链接
- **图片大小**：建议 < 20MB
- **分辨率**：KIMI会自动调整，建议不超过4096x4096

## 9. 更多资源

- **官方文档**：https://platform.moonshot.cn/docs
- **API参考**：https://platform.moonshot.cn/docs/api-reference
- **定价说明**：https://platform.moonshot.cn/pricing
- **社区支持**：https://platform.moonshot.cn/community

---

📝 **文档版本**：v1.2.4
📅 **更新日期**：2026-02-12
🔗 **RedLens GitHub**：[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)
