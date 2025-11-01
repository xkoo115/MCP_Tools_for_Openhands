#!/usr/bin/env python3
import sys
import json
import os
import requests
import base64
import mimetypes
import time
from urllib.parse import urlparse
from openai import OpenAI

# --- Qwen3_VL API Configuration ---
QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-YOUR-ACTUAL-API-KEY-HERE")
QWEN_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

TOOL_NAME = "analyze_image_with_qwen"

# --- Retry Constants ---
MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 3

# ==============================================================================
# (*** Gemini V6.1 优化：强化工具描述 ***)
# ==============================================================================
QWEN_TOOL_LIST = [
    {
        "name": TOOL_NAME,

        # (V6.1) 优化 description，明确区分图片和视频
        "description": (
            "Analyzes and understands **still images** using the Qwen-VL model. This tool **only accepts image URLs** (e.g., .png, .jpg, .jpeg) and **CANNOT** analyze video files (.mp4) directly.\n\n"
            "**IF THE FILE IS AN IMAGE** (e.g., /app/workspace/image.png):\n"
            "1. Use the 'shell' tool to upload it: `curl -s -F \"reqtype=fileupload\" -F \"fileToUpload=@/app/workspace/image.png\" https://catbox.moe/user/api.php`\n"
            "2. Call this tool (`analyze_image_with_qwen`) with the returned image URL.\n\n"
            "**IF THE FILE IS A VIDEO** (e.g., /app/workspace/video.mp4):\n"
            "1. You **must** first extract a keyframe (a single image) from the video. Use the 'shell' tool with `ffmpeg` (e.g., `ffmpeg -i /app/workspace/video.mp4 -ss 00:00:01 -vframes 1 /app/workspace/keyframe.jpg`).\n"
            "2. Upload the *new image* (`keyframe.jpg`) using `curl`: `curl -s -F \"reqtype=fileupload\" -F \"fileToUpload=@/app/workspace/keyframe.jpg\" https://catbox.moe/user/api.php`\n"
            "3. Call this tool (`analyze_image_with_qwen`) with the **new image URL**."
        ),

        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The question or prompt for Qwen-VL (e.g., 'What is in this image?')"
                },

                # (V6.1) 优化 image_url 描述
                "image_url": {
                    "type": "string",
                    "description": (
                        "The **public URL of the image** to be analyzed. This MUST be a URL for a **still image** (e.g., .png, .jpg, .jpeg)."
                        "**Do not** pass a URL to a video file (.mp4). Follow the instructions in the main tool description if you have a video file."
                    )
                }
            },
            "required": ["prompt", "image_url"]
        }
    }
]


# ==============================================================================
# JSON-RPC 2.0 Helper Functions (Unchanged)
# ==============================================================================

def send_raw_message(message):
    """Sends a raw JSON message to stdout"""
    try:
        sys.stdout.write(json.dumps(message) + '\n')
        sys.stdout.flush()
    except IOError as e:
        sys.stderr.write(f"[ERROR] Error writing to stdout: {e}\n")
        sys.stderr.flush()


def send_jsonrpc_response(request_id, result):
    """Sends a JSON-RPC success response"""
    response = {"jsonrpc": "2.0", "id": request_id, "result": result}
    send_raw_message(response)


def send_jsonrpc_error(request_id, code, message):
    """Sends a JSON-RPC error response"""
    response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    send_raw_message(response)


# ==============================================================================
# V5 Core Logic: encode_image_to_base64 (Unchanged)
# ==============================================================================

