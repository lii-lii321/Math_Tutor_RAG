"""
Dashboard 页面视图
显示学习统计、图表和热门话题
"""
import streamlit as st
from db_manager import DBManager
from streamlit_echarts import st_echarts
from collections import Counter
from utils import get_user_initials


def render_dashboard_page(user):
    """渲染 Dashboard 主页面"""
    # 左侧主内容区 (75%)
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # 欢迎区域
        st.markdown(f"""
        <div class="welcome-section">
            <h1 style="margin: 0; font-size: 2.5rem; font-weight: 700; color: #333333;">Welcome back, {user['username']}!</h1>
            <p style="color: #6b7280; font-size: 1.1rem; margin-top: 0.5rem;">Ready to master math today? 📚</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 功能卡片区域
        db = DBManager()
        all_history = db.get_history(user['id'], user['role'])
        
        # 统计数据
        total_questions = len(all_history)
        all_tags = []
        for item in all_history:
            for t in item['tags'].replace('，', ',').split(','):
                if t.strip(): 
                    all_tags.append(t.strip())
        unique_topics = len(set(all_tags))
        top_tags = Counter(all_tags).most_common(5) if all_tags else []
        
        # 创建卡片 - 使用 Morandi 配色
        col_card1, col_card2, col_card3, col_card4 = st.columns(4)
        
        with col_card1:
            st.markdown(f"""
            <div class="dashboard-card card-pink" style="min-height: 180px; display: flex; flex-direction: column; justify-content: center;">
                <div style="font-size: 3rem; font-weight: 700; margin-bottom: 0.5rem; color: #333333;">{total_questions}</div>
                <div style="font-size: 1rem; color: #333333; opacity: 0.8;">Total Questions</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_card2:
            st.markdown(f"""
            <div class="dashboard-card card-purple" style="min-height: 180px; display: flex; flex-direction: column; justify-content: center;">
                <div style="font-size: 3rem; font-weight: 700; margin-bottom: 0.5rem; color: #333333;">{unique_topics}</div>
                <div style="font-size: 1rem; color: #333333; opacity: 0.8;">Topics Covered</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_card3:
            st.markdown(f"""
            <div class="dashboard-card card-cyan" style="min-height: 180px; display: flex; flex-direction: column; justify-content: center;">
                <div style="font-size: 3rem; font-weight: 700; margin-bottom: 0.5rem; color: #333333;">{len(top_tags)}</div>
                <div style="font-size: 1rem; color: #333333; opacity: 0.8;">Hot Topics</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_card4:
            st.markdown(f"""
            <div class="dashboard-card card-orange" style="min-height: 180px; display: flex; flex-direction: column; justify-content: center;">
                <div style="font-size: 3rem; font-weight: 700; margin-bottom: 0.5rem; color: #333333;">⭐</div>
                <div style="font-size: 1rem; color: #333333; opacity: 0.8;">Keep Learning</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # 学习分析图表
        if top_tags:
            col_chart, col_list = st.columns([2, 1])
            
            with col_chart:
                st.markdown("### 📊 Learning Analytics")
                st_echarts(
                    options={
                        "tooltip": {"trigger": "item"},
                        "legend": {
                            "bottom": "5%",
                            "left": "center",
                            "itemGap": 15
                        },
                        "series": [{
                            "name": "Topic Distribution",
                            "type": "pie",
                            "radius": ["40%", "70%"],
                            "avoidLabelOverlap": True,
                            "itemStyle": {
                                "borderRadius": 10,
                                "borderColor": "#fff",
                                "borderWidth": 2
                            },
                            "label": {
                                "show": True,
                                "position": "outside",
                                "formatter": "{b}: {c}"
                            },
                            "data": [{"value": v, "name": k} for k, v in top_tags]
                        }]
                    },
                    height="400px"
                )
            
            with col_list:
                st.markdown("### 🔥 Hot Topics")
                for idx, (topic, count) in enumerate(top_tags, 1):
                    st.markdown(f"""
                    <div style="background: white; padding: 1rem; border-radius: 12px; margin-bottom: 0.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: #333333;">#{idx} {topic}</span>
                            <span style="color: #a78bfa; font-weight: 700;">{count}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    
    # 右侧信息栏 (25%)
    with col2:
        # 用户头像
        username_initials = get_user_initials(user['username'])
        st.markdown(f"""
        <div class="profile-section">
            <div style="text-align: center;">
                <div class="user-avatar" style="margin: 0 auto 1rem;">{username_initials}</div>
                <p style="font-weight: 600; margin: 0; color: #333333;">{user['username']}</p>
                <p style="color: #6b7280; font-size: 0.9rem; margin: 0;">{user['role'].upper()}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Activity 图表
        st.markdown("""
        <div class="activity-section">
            <h3 style="color: #333333; margin-bottom: 1rem;">Activity</h3>
            <p style="color: #6b7280; font-size: 0.9rem;">Your learning progress will be displayed here.</p>
        </div>
        """, unsafe_allow_html=True)
