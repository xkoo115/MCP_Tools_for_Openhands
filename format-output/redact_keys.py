import json
from pathlib import Path

# --- 1. 配置 ---

# ⚠️ 在此输入您要查找和替换的确切 API 密钥字符串
API_KEY_TO_FIND = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 您要扫描的文件夹路径 ( "." 代表当前目录)
SEARCH_PATH = Path(".")

# 用什么字符串来替换
REPLACEMENT_STRING = "****"

# --- ---------------- ---

if API_KEY_TO_FIND == "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx":
    print("错误: 请在脚本第 8 行更新 'API_KEY_TO_FIND' 变量为您真实的密钥。")
    print("脚本已退出。")
    exit(1)


def find_and_replace_recursive(node, target_value, replacement_value):
    """
    递归遍历一个 (可能是嵌套的) 字典或列表，
    查找 'target_value' 并将其替换为 'replacement_value'。

    返回: bool (如果进行了替换，则为 True)
    """
    modified = False

    if isinstance(node, dict):
        for key, value in node.items():
            if value == target_value:
                node[key] = replacement_value
                modified = True
            elif isinstance(value, (dict, list)):
                if find_and_replace_recursive(value, target_value, replacement_value):
                    modified = True

    elif isinstance(node, list):
        for i, item in enumerate(node):
            if item == target_value:
                node[i] = replacement_value
                modified = True
            elif isinstance(item, (dict, list)):
                if find_and_replace_recursive(item, target_value, replacement_value):
                    modified = True

    return modified


def main():
    """
    主执行函数
    """
    print(f"--- API 密钥清理工具 ---")
    print(f"搜索路径: {SEARCH_PATH.resolve()}")
    print(f"目标密钥: '{API_KEY_TO_FIND[:4]}...'")
    print(f"替换为: '{REPLACEMENT_STRING}'\n")

    # 确保搜索路径存在
    if not SEARCH_PATH.is_dir():
        print(f"错误: 路径 '{SEARCH_PATH}' 不是一个有效的目录。")
        return

    # rglob('*.json') 会递归地找到所有 .json 文件
    json_files = list(SEARCH_PATH.rglob('*.json'))

    if not json_files:
        print("未在指定路径下找到任何 .json 文件。")
        return

    print(f"总共找到 {len(json_files)} 个 .json 文件。开始扫描...\n")

    redacted_count = 0
    failed_count = 0

    for file_path in json_files:
        try:
            # 1. 读取 JSON 文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 如果文件为空，跳过
                if not content:
                    continue
                data = json.loads(content)

            # 2. 递归查找和替换
            modified = find_and_replace_recursive(data, API_KEY_TO_FIND, REPLACEMENT_STRING)

            # 3. 如果有修改，则写回文件
            if modified:
                print(f"[REDACTED] 在 {file_path} 中找到并替换了密钥。")
                with open(file_path, 'w', encoding='utf-8') as f:
                    # 使用 indent=4 保持 JSON 格式美观
                    json.dump(data, f, indent=4, ensure_ascii=False)
                redacted_count += 1

        except json.JSONDecodeError:
            print(f"[失败] {file_path} 不是一个有效的 JSON 文件，已跳过。")
            failed_count += 1
        except Exception as e:
            print(f"[错误] 处理 {file_path} 时发生未知错误: {e}")
            failed_count += 1

    print("\n--- 清理完成 ---")
    print(f"成功替换了 {redacted_count} 个文件中的密钥。")
    if failed_count > 0:
        print(f"{failed_count} 个文件处理失败（无效JSON或权限问题）。")


if __name__ == "__main__":
    main()