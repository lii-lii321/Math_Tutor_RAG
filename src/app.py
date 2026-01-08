import streamlit as st
import base64
import os
import time
import io
import concurrent.futures
import threading
from openai import OpenAI
from PIL import Image
from dotenv import load_dotenv
import streamlit_antd_components as sac
from db_manager import DBManager
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from streamlit_echarts import st_echarts  # 🟢 图表库
import re  # 🟢 新增：用于提取 AI 生成的标签
# 🟢 Word 处理库
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ================= 1. 全局配置与样式加载 (Style) =================

def load_css():
    """集中管理所有 CSS 样式"""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Nunito', sans-serif;
            color: #2D3436;
        }

        .stApp { background-color: #FDFBF7; }
        
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            box-shadow: 2px 0 20px rgba(0,0,0,0.02);
        }

        .cream-card {
            background-color: #FFFFFF;
            border-radius: 24px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.05); 
            margin-bottom: 25px;
            transition: transform 0.2s;
        }
        .cream-card:hover { transform: translateY(-2px); }

        h1 { color: #2D3436; font-weight: 800; }
        h2, h3 { color: #636E72; font-weight: 700; }
        
        /* 通用按钮样式 */
        .stButton>button {
            border-radius: 12px;
            font-weight: bold;
            border: none;
            transition: all 0.3s;
            width: 100%;
        }
        
        /* 针对首页数据看板的按钮样式优化 */
        div[data-testid="column"] .stButton button {
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            background-color: #fff;
            color: #2D3436;
            border: 1px solid #f0f0f0;
            height: 80px; 
        }
        div[data-testid="column"] .stButton button:hover {
            transform: scale(1.02);
            border-color: #74b9ff;
            color: #0984e3;
        }

        .stTextInput>div>div>input {
            border-radius: 12px;
            border: 2px solid #F0F2F5;
            background-color: #F9FAFB;
        }
    </style>
    """, unsafe_allow_html=True)

# ================= 2. 基础配置与工具函数 (Utils) =================

load_dotenv()
API_KEY = os.getenv("SILICONFLOW_API_KEY")
BASE_URL = "https://api.siliconflow.cn/v1"
MODEL_NAME = "Qwen/Qwen2-VL-72B-Instruct"

DATA_DIR = "../data/full_page_book"
IMG_DIR = os.path.join(DATA_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)
MAX_WORKERS = 1

st.set_page_config(page_title="MathMaster Edu", page_icon="✏️", layout="wide")

def compress_image(image_file):
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
    compressed = compress_image(image_file)
    return base64.b64encode(compressed.getvalue()).decode('utf-8')

def generate_word_exam(questions, exam_title="错题复习试卷"):
    doc = Document()
    heading = doc.add_heading(exam_title, 0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"生成时间: {time.strftime('%Y-%m-%d %H:%M')}")
    doc.add_paragraph("-" * 30)
    
    for idx, q in enumerate(questions, 1):
        p = doc.add_paragraph()
        run = p.add_run(f"【第 {idx} 题】 (ID: {q['id']})")
        run.bold = True
        run.font.size = Pt(12)
        
        if os.path.exists(q['image_path']):
            try:
                doc.add_picture(q['image_path'], width=Inches(4.5))
            except:
                doc.add_paragraph("[图片加载失败]")
        
        doc.add_paragraph("\n" * 3)
        doc.add_paragraph("_" * 40)
        
    doc.add_page_break()
    doc.add_heading("参考解析与答案", level=1)
    
    for idx, q in enumerate(questions, 1):
        p = doc.add_paragraph()
        run = p.add_run(f"【第 {idx} 题解析】")
        run.bold = True
        clean_content = q['ai_content'].replace('#', '').replace('*', '')
        doc.add_paragraph(clean_content)
        doc.add_paragraph("-" * 20)

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

def process_single_file(client, file_obj, user_tags, hint, user_id, ctx):
    if ctx: add_script_run_ctx(threading.current_thread(), ctx)
    time.sleep(1) 
    fname = file_obj.name
    try:
        img_b64 = encode_image(file_obj)
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
        
        ai_content = "AI生成失败"
        final_tags = user_tags
        
        for _ in range(3):
            try:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}, {"type": "text", "text": prompt}]}
                    ],
                    temperature=0.2, 
                )
                ai_content = response.choices[0].message.content
                match = re.search(r"## 🏷️ 标签[:：]?\s*(.*)", ai_content, re.DOTALL)
                if match:
                    ai_extracted_tags = match.group(1).strip()
                    ai_extracted_tags = ai_extracted_tags.replace("。", "").replace(".", "").strip()
                    if ai_extracted_tags:
                        final_tags = f"{user_tags}, {ai_extracted_tags}"
                        tag_list = [t.strip() for t in final_tags.replace("，", ",").split(",") if t.strip()]
                        final_tags = ", ".join(list(set(tag_list)))
                break
            except Exception as e:
                print(f"AI Error: {e}")
                time.sleep(2)

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
        return False, fname, str(e), ""

# ================= 3. 页面逻辑 (View & Controller) =================

def show_login_page():
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    
    with col2:
        st.markdown('<div class="cream-card">', unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center;'>✨ MathMaster</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #B2BEC3;'>让数学学习变得像呼吸一样简单</p>", unsafe_allow_html=True)
        st.divider()
        
        with st.form("login_form"):
            username = st.text_input("账号", placeholder="Student ID")
            password = st.text_input("密码", type="password", placeholder="Password")
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("🎈 登录系统", use_container_width=True)
            
            if submitted:
                db = DBManager()
                user = db.login(username, password)
                if user:
                    st.session_state['user_info'] = {'id': user[0], 'username': username, 'role': user[1]}
                    st.success("欢迎回来~")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("哎呀，账号或密码不对哦")
        st.markdown('</div>', unsafe_allow_html=True)

def show_main_page():
    load_css()
    user = st.session_state['user_info']
    
    default_index = 0
    if st.session_state.get('navigate_to') == '错题本':
        default_index = 1
        st.session_state['navigate_to'] = None 
    
    with st.sidebar:
        st.markdown(f"""
        <div style="text-align: center; padding: 20px;">
            <div style="background: #FFEAA7; width: 60px; height: 60px; border-radius: 50%; line-height: 60px; font-size: 30px; margin: 0 auto;">🦁</div>
            <h3 style="margin-top: 10px;">{user['username']}</h3>
            <p style="color: #B2BEC3; font-size: 12px;">{user['role'].upper()}</p>
        </div>
        """, unsafe_allow_html=True)
        
        menu_item = sac.menu([
            sac.MenuItem('学习中心', icon='book-half'),
            sac.MenuItem('错题本', icon='journal-bookmark-fill'),
            sac.MenuItem('设置', icon='gear-fill', type='group', children=[
                sac.MenuItem('退出登录', icon='box-arrow-right'),
            ]),
        ], index=default_index, format_func='title', color='orange', variant='light', open_all=True)

    if menu_item == '退出登录':
        st.session_state['user_info'] = None
        st.rerun()

    elif menu_item == '学习中心':
        col_hello, col_date = st.columns([3, 1])
        with col_hello:
            st.title(f"早安, {user['username']}! ☀️")
            st.caption("今天也是充满希望的一天，准备好攻克难题了吗？")
        
        st.markdown('<div class="cream-card">', unsafe_allow_html=True)
        col1, col2 = st.columns([2, 1])
        with col1:
            uploaded_files = st.file_uploader("📥 上传作业图片", accept_multiple_files=True, type=['jpg','png'])
        with col2:
            tags = st.text_input("🏷️ 本次标签", value="期末复习")
            hint = st.text_input("💡 小提示", placeholder="哪里不懂点哪里...")
            
        if uploaded_files:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 开始魔法解析", type="primary", use_container_width=True):
                client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
                ctx = get_script_run_ctx()
                progress = st.progress(0)
                status = st.status("🔮 AI 老师正在思考...", expanded=True)
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = []
                    for f in uploaded_files:
                        futures.append(executor.submit(process_single_file, client, f, tags, hint, user['id'], ctx))
                    
                    completed = 0
                    for future in concurrent.futures.as_completed(futures):
                        ok, fname, content, path = future.result()
                        completed += 1
                        progress.progress(completed / len(uploaded_files))
                        if ok:
                            status.write(f"✅ {fname} 完成")
                            with st.expander(f"📖 查看解析: {fname}"):
                                st.markdown('<div class="cream-card" style="background-color: #F8F9FA;">', unsafe_allow_html=True)
                                col_img, col_txt = st.columns([1, 2])
                                with col_img: st.image(path, use_column_width=True)
                                with col_txt: st.markdown(content)
                                st.markdown('</div>', unsafe_allow_html=True)
                        else:
                            status.error(f"❌ {fname} 失败")
                status.update(label="🎉 解析完成！已存入错题本", state="complete")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("### 📊 学习状态分析")
        
        db = DBManager()
        all_history = db.get_history(user['id'], user['role'])
        
        if not all_history:
            st.info("👋 还没有错题数据哦，快去上传第一道题吧！")
        else:
            from collections import Counter
            all_tags = []
            for item in all_history:
                tags = item['tags'].replace('，', ',').split(',')
                for t in tags:
                    t = t.strip()
                    if t: all_tags.append(t)
            
            tag_counts = Counter(all_tags)
            top_tags = tag_counts.most_common(5)
            
            c_chart, c_buttons = st.columns([1.5, 2])
            
            with c_chart:
                pie_data = [{"value": count, "name": tag} for tag, count in top_tags]
                options = {
                    "tooltip": {"trigger": "item"},
                    "legend": {"top": "5%", "left": "center"},
                    "series": [{
                        "name": "错题分布",
                        "type": "pie",
                        "radius": ["40%", "70%"],
                        "avoidLabelOverlap": False,
                        "itemStyle": {"borderRadius": 10, "borderColor": '#fff', "borderWidth": 2},
                        "label": {"show": False, "position": "center"},
                        "emphasis": {"label": {"show": True, "fontSize": "20", "fontWeight": "bold"}},
                        "labelLine": {"show": False},
                        "data": pie_data
                    }],
                    "color": ['#FF9A9E', '#a18cd1', '#fad0c4', '#84fab0', '#fccb90']
                }
                st_echarts(options=options, height="300px")
                
            with c_buttons:
                st.caption("🔥 你的高频错题点 (点击直达复习)")
                cols = st.columns(3)
                for idx, (tag_name, count) in enumerate(top_tags):
                    col = cols[idx % 3]
                    with col:
                        if st.button(f"{tag_name}\n({count})", key=f"btn_{tag_name}", use_container_width=True):
                            st.session_state['search_query'] = tag_name
                            st.session_state['navigate_to'] = "错题本"
                            st.rerun()

    elif menu_item == '错题本':
        st.title("📒 我的错题本")
        
        default_search = ""
        if st.session_state.get('search_query'):
            default_search = st.session_state['search_query']
            st.toast(f"🔍 已自动为您筛选：{default_search}")
            st.session_state['search_query'] = None 

        st.markdown('<div class="cream-card">', unsafe_allow_html=True)
        col_s, col_r, col_ex = st.columns([3, 1, 1.5]) 
        
        with col_s: 
            search_term = st.text_input("🔍 搜索...", value=default_search, placeholder="搜标签或内容...")
        with col_r: 
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 刷新", use_container_width=True): st.rerun()
            
        db = DBManager()
        full_history = db.get_history(user['id'], user['role'])
        
        if search_term:
            history = [item for item in full_history if search_term in item['tags'] or search_term in item['ai_content']]
        else:
            history = full_history

        with col_ex:
            st.markdown("<br>", unsafe_allow_html=True)
            if history:
                file_name = f"错题复习卷_{search_term if search_term else '全部'}_{int(time.time())}.docx"
                doc_io = generate_word_exam(history, exam_title=f"MathMaster - {search_term if search_term else '综合'}复习")
                st.download_button(
                    label="📥 导出为 Word 试卷",
                    data=doc_io,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    type="primary"
                )
        st.markdown('</div>', unsafe_allow_html=True)
            
        if not history:
            sac.result(label='空空如也', description='没有找到相关题目哦~', status='empty')
        else:
            # 🟢 全选逻辑
            col_sel_all, col_batch_msg = st.columns([1, 5])
            with col_sel_all:
                def toggle_all():
                    is_selected = st.session_state.select_all_checkbox
                    for item in history:
                        st.session_state[f"chk_{item['id']}"] = is_selected

                st.checkbox("全选", key="select_all_checkbox", on_change=toggle_all)

            batch_action_placeholder = st.empty()
            st.caption(f"共找到 {len(history)} 道错题")
            
            selected_ids = []
            for item in history:
                c_check, c_content = st.columns([0.05, 0.95]) 
                with c_check:
                    st.write("") 
                    st.write("")
                    if st.checkbox("", key=f"chk_{item['id']}"):
                        selected_ids.append(item['id'])
                
                with c_content:
                    expander_title = f"🏷️ {item['tags']}   |   📅 {item['date']}   |   🆔 {item['id']}"
                    with st.expander(expander_title):
                        col_top_info, col_delete = st.columns([6, 1])
                        with col_top_info:
                            st.info(f"录入时间：{item['date']}  |  归属人：{item['username']}")
                        with col_delete:
                            if st.button("🗑️ 删除", key=f"del_{item['id']}", type="secondary", use_container_width=True):
                                if db.delete_question(item['id']):
                                    st.toast("已删除！")
                                    time.sleep(0.5)
                                    st.rerun()
                        st.divider()
                        c_img, c_content_inner = st.columns([1, 2])
                        with c_img:
                            if os.path.exists(item['image_path']):
                                st.image(item['image_path'], use_container_width=True)
                                st.caption("错题原图")
                            else:
                                st.error("❌ 图片丢失")
                        with c_content_inner:
                            tab_view, tab_edit = st.tabs(["👀 预览解析", "✏️ 修改内容"])
                            with tab_view:
                                st.markdown(f"""
                                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #eee;">
                                    {item['ai_content']}
                                </div>
                                """, unsafe_allow_html=True)
                            with tab_edit:
                                with st.form(key=f"edit_form_{item['id']}"):
                                    new_tags = st.text_input("🏷️ 标签", value=item['tags'])
                                    new_content = st.text_area("📝 解析内容", value=item['ai_content'], height=400)
                                    if st.form_submit_button("💾 保存", type="primary", use_container_width=True):
                                        if db.update_question(item['id'], new_content, new_tags):
                                            st.success("已保存！")
                                            time.sleep(0.5)
                                            st.rerun()
                                        else:
                                            st.error("保存失败")

            # 🟢 批量删除逻辑
            if selected_ids:
                with batch_action_placeholder.container():
                    st.warning(f"⚡ 已选中 {len(selected_ids)} 道题目")
                    if st.button(f"🗑️ 立即批量删除 ({len(selected_ids)})", type="primary", use_container_width=True):
                        success_count = 0
                        for qid in selected_ids:
                            if db.delete_question(qid):
                                success_count += 1
                        if success_count > 0:
                            st.success(f"成功删除了 {success_count} 道题！")
                            st.session_state.select_all_checkbox = False
                            time.sleep(1)
                            st.rerun()

# ================= 4. 程序入口 =================

if 'user_info' not in st.session_state:
    st.session_state['user_info'] = None

if st.session_state['user_info'] is None:
    load_css()
    show_login_page()
else:
    show_main_page()