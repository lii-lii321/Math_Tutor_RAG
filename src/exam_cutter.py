import cv2
import numpy as np
import os
import shutil
import fitz  # PyMuPDF

# ================= 配置区域 =================
INPUT_FOLDER = "../data/raw_exams"       
OUTPUT_FOLDER = "../data/cut_questions"
DEBUG_FOLDER = "../data/debug_view"  # 🟢 新增：生成的调试图放这里，方便你看哪里切歪了

# 🟢 布局参数
FORCE_COLS = 3          # 还是按 3 栏切
HEADER_RATIO = 0.14     # 顶部标题占大概 14% (根据你的截图目测)
FOOTER_RATIO = 0.05     # 底部页码占 5%
MIN_QUESTION_H = 40     # 题目最小高度
# ===========================================

def ensure_dirs():
    for p in [INPUT_FOLDER, OUTPUT_FOLDER, DEBUG_FOLDER]:
        if not os.path.exists(p):
            os.makedirs(p)

def find_left_anchor(binary_img):
    """
    🟢 核心算法：寻找左侧的装订线 (竖实线)
    返回这条线的 x 坐标。如果找不到，返回图像宽度的 5% 作为默认值。
    """
    h, w = binary_img.shape
    
    # 只扫描左侧 20% 的区域
    roi = binary_img[:, 0:int(w*0.2)]
    
    # 垂直投影 (统计每一列有多少个黑色像素)
    # 注意：binary_img 是黑底白字(255)，所以我们反过来统计
    # 我们要找“黑线”，在二值图中黑线是 0，白纸是 255。
    # 为了方便，先把二值图反转：线变亮(255)，纸变黑(0)
    # 这里的 binary_img 假设已经是(黑底白字)了，所以线应该是亮的竖条？
    # 不，通常二值化 threshold 之后，字和线是 255(白)，背景是 0(黑)。
    
    v_proj = cv2.reduce(roi, 0, cv2.REDUCE_AVG)
    
    # 寻找峰值：这一列像素平均值很高（说明大部分都是白色/墨水）
    # 竖线是一条贯穿上下的线，所以它的投影值应该很大
    best_x = 0
    max_val = 0
    
    for x in range(len(v_proj[0])):
        val = v_proj[0][x]
        if val > max_val:
            max_val = val
            best_x = x
            
    # 如果峰值太低，说明没线，返回默认
    if max_val < 50: 
        print("      ⚠️ 未检测到明显装订线，使用默认左边距")
        return int(w * 0.08) # 默认跳过 8%
        
    print(f"      ⚓ 锁定装订线位置: x={best_x}")
    return best_x + 20 # 线本身有宽度，往右挪 20 像素开始切

def process_page(img, base_filename, page_num=0):
    print(f"   ...正在处理第 {page_num+1} 页...")
    h, w = img.shape[:2]
    
    # 1. 预处理
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    # 二值化：字/线=255(白)，纸=0(黑)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    
    # 2. 确定有效区域 (Cut Layout)
    # y_top: 跳过标题
    y_top = int(h * HEADER_RATIO)
    y_bottom = int(h * (1 - FOOTER_RATIO))
    
    # x_start: 通过算法自动找左边那条线
    x_start = find_left_anchor(binary)
    
    # 有效内容宽度
    content_width = w - x_start
    col_width = content_width // FORCE_COLS
    
    # ================= 调试绘图 (画出我们打算怎么切) =================
    debug_img = img.copy()
    # 画出有效区域框 (绿色)
    cv2.rectangle(debug_img, (x_start, y_top), (w, y_bottom), (0, 255, 0), 2)
    # 画出每一栏的分界线 (蓝色)
    for i in range(1, FORCE_COLS):
        cx = x_start + i * col_width
        cv2.line(debug_img, (cx, 0), (cx, h), (255, 0, 0), 2)
    
    # 保存调试图
    debug_path = os.path.join(DEBUG_FOLDER, f"debug_{base_filename}_p{page_num+1}.jpg")
    cv2.imwrite(debug_path, debug_img)
    # ===========================================================

    total_q = 0
    
    # 3. 开始循环切栏
    for i in range(FORCE_COLS):
        cx1 = x_start + i * col_width
        cx2 = x_start + (i + 1) * col_width
        if i == FORCE_COLS - 1: cx2 = w # 最后一栏到底
            
        # 拿到这一栏的图像 (只取中间部分，去掉头尾)
        col_img = img[y_top:y_bottom, cx1:cx2]
        
        # 4. 横向切题
        # 重新二值化这一栏
        col_gray = cv2.cvtColor(col_img, cv2.COLOR_BGR2GRAY)
        _, col_bin = cv2.threshold(col_gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        # 腐蚀掉横线干扰 (把横线变没)
        kernel_h = np.ones((1, 15), np.uint8) 
        clean_bin = cv2.erode(col_bin, kernel_h, iterations=1)
        clean_bin = cv2.dilate(clean_bin, kernel_h, iterations=1)
        
        # 水平投影
        h_proj = cv2.reduce(clean_bin, 1, cv2.REDUCE_AVG)
        
        # 找切点
        cuts = [0]
        is_gap = False
        gap_start = 0
        
        # 这里的 5 是横向缝隙的判断阈值，稍微调小点适应紧凑试卷
        for y in range(len(h_proj)):
            if h_proj[y][0] < 5: # 空白
                if not is_gap:
                    is_gap = True
                    gap_start = y
            else:
                if is_gap:
                    if (y - gap_start) > 20: # 缝隙高度 > 20像素才算
                        mid = gap_start + (y - gap_start)//2
                        cuts.append(mid)
                    is_gap = False
        cuts.append(len(h_proj))
        
        # 保存小题
        for k in range(len(cuts)-1):
            y1 = cuts[k]
            y2 = cuts[k+1]
            if (y2 - y1) > MIN_QUESTION_H:
                q_sub = col_img[y1:y2, :]
                # 检查是不是全白
                if cv2.mean(q_sub)[0] < 250:
                    save_name = f"{base_filename}_p{page_num+1}_c{i+1}_q{total_q+1}.jpg"
                    cv2.imwrite(os.path.join(OUTPUT_FOLDER, save_name), q_sub)
                    total_q += 1

    print(f"      ✅ 页面处理完毕，切出 {total_q} 道题")

def process_pdf(path, fname):
    print(f"📄 读取 PDF: {fname}")
    doc = fitz.open(path)
    base = os.path.splitext(fname)[0]
    for i in range(len(doc)):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n >= 3: img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        process_page(img, base, i)

if __name__ == "__main__":
    ensure_dirs()
    files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(('.pdf','.jpg','.png'))]
    if not files:
        print("请放入试卷文件")
    else:
        print("🚀 启动锚点自动定位切割...")
        for f in files:
            path = os.path.join(INPUT_FOLDER, f)
            if f.endswith('.pdf'): process_pdf(path, f)
            else: 
                img = cv2.imread(path)
                process_page(img, os.path.splitext(f)[0])
        print(f"\n🏁 完成！如果还是切歪了，请务必去 {DEBUG_FOLDER} 看看那张画线的图！")