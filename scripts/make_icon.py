"""生成 PWA 应用图标（开发辅助脚本，产物已提交，无需重复运行）。"""
from PIL import Image, ImageDraw

size = 192
image = Image.new("RGB", (size, size), "#2563eb")
draw = ImageDraw.Draw(image)
# 简洁的 M 字标
draw.rectangle([30, 130, 162, 146], fill="#ffffff")
draw.polygon([(40, 140), (40, 60), (70, 60), (96, 105), (122, 60), (152, 60), (152, 140), (126, 140), (126, 95), (96, 140), (66, 95), (66, 140)], fill="#ffffff")
image.save(".streamlit/static/icon.png")
print("icon written")
