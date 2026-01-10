import google.generativeai as genai
import os
from dotenv import load_dotenv

# 1. 加载你的 API Key
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)
# ... 上面的代码不变 ...

# 🔴 把这里改成 7890 试试！
os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"

print("📡 正在连接 Google 服务器查询模型列表...")
print(f"🔌 使用端口: 7890") # 这里也顺便改一下显示

# ... 下面的代码不变 ...

try:
    # 列出所有支持的模型
    for m in genai.list_models():
        # 我们只关心能生成内容 (generateContent) 的模型
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ 可用模型: {m.name}")
except Exception as e:
    print(f"❌ 连接失败: {e}")