def encode_image_to_base64(image_path_or_url):
    """
    (V5 Logic - Unchanged)
    Converts a path or URL into a Base64 Data URI.
    """
    try:
        # 1. Check for HTTP/HTTPS URL (server downloads itself)
        if urlparse(image_path_or_url).scheme in ['http', 'https']:
            sys.stderr.write(f"[INFO] Detected public URL, server is downloading it: {image_path_or_url[:70]}...\n")
            sys.stderr.flush()

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            try:
                response = requests.get(image_path_or_url, timeout=15, headers=headers)
                response.raise_for_status()
                content = response.content
                mime_type = response.headers.get('Content-Type', 'application/octet-stream')

                if not mime_type.startswith('image/'):
                    sys.stderr.write(f"[ERROR] Downloaded file is not an image! Content-Type: {mime_type}\n")
                    sys.stderr.flush()
                    raise ValueError(
                        f"Downloaded file is not an image (might be an HTML error page). Content-Type: {mime_type}")

                encoded_string = base64.b64encode(content).decode('utf-8')
                data_uri = f"data:{mime_type};base64,{encoded_string}"

                sys.stderr.write(
                    f"[INFO] URL downloaded and encoded successfully (Size: {len(data_uri) // 1024} KB).\n")
                sys.stderr.flush()
                return data_uri

            except requests.RequestException as e:
                raise Exception(f"Server failed to download image URL: {e}")

        # 2. Check if already Data URI
        elif image_path_or_url.startswith('data:image'):
            return image_path_or_url

        # 3. Check for 'file://' URI
        elif urlparse(image_path_or_url).scheme == 'file':
            local_path = urlparse(image_path_or_url).path
        # 4. Check for local path (accessible by the *server*)
        elif os.path.exists(image_path_or_url):
            local_path = image_path_or_url
        else:
            raise ValueError(f"Path is neither a URL nor a valid local file: {image_path_or_url}."
                             "Please ensure the Agent provides a public URL.")

        # 5. Read and encode local file
        sys.stderr.write(f"[INFO] Encoding local file: {local_path}\n")
        sys.stderr.flush()
        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        return f"data:{mime_type};base64,{encoded_string}"

    except Exception as e:
        raise Exception(f"Failed to process image path: {image_path_or_url}. Error: {e}")


# ==============================================================================
# V5 Core Logic: call_qwen_vl_api (Unchanged)
# ==============================================================================

def call_qwen_vl_api(prompt, image_path_or_url):
    """
    (V5 Logic - Unchanged)
    Calls the Qwen3_VL API with retry logic.
    """
    if not QWEN_API_KEY or QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        raise ValueError("QWEN_API_KEY is not set. Please set DASHSCOPE_API_KEY in environment or script.")

    if "compatible-mode" not in QWEN_BASE_URL:
        raise ValueError(
            f"QWEN_BASE_URL seems incorrect. OpenAI lib needs 'compatible-mode/v1' URL. Current: {QWEN_BASE_URL}")

    sys.stderr.write(f"[INFO] Processing image (V5 Mode): {image_path_or_url[:70]}...\n")
    sys.stderr.flush()

    encoded_data_uri = encode_image_to_base64(image_path_or_url)

    try:
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
        )
    except Exception as e:
        raise Exception(f"Failed to initialize OpenAI client: {e}")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": encoded_data_uri}},
                {"type": "text", "text": prompt}
            ]
        }
    ]

    attempts = 0
    last_exception = None

    while attempts < MAX_RETRIES:
        attempts += 1
        try:
            if attempts > 1:
                sys.stderr.write(f"[INFO] Starting attempt {attempts}/{MAX_RETRIES} (for Qwen API)...\n")
                sys.stderr.flush()

            completion = client.chat.completions.create(
                model="qwen-vl-plus",
                messages=messages
            )

            if completion.choices and completion.choices[0].message:
                text_response = completion.choices[0].message.content
                sys.stderr.write(f"[INFO] Qwen API call successful on attempt {attempts}.\n")
                sys.stderr.flush()
                return text_response
            else:
                raise Exception("No 'choices' or 'message' found in API response")

        except Exception as e:
            last_exception = e
            error_message = str(e).lower()

            if "timed out" in error_message or "timeout" in error_message or "500" in error_message or "503" in error_message or "service temporarily unavailable" in error_message:
                sys.stderr.write(
                    f"[WARNING] Attempt {attempts}/{MAX_RETRIES} failed: Qwen API reported timeout or server error.\n")
                sys.stderr.flush()
                if attempts < MAX_RETRIES:
                    sys.stderr.write(f"[INFO] Retrying in {RETRY_DELAY_SECONDS} seconds...\n")
                    sys.stderr.flush()
                    time.sleep(RETRY_DELAY_SECONDS)
            else:
                sys.stderr.write(f"[ERROR] Non-retryable error occurred: {e}\n")
                sys.stderr.flush()
                raise e

    sys.stderr.write(f"[ERROR] All {MAX_RETRIES} attempts failed.\n")
    sys.stderr.flush()
    raise last_exception


