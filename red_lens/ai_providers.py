"""
AI提供商抽象层 - 支持多AI模型提供商

采用策略模式设计，便于扩展新的AI提供商。
支持文本和多模态（Vision）模型。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from openai import OpenAI
import base64
import os


class BaseAIProvider(ABC):
    """AI提供商抽象基类"""

    def __init__(self, api_key: str, base_url: str, model: str, supports_vision: bool = False, **kwargs):
        """
        初始化AI提供商

        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
            supports_vision: 是否支持视觉分析（从配置中读取）
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._supports_vision = supports_vision  # 从配置读取，不是通过模型名判断
        self.kwargs = kwargs

        # 使用OpenAI兼容的客户端
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @abstractmethod
    def generate_report(self, messages: List[Dict], images: List[Dict] = None, **params) -> str:
        """
        生成AI报告

        Args:
            messages: 对话消息列表，格式: [{"role": "system", "content": "..."}, ...]
            images: 图片数据列表，格式: [{"type": "url", "data": "https://..."}, ...]
            **params: 生成参数（max_tokens, temperature等）

        Returns:
            生成的报告内容
        """
        pass

    @abstractmethod
    def supports_vision(self) -> bool:
        """
        是否支持视觉分析

        Returns:
            True if支持图像分析，False otherwise
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        获取提供商名称

        Returns:
            提供商显示名称
        """
        pass


class DeepseekProvider(BaseAIProvider):
    """Deepseek AI提供商 - 专注文本推理"""

    def generate_report(self, messages: List[Dict], images: List[Dict] = None, **params) -> str:
        """
        生成AI报告（Deepseek）

        注意：Deepseek当前版本不支持图像输入，images参数会被忽略
        """
        try:
            # 从analyzer.py迁移的现有逻辑
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=params.get('max_tokens', 5000),
                temperature=params.get('temperature', 1.0),
                timeout=params.get('timeout', 60)
            )

            return response.choices[0].message.content

        except Exception as e:
            raise RuntimeError(f"Deepseek API调用失败: {str(e)}")

    def supports_vision(self) -> bool:
        """从配置中读取是否支持视觉分析"""
        return self._supports_vision

    def get_provider_name(self) -> str:
        return "Deepseek"


class KimiProvider(BaseAIProvider):
    """KIMI (Moonshot AI) 提供商 - 支持多模态"""

    def generate_report(self, messages: List[Dict], images: List[Dict] = None, **params) -> str:
        """
        生成AI报告（KIMI）

        如果模型支持vision且提供了图片，会自动构建多模态消息
        """
        import time

        max_retries = 3
        retry_delay = 5  # 秒

        for attempt in range(max_retries):
            try:
                # 如果有图片且模型支持vision，构建多模态消息
                if images and self.supports_vision():
                    print(f"[KIMI] 准备多模态消息，包含 {len(images)} 张图片")
                    messages = self._build_multimodal_messages(messages, images)

                # 调用KIMI API (OpenAI兼容)
                print(f"[KIMI] 发送请求 (attempt {attempt + 1}/{max_retries})...")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=params.get('max_tokens', 4096),
                    temperature=params.get('temperature', 0.3),
                    timeout=params.get('timeout', 180)
                )

                return response.choices[0].message.content

            except Exception as e:
                error_msg = str(e)

                # 检查是否是超时错误
                if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                    if attempt < max_retries - 1:
                        print(f"[KIMI] ⚠️ 请求超时，{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise RuntimeError(f"KIMI API调用超时（已重试{max_retries}次）。建议：减少图片数量或增加timeout")

                # 其他错误直接抛出
                raise RuntimeError(f"KIMI API调用失败: {error_msg}")

        raise RuntimeError(f"KIMI API调用失败: 达到最大重试次数")

    def _build_multimodal_messages(self, messages: List[Dict], images: List[Dict]) -> List[Dict]:
        """
        构建多模态消息格式（KIMI要求使用base64编码的图片）

        Args:
            messages: 原始消息列表
            images: 图片数据列表

        Returns:
            多模态格式的消息列表
        """
        # 复制消息避免修改原始数据
        multimodal_messages = messages.copy()

        # 找到最后一条user消息
        for i in range(len(multimodal_messages) - 1, -1, -1):
            if multimodal_messages[i]["role"] == "user":
                user_message = multimodal_messages[i]

                # 构建多模态content
                content_parts = []

                # 先添加图片（KIMI要求使用base64格式）
                for img in images[:15]:  # 限制最多15张图片
                    if img.get('type') == 'base64' and img.get('data'):
                        # KIMI要求的格式: data:image/jpeg;base64,{base64_string}
                        mime_type = img.get('mime_type', 'image/jpeg')
                        data_url = f"data:{mime_type};base64,{img['data']}"

                        content_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": data_url
                            }
                        })
                        print(f"[KIMI] 添加图片: {img.get('note_id', 'unknown')} - {img.get('title', '')[:30]}")

                # 最后添加文本
                content_parts.append(
                    {"type": "text", "text": user_message["content"]}
                )

                # 替换为多模态格式
                multimodal_messages[i] = {
                    "role": "user",
                    "content": content_parts
                }

                break

        return multimodal_messages

    def supports_vision(self) -> bool:
        """从配置中读取是否支持视觉分析"""
        return self._supports_vision

    def get_provider_name(self) -> str:
        return "KIMI (Moonshot AI)"


