#!/usr/bin/env python3
import sys
import json
import os
import requests
import base64
import mimetypes
from urllib.parse import urlparse

# --- Qwen3_VL API 配置 ---
# 替换为你的 Qwen3_VL API 地址和 Key
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_API_KEY = os.environ.get("QWEN_API_KEY")  # 推荐使用环境变量

# 你希望在 OpenHands 中看到的工具名称
TOOL_NAME = "analyze_image_with_qwen"


def send_message(message):
    """向 OpenHands (stdout) 发送 JSON 消息"""
    sys.stdout.write(json.dumps(message) + '\n')
    sys.stdout.flush()


def encode_image_to_base64(image_path_or_url):
    """
    将本地文件路径或 URL 转换为 base64 数据 URI。
    Qwen-VL API 接受 http/https URL 或 base64 data URI。
    """
    try:
        if urlparse(image_path_or_url).scheme in ['http', 'https']:
            # 已经是 URL，Qwen API 可以直接处理
            return image_path_or_url

        if urlparse(image_path_or_url).scheme == 'file':
            # 本地文件路径 (e.g., file:///path/to/image.jpg)
            local_path = urlparse(image_path_or_url).path
        elif os.path.exists(image_path_or_url):
            # 假设是本地文件路径 (e.g., /path/to/image.jpg)
            local_path = image_path_or_url
        else:
            # 可能是 base64 字符串，直接返回
            if image_path_or_url.startswith('data:image'):
                return image_path_or_url
            raise ValueError("路径既不是 URL 也不是有效的本地文件")

        # 读取本地文件并编码
        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

        # 获取 MIME 类型
        mime_type = mimetypes.guess_type(local_path)[0]
        if not mime_type:
            mime_type = 'application/octet-stream'  # 默认

        return f"data:{mime_type};base64,{encoded_string}"

    except Exception as e:
        raise Exception(f"处理图片路径失败: {image_path_or_url}. 错误: {e}")


def call_qwen_vl_api(prompt, image_url):
    """
    调用 Qwen3_VL API。
    这里的核心是将 OpenHands 的简单输入转换为 Qwen API 所需的复杂格式。
    """

    # *** 这是关键的修改 ***
    # 在函数内部读取环境变量，确保能读到 setUp 中设置的值
    QWEN_API_KEY = os.environ.get("QWEN_API_KEY")

    if not QWEN_API_KEY:
        raise ValueError("未设置 QWEN_API_KEY 环境变量")

    # 1. 将图片路径/URL 转换为 API 可接受的格式
    encoded_image_url = encode_image_to_base64(image_url)

    # 2. 构建 Qwen3_VL API 的输入格式
    payload = {
        "model": "qwen-vl-plus",  # 或 "qwen-vl-max" 等
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": encoded_image_url}}
                    ]
                }
            ]
        },
        "parameters": {
            "result_format": "message"
        }
    }

    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",  # 现在这里使用的是函数内部的 QWEN_API_KEY
        "Content-Type": "application/json"
    }

    # 3. 发送请求
    response = requests.post(QWEN_API_URL, json=payload, headers=headers)
    response.raise_for_status()

    # 4. 解析响应并返回
    result = response.json()

    if result.get("output", {}).get("choices"):
        text_response = result["output"]["choices"][0]["message"]["content"]
        if isinstance(text_response, list):
            for part in text_response:
                if part.get("type") == "text":
                    return part["text"]
        elif isinstance(text_response, str):
            return text_response

    raise Exception(f"无法从 Qwen API 响应中解析出文本内容: {result}")


def send_capabilities():
    """告诉 OpenHands 这个服务器提供了什么工具"""
    capabilities = {
        "id": 0,
        "method": "set_capabilities",
        "params": {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": TOOL_NAME,
                        "description": "使用 Qwen3-VL 模型分析和理解图片。当你需要描述图片内容、回答关于图片的问题或识别图中物体时使用。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "prompt": {
                                    "type": "string",
                                    "description": "向 Qwen-VL 提出的问题或提示词 (例如: '这张图片里有什么？', '描述一下这个场景。')"
                                },
                                "image_url": {
                                    "type": "string",
                                    "description": "要分析的图片的 URL 或本地文件路径 (例如 'https://example.com/img.png', 'file:///tmp/image.jpg' 或 '/tmp/image.jpg')"
                                }
                            },
                            "required": ["prompt", "image_url"]
                        }
                    }
                }
            ]
        }
    }
    send_message(capabilities)


def main():
    # 1. MCP 握手
    send_message({"mcp": "0.1.0"})

    # 2. 发送工具能力
    send_capabilities()

    # 3. 循环监听来自 OpenHands 的请求
    try:
        for line in sys.stdin:
            if not line:
                break

            request = json.loads(line)

            if request.get("method") == "call_tool":
                request_id = request["id"]
                tool_name = request["params"].get("name")
                tool_input = request["params"].get("input", {})

                if tool_name == TOOL_NAME:
                    try:
                        prompt = tool_input.get("prompt")
                        image_url = tool_input.get("image_url")

                        if not prompt or not image_url:
                            raise ValueError("缺少 'prompt' 或 'image_url' 参数")

                        # 核心：调用 API
                        result = call_qwen_vl_api(prompt, image_url)

                        # 向 OpenHands 发回成功结果
                        response = {
                            "id": request_id,
                            "result": {"content": result}  # 结果必须是 {"content": "..."} 格式
                        }
                    except Exception as e:
                        # 向 OpenHands 发回错误
                        response = {
                            "id": request_id,
                            "error": {"code": -32000, "message": str(e)}
                        }

                    send_message(response)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        # 记录未捕获的异常
        error_msg = {"id": -1, "error": {"code": -32001, "message": f"服务器内部错误: {e}"}}
        send_message(error_msg)


if __name__ == "__main__":
    main()