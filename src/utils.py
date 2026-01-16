"""
工具函数模块
提供 CSS 加载、文件处理等通用功能
"""
import os
import streamlit as st


def load_css(file_path: str = None) -> None:
    """
    加载并注入 CSS 样式文件
    
    Args:
        file_path: CSS 文件路径，默认为 src/assets/style.css
    """
    if file_path is None:
        # 默认路径：从当前文件位置计算
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "assets", "style.css")
    
    if not os.path.exists(file_path):
        st.warning(f"⚠️ CSS 文件未找到: {file_path}")
        return
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
        
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"❌ 加载 CSS 文件失败: {e}")


def get_user_initials(username: str) -> str:
    """
    获取用户名的首字母缩写
    
    Args:
        username: 用户名
        
    Returns:
        首字母缩写（大写）
    """
    if len(username) >= 2:
        return username[:2].upper()
    return username[0].upper() if username else "U"
