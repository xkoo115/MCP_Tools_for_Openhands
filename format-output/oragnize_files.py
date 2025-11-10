import shutil
from pathlib import Path
import sys

# --- 1. 配置路径 ---

# 源目录
SOURCE_DIR = Path("outputs_ds_v32_imp1")

# 目标目录 1: 筛选（保持结构）
SELECT_DIR = Path("select-outputs")

# 目标目录 2: 重组（新结构）
FORMAT_DIR = Path("format-outputs")

# 任务列表文件名
TASK_LIST_FILE = Path("tasks.txt")

# --- 2. 检查源文件是否存在 ---
if not SOURCE_DIR.is_dir():
    print(f"错误: 源目录 '{SOURCE_DIR}' 不存在。请在正确的路径下运行脚本。")
    sys.exit(1)

if not TASK_LIST_FILE.is_file():
    print(f"错误: 任务列表 '{TASK_LIST_FILE}' 未找到。")
    sys.exit(1)

# --- 3. 定义并创建目标目录结构 ---

# 目标 1: select-outputs
select_screenshots_dir = SELECT_DIR / "screenshots"
select_screenshots_dir.mkdir(parents=True, exist_ok=True)

# 目标 2: format-outputs
format_screenshots_dir = FORMAT_DIR / "screenshots"
format_results_dir = FORMAT_DIR / "results"
format_states_dir = FORMAT_DIR / "states"
format_traj_dir = FORMAT_DIR / "trajectories"

format_screenshots_dir.mkdir(parents=True, exist_ok=True)
format_results_dir.mkdir(parents=True, exist_ok=True)
format_states_dir.mkdir(parents=True, exist_ok=True)
format_traj_dir.mkdir(parents=True, exist_ok=True)

# --- 4. 读取任务列表 ---
try:
    with open(TASK_LIST_FILE, 'r', encoding='utf-8') as f:
        # 读取每一行，去除首尾空白（如换行符），并过滤掉空行
        tasks = [line.strip() for line in f if line.strip()]
    print(f"成功读取 {len(tasks)} 个任务，来自 '{TASK_LIST_FILE}'。")
except Exception as e:
    print(f"读取任务文件时出错: {e}")
    sys.exit(1)

# --- 5. 循环处理每个任务 ---
copied_count = 0
error_count = 0

print("\n--- 开始处理文件复制和重组 ---")

for task in tasks:
    task_suffix = f"{task}-image"
    print(f"\n[任务: {task}] (文件后缀: {task_suffix})")

    # 定义所有源文件/目录的路径
    src_screenshot_dir = SOURCE_DIR / "screenshots" / task_suffix
    src_eval_file = SOURCE_DIR / f"eval_{task_suffix}.json"
    src_state_file = SOURCE_DIR / f"state_{task_suffix}.json"
    src_traj_file = SOURCE_DIR / f"traj_{task_suffix}.json"

    # 检查所有源文件是否存在
    all_sources_exist = True
    sources_to_check = [src_screenshot_dir, src_eval_file, src_state_file, src_traj_file]
    for src in sources_to_check:
        if not src.exists():
            print(f"  [警告] 源文件或目录不存在: {src}。跳过此任务。")
            all_sources_exist = False
            error_count += 1
            break

    if not all_sources_exist:
        continue

    try:
        # --- 任务 1: 复制到 'select-outputs' (保持结构) ---

        # 复制截图目录
        shutil.copytree(src_screenshot_dir, select_screenshots_dir / task_suffix, dirs_exist_ok=True)

        # 复制JSON文件
        shutil.copy2(src_eval_file, SELECT_DIR / src_eval_file.name)
        shutil.copy2(src_state_file, SELECT_DIR / src_state_file.name)
        shutil.copy2(src_traj_file, SELECT_DIR / src_traj_file.name)

        print(f"  > 成功复制到 '{SELECT_DIR}'")

        # --- 任务 2: 复制到 'format-outputs' (重组结构) ---

        # 复制截图目录
        shutil.copytree(src_screenshot_dir, format_screenshots_dir / task_suffix, dirs_exist_ok=True)

        # 复制JSON文件到新位置
        shutil.copy2(src_eval_file, format_results_dir / src_eval_file.name)
        shutil.copy2(src_state_file, format_states_dir / src_state_file.name)
        shutil.copy2(src_traj_file, format_traj_dir / src_traj_file.name)

        print(f"  > 成功复制并重组到 '{FORMAT_DIR}'")
        copied_count += 1

    except FileNotFoundError as e:
        print(f"  [错误] 文件未找到: {e}。")
        error_count += 1
    except Exception as e:
        print(f"  [未知错误] 处理任务 '{task}' 时出错: {e}")
        error_count += 1

# --- 6. 总结 ---
print("\n--- 整理完成 ---")
print(f"成功处理任务数: {copied_count}")
print(f"失败/跳过任务数: {error_count}")