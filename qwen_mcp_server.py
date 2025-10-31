#!/usr/bin/env python3
import sys
import json
import os
import requests  # (V5 needs this)
import base64
import mimetypes
import time
from urllib.parse import urlparse
from openai import OpenAI

# --- Qwen3_VL API Configuration ---
# Prioritize reading from environment variables; fall back to the default Beijing region URL.
# Ensure your API Key matches this region.
QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "sk-YOUR-ACTUAL-API-KEY-HERE")
QWEN_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

TOOL_NAME = "analyze_image_with_qwen"

# --- Retry Constants ---
MAX_RETRIES = 1  # Total 3 attempts
RETRY_DELAY_SECONDS = 3  # Wait 3 seconds before each retry

# --- Tool Definition ---
QWEN_TOOL_LIST = [
    {
        "name": TOOL_NAME,

        # Instructions for the OpenHands LLM
        "description": (
            "Analyzes and understands images using the Qwen-VL model. This tool only accepts **publicly accessible URLs**.\n"
            "**Important Instruction**: If the image is a local file path (e.g., /app/workspace/image.png),"
            "you **must** first upload it to a public image host using the 'shell' tool,"
            "and then call this tool with the returned URL.\n"
            "Upload command example: \n"
            "curl -s -F \"reqtype=fileupload\" -F \"fileToUpload=@/app/workspace/image.png\" https://catbox.moe/user/api.php"
        ),

        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The question or prompt for Qwen-VL (e.g., 'What is in this image?')"
                },
                "image_url": {
                    "type": "string",
                    "description": (
                        "The **public URL** of the image. Must be in http://, https://, or data:image//... format."
                        "**Do not** pass a local file path (e.g., /app/workspace/...).."
                        "Please follow the upload instructions in the main tool description."
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
# (*** Gemini V5 Upgrade: Key Modification ***)
# ==============================================================================

def encode_image_to_base64(image_path_or_url):
    """
    (V5 Upgrade)
    Converts a path or URL into a Base64 Data URI.
    - If 'http/https' URL, this function will *download it* and convert to Base64.
    - If local path, it reads and encodes.
    - If Data URI, it returns directly.
    """
    try:
        # 1. Check for HTTP/HTTPS URL (server downloads itself)
        if urlparse(image_path_or_url).scheme in ['http', 'https']:
            sys.stderr.write(f"[INFO] Detected public URL, server is downloading it: {image_path_or_url[:70]}...\n")
            sys.stderr.flush()

            # Act like a browser to prevent 403
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            try:
                # Download image content
                response = requests.get(image_path_or_url, timeout=15, headers=headers)
                response.raise_for_status()  # Check for 4xx/5xx errors

                content = response.content
                mime_type = response.headers.get('Content-Type', 'application/octet-stream')

                # Validate if the download is an image (prevents HTML error pages)
                if not mime_type.startswith('image/'):
                    sys.stderr.write(f"[ERROR] Downloaded file is not an image! Content-Type: {mime_type}\n")
                    sys.stderr.flush()
                    raise ValueError(
                        f"Downloaded file is not an image (might be an HTML error page). Content-Type: {mime_type}")

                # Encode to Base64 Data URI
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
            return image_path_or_url  # Already Base64, return directly

        # 3. Check for 'file://' URI
        elif urlparse(image_path_or_url).scheme == 'file':
            local_path = urlparse(image_path_or_url).path
        # 4. Check for local path (must be accessible by the *server*)
        elif os.path.exists(image_path_or_url):
            local_path = image_path_or_url
        else:
            # If Agent mistakenly passes /app/workspace/..., it will fail here
            raise ValueError(f"Path is neither a URL nor a valid local file: {image_path_or_url}."
                             "Please ensure the Agent provides a public URL.")

        # 5. (Unchanged) Read and encode local file
        sys.stderr.write(f"[INFO] Encoding local file: {local_path}\n")
        sys.stderr.flush()
        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
        return f"data:{mime_type};base64,{encoded_string}"

    except Exception as e:
        # Raise exception, which will be returned to OpenHands via JSON-RPC
        raise Exception(f"Failed to process image path: {image_path_or_url}. Error: {e}")


# ==============================================================================
# API Call Function (with Retry Logic)
# ==============================================================================

def call_qwen_vl_api(prompt, image_path_or_url):
    """
    Calls the Qwen3_VL API.
    V5's encode_image_to_base64 ensures a Base64 Data URI is passed to Qwen.
    """
    if not QWEN_API_KEY or QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        raise ValueError("QWEN_API_KEY is not set. Please set DASHSCOPE_API_KEY in environment or script.")

    if "compatible-mode" not in QWEN_BASE_URL:
        raise ValueError(
            f"QWEN_BASE_URL seems incorrect. OpenAI lib needs 'compatible-mode/v1' URL. Current: {QWEN_BASE_URL}")

    sys.stderr.write(f"[INFO] Processing image (V5 Mode): {image_path_or_url[:70]}...\n")
    sys.stderr.flush()

    # 1. (Key) Call V5 encoding function
    # Input (URL or path) will be converted to Base64 Data URI
    encoded_data_uri = encode_image_to_base64(image_path_or_url)

    # 2. (Unchanged) Instantiate OpenAI client
    try:
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
        )
    except Exception as e:
        raise Exception(f"Failed to initialize OpenAI client: {e}")

    # 3. (Unchanged) Build message, image_url.url is now always Base64
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": encoded_data_uri}},
                {"type": "text", "text": prompt}
            ]
        }
    ]

    # --- (Unchanged) V4 Retry Loop ---
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

            # 5. Success: parse and return
            if completion.choices and completion.choices[0].message:
                text_response = completion.choices[0].message.content
                sys.stderr.write(f"[INFO] Qwen API call successful on attempt {attempts}.\n")
                sys.stderr.flush()
                return text_response  # Success, break loop and return value
            else:
                raise Exception("No 'choices' or 'message' found in API response")

        except Exception as e:
            # 6. Catch exception
            last_exception = e
            error_message = str(e).lower()

            # (V5) Check for Qwen API's own timeout or server errors (no more "Download timed out")
            # But we keep retry logic for Qwen API timeouts or 5xx errors.
            if "timed out" in error_message or "timeout" in error_message or "500" in error_message or "503" in error_message or "service temporarily unavailable" in error_message:
                sys.stderr.write(
                    f"[WARNING] Attempt {attempts}/{MAX_RETRIES} failed: Qwen API reported timeout or server error.\n")
                sys.stderr.flush()
                if attempts < MAX_RETRIES:
                    sys.stderr.write(f"[INFO] Retrying in {RETRY_DELAY_SECONDS} seconds...\n")
                    sys.stderr.flush()
                    time.sleep(RETRY_DELAY_SECONDS)
                # (Continue to next loop)
            else:
                # Non-retryable error (e.g., API Key, "image format illegal" etc.)
                sys.stderr.write(f"[ERROR] Non-retryable error occurred: {e}\n")
                sys.stderr.flush()
                raise e  # Re-throw non-timeout error, terminating loop

    # 7. (New) If loop finishes without success
    sys.stderr.write(f"[ERROR] All {MAX_RETRIES} attempts failed.\n")
    sys.stderr.flush()
    raise last_exception  # Re-throw the last captured exception


