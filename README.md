# 🦁 MathMaster Edu - 基于视觉大模型的智能错题教研系统

> **让错题管理变得像呼吸一样简单。** > *A Smart Wrong Question Notebook System powered by Vision LLM & RAG.*

---

## 📖 项目简介 (Introduction)

**MathMaster Edu** 是一个专为学生和教育工作者设计的智能错题管理平台。它彻底改变了传统的手抄错题模式，利用 **Qwen2-VL-72B (通义千问视觉大模型)** 的强大能力，实现“拍照即录入”。

系统不仅能自动识别手写数学作业、生成详细解析，还能通过 RAG 技术对错题进行 **智能打标签** 和 **知识点归类**。配合可视化的学情分析看板和一键导出试卷功能，帮助用户高效通过“费曼学习法”攻克薄弱环节。

## ✨ 核心功能 (Key Features)

### 1. 📸 AI 魔法录入 (Smart Entry)
* **视觉识别**：支持上传手写作业/试卷图片，精准识别数学公式与手写痕迹。
* **智能解析**：自动生成【考点分析】、【详细步骤】和【正确答案】。
* **自动标签**：AI 自动分析题目考点（如“几何”、“行程问题”），并与用户标签智能合并。

### 2. 📒 交互式错题本 (Interactive Notebook)
* **增删改查**：支持对错题内容的二次编辑与修正。
* **批量管理**：支持 **全选/多选** 模式，一键批量删除过期错题，极大提升整理效率。
* **折叠式设计**：列表页采用紧凑折叠卡片，信息密度高，浏览体验流畅。

### 3. 📊 学情数据驾驶舱 (Data Dashboard)
* **可视化分析**：首页集成 ECharts 动态环形图，实时展示错题知识点分布。
* **薄弱点直达**：点击图表色块即可直接跳转筛选出对应知识点的所有错题。

### 4. 🖨️ 智能组卷导出 (Exam Generator)
* **Word 导出**：支持根据搜索条件（或全部错题）一键生成 `.docx` 格式的复习试卷。
* **排版优化**：自动保留题目原图，并在题目下方预留答题空白区，方便打印重练。

---

## 🛠️ 技术栈 (Tech Stack)

* **前端框架**: [Streamlit](https://streamlit.io/)
* **UI 组件库**: Streamlit-Antd-Components (SAC), Streamlit-ECharts
* **后端逻辑**: Python 3.10+
* **大模型 API**: Qwen2-VL-72B-Instruct (via SiliconFlow)
* **数据库**: SQLite (轻量级本地存储)
* **文档处理**: Python-Docx (用于生成 Word 试卷)
* **图像处理**: Pillow

---

## 🚀 快速开始 (Quick Start)

### 1. 克隆项目
```bash
git clone [https://github.com/lii-lii321/Math_Tutor_RAG.git](https://github.com/lii-lii321/Math_Tutor_RAG.git)
cd Math_Tutor_RAG