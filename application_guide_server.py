#!/usr/bin/env python3
import sys
import json
import os
import fcntl  # For file locking to ensure safe read/write

# --- Configuration ---
# Define the storage location for the SOP guide file
GUIDE_FILE = "application_guide.json"

# ==============================================================================
# Tool Definitions
# ==============================================================================

GUIDE_TOOL_LIST = [
    {
        "name": "get_platform_guide_list",
        "description": (
            "Queries all currently known operation guides (SOPs) for a specific platform (e.g., 'GitLab', 'ownCloud', 'Plane', 'RocketChat'). "
            "Call this tool before attempting any operation to see if existing experience can be followed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "The name of the platform you are querying (e.g., 'GitLab', 'ownCloud', 'Plane', 'RocketChat')."
                }
            },
            "required": ["platform"]
        }
    },
    {
        "name": "get_operation_details",
        "description": (
            "Retrieves the detailed steps for a specific operation (SOP) on a platform. "
            "You should first call 'get_platform_guide_list' to get the correct operation name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform name (e.g., 'GitLab', 'ownCloud', 'Plane', 'RocketChat')."
                },
                "operation": {
                    "type": "string",
                    "description": "The short name of the operation (e.g., 'CreatePullRequest', 'DeployToVercel')."
                }
            },
            "required": ["platform", "operation"]
        }
    },
    {
        "name": "update_operation_guide",
        "description": (
            "Adds a new operation guide (SOP) for a platform or updates an existing one. "
            "Call this tool to summarize and save your experience after successfully completing a new operation or optimizing an existing flow."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform name (e.g., 'GitLab', 'ownCloud', 'Plane', 'RocketChat')."
                },
                "operation": {
                    "type": "string",
                    "description": (
                        "The short name of the operation. Please use CamelCase, e.g., 'CreatePullRequest', 'DeployToVercel'."
                    )
                },
                "details": {
                    "type": "string",
                    "description": "Detailed operation steps and experience summary (SOP)."
                }
            },
            "required": ["platform", "operation", "details"]
        }
    }
]


# ==============================================================================
# Core Logic: Guide File I/O
#
# We will use a simple file lock (fcntl) to prevent concurrent R/W
# from corrupting the JSON file. While not strictly necessary
# in a single-instance MCP, it's good practice for robustness.
# ==============================================================================

