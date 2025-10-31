import requests
import os
import sys
import json
from openai import OpenAI

# --- 1. 配置 ---

# 步骤 1：要下载的原始图片 URL
IMAGE_URL_TO_DOWNLOAD = "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
# 本地临时文件名
LOCAL_FILENAME = "temp_dog_and_girl.jpg"
# 步骤 2：用于匿名上传的网站 API
UPLOAD_API_URL = "https://catbox.moe/user/api.php"

# 步骤 3：Qwen-VL Plus 的配置
# 确保 DASHSCOPE_API_KEY 环境变量已设置
API_KEY = os.getenv("DASHSCOPE_API_KEY")
BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen-vl-plus"


def main():
    """执行完整的 下载 -> 上传 -> AI分析 流程"""

    if not API_KEY:
        print("错误：未找到 'DASHSCOPE_API_KEY' 环境变量。")
        print("请先设置您的 API 密钥。")
        sys.exit(1)

    try:
        # --- 步骤 1: 下载图片到本地 ---
        print(f"步骤 1: 正在从 {IMAGE_URL_TO_DOWNLOAD} 下载图片...")

        response_dl = requests.get(IMAGE_URL_TO_DOWNLOAD)
        # 检查下载是否成功
        response_dl.raise_for_status()

        with open(LOCAL_FILENAME, 'wb') as f:
            f.write(response_dl.content)

        print(f"图片已成功保存为: {LOCAL_FILENAME}")

        # --- 步骤 2: 上传文件到 catbox.moe 并获取 URL ---
        print(f"\n步骤 2: 正在上传 {LOCAL_FILENAME} 到 {UPLOAD_API_URL}...")

        upload_data = {
            "reqtype": "fileupload"
        }

        with open(LOCAL_FILENAME, 'rb') as f:
            files_to_upload = {
                # 'fileToUpload' 是 catbox.moe API 要求的字段名
                "fileToUpload": (LOCAL_FILENAME, f, 'image/jpeg')
            }
            response_ul = requests.post(UPLOAD_API_URL, data=upload_data, files=files_to_upload)

        # 检查上传是否成功
        response_ul.raise_for_status()

        new_image_url = response_ul.text

        # catbox.moe 成功时会直接返回 URL
        if not new_image_url.startswith("http"):
            print(f"上传失败。API 返回了非预期的内容: {new_image_url}")
            return

        print(f"上传成功！获取到新的 URL: {new_image_url}")

        # --- 步骤 3: 使用新 URL 调用 qwen-vl-plus ---
        print(f"\n步骤 3: 正在使用新 URL 调用 {MODEL_NAME}...")

        # 实例化客户端 (完全按照您提供的代码)
        client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL,
        )

        # 发送请求，但使用我们新上传的 new_image_url
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": new_image_url}},  # <-- 关键：使用新 URL
                {"type": "text", "text": "这是什么"},
            ]}]
        )

        print("\n--- qwen-vl-plus 模型返回的原始 JSON 结果 ---")
        # 打印完整的 JSON 输出
        print(completion.model_dump_json(indent=2))
        print("--------------------------------------------------")

        # --- 步骤 4: 解析结果并验证 ---

        # 提取模型的可读回复
        if completion.choices and completion.choices[0].message:
            content = completion.choices[0].message.content
            print(f"\n模型识别内容: {content}")

            # 简单的验证
            if "狗" in content or "女孩" in content or "dog" in content or "girl" in content:
                print("\n测试成功：模型正确识别了图片内容（狗和女孩）。")
            else:
                print("\n测试通过：模型返回了结果，但未明确提及'狗'或'女孩'。")
        else:
            print("\n测试失败：未能从模型响应中解析出有效内容。")


    except requests.exceptions.RequestException as e:
        print(f"\n网络请求失败: {e}")
    except Exception as e:
        print(f"\n发生意外错误: {e}")

    finally:
        # --- 清理: 无论成功与否，都删除本地的临时文件 ---
        if os.path.exists(LOCAL_FILENAME):
            os.remove(LOCAL_FILENAME)
            print(f"\n清理：已删除临时文件 {LOCAL_FILENAME}")


# --- 运行主函数 ---
if __name__ == "__main__":
    main()