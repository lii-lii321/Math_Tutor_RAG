import google.generativeai as genai
import os
from dotenv import load_dotenv

# 1. 加载环境变量
load_dotenv()

# 2. 配置代理（从环境变量读取）
http_proxy = os.getenv('HTTP_PROXY', '')
https_proxy = os.getenv('HTTPS_PROXY', '')
if http_proxy:
    os.environ["HTTP_PROXY"] = http_proxy
    print(f"🔌 HTTP 代理: {http_proxy}")
if https_proxy:
    os.environ["HTTPS_PROXY"] = https_proxy
    print(f"🔌 HTTPS 代理: {https_proxy}")

# 3. 加载 API Key
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("❌ 错误：未找到 GOOGLE_API_KEY！")
    print("👉 请在 .env 文件中设置 GOOGLE_API_KEY")
    exit(1)

genai.configure(api_key=api_key)

print("📡 正在连接 Google 服务器查询模型列表...")

# ... 下面的代码不变 ...

try:
    # 列出所有支持的模型
    for m in genai.list_models():
        # 我们只关心能生成内容 (generateContent) 的模型
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ 可用模型: {m.name}")
except Exception as e:
    print(f"❌ 连接失败: {e}")