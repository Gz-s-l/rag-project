# RAG 穿搭 / 客服知识库系统（Streamlit 单机版）

基于通义千问 + Chroma 的本地知识库问答系统，支持文件上传、对话记忆、向量检索。

> **注意**：本仓库只保留原版 Streamlit 单机项目。
> 前后端分离的重构版（Vue3 + SpringBoot + FastAPI + MySQL）已拆分为独立仓库，路径 `D:\Vscode\outfit-chat`，与本仓库完全解耦，互不依赖。

---

## 目录结构

```
├── app_qa.py               # 对话问答主界面
├── app_file_uploader.py    # 知识库文件上传界面
├── config_data.py          # 配置文件（API Key、路径、模型参数）
├── rag.py                  # RAG 核心逻辑
├── knowledge_base.py       # 知识库写入与去重
├── vector_stores.py        # 向量库检索
├── file_history_store.py   # 对话历史管理
├── requirements.txt        # 依赖包
├── .env                    # 环境变量（需自行创建）
├── chroma_db/              # 向量库（自动生成）
└── md5.txt                 # 文件去重记录（自动生成）
```

## 运行

```bash
pip install -r requirements.txt

# .env 中填入 DASHSCOPE_API_KEY=你的通义千问API Key

streamlit run app_file_uploader.py   # 先构建知识库
streamlit run app_qa.py              # 再启动问答
```

## 功能

- 支持 TXT 文件上传并自动向量化
- MD5 去重，避免重复导入
- 多轮对话记忆
- 基于本地 Chroma 向量库

## 常见问题

- 报错找不到模块：检查依赖是否安装完整
- Chroma 无法写入：关闭程序后删除 `chroma_db` 再重启
- API Key 报错：检查 `.env` 是否放在项目根目录
