#!/usr/bin/env python3
import sys
import json
import os
import requests  # (确保 requests 已导入)
import base64
import mimetypes
import time
from urllib.parse import urlparse
from openai import OpenAI


# ... (所有配置, TOOL_NAME, MAX_RETRIES, RETRY_DELAY_SECONDS, QWEN_TOOL_LIST 保持不变) ...
# ... (JSON-RPC 辅助函数 send_raw_message, send_jsonrpc_response, send_jsonrpc_error 保持不变) ...


# ==============================================================================
# (*** Gemini 升级 V5: 关键修改 ***)
# ==============================================================================

def encode_image_to_base64(image_path_or_url):
    """
    (V5 升级)
    将路径或 URL 转换为 Base64 Data URI。
    - 如果是 'http/https' URL, 此函数将 *自己下载* 它并转换为 Base64。
    - 如果是本地路径, 则读取并编码。
    - 如果是 Data URI, 直接返回。
    """
    try:
        # 1. 检查是否为 HTTP/HTTPS URL
        if urlparse(image_path_or_url).scheme in ['http', 'https']:
            sys.stderr.write(f"[INFO] 检测到公网 URL，服务器正在自行下载: {image_path_or_url[:70]}...\n")
            sys.stderr.flush()

            # (新) 伪装成浏览器去下载，防止被 403
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            try:
                # (新) 下载图片内容
                response = requests.get(image_path_or_url, timeout=15, headers=headers)
                response.raise_for_status()  # 检查 4xx/5xx 错误

                content = response.content
                mime_type = response.headers.get('Content-Type', 'application/octet-stream')

                # (新) 验证下载的是否真的是图片
                if not mime_type.startswith('image/'):
                    sys.stderr.write(f"[ERROR] 下载的文件不是图片! Content-Type: {mime_type}\n")
                    sys.stderr.flush()
                    raise ValueError(f"下载的文件不是图片 (可能是 HTML 错误页)。Content-Type: {mime_type}")

                # (新) 编码为 Base64 Data URI
                encoded_string = base64.b64encode(content).decode('utf-8')
                data_uri = f"data:{mime_type};base64,{encoded_string}"

                sys.stderr.write(f"[INFO] URL 下载并编码成功 (大小: {len(data_uri) // 1024} KB)。\n")
                sys.stderr.flush()
                return data_uri

            except requests.RequestException as e:
                raise Exception(f"服务器下载图片 URL 失败: {e}")

        # 2. 检查是否已经是 Data URI
        elif image_path_or_url.startswith('data:image'):
            return image_path_or_url  # 已经是 Base64，直接返回

        # 3. 检查是否为 'file://' URI
        elif urlparse(image_path_or_url).scheme == 'file':
            local_path = urlparse(image_path_or_url).path
        # 4. 检查是否为本地路径 (必须是 *服务器* 能访问的路径)
        elif os.path.exists(image_path_or_url):
            local_path = image_path_or_url
        else:
            raise ValueError(f"路径既不是 URL 也不是有效的本地文件: {image_path_or_url}。"
                             "请确保 Agent 提供了公网 URL。")

        # 5. (不变) 读取本地文件并编码
        sys.stderr.write(f"[INFO] 正在编码本地文件: {local_path}\n")
        sys.stderr.flush()
        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        return f"data:{mime_type};base64,{encoded_string}"

    except Exception as e:
        # 抛出异常，这将通过 JSON-RPC 返回给 OpenHands
        raise Exception(f"处理图片路径失败: {image_path_or_url}. 错误: {e}")


# ==============================================================================
# API 调用函数 (V4 的重试逻辑保持不变, V5 的修改会自动生效)
# ==============================================================================

