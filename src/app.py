"""
MathMaster Edu - 主程序入口
负责配置加载、样式注入、路由分发
"""
import streamlit as st
import os
from dotenv import load_dotenv
import streamlit_antd_components as sac
import google.generativeai as genai

# 导入工具函数和视图
from utils import load_css
from db_manager import DBManager
from views.dashboard import render_dashboard_page
from views.tutor import render_tutor_page
from views.progress import render_progress_page
from views.settings import render_settings_page

# ================= 1. 网络代理配置 =================
http_proxy = os.getenv('HTTP_PROXY', '')
https_proxy = os.getenv('HTTPS_PROXY', '')
if http_proxy:
    os.environ["HTTP_PROXY"] = http_proxy
if https_proxy:
    os.environ["HTTPS_PROXY"] = https_proxy

# ================= 2. 全局配置 =================
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 初始化 AI 模型
model = None
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-flash-latest')
    except Exception as e:
        print(f"⚠️ AI 模型初始化失败: {e}")

# ================= 3. 页面配置 =================
st.set_page_config(
    page_title="MathMaster Edu", 
    page_icon="✏️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 4. 加载样式 =================
load_css()

# ================= 5. 登录页面 =================
def show_login_page():
    """显示登录页面"""
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div class="dashboard-card" style="text-align: center;">
            <h1 style="font-size: 3rem; margin-bottom: 1rem; color: #333333;">✨ MathMaster</h1>
            <p style="color: #6b7280; font-size: 1.2rem;">Make math learning as easy as breathing</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Student ID")
            password = st.text_input("Password", type="password", placeholder="Password")
            if st.form_submit_button("🎈 Login", use_container_width=True):
                db = DBManager()
                user = db.login(username, password)
                if user:
                    st.session_state['user_info'] = {
                        'id': user[0], 
                        'username': username, 
                        'role': user[1]
                    }
                    st.rerun()
                else:
                    st.error("Invalid username or password")

# ================= 6. 主页面 =================
def show_main_page():
    """显示主页面"""
    user = st.session_state['user_info']
    
    # 初始化当前页面
    if 'current_page' not in st.session_state:
        st.session_state['current_page'] = 'Dashboard'
    
    # 侧边栏导航
    with st.sidebar:
        # 用户信息
        from utils import get_user_initials
        username_initials = get_user_initials(user['username'])
        st.markdown(f"""
        <div style="text-align: center; padding: 1.5rem 0;">
            <div class="user-avatar" style="margin: 0 auto 1rem;">{username_initials}</div>
            <h3 style="margin: 0; color: #333333;">{user['username']}</h3>
            <p style="color: #6b7280; font-size: 0.9rem; margin: 0;">{user['role'].upper()}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<hr style='margin: 1rem 0; border: none; border-top: 1px solid #e5e7eb;'>", unsafe_allow_html=True)
        
        # 导航菜单
        menu_options = ['Dashboard', 'Math Tutor', 'My Progress', 'Settings']
        current_index = menu_options.index(st.session_state.get('current_page', 'Dashboard')) if st.session_state.get('current_page', 'Dashboard') in menu_options else 0
        
        menu_item = sac.menu([
            sac.MenuItem('Dashboard', icon='house'),
            sac.MenuItem('Math Tutor', icon='robot'),
            sac.MenuItem('My Progress', icon='graph-up'),
            sac.MenuItem('Settings', icon='gear'),
        ], index=current_index, format_func='title', color='purple', variant='light', open_all=True, key='main_nav')
        
        # 更新当前页面
        if menu_item and menu_item != st.session_state.get('current_page'):
            st.session_state['current_page'] = menu_item
            st.rerun()
        
        st.markdown("<hr style='margin: 1rem 0; border: none; border-top: 1px solid #e5e7eb;'>", unsafe_allow_html=True)
        
        # 退出登录按钮
        if st.button("🚪 Logout", use_container_width=True, type="secondary"):
            st.session_state['user_info'] = None
            st.rerun()
    
    # 根据菜单选择渲染不同页面
    current_page = st.session_state.get('current_page', 'Dashboard')
    
    if current_page == 'Dashboard':
        render_dashboard_page(user)
    elif current_page == 'Math Tutor':
        render_tutor_page(user, model)
    elif current_page == 'My Progress':
        render_progress_page(user)
    elif current_page == 'Settings':
        render_settings_page(user)

# ================= 7. 主程序入口 =================
if __name__ == "__main__":
    if 'user_info' not in st.session_state:
        st.session_state['user_info'] = None

    if st.session_state['user_info'] is None:
        show_login_page()
    else:
        show_main_page()
