import streamlit as st
import base64
import os
import datetime
import json
import time
import io
import concurrent.futures
import threading
from openai import OpenAI
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from PIL import Image
from dotenv import load_dotenv # 导入安全插件

# 关键库：给线程发身份证，防止 Streamlit 报错
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# ================= 配置区域 (已修复) =================
# 1. 加载本地保险箱 (.env)
load_dotenv()

# 2. 从保险箱里拿钥匙
API_KEY = os.getenv("SILICONFLOW_API_KEY")

# 3. 检查钥匙
if not API_KEY:
    # 如果没拿到，就在终端打印个红色警告
    print("❌ 严重错误：找不到 API Key！请确认你创建了 .env 文件，并且里面写了 SILICONFLOW_API_KEY=你的密钥")

BASE_URL = "https://api.siliconflow.cn/v1"
MODEL_NAME = "Qwen/Qwen2-VL-72B-Instruct"

# 👇 刚才丢失的关键配置，现在补回来了！
DATA_DIR = "../data/full_page_book"
MAX_WORKERS = 1  
# ===================================================

st.set_page_config(page_title="AI 全能教研员", page_icon="👨‍🏫", layout="wide")

os.makedirs(os.path.join(DATA_DIR, "images"), exist_ok=True)
json_path = os.path.join(DATA_DIR, "records.json")

# --- 核心工具函数 ---
def compress_image(image_file):
    """压缩图片，防止传给 AI 的包太大"""
    try:
        image_file.seek(0)
        img = Image.open(image_file)
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        
        max_width = 1600 
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.BILINEAR)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=75)
        buffer.seek(0)
        return buffer
    except Exception:
        image_file.seek(0)
        return image_file

def encode_image(image_file):
    compressed_file = compress_image(image_file)
    return base64.b64encode(compressed_file.getvalue()).decode('utf-8')

def process_single_file(client, file_obj, tags, hint, status_container, ctx):
    """处理单张图片的核心逻辑"""
    # 1. 绑定上下文
    if ctx:
        add_script_run_ctx(threading.current_thread(), ctx)
        
    # 2. 安全延时
    time.sleep(1.5) 

    fname = file_obj.name
    try:
        img_b64 = encode_image(file_obj)
        
        # 🟢 核心 Prompt
        prompt = """
        你是一名【资深小学数学教研组长】，拥有 20 年一线教学经验。请对这张图片中的错题进行【全题型深度诊断与解析】。
        
        ### 🧠 核心思维逻辑（思维路由）：
        拿到题目后，请先在内心判断它属于哪一类，并执行对应的**强制分析法则**：

        #### 📐 类型一：图形与几何（求长/周长/面积/体积/角度）
        - **视觉拆解**：必须用文字描述图形的组合方式（如“长方形挖去一个半圆”）。
        - **围栏法（求周长特用）**：想象沿着图形边缘走一圈，**严禁漏掉内部的线段或外部的曲线**。拆解为：$周长 = 线段A + 线段B + 曲线C$。
        - **割补法（求面积特用）**：明确指出是使用“割法”（分块相加）还是“补法”（大减小）。

        #### 🚗 类型二：典型应用题（行程/工程/浓度/经济/鸡兔同笼）
        - **寻找“不变量”**：指出题目中哪个量是不变的（如总路程、总工作量）。
        - **建立模型**：明确写出数量关系式。
          - *行程问题*：$路程 = 速度 \\times 时间$（注意相遇还是追及）。
          - *分数/百分数*：找准“单位1”。
        - **单位陷阱**：**必须检查单位！**（如米 vs 千米，分钟 vs 小时），如有不同请在解析中强调换算步骤。

        #### 🔢 类型三：数与代数（计算/方程/比与比例）
        - **符号检查**：仔细区分 $\\div$（除号）和 $+$（加号）。
        - **运算顺序**：强调先乘除后加减，有括号先算括号。
        - **结果验证**：如果是解方程，请代入验证是否成立。

        #### 📊 类型四：统计与概率（条形/折线/扇形图）
        - **读图优先**：先读取横轴、纵轴的含义和刻度值，不要凭感觉估算。
        - **数据一致性**：检查表格数据与图表数据是否对应。
        """

        if hint:
            prompt += f"""
            
            ### 🔑 老师特别提示 (这是正确线索，请务必参考)：
            {hint}
            
            (请根据以上提示，重新审视你的解题思路，确保解析逻辑能推导出该结果，不要产生幻觉。)
            """

        prompt += """
        ---

        ### ⚠️ 输出格式（严格遵守，方便家长辅导）：
        请为每一道题输出一段内容，题目之间用 "=======" (7个等号) 分隔。
        每段内容必须包含以下模块：

        题号：[自动识别的数字]
        【题型】：[例如：几何-求阴影面积 / 行程-相遇问题 / 统计-折线图分析]
        【题目】：[完整抄录题目。数学公式请用通俗写法，如“3.14乘以半径的平方”，复杂公式再用LaTeX]
        【名师精讲】：
        1. **👀 审题眼**：[一针见血指出题目里的“坑”或“关键词”。例如：“注意！这道题单位不统一”或“注意！阴影部分包含两条半径”。]
        2. **💡 思路拆解**：[分步骤的逻辑推导。如果是几何，写出图形拆解；如果是应用题，写出数量关系式。]
        3. **📝 规范解答**：[给出最终算式和结果。]
        
        ======
        """
        
        # 重试机制
        max_retries = 3
        ai_content = ""
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "user", 
                         "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                            {"type": "text", "text": prompt}
                         ]
                        }
                    ],
                    temperature=0.2, 
                )
                ai_content = response.choices[0].message.content
                break
            except Exception as e:
                if attempt == max_retries - 1: raise e
                time.sleep(2)

        # 保存图片
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(int(time.time() * 10000))[-6:]
        img_filename = f"Exam_{timestamp}_{unique_id}.jpg"
        img_path = os.path.join(DATA_DIR, "images", img_filename)
        
        file_obj.seek(0)
        with open(img_path, "wb") as f:
            f.write(file_obj.read())
            
        # 构造数据记录
        new_record = {
            "id": unique_id,
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "tags": tags,
            "image_path": img_path,
            "ai_content": ai_content,
            "filename": file_obj.name
        }
        
        # 写入 JSON
        current_records = []
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    current_records = json.load(f)
            except: pass
            
        current_records.append(new_record)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(current_records, f, ensure_ascii=False, indent=2)
            
        return True, fname, ai_content, img_path
    except Exception as e:
        return False, str(e), "", ""