# ==============================================================================
# MCP Protocol Handling (main function unchanged)
# ==============================================================================

def main():
    send_raw_message({"mcp": "0.1.0"})
    sys.stderr.write("[INFO] Qwen-VL MCP Server (V5 - Server-Side Download) starting, waiting for connection...\n")
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
                        "serverInfo": {"name": "Qwen-VL-MCP-Server", "version": "1.4.0-Server-Download-Proxy"},
                        "capabilities": {}
                    }
                    send_jsonrpc_response(request_id, compliant_result)

                elif method == "tools/list":
                    # OpenHands is requesting the tool list (with new instructions)
                    send_jsonrpc_response(request_id, {"tools": QWEN_TOOL_LIST})

                elif method == "tools/call":
                    # OpenHands is calling the tool
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

                        # (Unchanged) Call V5 function
                        result_content = call_qwen_vl_api(prompt, image_url)

                        # Success, return result
                        send_jsonrpc_response(request_id, {"content": result_content})

                    except Exception as e:
                        # (Unchanged) Only arrives here if call_qwen_vl_api *finally* fails
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
    # Ensure API Key is set
    if not QWEN_API_KEY or QWEN_API_KEY == "sk-YOUR-ACTUAL-API-KEY-HERE":
        sys.stderr.write("=" * 50 + "\n")
        sys.stderr.write("[FATAL ERROR] DASHSCOPE_API_KEY is not set.\n")
        sys.stderr.write(
            "Please set DASHSCOPE_API_KEY in your environment variables or edit QWEN_API_KEY at the top of the script.\n")
        sys.stderr.write("=" * 50 + "\n")
        sys.stderr.flush()
        sys.exit(1)

    main()