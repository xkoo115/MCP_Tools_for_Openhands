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
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_API_KEY = "sk-YOUR-ACTUAL-API-KEY-HERE"  # <--- 在这里填入你的真实 Key

TOOL_NAME = "analyze_image_with_qwen"

# --- (新) 全局工具定义 (改回 URL 形式) ---
QWEN_TOOL_LIST = [
    {
        "name": TOOL_NAME,
        # (Gemini 修改 1) 更新描述，接受 URL 或本地路径
        "description": "使用 Qwen3-VL 模型分析和理解图片。图片可以是一个 URL 或本地文件路径。",

        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "向 Qwen-VL 提出的问题或提示词 (例如: '这张图片里有什么？')"
                },
                # (Gemini 修改 2) 更改参数名和描述
                "image_url": {
                    "type": "string",
                    "description": "图片的 URL (请上传至公共网站)，或利用命令shutil.move(image_file_path, /root/MCP_Tools_for_Openhands/image_file_name)将保存在本地的图片传至MCP工具目录下，并填写为这个路径"
                }
            },
            # (Gemini 修改 3) 更新 required 字段
            "required": ["prompt", "image_url"]
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
    将本地路径或 URL 转换为 Base64 Data URI。
    如果输入已经是 Data URI，则直接返回。
    """
    try:
        # 1. 检查是否为 HTTP/HTTPS URL
        if urlparse(image_path_or_url).scheme in ['http', 'https']:
            # Qwen API 支持直接传入 URL
            return image_path_or_url

        # 2. 检查是否已经是 Data URI
        if image_path_or_url.startswith('data:image'):
            return image_path_or_url

        # 3. 检查是否为 'file://' URI
        if urlparse(image_path_or_url).scheme == 'file':
            local_path = urlparse(image_path_or_url).path
        # 4. 检查是否为本地路径
        elif os.path.exists(image_path_or_url):
            local_path = image_path_or_url
        else:
            raise ValueError("路径既不是 URL 也不是有效的本地文件")

        # 5. 读取本地文件并编码
        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        raise Exception(f"处理图片路径失败: {image_path_or_url}. 错误: {e}")


# ==============================================================================
# (*** Gemini 关键修改 2: 重写 API 调用函数 ***)
# ==============================================================================

def call_qwen_vl_api(prompt, image_path_or_url):
    """
    调用 Qwen3_VL API (***使用 OpenAI 官方兼容库***)。
    """
    if not QWEN_API_KEY or not QWEN_API_URL:
        raise ValueError("QWEN_API_KEY 或 QWEN_API_URL 未在脚本中设置")

    if QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        raise ValueError("请在脚本顶部将 QWEN_API_KEY 替换为你的真实 Key")

    # 1. (不变) 确保图片是 URL 或 Base64 Data URI
    encoded_image_url = encode_image_to_base64(image_path_or_url)

    # 2. (新) 实例化 OpenAI 客户端
    try:
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_API_URL,
        )
    except Exception as e:
        raise Exception(f"初始化 OpenAI 客户端失败: {e}")

    # 3. (新) 构建消息并调用
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
            model="qwen-vl-plus",  # 确保模型名称正确
            messages=messages
        )

        # 4. (新) 解析 OpenAI 客户端的响应
        if completion.choices and completion.choices[0].message:
            text_response = completion.choices[0].message.content
            return text_response
        else:
            raise Exception("API 响应中未找到 'choices' 或 'message'")

    except Exception as e:
        # 捕获来自 client.chat.completions.create 的 API 错误
        raise Exception(f"调用 Qwen (OpenAI 兼容模式) API 失败: {e}")


# ==============================================================================
# MCP 协议处理 (最终修复版)
# ==============================================================================

def main():
    # 1. 发送 MCP 协议版本
    send_raw_message({"mcp": "0.1.0"})

    # 2. 循环监听来自 OpenHands 的 JSON-RPC 请求
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
                # 这是一个“请求”(Request)，我们必须回复

                if method == "initialize":
                    client_protocol_version = request.get("params", {}).get("protocolVersion", "2025-03-26")
                    compliant_result = {
                        "protocolVersion": client_protocol_version,
                        "serverInfo": {"name": "Qwen-VL-MCP-Server", "version": "1.0.0"},
                        "capabilities": {}
                    }
                    send_jsonrpc_response(request_id, compliant_result)

                elif method == "tools/list":
                    # OpenHands 正在请求工具列表
                    send_jsonrpc_response(request_id, {"tools": QWEN_TOOL_LIST})

                elif method == "tools/call":
                    # 响应 OpenHands 的 tools/call 请求
                    try:
                        tool_name = request["params"].get("name")
                        tool_input = request["params"].get("input") or request["params"].get("arguments") or {}

                        if tool_name != TOOL_NAME:
                            raise ValueError(f"未知的工具名称: {tool_name}")

                        prompt = tool_input.get("prompt")

                        # (Gemini 修改 5) 读取 'image_url' 参数
                        image_url = tool_input.get("image_url")

                        if not prompt or not image_url:
                            # (Gemini 修改 6) 更新错误信息
                            raise ValueError(f"缺少 'prompt' 或 'image_url' 参数。收到: {tool_input}")

                        # (Gemini 修改 7) 将 image_url 传递给 API 函数
                        result_content = call_qwen_vl_api(prompt, image_url)

                        send_jsonrpc_response(request_id, {"content": result_content})

                    except Exception as e:
                        send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                # (Gemini 清理) 移除了旧的、被注释掉的 tools/call 处理块

                elif method:
                    # 收到未知的 method
                    send_jsonrpc_error(request_id, -32601, f"Method not found: {method}")

            else:
                # 这是一个“通知”(Notification)，我们绝不能回复
                if method == "notifications/initialized":
                    pass
                else:
                    # 忽略所有其他未知的通知
                    pass

    except KeyboardInterrupt:
        pass
    except Exception as e:
        send_jsonrpc_error(-1, -32001, f"Internal server error: {e}")


if __name__ == "__main__":
    main()