def generate_word_doc():
    """生成清洗版的 Word 文档"""
    if not os.path.exists(json_path): return False, "暂无数据"
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not records: return False, "库是空的"
            
        doc = Document()
        doc.styles['Normal'].font.name = u'微软雅黑'
        doc.styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'), u'微软雅黑')
        
        doc.add_heading('AI 全科错题诊断报告', 0)
        
        for rec in records:
            content = rec['ai_content']
            content = content.replace("**", "").replace("##", "").replace("###", "")
            
            doc.add_heading(f"来源: {rec['filename']}", level=1)
            
            if os.path.exists(rec['image_path']):
                try: 
                    doc.add_picture(rec['image_path'], width=Inches(5.5))
                except: 
                    doc.add_paragraph("[图片加载失败]")
            
            doc.add_paragraph("") 
            
            questions = content.split('======')
            
            table = doc.add_table(rows=1, cols=2)
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = '题目内容'
            hdr_cells[1].text = '名师诊断 & 解析'
            
            for q in questions:
                if not q.strip(): continue
                
                lines = q.strip().split('\n')
                q_text = ""
                a_text = ""
                
                for line in lines:
                    line = line.strip()
                    if "题号" in line:
                        continue 
                    elif "【题目】" in line:
                        q_text += line.replace("【题目】", "").replace(":", "").replace("：", "") + "\n"
                    else:
                        if line: a_text += line + "\n"
                
                if q_text.strip() or a_text.strip():
                    row_cells = table.add_row().cells
                    row_cells[0].text = q_text.strip()
                    row_cells[1].text = a_text.strip()
            
            doc.add_page_break()
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_name = f"Master_Analysis_{timestamp}.docx"
        save_path = os.path.join("../data", save_name)
        doc.save(save_path)
        return True, save_path
        
    except Exception as e:
        return False, str(e)

# ================= 界面逻辑 =================
with st.sidebar:
    st.title("👨‍🏫 AI 全能教研员")
    count = 0
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            try: count = len(json.load(f))
            except: pass
    st.metric("📚 已收录错题", f"{count} 页")
    
    st.markdown("---")
    with st.expander("🗑️ 清空题库"):
        st.warning("确定要删除所有记录吗？")
        if st.checkbox("确认清空"):
            if st.button("🔴 执行清空"):
                if os.path.exists(json_path): os.remove(json_path)
                import shutil
                if os.path.exists(os.path.join(DATA_DIR, "images")):
                    shutil.rmtree(os.path.join(DATA_DIR, "images"))
                st.rerun()

tab1, tab2 = st.tabs(["📸 录入 & 实时诊断", "📘 导出诊断报告"])

with tab1:
    st.info("💡 提示：本模式已启用【全能思维路由】。难点题请在右侧输入“锦囊”提示。")
    uploaded_files = st.file_uploader("拖入错题图片 (支持批量)", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        tags = st.text_input("标签", placeholder="例如: 六年级上册期末复习")
        if not tags: tags = "未分类"
    with col_input2:
        user_hint = st.text_input("💡 锦囊 (选填)", placeholder="例如：答案是2626 / 注意绳子会转弯")
    
    if uploaded_files:
        if st.button("🚀 开始诊断", type="primary"):
            client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
            ctx = get_script_run_ctx()

            progress_bar = st.progress(0)
            status_text = st.empty()
            
            result_area = st.container()

            completed = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for i, f in enumerate(uploaded_files):
                    futures.append(executor.submit(process_single_file, client, f, tags, user_hint, status_container=None, ctx=ctx))
                
                status_text.write("🔥 AI 正在逐题分析中 (稳健模式)...")
                
                for future in concurrent.futures.as_completed(futures):
                    success, fname, content, img_path = future.result()
                    completed += 1
                    progress_bar.progress(completed / len(uploaded_files))
                    
                    if success:
                        with result_area:
                            with st.expander(f"✅ 完成: {fname} (点击查看解析)", expanded=True):
                                col1, col2 = st.columns([1, 2])
                                with col1:
                                    if os.path.exists(img_path):
                                        st.image(img_path, caption="原图")
                                with col2:
                                    st.markdown("### 📝 AI 诊断结果")
                                    st.markdown(content) 
                    else:
                        st.error(f"❌ {fname} 失败: {content}")

            status_text.success("🎉 所有题目处理完毕！")
            st.balloons()

with tab2:
    st.write("将所有已录入的错题导出为 Word 文档，方便打印或复习。")
    if st.button("📄 生成 Word 讲义", type="primary"):
        with st.spinner("正在排版清洗..."):
            ok, path = generate_word_doc()
        if ok:
            st.success(f"✅ 讲义已生成！")
            with open(path, "rb") as f:
                st.download_button("📥 点击下载 (.docx)", f, os.path.basename(path))
        else:
            st.error(f"❌ 生成失败: {path}")