import pymssql
import datetime
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class DBManager:
    def __init__(self):
        # ================= 数据库配置 =================
        # 从环境变量读取配置，确保安全性
        self.db_settings = {
            'server': os.getenv('DB_SERVER', '.'),
            'user': os.getenv('DB_USER', 'sa'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_DATABASE', 'MathTutorDB')
        }
        
        # 检查必要的配置是否存在
        if not self.db_settings['password']:
            raise ValueError("❌ 数据库密码未配置！请在 .env 文件中设置 DB_PASSWORD")

    def get_connection(self):
        return pymssql.connect(**self.db_settings)

    def login(self, username, password):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            sql = "SELECT UserID, Role FROM Users WHERE Username=%s AND Password=%s"
            cursor.execute(sql, (username, password))
            return cursor.fetchone()
        finally:
            conn.close()

    def save_question(self, user_id, filename, ai_content, image_path, tags):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            sql = """
                INSERT INTO Questions (UserID, Content, ImagePath, Tags, CreatedDate)
                VALUES (%s, %s, %s, %s, GETDATE())
            """
            cursor.execute(sql, (user_id, ai_content, image_path, tags))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 保存失败: {e}")
            return False
        finally:
            conn.close()

    # 🟢 新增功能：删题
    def delete_question(self, question_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 只有知道 ID 才能删
            sql = "DELETE FROM Questions WHERE QuestionID=%s"
            cursor.execute(sql, (question_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 删除失败: {e}")
            return False
        finally:
            conn.close()

    def get_history(self, user_id, role):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
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
            return results
        finally:
            conn.close()
    # 🟢 新增功能：修改错题
    def update_question(self, question_id, new_content, new_tags):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 更新 Content 和 Tags 两个字段
            sql = "UPDATE Questions SET Content=%s, Tags=%s WHERE QuestionID=%s"
            cursor.execute(sql, (new_content, new_tags, question_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 修改失败: {e}")
            return False
        finally:
            conn.close()