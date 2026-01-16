"""
Settings 页面视图
显示账户信息和设置选项
"""
import streamlit as st


def render_settings_page(user):
    """渲染 Settings 页面"""
    st.markdown("### ⚙️ Settings")
    
    st.markdown("""
    <div class="dashboard-card">
        <h3 style="color: #333333;">Account Information</h3>
        <p style="color: #333333;"><strong>Username:</strong> {}</p>
        <p style="color: #333333;"><strong>Role:</strong> {}</p>
        <p style="color: #333333;"><strong>User ID:</strong> {}</p>
    </div>
    """.format(user['username'], user['role'], user['id']), unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("🚪 Logout", type="primary", use_container_width=True):
        st.session_state['user_info'] = None
        st.rerun()
