from openai import OpenAI
import sys

# 🔴 请再次确认你的 Key 填在这里
KEY = "sk-ygqrtjbuzgpiilwxfxmoojywrnygwjclewlwsqlcvaslzfzl"

print(f"🔑 正在诊断 Key: {KEY[:8]}......{KEY[-5:]}")
print("--------------------------------------------------")

# === 测试通道 1：硅基流动 (SiliconFlow) ===
print("📡 1. 尝试连接 [硅基流动]...")
try:
    client = OpenAI(api_key=KEY, base_url="https://api.siliconflow.cn/v1")
    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-V3",
        messages=[{"role": "user", "content": "hi"}],
        stream=False
    )
    print("✅ 成功！原来这是 [硅基流动] 的 Key！")
    print("👉 请在 app.py 里使用：https://api.siliconflow.cn/v1")
    sys.exit() # 成功就退出
except Exception as e:
    print(f"❌ 失败 ({e})")

print("--------------------------------------------------")

# === 测试通道 2：DeepSeek 官方 ===
print("📡 2. 尝试连接 [DeepSeek 官方]...")
try:
    client = OpenAI(api_key=KEY, base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "hi"}],
        stream=False
    )
    print("✅ 成功！原来这是 [DeepSeek 官方] 的 Key！")
    print("👉 请在 app.py 里使用：https://api.deepseek.com")
    sys.exit()
except Exception as e:
    print(f"❌ 失败 ({e})")

print("--------------------------------------------------")
print("💀 结论：这把 Key 在两个平台都失效了。")
print("👉 解决办法：请去 https://cloud.siliconflow.cn/ 重新创建一个新 Key。")