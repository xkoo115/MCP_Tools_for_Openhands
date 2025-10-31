import os
import httpx
from openai import OpenAI
import urllib3
import requests  # <--- 新增: 用于下载图片
import base64    # <--- 新增: 用于编码
import mimetypes # <--- 新增: 用于猜测MIME类型
# ---
# !!! 用户请在此处填入你的凭证 !!!
# ---

# # 1. 填入你的 API Key
# QWEN_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxx"  # <--- 在这里填入你的真实 Key
#
# # 2. 填入你的 API Base URL (注意: *不要* 包含 /chat/completions)
# QWEN_API_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


# 3. 填入你的代理凭证 (如果不需要代理，设为 None)
# 格式: "http://用户名:密码@代理地址:端口"
# 示例: "http://my_user:my_pass@proxy.company.com:8080"
#
# PROXY_URL = None  # <--- 如果你不需要代理，请使用这一行

# 4. SSL 证书设置 (解决 'CERTIFICATE_VERIFY_FAILED')
# True = 严格验证 (默认)
# False = 不验证 (不安全，但用于绕过自签名证书)
# "path/to/ca.pem" = 信任你公司的根证书 (安全，推荐)
SSL_VERIFY = False  # <--- 设为 False 来跳过 SSL 验证

# --- (配置结束) ---


# ---
# 辅助设置
# ---

# 1. 如果跳过 SSL 验证 (verify=False)，禁用 Python 的警告
if SSL_VERIFY is False:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print("[警告] 已禁用 SSL 证书验证 (verify=False)。")

# 2. 配置代理 (如果已提供)
proxies_config = None
if PROXY_URL:
    proxies_config = {
        "http://": PROXY_URL,
        "https://": PROXY_URL,
    }
    print(f"已配置代理，将通过 {PROXY_URL.split('@')[-1]} 连接。")


# ---
# 新增辅助函数：编码本地图片
# ---
def encode_local_image_to_base64(filepath):
    """
    将本地图片文件编码为 Base64 Data URI
    """
    try:
        # 猜测文件的 Mime Type
        mime_type, _ = mimetypes.guess_type(filepath)
        if mime_type is None:
            mime_type = "application/octet-stream"  # 默认值

        # 读取二进制文件内容
        with open(filepath, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

        # 格式化为 Data URI
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        print(f"Error encoding image {filepath}: {e}")
        raise


# ---
# 主执行函数
# ---
if __name__ == "__main__":

    if "xxxx" in QWEN_API_KEY:
        print("\n!!! 警告: 请先在脚本顶部填入你的 QWEN_API_KEY !!!")
        exit(1)

    # ---
    # 步骤 1: 下载测试图片
    # ---
    image_url_to_download = "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
    local_image_path = "temp_test_image.jpeg"  # 我们将下载到这个文件

    print(f"--- 正在测试本地图片上传 ---")

    try:
        # 我们使用同一个 httpx.Client 来处理下载，
        # 这样它也能复用我们的代理和 SSL 设置
        with httpx.Client(verify=SSL_VERIFY) as http_client:

            print(f"正在下载测试图片: {image_url_to_download} ...")
            response = http_client.get(image_url_to_download)
            response.raise_for_status()  # 确保下载成功

            # 将图片写入本地文件
            with open(local_image_path, "wb") as f:
                f.write(response.content)
            print(f"图片已成功下载到: {local_image_path}")

            # ---
            # 步骤 2: 将本地图片编码为 Base64
            # ---
            print(f"正在将 '{local_image_path}' 编码为 Base64 Data URI...")
            base64_image_uri = encode_local_image_to_base64(local_image_path)
            print("编码完成。")
            # print(f"  > (前 50 字符): {base64_image_uri[:50]}...") # (调试用)

            # ---
            # 步骤 3: 初始化 OpenAI 客户端
            # ---
            client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url=QWEN_API_URL,
                http_client=http_client  # 传入配置好的 http 客户端
            )

            print(f"目标 Base URL: {QWEN_API_URL}")
            print("正在发送 /chat/completions 请求 (使用 Base64 本地图片)...")

            # ---
            # 步骤 4: 发起 API 调用
            # ---
            completion = client.chat.completions.create(
                model="qwen-vl-plus",
                messages=[{"role": "user", "content": [
                    {
                        "type": "image_url",
                        # *** 关键更改 ***
                        # 现在我们传入的是 Base64 字符串
                        "image_url": {"url": base64_image_uri}
                    },
                    {"type": "text", "text": "这张图里有什么?"},
                ]}]
            )

            print("\n--- ✅ 测试成功! ---")
            print("API 返回内容 (基于本地图片):")
            print(completion.choices[0].message.content)

    except Exception as e:
        print(f"\n--- ❌ 测试失败! ---")
        print(f"发生错误: {e}")

    finally:
        # ---
        # 步骤 5: 清理下载的临时文件
        # ---
        if os.path.exists(local_image_path):
            os.remove(local_image_path)
            print(f"\n已清理临时文件: {local_image_path}")