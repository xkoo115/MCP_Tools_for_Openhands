import sys
from pathlib import Path

# --- 1. 请在这里配置 ---

# 填入您要查找和替换的 API KEY 字符串
API_KEY_TO_FIND = "sk-xxx"

# 填入您要扫描的顶层文件夹路径
FOLDER_TO_SCAN = "xxx"

# 填入您希望用来替换的字符串
REPLACEMENT_STRING = "****"


# --- 脚本正文 (无需修改) ---

def scan_and_redact(api_key: str, folder_path: Path, replacement: str) -> bool:
    """
    递归扫描指定文件夹中的所有 .json 文件，
    查找 API Key 字符串并将其替换。
    """
    total_replaced_files = 0
    key_display = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "..."

    print(f"--- 开始扫描并清理文件夹: {folder_path.resolve()} ---")
    print(f"--- 查找目标 Key: '{key_display}' ---")
    print(f"--- 替换为: '{replacement}' ---")

    # 使用 .rglob('*.json') 递归查找所有 .json 文件
    json_files = list(folder_path.rglob('*.json'))

    if not json_files:
        print("未在该文件夹及其子文件夹中找到 .json 文件。")
        return False

    print(f"共找到 {len(json_files)} 个 .json 文件，正在逐一检查和修改...")

    for file_path in json_files:
        try:
            # 1. 以 UTF-8 编码读取文件内容
            content = file_path.read_text(encoding='utf-8')

            # 2. 检查 API Key 是否在文件内容中
            if api_key in content:
                # 3. 如果存在，执行替换
                print(f"[REPLACED] 在 {file_path} 中找到并替换了密钥。")

                # 替换所有出现的密钥
                modified_content = content.replace(api_key, replacement)

                # 4. 将修改后的内容写回文件
                file_path.write_text(modified_content, encoding='utf-8')
                total_replaced_files += 1
            else:
                # （可选）如果您想看到所有被跳过的文件，请取消下面一行的注释
                # print(f"[SKIPPED] {file_path} 中未发现密钥。")
                pass

        except UnicodeDecodeError:
            print(f"[警告] 无法以 UTF-8 编码读取文件 {file_path}。已跳过。")
        except IOError as e:
            print(f"[错误] 无法读/写文件 {file_path}: {e}。已跳过。")
        except Exception as e:
            print(f"[未知错误] 处理 {file_path} 时出错: {e}。已跳过。")

    print(f"\n--- 清理完成 ---")
    if total_replaced_files > 0:
        print(f"结果: 成功在 {total_replaced_files} 个文件中替换了密钥。")
    else:
        print("结果: 未在任何 .json 文件中发现您提供的 API Key。")

    return total_replaced_files > 0


def main():
    # 简单的配置检查
    if "sk-326d3629fead49b8ab54750b4869fc80" in API_KEY_TO_FIND or not API_KEY_TO_FIND:
        print("警告: 您似乎正在使用示例 API Key。")
        print("      请确保 'API_KEY_TO_FIND' 变量已更新为您真实的 Key。")
        # （为防止意外，您可以选择在这里退出，但目前我假设您可能真的要替换这个示例key）
        # sys.exit(1)

    if not FOLDER_TO_SCAN:
        print("错误: 'FOLDER_TO_SCAN' 变量不能为空。")
        sys.exit(1)

    search_folder = Path(FOLDER_TO_SCAN)

    if not search_folder.is_dir():
        print(f"错误: 路径 '{search_folder}' 不是一个有效的文件夹。")
        sys.exit(1)

    # 运行扫描和替换
    scan_and_redact(API_KEY_TO_FIND, search_folder, REPLACEMENT_STRING)


if __name__ == "__main__":
    main()