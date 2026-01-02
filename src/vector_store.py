import chromadb
from sentence_transformers import SentenceTransformer
from PIL import Image
import os

# ================= 模型加载区域 =================
print("正在初始化视觉模型 (CLIP)...")
# 🟢 回退到最稳定的 CLIP 模型
# 这个模型兼容性最好，不需要 trust_remote_code，也不会报错
model = SentenceTransformer('clip-ViT-B-32')
# ===============================================

class MathKnowledgeBase:
    def __init__(self):
        # 数据库路径
        # 🟢 我们改回用 clip 命名的文件夹，方便区分
        self.db_path = "./chroma_db_clip" 
        self.client = chromadb.PersistentClient(path=self.db_path)
        
        # 创建集合
        self.collection = self.client.get_or_create_collection(
            name="math_questions_visual",
            metadata={"hnsw:space": "cosine"}
        )

    def _get_image_embedding(self, image_path):
        """
        CLIP 模型非常简单，直接传图片就行，不需要前缀
        """
        try:
            img = Image.open(image_path)
            # CLIP 只要图片，不要任何花里胡哨的前缀
            embedding = model.encode(img)
            return embedding.tolist()
        except Exception as e:
            print(f"❌ 向量化失败: {e}")
            return None

    def add_question(self, text_content, image_path, tags="", source="User"):
        if not os.path.exists(image_path):
            return False

        # 计算特征
        visual_vector = self._get_image_embedding(image_path)
        
        if visual_vector:
            doc_id = str(self.collection.count() + 1)
            self.collection.add(
                documents=[text_content],
                embeddings=[visual_vector], 
                metadatas=[{
                    "source": source, 
                    "tags": tags, 
                    "image_path": image_path
                }],
                ids=[doc_id]
            )
            return True
        return False

    def search_similar_image(self, query_image_path, top_k=1):
        # 搜索
        query_vector = self._get_image_embedding(query_image_path)
        
        if query_vector:
            results = self.collection.query(
                query_embeddings=[query_vector], 
                n_results=top_k
            )
            return results
        return None