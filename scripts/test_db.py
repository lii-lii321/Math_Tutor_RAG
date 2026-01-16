import pymssql
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_connection():
    print("🔄 正在尝试连接 SQL Server...")
    
    # ================= 从环境变量读取数据库配置 =================
    DB_SETTINGS = {
        'server': os.getenv('DB_SERVER', '.'),           # 本机地址，通常是 . 或者 localhost
        'user': os.getenv('DB_USER', 'sa'),            # 默认管理员账号
        'password': os.getenv('DB_PASSWORD', ''),  # 从环境变量读取
        'database': os.getenv('DB_DATABASE', 'MathTutorDB')
    }
    
    if not DB_SETTINGS['password']:
        print("❌ 错误：数据库密码未配置！")
        print("👉 请在 .env 文件中设置 DB_PASSWORD")
        return
    # ===============================================

    try:
        # 1. 发起连接
        conn = pymssql.connect(**DB_SETTINGS)
        cursor = conn.cursor()
        
        # 2. 查查看刚才有没有插入 'admin' 用户
        cursor.execute("SELECT Username, Role FROM Users")
        
        print("\n✅ 连接成功！读取到以下用户：")
        print("-" * 30)
        
        # 3. 打印结果
        for row in cursor:
            print(f"👤 用户名: {row[0]} | 身份: {row[1]}")
            
        print("-" * 30)
        conn.close()
        
    except Exception as e:
        print("\n❌ 连接失败！原因如下：")
        print(e)
        print("\n💡 提示：")
        print("1. 检查密码对不对？")
        print("2. 如果你平时是用 'Windows 身份验证' 登录的，请告诉我，代码写法不一样。")

if __name__ == "__main__":
    test_connection()