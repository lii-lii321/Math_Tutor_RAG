from paddleocr import PaddleOCR
import os
import logging

# 关闭繁琐的日志
logging.getLogger("ppocr").setLevel(logging.WARNING)

print("🔍 正在初始化侦探程序...")

# 🟢 修正：只保留最核心的参数，去掉所有可能报错的旧参数
ocr = PaddleOCR(lang="ch")

# 图片路径
relative_path = "../data/raw_images/test.jpg"
abs_path = os.path.abspath(relative_path)

print(f"\n📸 正在读取文件: {abs_path}")

if not os.path.exists(relative_path):
    print("❌ 错误：文件不存在！请检查路径。")
else:
    # 打印文件大小，帮你确认是不是那张几何题（几何题通常比纯公式图大）
    file_size = os.path.getsize(relative_path) / 1024
    print(f"📂 文件大小: {file_size:.2f} KB")
    
    print("\n--- 开始识别 ---")
    try:
        # 不加 cls 参数，防止报错
        result = ocr.ocr(relative_path)
        
        if result and result[0]:
            print("✅ 识别到了内容：")
            for line in result[0]:
                text = line[1][0]
                confidence = line[1][1]
                print(f"  📝 {text} (置信度: {confidence:.2f})")
        else:
            print("⚠️ 识别结果为空，或者只识别到了乱码。")
            print("👉 如果你看到这里，请务必确认 data/raw_images/test.jpg 是那张带汉字的几何题！")
            
    except Exception as e:
        print(f"❌ 运行出错: {e}")