def call_qwen_vl_api(prompt, image_path_or_url):
    """
    (V5 - 无需修改此函数)
    调用 Qwen3_VL API。
    encode_image_to_base64(V5) 会确保 image_path_or_url
    在传入 client.chat.completions.create 之前 *总是* 一个 Base64 Data URI。
    """
    if not QWEN_API_KEY or QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        raise ValueError("QWEN_API_KEY 未设置。")

    if "compatible-mode" not in QWEN_BASE_URL:
        raise ValueError(f"QWEN_BASE_URL 看上去不正确。")

    sys.stderr.write(f"[INFO] 正在处理图片: {image_path_or_url[:70]}...\n")
    sys.stderr.flush()

    # 1. (关键) 调用 V5 的编码函数
    # 无论输入是 URL 还是本地路径，输出都将是 Base64 Data URI
    encoded_data_uri = encode_image_to_base64(image_path_or_url)

    # 2. (不变) 实例化 OpenAI 客户端
    try:
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
        )
    except Exception as e:
        raise Exception(f"初始化 OpenAI 客户端失败: {e}")

    # 3. (不变) 构建消息, 但现在 image_url.url 始终是 Base64
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": encoded_data_uri}},
                {"type": "text", "text": prompt}
            ]
        }
    ]

    # --- (不变) V4 的重试循环 ---
    attempts = 0
    last_exception = None

    while attempts < MAX_RETRIES:
        attempts += 1
        try:
            if attempts > 1:
                sys.stderr.write(f"[INFO] 开始第 {attempts}/{MAX_RETRIES} 次尝试 (针对 Qwen API)...\n")
                sys.stderr.flush()

            completion = client.chat.completions.create(
                model="qwen-vl-plus",
                messages=messages
            )

            if completion.choices and completion.choices[0].message:
                text_response = completion.choices[0].message.content
                sys.stderr.write(f"[INFO] Qwen API 在第 {attempts} 次尝试中调用成功。\n")
                sys.stderr.flush()
                return text_response
            else:
                raise Exception("API 响应中未找到 'choices' 或 'message'")

        except Exception as e:
            last_exception = e
            error_message = str(e)

            # (V5 注意) 现在 Qwen 不会再报 "Download timed out" 了，
            # 因为我们是直接发送的 Base64。
            # 但我们保留重试逻辑，以防 Qwen API 本身超时或 5xx 错误。
            if "timed out" in error_message.lower() or "timeout" in error_message.lower() or "500" in error_message or "503" in error_message:
                sys.stderr.write(f"[WARNING] 尝试 {attempts}/{MAX_RETRIES} 失败: Qwen API 报告超时或服务器错误。\n")
                sys.stderr.flush()
                if attempts < MAX_RETRIES:
                    sys.stderr.write(f"[INFO] 将在 {RETRY_DELAY_SECONDS} 秒后重试...\n")
                    sys.stderr.flush()
                    time.sleep(RETRY_DELAY_SECONDS)
                # (继续下一次循环)
            else:
                # 不可重试的错误 (例如 "image format illegal" -- 如果发生说明 Base64 编码出错了)
                sys.stderr.write(f"[ERROR] 发生不可重试的错误: {e}\n")
                sys.stderr.flush()
                raise e

    sys.stderr.write(f"[ERROR] 所有 {MAX_RETRIES} 次尝试均失败。\n")
    sys.stderr.flush()
    raise last_exception


# ==============================================================================
# MCP 协议处理 (main 函数完全不变)
# ==============================================================================

def main():
    send_raw_message({"mcp": "0.1.0"})
    sys.stderr.write("[INFO] Qwen-VL MCP 服务器(V5 - 服务器端下载)启动，等待连接...\n")
    sys.stderr.flush()

    try:
        for line in sys.stdin:
            if not line:
                break
            # ... (main 函数的其余所有代码保持不变) ...
            # ... (main 函数的其余所有代码保持不变) ...
            request_id = request.get("id")
            method = request.get("method")

            if request_id is not None:
                if method == "initialize":
                    client_protocol_version = request.get("params", {}).get("protocolVersion", "2025-03-26")
                    compliant_result = {
                        "protocolVersion": client_protocol_version,
                        "serverInfo": {"name": "Qwen-VL-MCP-Server", "version": "1.4.0-Server-Download-Proxy"},
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

                        # (不变) 调用 V5 函数
                        result_content = call_qwen_vl_api(prompt, image_url)

                        send_jsonrpc_response(request_id, {"content": result_content})

                    except Exception as e:
                        sys.stderr.write(f"[ERROR] Tool execution error after retries: {e}\n")
                        sys.stderr.flush()
                        send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                elif method:
                    send_jsonrpc_error(request_id, -32601, f"Method not found: {method}")

            else:
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