def get_ai_provider(provider_name: str, model: str = None, **kwargs) -> BaseAIProvider:
    """
    工厂函数：根据配置实例化AI提供商

    Args:
        provider_name: 提供商名称 ("deepseek" | "kimi" | ...)
        model: 模型名称，如果为None则使用提供商的默认模型
        **kwargs: 其他配置参数

    Returns:
        实例化的AI提供商对象

    Raises:
        ValueError: 如果提供商不存在或未实现
    """
    from config import ai_config

    # 检查提供商是否存在
    if provider_name not in ai_config.AI_PROVIDERS:
        available = ", ".join(ai_config.AI_PROVIDERS.keys())
        raise ValueError(f"未知的AI提供商: {provider_name}。可用: {available}")

    provider_config = ai_config.AI_PROVIDERS[provider_name]

    # 检查API Key（优先使用kwargs中的api_key，其次从环境变量或配置文件读取）
    api_key = kwargs.get('api_key') or provider_config["api_key"] or os.getenv(f"{provider_name.upper()}_API_KEY")
    if not api_key:
        raise ValueError(
            f"{provider_name.upper()}_API_KEY 未配置！\n"
            f"请设置环境变量、修改 config/ai_config.py 或手动输入API Key"
        )

    base_url = provider_config["base_url"]

    # 确定使用的模型
    if not model:
        model = provider_config["default_model"]

    # 验证模型是否存在
    if model not in provider_config["models"]:
        available_models = ", ".join(provider_config["models"].keys())
        raise ValueError(
            f"模型 '{model}' 不存在于提供商 '{provider_name}'。\n"
            f"可用模型: {available_models}"
        )

    # 从配置中读取模型的supports_vision属性
    model_config = provider_config["models"][model]
    supports_vision = model_config.get("supports_vision", False)

    print(f"[Factory] 创建AI提供商: {provider_name} | 模型: {model} | Vision: {supports_vision}")

    # 实例化对应的提供商
    if provider_name == "deepseek":
        return DeepseekProvider(api_key, base_url, model, supports_vision=supports_vision, **kwargs)
    elif provider_name == "kimi":
        return KimiProvider(api_key, base_url, model, supports_vision=supports_vision, **kwargs)
    else:
        raise ValueError(
            f"提供商 '{provider_name}' 已配置但未实现。\n"
            f"请在 ai_providers.py 中添加对应的 Provider 类。"
        )


# 便捷函数：获取所有可用的提供商
def get_available_providers() -> List[str]:
    """
    获取所有已配置的AI提供商列表

    Returns:
        提供商名称列表
    """
    from config import ai_config
    return list(ai_config.AI_PROVIDERS.keys())


# 便捷函数：获取提供商的可用模型
def get_provider_models(provider_name: str) -> Dict[str, Dict]:
    """
    获取指定提供商的所有可用模型

    Args:
        provider_name: 提供商名称

    Returns:
        模型配置字典
    """
    from config import ai_config

    if provider_name not in ai_config.AI_PROVIDERS:
        raise ValueError(f"未知的AI提供商: {provider_name}")

    return ai_config.AI_PROVIDERS[provider_name]["models"]
