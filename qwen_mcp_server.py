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

# (Gemini 修正 1)
# 您的代码使用了 OpenAI 库，因此必须使用 "compatible-mode" 的 URL。
# 优先从环境变量获取，如果失败，则使用默认的北京地域 URL。
# 确保您的 API Key 与此地域匹配。
QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-YOUR-ACTUAL-API-KEY-HERE")
QWEN_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

TOOL_NAME = "analyze_image_with_qwen"

# ==============================================================================
# (*** Gemini 核心修改：更新工具定义以指导 LLM ***)
# ==============================================================================
QWEN_TOOL_LIST = [
    {
        "name": TOOL_NAME,

        # (Gemini 升级 1) 更新 description，提供给 OpenHands LLM 的明确指令
        "description": (
            "使用 Qwen-VL 模型分析和理解图片。此工具只接受**公网可访问的 URL**。\n"
            "**重要指令**：如果图片是本地文件路径 (例如 /app/workspace/image.png)，"
            "您**必须**先使用 'shell' 工具将其上传到公共图床，"
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

                # (Gemini 升级 2) 更新 image_url 描述
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
# 工具核心逻辑 (不变, 依赖此函数在无效本地路径时失败)
# ==============================================================================

def encode_image_to_base64(image_path_or_url):
    """
    将本地路径或 URL 转换为 Base64 Data URI。
    如果输入已经是 Data URI 或公网 URL，则直接返回。
    如果输入是服务器无法访问的本地路径 (如 /app/workspace/...)，此函数将引发异常。
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
        # 4. 检查是否为本地路径 (必须是 *服务器* 能访问的路径)
        elif os.path.exists(image_path_or_url):
            local_path = image_path_or_url
        else:
            # (关键) 如果 OpenHands 传入 /app/workspace/...，os.path.exists 将为 False
            raise ValueError(f"路径既不是 URL 也不是有效的本地文件: {image_path_or_url}。"
                             "请确保 Agent 提供了公网 URL。")

        # 5. 读取本地文件并编码
        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        # 抛出异常，这将通过 JSON-RPC 返回给 OpenHands
        raise Exception(f"处理图片路径失败: {image_path_or_url}. 错误: {e}")


# ==============================================================================
# (Gemini 修正 2) API 调用函数 (确保使用正确的 Base URL)
# ==============================================================================

def call_qwen_vl_api(prompt, image_path_or_url):
    """
    调用 Qwen3_VL API (使用 OpenAI 官方兼容库)。
    """
    if not QWEN_API_KEY or QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        raise ValueError("QWEN_API_KEY 未设置。请在脚本顶部或环境变量中设置 DASHSCOPE_API_KEY。")

    if "compatible-mode" not in QWEN_BASE_URL:
        raise ValueError(
            f"QWEN_BASE_URL 看上去不正确。OpenAI 库需要兼容模式的 URL (应包含 'compatible-mode/v1')。当前: {QWEN_BASE_URL}")

    sys.stderr.write(f"[INFO] 正在处理图片: {image_path_or_url[:70]}...\n")
    sys.stderr.flush()

    # 1. (关键) 尝试编码/验证路径
    # 如果 image_path_or_url 是 /app/workspace/...，此步将失败
    encoded_image_url = encode_image_to_base64(image_path_or_url)

    # 2. 实例化 OpenAI 客户端
    try:
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
        )
    except Exception as e:
        raise Exception(f"初始化 OpenAI 客户端失败: {e}")

    # 3. 构建消息并调用
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

        # 4. 解析 OpenAI 客户端的响应
        if completion.choices and completion.choices[0].message:
            text_response = completion.choices[0].message.content
            sys.stderr.write("[INFO] Qwen API 调用成功。\n")
            sys.stderr.flush()
            return text_response
        else:
            raise Exception("API 响应中未找到 'choices' 或 'message'")

    except Exception as e:
        raise Exception(f"调用 Qwen (OpenAI 兼容模式) API 失败: {e}")


# ==============================================================================
# MCP 协议处理 (已简化，不包含“握手”逻辑)
# ==============================================================================

def main():
    send_raw_message({"mcp": "0.1.0"})
    sys.stderr.write("[INFO] Qwen-VL MCP 服务器(V3)启动，等待连接...\n")
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
                        "serverInfo": {"name": "Qwen-VL-MCP-Server", "version": "1.2.0-Pre-Upload-Instruction"},
                        "capabilities": {}
                    }
                    send_jsonrpc_response(request_id, compliant_result)

                elif method == "tools/list":
                    # OpenHands 正在请求工具列表 (包含新的说明)
                    send_jsonrpc_response(request_id, {"tools": QWEN_TOOL_LIST})

                elif method == "tools/call":
                    # OpenHands 正在调用工具
                    try:
                        tool_name = request["params"].get("name")
                        tool_input = request["params"].get("input") or request["params"].get("arguments") or {}

                        if tool_name != TOOL_NAME:
                            raise ValueError(f"未知的工具名称: {tool_name}")

                        prompt = tool_input.get("prompt")
                        image_url = tool_input.get("image_url")  # 获取路径

                        if not prompt or not image_url:
                            raise ValueError(f"缺少 'prompt' 或 'image_url' 参数。收到: {tool_input}")

                        # --- (关键) 直接尝试调用 API ---
                        # 如果 image_url 是 '/app/workspace/...'，
                        # call_qwen_vl_api 会失败并抛出异常

                        sys.stderr.write(
                            f"[INFO] 收到工具调用: {TOOL_NAME} (Prompt: '{prompt}', URL/Path: '{image_url}')\n")
                        sys.stderr.flush()

                        result_content = call_qwen_vl_api(prompt, image_url)

                        # 成功，返回结果
                        send_jsonrpc_response(request_id, {"content": result_content})

                    except Exception as e:
                        # --- (关键) 失败，将错误信息返回给 LLM ---
                        # LLM 看到这个错误 ("...路径既不是 URL 也不是有效的本地文件...")
                        # 再结合它刚读过的 description，就应该知道该怎么做了
                        sys.stderr.write(f"[ERROR] Tool execution error: {e}\n")
                        sys.stderr.flush()
                        send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                elif method:
                    send_jsonrpc_error(request_id, -32601, f"Method not found: {method}")

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