from dotenv import load_dotenv
import os

from requests import session

load_dotenv()
DASHSCOPE_API_KEY=os.getenv("DASHSCOPE_API_KEY")

# 1. 拿到 config.py 文件所在的真实目录（固定不变）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 所有路径都基于这个目录拼接
md5_path = os.path.join(BASE_DIR, "md5.txt")
persist_directory = os.path.join(BASE_DIR, "chroma_db")

# Chroma
collection_name="rag"

# spliter
chunk_size = 1000
chunk_overlap = 100
separators = ["\n\n","\n",".",",","?","!","。","，","！","？"," ",""]

max_split_char_number =1000       #文本分割阈值

#
top_k=2

embedding_model_name = "text-embedding-v4"
chat_model_name ="qwen3-max"

session_config ={
    "configurable":{
        "session_id":"uesr_001",
    }
}