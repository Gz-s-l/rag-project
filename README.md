# RAG 智能客服知识库系统

基于通义千问 + Chroma 实现的本地知识库问答系统，支持文件上传、对话记忆、向量检索。

## 项目结构
├── app_qa.py               # 对话问答主界面
├── app_file_uploader.py    # 知识库文件上传界面
├── config_data.py          # 配置文件（API Key、路径、模型参数）
├── rag.py                  # RAG 核心逻辑
├── knowledge_base.py       # 知识库写入与去重
├── vector_stores.py        # 向量库检索
├── file_history_store.py   # 对话历史管理
├── .env                    # 环境变量（需自行创建）
├── requirements.txt        # 依赖包
├── chroma_db/              # 向量库（自动生成）
└── md5.txt                 # 文件去重记录（自动生成）

## 环境配置
1. 安装依赖
```bash
pip install -r requirements.txt
2. 创建  .env  文件，填入：
DASHSCOPE_API_KEY=你的通义千问API Key
运行方式
 
启动文件上传（构建知识库）
streamlit run app_file_uploader.py
启动智能问答
streamlit run app_qa.py
功能说明
 
- 支持 TXT 文件上传并自动向量化

- 自动 MD5 去重，避免重复导入

- 支持多轮对话记忆

- 基于本地 Chroma 向量库，数据不上传云端
 
常见问题
 
- 报错找不到模块：检查依赖是否安装完整

- Chroma 无法写入：关闭程序后删除 chroma_db 再重启

- API Key 报错：检查 .env 文件是否放在项目根目录