# ==============================================================================
# MCP Protocol Handling (V6 FIX - Unchanged)
# ==============================================================================

def main():
    send_raw_message({"mcp": "0.1.0"})
    sys.stderr.write("[INFO] Qwen-VL MCP Server (V6.1 - Video/Image Fix) starting, waiting for connection...\n")
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
                # --- Is a "Request", must reply ---

                if method == "initialize":
                    client_protocol_version = request.get("params", {}).get("protocolVersion", "2025-03-26")
                    compliant_result = {
                        "protocolVersion": client_protocol_version,
                        "serverInfo": {"name": "Qwen-VL-MCP-Server", "version": "1.6.0-Video-Check"},
                        "capabilities": {}
                    }
                    send_jsonrpc_response(request_id, compliant_result)

                elif method == "tools/list":
                    # (V6.1) 发送优化后的工具列表
                    send_jsonrpc_response(request_id, {"tools": QWEN_TOOL_LIST})

                elif method == "tools/call":
                    try:
                        tool_name = request["params"].get("name")
                        tool_input = request["params"].get("input") or request["params"].get("arguments") or {}

                        if tool_name != TOOL_NAME:
                            raise ValueError(f"Unknown tool name: {tool_name}")

                        prompt = tool_input.get("prompt")
                        image_url = tool_input.get("image_url")

                        if not prompt or not image_url:
                            raise ValueError(f"Missing 'prompt' or 'image_url' parameters. Received: {tool_input}")

                        sys.stderr.write(
                            f"[INFO] Received tool call: {TOOL_NAME} (Prompt: '{prompt[:30]}...', URL/Path: '{image_url}')\n")
                        sys.stderr.flush()

                        # (V6) Call V5 function to get the result string
                        result_content_string = call_qwen_vl_api(prompt, image_url)

                        # (V6) Wrap the string result in a list
                        structured_content_list = [
                            {
                                "type": "text",
                                "text": result_content_string
                            }
                        ]

                        # Send the correctly formatted list
                        send_jsonrpc_response(request_id, {"content": structured_content_list})

                    except Exception as e:
                        sys.stderr.write(f"[ERROR] Tool execution error after processing/retries: {e}\n")
                        sys.stderr.flush()
                        send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                elif method:
                    send_jsonrpc_error(request_id, -32601, f"Method not found: {method}")

            else:
                # --- Is a "Notification", must not reply ---
                if method == "notifications/initialized":
                    sys.stderr.write("[INFO] OpenHands client has initialized.\n")
                    sys.stderr.flush()
                else:
                    pass

    except KeyboardInterrupt:
        sys.stderr.write("\n[INFO] Received KeyboardInterrupt, server shutting down.\n")
        sys.stderr.flush()
    except Exception as e:
        sys.stderr.write(f"\n[FATAL] An unhandled critical error occurred: {e}\n")
        sys.stderr.flush()
        send_jsonrpc_error(-1, -32001, f"Internal server error: {e}")


if __name__ == "__main__":
    if not QWEN_API_KEY or QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        sys.stderr.write("=" * 50 + "\n")
        sys.stderr.write("[FATAL ERROR] DASHSCOPE_API_KEY is not set.\n")
        sys.stderr.write(
            "Please set DASHSCOPE_API_KEY in your environment variables or edit QWEN_API_KEY at the top of the script.\n")
        sys.stderr.write("=" * 50 + "\n")
        sys.stderr.flush()
        sys.exit(1)

    main()