def load_guides_from_file(filepath):
    """
    Safely loads guide data from the JSON file.
    If the file doesn't exist or is empty, returns an empty dictionary.
    """
    if not os.path.exists(filepath):
        sys.stderr.write(f"[INFO] Guide file not found at {filepath}, initializing empty guide.\n")
        sys.stderr.flush()
        return {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # Acquire shared lock (read lock)
            fcntl.flock(f, fcntl.LOCK_SH)
            content = f.read()
            # Release lock
            fcntl.flock(f, fcntl.LOCK_UN)

            if not content:
                sys.stderr.write(f"[INFO] Guide file {filepath} is empty, initializing empty guide.\n")
                sys.stderr.flush()
                return {}

            return json.loads(content)

    except (json.JSONDecodeError, IOError) as e:
        sys.stderr.write(f"[ERROR] Failed to load or parse guide file {filepath}: {e}\n")
        sys.stderr.flush()
        # If file is corrupt, return empty dict to continue running instead of crashing
        return {}


def save_guides_to_file(filepath, data):
    """
    Safely saves guide data back to the JSON file.
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            # Acquire exclusive lock (write lock)
            fcntl.flock(f, fcntl.LOCK_EX)
            # Indent with 4 spaces for readability
            json.dump(data, f, indent=4, ensure_ascii=False)
            # Release lock
            fcntl.flock(f, fcntl.LOCK_UN)

        sys.stderr.write(f"[INFO] Successfully saved guides to {filepath}\n")
        sys.stderr.flush()
    except IOError as e:
        sys.stderr.write(f"[ERROR] Failed to save guide file {filepath}: {e}\n")
        sys.stderr.flush()
        # Raise exception so tools/call knows the operation failed
        raise e


# ==============================================================================
# JSON-RPC 2.0 Helper Functions (from your template)
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
# MCP Protocol Handling
# ==============================================================================

def main():
    # 1. Send MCP handshake on startup
    send_raw_message({"mcp": "0.1.0"})
    sys.stderr.write("[INFO] ApplicationGuide MCP Server starting, waiting for connection...\n")
    sys.stderr.flush()

    # 2. Load guide data into memory once on startup
    try:
        guides_data = load_guides_from_file(GUIDE_FILE)
    except Exception as e:
        sys.stderr.write(f"[FATAL] Could not load initial guide data: {e}. Exiting.\n")
        sys.stderr.flush()
        return

    # 3. Start listening to stdin
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
                # --- This is a "Request", must reply ---

                if method == "initialize":
                    client_protocol_version = request.get("params", {}).get("protocolVersion", "2025-03-26")
                    compliant_result = {
                        "protocolVersion": client_protocol_version,
                        "serverInfo": {"name": "ApplicationGuide-MCP-Server", "version": "1.0.0"},
                        "capabilities": {}
                    }
                    send_jsonrpc_response(request_id, compliant_result)

                elif method == "tools/list":
                    # Send our defined tool list
                    send_jsonrpc_response(request_id, {"tools": GUIDE_TOOL_LIST})

                elif method == "tools/call":
                    try:
                        tool_name = request["params"].get("name")
                        tool_input = request["params"].get("input") or request["params"].get("arguments") or {}

                        # Prepare the string to be returned to the Agent
                        result_content_string = ""

                        # --- Core Logic Dispatch ---

                        if tool_name == "get_platform_guide_list":
                            platform = tool_input.get("platform")
                            if not platform:
                                raise ValueError("Missing 'platform' parameter.")

                            sys.stderr.write(f"[INFO] Received tool call: {tool_name} (Platform: '{platform}')\n")

                            # Find from the dictionary in memory
                            platform_guides = guides_data.get(platform, {})
                            operation_list = list(platform_guides.keys())

                            if not operation_list:
                                result_content_string = f"No operations (SOPs) found for platform: '{platform}'."
                            else:
                                # Return a clear list
                                result_content_string = f"Known operations for '{platform}': {', '.join(operation_list)}"

                        elif tool_name == "get_operation_details":
                            platform = tool_input.get("platform")
                            operation = tool_input.get("operation")
                            if not platform or not operation:
                                raise ValueError("Missing 'platform' or 'operation' parameter.")

                            sys.stderr.write(
                                f"[INFO] Received tool call: {tool_name} (Platform: '{platform}', Op: '{operation}')\n")

                            platform_guides = guides_data.get(platform, {})
                            details = platform_guides.get(operation)

                            if not details:
                                result_content_string = f"Error: Operation '{operation}' not found for platform '{platform}'."
                            else:
                                # Directly return SOP details
                                result_content_string = details

                        elif tool_name == "update_operation_guide":
                            platform = tool_input.get("platform")
                            operation = tool_input.get("operation")
                            details = tool_input.get("details")
                            if not platform or not operation or not details:
                                raise ValueError("Missing 'platform', 'operation', or 'details' parameter.")

                            sys.stderr.write(
                                f"[INFO] Received tool call: {tool_name} (Platform: '{platform}', Op: '{operation}')\n")

                            # Update the dictionary in memory
                            if platform not in guides_data:
                                guides_data[platform] = {}
                            guides_data[platform][operation] = details

                            # Write the updated dictionary back to the file
                            save_guides_to_file(GUIDE_FILE, guides_data)

                            result_content_string = f"Successfully saved new guide '{operation}' for platform '{platform}'."

                        else:
                            raise ValueError(f"Unknown tool name: {tool_name}")

                        # --- Wrap the result in the standard format ---
                        structured_content_list = [
                            {
                                "type": "text",
                                "text": result_content_string
                            }
                        ]
                        send_jsonrpc_response(request_id, {"content": structured_content_list})

                    except Exception as e:
                        sys.stderr.write(f"[ERROR] Tool execution error: {e}\n")
                        sys.stderr.flush()
                        send_jsonrpc_error(request_id, -32000, f"Tool execution error: {e}")

                elif method:
                    send_jsonrpc_error(request_id, -32601, f"Method not found: {method}")

            else:
                # --- This is a "Notification", must not reply ---
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
        # Try to send one last error
        send_jsonrpc_error(-1, -32001, f"Internal server error: {e}")


if __name__ == "__main__":
    main()