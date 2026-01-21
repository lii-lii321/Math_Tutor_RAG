import pymssql
import datetime
import os
import streamlit as st
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class DBManager:
    def __init__(self):
        # ================= 数据库配置 =================
        self.db_settings = {
            'server': os.getenv('DB_SERVER', 'localhost'),
            'user': os.getenv('DB_USER', 'sa'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_DATABASE', 'MathTutorDB')
        }
        
        # ================= 演示模式内存初始化 =================
        # 如果连不上数据库，我们就把题目暂时存在这里
        if 'demo_questions' not in st.session_state:
            st.session_state.demo_questions = [
                # 预置一条演示数据，让你打开历史记录不为空
                {
                    "id": 1, 
                    "username": "admin (Demo)", 
                    "ai_content": "这是一个演示题目。\n知识点：导数\n解析：这是手动添加的演示数据。", 
                    "image_path": "demo.jpg", 
                    "tags": "演示, 导数", 
                    "date": datetime.datetime.now().strftime("%Y-%m-%d")
                }
            ]

    def get_connection(self):
        return pymssql.connect(**self.db_settings)

    # 1. 登录功能（已修复，保持原样）
    def login(self, username, password):
        try:
            conn = self.get_connection()
            cursor = conn.cursor(as_dict=True)
            cursor.execute(
                "SELECT id, username, role FROM users WHERE username=%s AND password=%s",
                (username, password)
            )
            user = cursor.fetchone()
            conn.close()
            return user
        except Exception:
            # 演示模式：只要密码对就放行
            if username == "admin" and password == "123456":
                return {"id": 999, "username": "admin (Demo)", "role": "student"}
            return None

    # 2. 存题功能（新增防崩坏逻辑）
    def save_question(self, user_id, filename, ai_content, image_path, tags):
        """尝试保存：优先存库，失败则存入临时列表"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = """
                INSERT INTO Questions (UserID, Content, ImagePath, Tags, CreatedDate)
                VALUES (%s, %s, %s, %s, GETDATE())
            """
            cursor.execute(sql, (user_id, ai_content, image_path, tags))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Database unavailable, saving to Demo Memory: {e}")
            # === 演示模式：存入 session_state ===
            new_id = len(st.session_state.demo_questions) + 1
            st.session_state.demo_questions.insert(0, { # 插到最前面
                "id": new_id,
                "username": "Me",
                "ai_content": ai_content,
                "image_path": image_path, # 注意：云端并没有真实保存图片文件，但不影响文字演示
                "tags": tags,
                "date": datetime.datetime.now().strftime("%Y-%m-%d")
            })
            return True

    # 3. 删除功能（新增防崩坏逻辑）
    def delete_question(self, question_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "DELETE FROM Questions WHERE QuestionID=%s"
            cursor.execute(sql, (question_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            # === 演示模式：从内存列表删除 ===
            st.session_state.demo_questions = [
                q for q in st.session_state.demo_questions if q['id'] != question_id
            ]
            return True

    # 4. 获取历史记录（新增防崩坏逻辑）
    def get_history(self, user_id, role):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            # ... 原有的数据库查询逻辑 ...
            if role == 'admin':
                sql = """
                    SELECT q.QuestionID, u.Username, q.Content, q.ImagePath, q.Tags, q.CreatedDate
                    FROM Questions q
                    JOIN Users u ON q.UserID = u.UserID
                    ORDER BY q.CreatedDate DESC
                """
                cursor.execute(sql)
            else:
                sql = """
                    SELECT QuestionID, '我' as Username, Content, ImagePath, Tags, CreatedDate
                    FROM Questions
                    WHERE UserID=%s
                    ORDER BY CreatedDate DESC
                """
                cursor.execute(sql, (user_id,))
            
            results = []
            for row in cursor:
                results.append({
                    "id": row[0],
                    "username": row[1],
                    "ai_content": row[2],
                    "image_path": row[3],
                    "tags": row[4],
                    "date": row[5].strftime("%Y-%m-%d")
                })
            conn.close()
            return results
        except Exception:
            # === 演示模式：返回内存里的数据 ===
            return st.session_state.demo_questions

    # 5. 修改功能（新增防崩坏逻辑）
    def update_question(self, question_id, new_content, new_tags):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            sql = "UPDATE Questions SET Content=%s, Tags=%s WHERE QuestionID=%s"
            cursor.execute(sql, (new_content, new_tags, question_id))
            conn.commit()
            conn.close()
            return True
        except Exception:
            # === 演示模式：修改内存里的数据 ===
            for q in st.session_state.demo_questions:
                if q['id'] == question_id:
                    q['ai_content'] = new_content
                    q['tags'] = new_tags
                    break
            return True