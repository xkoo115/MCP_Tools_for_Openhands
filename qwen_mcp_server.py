#!/usr/bin/env python3
import sys
import json
import os
import requests
import base64
import mimetypes
import time  # (*** Gemini 升级 1: 导入 time 模块 ***)
from urllib.parse import urlparse
from openai import OpenAI

# --- Qwen3_VL API 配置 ---
QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-YOUR-ACTUAL-API-KEY-HERE")
QWEN_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

TOOL_NAME = "analyze_image_with_qwen"

# --- (Gemini 升级 2: 定义重试常量) ---
MAX_RETRIES = 3  # 总共尝试 3 次
RETRY_DELAY_SECONDS = 3  # 每次重试前等待 3 秒

# --- 工具定义 (不变) ---
QWEN_TOOL_LIST = [
    {
        "name": TOOL_NAME,
        "description": (
            "使用 Qwen-VL 模型分析和理解图片。此工具只接受**公网可访问的 URL**。\n"
            "**重要指令**：如果图片是本地文件路径 (例如 /app/workspace/image.png)，"
            "您**必须**先使用 'shell' 工具将其上传到公共图床 (这个上传操作不需要身份认证)，"
            "然后再用返回的 URL 调用此工具。\n"
            "上传命令示例: \n"
            "curl -s -F \"reqtype=fileupload\" -F \"fileToUpload=@/app/workspace/image.png\" https://catbox.moe/user/api.php"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "向 Qwen-VL 提出的问题或提示词 (例如: '这张图片里有什么？')"
                },
                "image_url": {
                    "type": "string",
                    "description": (
                        "图片的**公网 URL**。这必须是 http://, https:// 或 data:image//... 格式。"
                        "**请勿**传入本地文件路径 (如 /app/workspace/...)。"
                        "请遵循工具主描述中的上传指令。"
                    )
                }
            },
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
        sys.stderr.write(f"[ERROR] Error writing to stdout: {e}\n")
        sys.stderr.flush()


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
    (不变) 将本地路径或 URL 转换为 Base64 Data URI。
    """
    try:
        if urlparse(image_path_or_url).scheme in ['http', 'https']:
            return image_path_or_url
        if image_path_or_url.startswith('data:image'):
            return image_path_or_url
        if urlparse(image_path_or_url).scheme == 'file':
            local_path = urlparse(image_path_or_url).path
        elif os.path.exists(image_path_or_url):
            local_path = image_path_or_url
        else:
            raise ValueError(f"路径既不是 URL 也不是有效的本地文件: {image_path_or_url}。"
                             "请确保 Agent 提供了公网 URL。")
        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        raise Exception(f"处理图片路径失败: {image_path_or_url}. 错误: {e}")


# ==============================================================================
# (*** Gemini 升级 3: 实现 API 调用的重试逻辑 ***)
# ==============================================================================

def call_qwen_vl_api(prompt, image_path_or_url):
    """
    调用 Qwen3_VL API (使用 OpenAI 官方兼容库)。
    (新) 增加了针对下载超时的重试机制。
    """
    if not QWEN_API_KEY or QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        raise ValueError("QWEN_API_KEY 未设置。请在脚本顶部或环境变量中设置 DASHSCOPE_API_KEY。")

    if "compatible-mode" not in QWEN_BASE_URL:
        raise ValueError(
            f"QWEN_BASE_URL 看上去不正确。OpenAI 库需要兼容模式的 URL (应包含 'compatible-mode/v1')。当前: {QWEN_BASE_URL}")

    sys.stderr.write(f"[INFO] 正在处理图片: {image_path_or_url[:70]}...\n")
    sys.stderr.flush()

    # 1. (不变) 尝试编码/验证路径
    encoded_image_url = encode_image_to_base64(image_path_or_url)

    # 2. (不变) 实例化 OpenAI 客户端
    try:
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
        )
    except Exception as e:
        raise Exception(f"初始化 OpenAI 客户端失败: {e}")

    # 3. (不变) 构建消息
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": encoded_image_url}},
                {"type": "text", "text": prompt}
            ]
        }
    ]

    # --- (新) 重试循环 ---
    attempts = 0
    last_exception = None

    while attempts < MAX_RETRIES:
        attempts += 1
        try:
            # 4. (新) 尝试调用 API
            if attempts > 1:
                sys.stderr.write(f"[INFO] 开始第 {attempts}/{MAX_RETRIES} 次尝试...\n")
                sys.stderr.flush()

            completion = client.chat.completions.create(
                model="qwen-vl-plus",
                messages=messages
            )

            # 5. (新) 成功则解析并返回
            if completion.choices and completion.choices[0].message:
                text_response = completion.choices[0].message.content
                sys.stderr.write(f"[INFO] Qwen API 在第 {attempts} 次尝试中调用成功。\n")
                sys.stderr.flush()
                return text_response  # 成功，跳出循环并返回值
            else:
                raise Exception("API 响应中未找到 'choices' 或 'message'")

        except Exception as e:
            # 6. (新) 捕获异常
            last_exception = e
            error_message = str(e)

            # 检查是否是我们关心的“下载超时”错误
            if "Download the media resource timed out" in error_message or "timed out during the data inspection" in error_message:
                sys.stderr.write(f"[WARNING] 尝试 {attempts}/{MAX_RETRIES} 失败: Qwen API 下载图片超时。\n")
                sys.stderr.flush()
                if attempts < MAX_RETRIES:
                    sys.stderr.write(f"[INFO] 将在 {RETRY_DELAY_SECONDS} 秒后重试...\n")
                    sys.stderr.flush()
                    time.sleep(RETRY_DELAY_SECONDS)
                # (继续下一次循环)
            else:
                # 如果是其他错误 (如 API Key 错、参数错)，则立即失败，不重试
                sys.stderr.write(f"[ERROR] 发生不可重试的错误: {e}\n")
                sys.stderr.flush()
                raise e  # 抛出非超时错误，终止循环

    # 7. (新) 如果循环结束仍未成功 (即所有重试都失败了)
    sys.stderr.write(f"[ERROR] 所有 {MAX_RETRIES} 次尝试均失败。\n")
    sys.stderr.flush()
    raise last_exception  # 抛出最后一次捕获的异常


# ==============================================================================
# MCP 协议处理 (不变)
# ==============================================================================

def main():
    send_raw_message({"mcp": "0.1.0"})
    sys.stderr.write("[INFO] Qwen-VL MCP 服务器(V4 - 带重试)启动，等待连接...\n")
    sys.stderr.flush()

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
                # --- 是“请求”(Request)，必须回复 ---

                if method == "initialize":
                    client_protocol_version = request.get("params", {}).get("protocolVersion", "2025-03-26")
                    compliant_result = {
                        "protocolVersion": client_protocol_version,
                        "serverInfo": {"name": "Qwen-VL-MCP-Server", "version": "1.3.0-Server-Retry"},
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
                        image_url = tool_input.get("image_url")

                        if not prompt or not image_url:
                            raise ValueError(f"缺少 'prompt' 或 'image_url' 参数。收到: {tool_input}")

                        sys.stderr.write(
                            f"[INFO] 收到工具调用: {TOOL_NAME} (Prompt: '{prompt[:30]}...', URL/Path: '{image_url}')\n")
                        sys.stderr.flush()

                        # (不变) 调用函数，但现在这个函数内置了重试逻辑
                        result_content = call_qwen_vl_api(prompt, image_url)

                        # 成功，返回结果
                        send_jsonrpc_response(request_id, {"content": result_content})

                    except Exception as e:
                        # (不变) 只有当 call_qwen_vl_api *最终* 失败后 (耗尽重试)，才会到这里
                        sys.stderr.write(f"[ERROR] Tool execution error after retries: {e}\n")
                        sys.stderr.flush()
                        send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                elif method:
                    send_jsonrpc_error(request_id, -3601, f"Method not found: {method}")

            else:
                # --- 是“通知”(Notification)，绝不能回复 ---
                if method == "notifications/initialized":
                    sys.stderr.write("[INFO] OpenHands 客户端已初始化。\n")
                    sys.stderr.flush()
                else:
                    pass

    except KeyboardInterrupt:
        sys.stderr.write("\n[INFO] 收到 KeyboardInterrupt，服务器关闭。\n")
        sys.stderr.flush()
    except Exception as e:
        sys.stderr.write(f"\n[FATAL] 发生未捕获的严重错误: {e}\n")
        sys.stderr.flush()
        send_jsonrpc_error(-1, -32001, f"Internal server error: {e}")


if __name__ == "__main__":
    main()