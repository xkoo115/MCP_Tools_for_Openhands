#!/usr/bin/env python3
import sys
import json
import os
import requests
import base64
import mimetypes
from urllib.parse import urlparse

# --- Qwen3_VL API 配置 ---
# 根据你的要求，我们将 API Key 和 URL 硬编码在这里
# 警告：请勿将此文件上传到公共仓库！
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_API_KEY = "sk-YOUR-ACTUAL-API-KEY-HERE"  # <--- 在这里填入你的真实 Key

TOOL_NAME = "analyze_image_with_qwen"


# ==============================================================================
# JSON-RPC 2.0 辅助函数 (新)
# ==============================================================================

def send_raw_message(message):
    """(原 send_message) 向 OpenHands (stdout) 发送一个原始的 dict 消息"""
    try:
        sys.stdout.write(json.dumps(message) + '\n')
        sys.stdout.flush()
    except IOError as e:
        # 当 OpenHands 进程关闭 stdout 时，可能会发生这种情况
        sys.stderr.write(f"Error writing to stdout: {e}\n")


def send_jsonrpc_response(request_id, result):
    """
    发送一个符合规范的 JSON-RPC 2.0 成功响应。
    """
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result
    }
    send_raw_message(response)


def send_jsonrpc_error(request_id, code, message):
    """
    发送一个符合规范的 JSON-RPC 2.0 错误响应。
    """
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message}
    }
    send_raw_message(response)


def send_jsonrpc_notification(method, params):
    """
    发送一个符合规范的 JSON-RPC 2.0 通知 (没有 'id')。
    """
    notification = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params
    }
    send_raw_message(notification)


# ==============================================================================
# 工具核心逻辑 (不变)
# ==============================================================================

def encode_image_to_base64(image_path_or_url):
    """
    将本地文件路径或 URL 转换为 base64 数据 URI。
    """
    try:
        if urlparse(image_path_or_url).scheme in ['http', 'https']:
            return image_path_or_url

        if urlparse(image_path_or_url).scheme == 'file':
            local_path = urlparse(image_path_or_url).path
        elif os.path.exists(image_path_or_url):
            local_path = image_path_or_url
        else:
            if image_path_or_url.startswith('data:image'):
                return image_path_or_url
            raise ValueError("路径既不是 URL 也不是有效的本地文件")

        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        return f"data:{mime_type};base64,{encoded_string}"

    except Exception as e:
        raise Exception(f"处理图片路径失败: {image_path_or_url}. 错误: {e}")


def call_qwen_vl_api(prompt, image_url):
    """
    调用 Qwen3_VL API。
    """
    if not QWEN_API_KEY or not QWEN_API_URL:
        raise ValueError("QWEN_API_KEY 或 QWEN_API_URL 未在脚本中设置")

    encoded_image_url = encode_image_to_base64(image_url)

    payload = {
        "model": "qwen-vl-plus",
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
        "parameters": {"result_format": "message"}
    }

    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(QWEN_API_URL, json=payload, headers=headers)
    response.raise_for_status()
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


# ==============================================================================
# MCP 协议处理 (重构)
# ==============================================================================

def send_capabilities():
    """
    (重构) 以“通知”形式向 OpenHands 发送工具能力。
    这更符合 JSON-RPC 规范，因为它只是“通知”，不期望响应。
    """
    capabilities_params = {
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
    # 作为“通知”发送 (没有 id)
    send_jsonrpc_notification("set_capabilities", capabilities_params)


def main():
    """
    (重构) 主事件循环，使用 JSON-RPC 辅助函数。
    """
    # 1. 发送 MCP 协议版本 (这不是 JSON-RPC)
    send_raw_message({"mcp": "0.1.0"})

    # 2. 发送工具能力 (作为 JSON-RPC 通知)
    send_capabilities()

    # 3. 循环监听来自 OpenHands 的 JSON-RPC 请求
    try:
        for line in sys.stdin:
            if not line:
                break

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                # 收到无效的 JSON
                send_jsonrpc_error(-1, -32700, "Parse error: Invalid JSON received")
                continue

            request_id = request.get("id")
            method = request.get("method")

            if method == "initialize":
                # 响应 OpenHands 的 initialize 握手请求
                send_jsonrpc_response(
                    request_id,
                    {"status": "success", "message": "Initialized Qwen VL server"}
                )

            elif method == "call_tool":
                # 响应 OpenHands 的 call_tool 请求
                try:
                    tool_name = request["params"].get("name")
                    tool_input = request["params"].get("input", {})

                    if tool_name != TOOL_NAME:
                        raise ValueError(f"未知的工具名称: {tool_name}")

                    prompt = tool_input.get("prompt")
                    image_url = tool_input.get("image_url")

                    if not prompt or not image_url:
                        raise ValueError("缺少 'prompt' 或 'image_url' 参数")

                    # 核心：调用 API
                    result_content = call_qwen_vl_api(prompt, image_url)

                    # 发送成功响应
                    send_jsonrpc_response(request_id, {"content": result_content})

                except Exception as e:
                    # 发送工具执行期间的错误响应
                    send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

            elif method:
                # 收到未知的 method
                send_jsonrpc_error(request_id, -32601, f"Method not found: {method}")

    except KeyboardInterrupt:
        # 干净地退出
        pass
    except Exception as e:
        # 捕获任何意外的服务器崩溃
        send_jsonrpc_error(-1, -32001, f"Internal server error: {e}")


if __name__ == "__main__":
    main()