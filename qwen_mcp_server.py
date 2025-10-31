#!/usr/bin/env python3
import sys
import json
import os
import requests
import base64
import mimetypes
from urllib.parse import urlparse
from openai import OpenAI

# --- Qwen3_VL API 配置 ---
# (使用 OpenAI 兼容模式)
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_API_KEY = "sk-YOUR-ACTUAL-API-KEY-HERE"  # <--- 在这里填入你的真实 Key

TOOL_NAME = "analyze_image_with_qwen"

# --- (Gemini 关键修改) ---
# (改回 Base64 专用版本，以解决跨环境路径问题)
QWEN_TOOL_LIST = [
    {
        "name": TOOL_NAME,
        # (修改 1) 更新描述，强制 LLM (OpenHands) 提供 Base64
        "description": "使用 Qwen3-VL 模型分析和理解图片。图片必须作为 Base64 编码的 Data URI 字符串提供。",

        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "向 Qwen-VL 提出的问题或提示词 (例如: '这张图片里有什么？')"
                },
                # (修改 2) 更改参数名和描述
                "image_data_uri": {
                    "type": "string",
                    "description": "图片的 Base64 编码的 Data URI (例如: 'data:image/png;base64,iVBORw0KG...'). 代理(Agent)必须读取本地文件并将其编码为此格式。不要使用本地文件路径。"
                }
            },
            # (修改 3) 更新 required 字段
            "required": ["prompt", "image_data_uri"]
        }
    }
]


# ==============================================================================
# JSON-RPC 2.0 辅助函数 (不变)
# ==============================================================================

def send_raw_message(message):
    try:
        sys.stdout.write(json.dumps(message) + '\n')
        sys.stdout.flush()
    except IOError as e:
        sys.stderr.write(f"Error writing to stdout: {e}\n")


def send_jsonrpc_response(request_id, result):
    response = {"jsonrpc": "2.0", "id": request_id, "result": result}
    send_raw_message(response)


def send_jsonrpc_error(request_id, code, message):
    response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    send_raw_message(response)


# ==============================================================================
# 工具核心逻辑 (不变)
# ==============================================================================

def encode_image_to_base64(image_path_or_url):
    """
    此函数现在主要用于验证和传递 Data URI。
    它仍然可以处理公共 URL (如果 agent 提供了) 或本地路径 (如果该路径对 *工具* 可见)。
    """
    try:
        # 1. 检查是否为 HTTP/HTTPS URL
        if urlparse(image_path_or_url).scheme in ['http', 'https']:
            return image_path_or_url

        # 2. 检查是否已经是 Data URI (这是我们期望的)
        if image_path_or_url.startswith('data:image'):
            return image_path_or_url

        # 3. 检查是否为 'file://' URI
        if urlparse(image_path_or_url).scheme == 'file':
            local_path = urlparse(image_path_or_url).path
        # 4. 检查是否为本地路径 (这很可能失败，除非是共享卷)
        elif os.path.exists(image_path_or_url):
            local_path = image_path_or_url
        else:
            # 这就是你遇到的错误
            raise ValueError("路径既不是 URL, 也不是 Data URI, 也不是有效的本地文件")

        # 5. 如果它 *是* 一个有效的本地路径 (对工具可见)，则编码
        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        raise Exception(f"处理图片路径失败: {image_path_or_url}. 错误: {e}")


# ==============================================================================
# API 调用函数 (使用 OpenAI 库)
# ==============================================================================

def call_qwen_vl_api(prompt, image_input):
    """
    调用 Qwen3_VL API (使用 OpenAI 官方兼容库)。
    (修改 4) image_input 预计是 Data URI 或公共 URL
    """
    if not QWEN_API_KEY or not QWEN_BASE_URL:
        raise ValueError("QWEN_API_KEY 或 QWEN_BASE_URL 未在脚本中设置")

    if QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        raise ValueError("请在脚本顶部将 QWEN_API_KEY 替换为你的真实 Key")

    # (不变) 确保图片是 URL 或 Base64 Data URI
    # encode_image_to_base64 将处理输入
    encoded_image_url = encode_image_to_base64(image_input)

    try:
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
        )
    except Exception as e:
        raise Exception(f"初始化 OpenAI 客户端失败: {e}")

    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": encoded_image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]

        completion = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=messages
        )

        if completion.choices and completion.choices[0].message:
            text_response = completion.choices[0].message.content
            return text_response
        else:
            raise Exception("API 响应中未找到 'choices' 或 'message'")

    except Exception as e:
        raise Exception(f"调用 Qwen (OpenAI 兼容模式) API 失败: {e}")


# ==============================================================================
# MCP 协议处理
# ==============================================================================

def main():
    send_raw_message({"mcp": "0.1.0"})

    try:
        for line in sys.stdin:
            if not line:
                break

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                send_jsonrpc_error(-1, -32700, "Parse error: Invalid JSON received")
                continue

            request_id = request.get("id")
            method = request.get("method")

            if request_id is not None:
                if method == "initialize":
                    client_protocol_version = request.get("params", {}).get("protocolVersion", "2025-03-26")
                    compliant_result = {
                        "protocolVersion": client_protocol_version,
                        "serverInfo": {"name": "Qwen-VL-MCP-Server", "version": "1.0.0"},
                        "capabilities": {}
                    }
                    send_jsonrpc_response(request_id, compliant_result)

                elif method == "tools/list":
                    send_jsonrpc_response(request_id, {"tools": QWEN_TOOL_LIST})

                elif method == "tools/call":
                    try:
                        tool_name = request["params"].get("name")
                        tool_input = request["params"].get("input") or request["params"].get("arguments") or {}

                        if tool_name != TOOL_NAME:
                            raise ValueError(f"未知的工具名称: {tool_name}")

                        prompt = tool_input.get("prompt")

                        # (Gemini 修改 5) 读取 'image_data_uri'
                        image_data = tool_input.get("image_data_uri")

                        if not prompt or not image_data:
                            # (Gemini 修改 6) 更新错误信息
                            raise ValueError(f"缺少 'prompt' 或 'image_data_uri' 参数。收到: {tool_input}")

                        # (Gemini 修改 7)
                        result_content = call_qwen_vl_api(prompt, image_data)

                        send_jsonrpc_response(request_id, {"content": result_content})

                    except Exception as e:
                        send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                elif method:
                    send_jsonrpc_error(request_id, -32601, f"Method not found: {method}")

            else:
                if method == "notifications/initialized":
                    pass
                else:
                    pass

    except KeyboardInterrupt:
        pass
    except Exception as e:
        send_jsonrpc_error(-1, -32001, f"Internal server error: {e}")


if __name__ == "__main__":
    main()