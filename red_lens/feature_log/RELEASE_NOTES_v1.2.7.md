# RedLens v1.2.7 - KIMI模型调用修复

## 🐛 Bug修复

### 问题
现有代码无法正常调用KIMI模型，因为KIMI要求使用base64编码的图片，而不是URL。

### 根本原因
```python
# ❌ 错误的实现（之前）
content_parts.append({
    "type": "image_url",
    "image_url": {"url": "https://cdn.xiaohongshu.com/..."}  # KIMI不支持URL
})
```

### 解决方案
```python
# ✅ 正确的实现（现在）
# 1. 下载图片并转换为base64
img_base64 = base64.b64encode(response.content).decode('utf-8')

# 2. 使用data URL格式
content_parts.append({
    "type": "image_url",
    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}  # ✅ 正确格式
})
```

---

## 📝 修改内容

### 1. `red_lens/analyzer.py`

**修改**: `prepare_images_for_ai()` 函数
- 新增参数: `use_base64: bool = False`
- 当`use_base64=True`时：
  - 使用requests下载图片
  - 转换为base64编码
  - 返回`{"type": "base64", "data": "...", "mime_type": "..."}`

**修改**: 调用逻辑 (line 658-664)
```python
# KIMI requires base64-encoded images
use_base64 = (provider == "kimi")
images = prepare_images_for_ai(top_notes, max_images=config.AI_MAX_IMAGES_PER_REPORT, use_base64=use_base64)
```

### 2. `red_lens/ai_providers.py`

**修改**: `KimiProvider._build_multimodal_messages()` 方法
- 改为检查`img.get('type') == 'base64'`（之前是`'url'`）
- 构建data URL格式: `f"data:{mime_type};base64,{img['data']}"`
- 调整顺序：**图片在前，文本在后**（符合官方API要求）

---

## ✅ 测试结果

```bash
$ python3 test_kimi_fix.py

============================================================
🎉 所有测试通过！KIMI调用已修复
============================================================

关键改进：
1. ✅ prepare_images_for_ai支持base64编码
2. ✅ KIMI自动使用base64模式下载图片
3. ✅ 消息构建使用data:image/xxx;base64,格式
4. ✅ 图片在前，文本在后（符合官方示例）
```

---

## 🎯 影响范围

### KIMI用户
✅ **现在可以正常使用** - 图片会自动下载并正确编码

### Deepseek用户
✅ **无影响** - Deepseek不支持vision，不会执行图片处理

### 性能影响
⚠️ **轻微增加** - 需要下载图片（每张约1-2秒）
- 5张图片约需5-10秒额外时间
- 可通过调整`AI_MAX_IMAGES_PER_REPORT`优化

---

## 📚 相关文档

- 详细修复说明: `KIMI_FIX_NOTES.md`
- 测试脚本: `test_kimi_fix.py`
- KIMI配置指南: `red_lens/KIMI_API_SETUP.md`

---

## 🚀 使用方法

### 快速开始
1. 配置KIMI API Key（环境变量或界面输入）
2. 在RedLens中选择KIMI provider
3. 选择kimi-k2.5模型
4. 生成报告 - **现在可以正常工作了！**

### 预期日志
```
[Factory] 创建AI提供商: kimi | 模型: kimi-k2.5 | Vision: True
  • Downloading image: 笔记标题...
    ✓ Encoded to base64 (234567 chars)
  • Prepared 5 cover images (base64 format)
[KIMI] 添加图片: note123 - 笔记标题
```

---

**版本**: v1.2.7
**修复日期**: 2026-02-12
**状态**: ✅ 已修复并测试通过
**向后兼容**: ✅ 完全兼容
