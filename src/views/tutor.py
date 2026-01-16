"""
Math Tutor 页面视图
处理图片上传和 AI 分析
"""
import streamlit as st
import os
import time
import concurrent.futures
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
import google.generativeai as genai
import re
from db_manager import DBManager


# 全局配置
DATA_DIR = "../data/full_page_book"
IMG_DIR = os.path.join(DATA_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)
MAX_WORKERS = 1


def process_single_file(file_obj, user_tags, hint, user_id, model, ctx):
    """处理单个上传的文件"""
    if ctx: 
        add_script_run_ctx(threading.current_thread(), ctx)
    time.sleep(0.5) 
    fname = file_obj.name
    
    try:
        if not model:
            return False, fname, "AI 模型未初始化，请检查 GOOGLE_API_KEY 配置", ""
            
        from PIL import Image
        image = Image.open(file_obj)
        prompt = f"""
        你是一名亲切的小学数学老师。请对这张错题进行温柔、详细的讲解。
        【用户提示】：{hint if hint else "无"}
        
        请严格按照以下 Markdown 格式输出：
        ## 🧠 考点在哪里？
        (简要分析考点)
        ## 📝 老师来细讲
        (详细的步骤解析)
        ## ✅ 正确答案
        (给出最终结果)
        ## 🏷️ 标签
        (请提取 2-3 个核心知识点关键词，用逗号分隔。例如：几何, 相似三角形, 计算)
        """
        
        ai_content = ""
        last_error = ""
        
        # 尝试 3 次调用
        for i in range(3):
            try:
                response = model.generate_content([prompt, image])
                ai_content = response.text
                break
            except Exception as e:
                last_error = str(e)
                print(f"❌ Gemini API Error (Attempt {i+1}): {e}")
                time.sleep(2)

        if not ai_content:
            return False, fname, f"AI 连接失败: {last_error}", ""

        # 提取标签
        final_tags = user_tags
        match = re.search(r"## 🏷️ 标签[:：]?\s*(.*)", ai_content, re.DOTALL)
        if match:
            ai_extracted_tags = match.group(1).strip()
            ai_extracted_tags = ai_extracted_tags.replace("。", "").replace(".", "").strip()
            if ai_extracted_tags:
                final_tags = f"{user_tags}, {ai_extracted_tags}"
                tag_list = [t.strip() for t in final_tags.replace("，", ",").split(",") if t.strip()]
                final_tags = ", ".join(list(set(tag_list)))

        timestamp = str(int(time.time() * 1000))
        save_name = f"User{user_id}_{timestamp}.jpg"
        save_path = os.path.join(IMG_DIR, save_name)
        
        file_obj.seek(0)
        with open(save_path, "wb") as f:
            f.write(file_obj.read())
            
        db = DBManager()
        db.save_question(user_id, fname, ai_content, save_path, final_tags)
        return True, fname, ai_content, save_path
        
    except Exception as e:
        return False, fname, f"系统错误: {str(e)}", ""


def render_tutor_page(user, model):
    """渲染 Math Tutor 页面（原有的 RAG 对话逻辑）"""
    st.markdown("### 📸 Upload Your Math Questions")
    
    st.markdown("""
    <div class="dashboard-card" style="margin-bottom: 2rem;">
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns([2, 1])
    with c1: 
        uploaded_files = st.file_uploader(
            "📥 Upload homework images", 
            accept_multiple_files=True, 
            type=['jpg', 'png'],
            help="Upload images of your math problems"
        )
    with c2: 
        tags = st.text_input("🏷️ Tags", value="期末复习", help="Add tags for this session")
        hint = st.text_input("💡 Hint", placeholder="What do you need help with?", help="Tell us what you're struggling with")
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    if uploaded_files:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Start AI Analysis", type="primary", use_container_width=True):
            if not model:
                st.error("⚠️ AI model not initialized. Please check GOOGLE_API_KEY in .env file!")
                return
                
            ctx = get_script_run_ctx()
            progress = st.progress(0)
            status = st.status("🔮 AI teacher is thinking...", expanded=True)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for f in uploaded_files:
                    futures.append(executor.submit(process_single_file, f, tags, hint, user['id'], model, ctx))
                
                completed = 0
                for future in concurrent.futures.as_completed(futures):
                    ok, fname, content, path = future.result()
                    completed += 1
                    progress.progress(completed / len(uploaded_files))
                    if ok:
                        status.write(f"✅ {fname} completed")
                        with st.expander(f"📖 View Analysis: {fname}"):
                            col_img, col_content = st.columns([1, 2])
                            with col_img:
                                st.image(path, use_container_width=True)
                            with col_content:
                                st.markdown(content)
                    else:
                        status.error(f"❌ {fname} failed: {content}")
                        st.error(f"⚠️ Error details: {content}")
            
            status.update(label="🎉 Processing complete", state="complete")
