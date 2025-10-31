#!/usr/bin/env python3
import sys
import json
import os
import requests
import base64
import mimetypes
from urllib.parse import urlparse

# --- Qwen3_VL API 配置 ---
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_API_KEY = "sk-YOUR-ACTUAL-API-KEY-HERE"  # <--- 在这里填入你的真实 Key

TOOL_NAME = "analyze_image_with_qwen"

# --- (新) 全局工具定义 (强制使用 Base64) ---
QWEN_TOOL_LIST = [
    {
        "name": TOOL_NAME,
        # (关键修改 1) 更新描述，告诉 LLM 它必须提供 Base64
        "description": "使用 Qwen3-VL 模型分析和理解图片。图片必须作为 Base64 编码的 Data URI 字符串提供。",

        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "向 Qwen-VL 提出的问题或提示词 (例如: '这张图片里有什么？')"
                },
                # (关键修改 2) 更改参数名和描述
                "image_data_uri": {
                    "type": "string",
                    "description": "图片的 Base64 编码的 Data URI (例如: 'data:image/png;base64,iVBORw0KG...')。不要使用本地文件路径。"
                }
            },
            # (关键修改 3) 更新 required 字段
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


def call_qwen_vl_api(prompt, image_data_uri):
    """
    调用 Qwen3_VL API (***已更新为 OpenAI 兼容格式***)。
    """
    if not QWEN_API_KEY or not QWEN_API_URL:
        raise ValueError("QWEN_API_KEY 或 QWEN_API_URL 未在脚本中设置")

    # encode_image_to_base64 函数保持不变，它能正确处理 data URIs
    encoded_image_url = encode_image_to_base64(image_data_uri)

    # (*** 关键修复 1: 构建 OpenAI 兼容的 Payload ***)
    # 结构从 {"model": ..., "input": {"messages": [...]}}
    # 变为     {"model": ..., "messages": [...]}
    payload = {
        "model": "qwen-vl-plus",  # 确保模型名称正确
        "messages": [
            {
                "role": "user",
                "content": [
                    # 遵循你提供的官方示例的顺序
                    {"type": "image_url", "image_url": {"url": encoded_image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        # 注意: 原生的 "parameters" 字段在这里不再需要
    }

    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }

    # API 调用不变
    response = requests.post(QWEN_API_URL, json=payload, headers=headers)
    response.raise_for_status()  # 检查 HTTP 错误
    result = response.json()

    # (*** 关键修复 2: 解析 OpenAI 兼容的 Response ***)
    # 结构从 result["output"]["choices"][0]["message"]["content"]
    # 变为     result["choices"][0]["message"]["content"]
    try:
        # 遵循 OpenAI 格式: result.choices[0].message.content
        text_response = result["choices"][0]["message"]["content"]

        # Qwen 的 OpenAI 兼容模式在返回纯文本时, content 就是一个字符串
        if isinstance(text_response, str):
            return text_response

        # 如果它(在未来)返回一个列表 (例如，图文并茂的回答)，我们只提取文本部分
        if isinstance(text_response, list):
            for part in text_response:
                if part.get("type") == "text":
                    return part["text"]

        return str(text_response)

    except (KeyError, IndexError) as e:
        # 如果 'choices' 或 'message' 等键不存在
        raise Exception(f"无法从 Qwen OpenAI 兼容 API 响应中解析出文本内容: {result}. 错误: {e}")

# def call_qwen_vl_api(prompt, image_url):
#     if not QWEN_API_KEY or not QWEN_API_URL:
#         raise ValueError("QWEN_API_KEY 或 QWEN_API_URL 未在脚本中设置")
#     encoded_image_url = encode_image_to_base64(image_url)
#     payload = {
#         "model": "qwen-vl-plus",
#         "input": {"messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url",
#                                                                                                "image_url": {
#                                                                                                    "url": encoded_image_url}}]}]},
#         "parameters": {"result_format": "message"}
#     }
#     headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
#     response = requests.post(QWEN_API_URL, json=payload, headers=headers)
#     response.raise_for_status()
#     result = response.json()
#     if result.get("output", {}).get("choices"):
#         text_response = result["output"]["choices"][0]["message"]["content"]
#         if isinstance(text_response, list):
#             for part in text_response:
#                 if part.get("type") == "text":
#                     return part["text"]
#         elif isinstance(text_response, str):
#             return text_response
#     raise Exception(f"无法从 Qwen API 响应中解析出文本内容: {result}")


# ==============================================================================
# MCP 协议处理 (最终修复版)
# ==============================================================================

def main():
    # 1. 发送 MCP 协议版本
    send_raw_message({"mcp": "0.1.0"})

    # (注意: 我们不再主动发送 send_capabilities()，我们将等待客户端通过 tools/list 来请求)

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

            request_id = request.get("id")  # 对于通知，这将是 None
            method = request.get("method")

            # --- (新) 规范的请求/通知处理 ---

            if request_id is not None:
                # 这是一个“请求”(Request)，我们必须回复

                if method == "initialize":
                    # 响应 OpenHands 的 initialize 握手请求
                    client_protocol_version = request.get("params", {}).get("protocolVersion", "2025-03-26")
                    compliant_result = {
                        "protocolVersion": client_protocol_version,
                        "serverInfo": {"name": "Qwen-VL-MCP-Server", "version": "1.0.0"},
                        "capabilities": {}
                    }
                    send_jsonrpc_response(request_id, compliant_result)

                elif method == "tools/list":
                    # (*** 主要修复 ***)
                    # OpenHands 正在请求工具列表
                    send_jsonrpc_response(request_id, {"tools": QWEN_TOOL_LIST})

                # ... 保持 main() 函数的其他部分不变 ...

                elif method == "tools/call":
                    # 响应 OpenHands 的 tools/call 请求
                    try:
                        tool_name = request["params"].get("name")

                        tool_input = request["params"].get("input") or request["params"].get("arguments") or {}

                        if tool_name != TOOL_NAME:
                            raise ValueError(f"未知的工具名称: {tool_name}")

                        prompt = tool_input.get("prompt")

                        # (关键修改 4) 读取新的参数名
                        image_uri = tool_input.get("image_data_uri")

                        if not prompt or not image_uri:
                            # 更新错误信息
                            raise ValueError(f"缺少 'prompt' 或 'image_data_uri' 参数。收到: {tool_input}")

                        # (关键修改 5) 将新的参数传递给 API 函数
                        result_content = call_qwen_vl_api(prompt, image_uri)

                        send_jsonrpc_response(request_id, {"content": result_content})

                    except Exception as e:
                        send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                # ... 保持 main() 函数的其余部分不变 ...

                # elif method == "tools/call":
                #     # 响应 OpenHands 的 call_tool 请求
                #     try:
                #         tool_name = request["params"].get("name")
                #
                #         # --- (关键修复) ---
                #         # OpenHands 客户端发送 'arguments'，但标准 MCP 可能发送 'input'
                #         # 我们同时检查这两个键，以确保兼容性
                #         tool_input = request["params"].get("input") or request["params"].get("arguments") or {}
                #         # --- (修复结束) ---
                #
                #         if tool_name != TOOL_NAME:
                #             raise ValueError(f"未知的工具名称: {tool_name}")
                #
                #         prompt = tool_input.get("prompt")
                #         image_url = tool_input.get("image_url")
                #
                #         if not prompt or not image_url:
                #             raise ValueError(f"缺少 'prompt' 或 'image_url' 参数。收到: {tool_input}")
                #
                #         result_content = call_qwen_vl_api(prompt, image_url)
                #
                #         # 我们的响应 {"content": "..."} 是符合 CallToolResult 规范的
                #         send_jsonrpc_response(request_id, {"content": result_content})
                #
                #     except Exception as e:
                #         send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                elif method:
                    # 收到未知的 method
                    send_jsonrpc_error(request_id, -32601, f"Method not found: {method}")

            else:
                # 这是一个“通知”(Notification)，我们绝不能回复

                if method == "notifications/initialized":
                    # (*** 次要修复 ***)
                    # 客户端在告诉我们它已准备就绪。
                    # 我们什么都不做，静默处理即可。
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