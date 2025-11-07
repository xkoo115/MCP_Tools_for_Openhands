import os
import glob
import re
import json
import csv
from typing import List, Tuple, Dict, Any


def extract_eval_results_to_csv(input_folder: str, output_csv_file: str):
    """
    分析一个文件夹中所有的 eval_*.json 文件，并将提取的总分和结果保存到 CSV 文件中。

    Args:
        input_folder: 包含 eval_*.json 文件的文件夹路径。
        output_csv_file: 要创建的 CSV 文件的路径。
    """

    # 构建搜索模式以查找所有 eval_*.json 文件
    eval_pattern = os.path.join(input_folder, "eval_*.json")
    json_files = glob.glob(eval_pattern)

    if not json_files:
        print(f"在 '{input_folder}' 文件夹中未找到 'eval_*.json' 文件。")
        return

    results_data: List[List[Any]] = []

    # 遍历处理每个找到的文件
    for filepath in json_files:
        filename = os.path.basename(filepath)

        # 使用正则表达式从文件名中提取任务名称
        # 例如：从 "eval_task-A.json" 提取 "task-A"
        match = re.search(r"eval_(.+)\.json", filename)

        if not match:
            print(f"跳过文件名格式不匹配的文件: {filename}")
            continue

        task_name = match.group(1)

        # 读取和解析 JSON 数据
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 安全地获取 final_score 字典，如果不存在则使用空字典
            final_score: Dict[str, int] = data.get('final_score', {})

            # 安全地获取 total 和 result，如果不存在则默认为 0
            total = final_score.get('total', 0)
            result = final_score.get('result', 0)

            results_data.append([task_name, total, result])

        except json.JSONDecodeError as e:
            print(f"解析 JSON 文件 {filepath} 时出错: {e}。跳过此文件。")
        except Exception as e:
            print(f"处理文件 {filepath} 时发生未知错误: {e}。跳过此文件。")

    # 将提取的数据写入 CSV 文件
    try:
        with open(output_csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # 写入表头
            writer.writerow(['task', 'total', 'result'])

            # 写入所有数据行
            writer.writerows(results_data)

        print(f"成功将数据提取到 '{output_csv_file}'。")

    except IOError as e:
        print(f"写入 CSV 文件 {output_csv_file} 时出错: {e}")


# --- 主程序执行 ---
if __name__ == "__main__":
    # 定义输入的文件夹名称和输出的 CSV 文件名
    INPUT_DIR = "outputs_mcp_test"  # 假设 JSON 文件在 "outputs" 文件夹中
    OUTPUT_CSV = "evaluation_summary_mcp_test_1106.csv"

    # 确保输入文件夹存在
    if not os.path.isdir(INPUT_DIR):
        print(f"错误: 输入文件夹 '{INPUT_DIR}' 不存在。")
    else:
        # 执行提取函数
        extract_eval_results_to_csv(INPUT_DIR, OUTPUT_CSV)