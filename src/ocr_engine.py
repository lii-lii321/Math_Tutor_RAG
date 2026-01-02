from paddleocr import PaddleOCR
import os
import logging

# 🤫 关闭调试日志
logging.getLogger("ppocr").setLevel(logging.WARNING)

print("正在初始化 PaddleOCR...")

# 🟢 修复点：
# 1. 删掉了报错的 show_log 参数
# 2. 把 use_angle_cls 换成了新版的 use_textline_orientation
ocr = PaddleOCR(use_textline_orientation=True, lang="ch")

def ocr_image_to_markdown(image_path):
    """
    使用 PaddleOCR 读取图片中的所有文字
    """
    if not os.path.exists(image_path):
        print(f"❌ 错误：找不到图片文件 {image_path}")
        return None

    print(f"🔍 正在读取图片: {image_path} ...")
    
    try:
        # 开始识别
        result = ocr.ocr(image_path)
        
        # 解析结果
        text_lines = []
        if result and result[0]:
            for line in result[0]:
                text_content = line[1][0]
                text_lines.append(text_content)
        
        full_text = "\n".join(text_lines)
        
        print("✅ 识别成功！")
        return full_text
        
    except Exception as e:
        print(f"❌ 识别出错: {e}")
        return None

# --- 测试代码 ---
if __name__ == "__main__":
    test_image_path = "../data/raw_images/test.jpg"
    
    if os.path.exists(test_image_path):
        print("\n--- 开始测试识别 ---")
        res = ocr_image_to_markdown(test_image_path)
        print("\n--- 识别结果 ---")
        print(res)
    else:
        print(f"请先在 {test_image_path} 放一张 test.jpg 图片进行测试")