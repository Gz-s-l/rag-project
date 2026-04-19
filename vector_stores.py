from langchain_chroma import Chroma
import config_data as config
from chromadb.config import Settings

class VectorStoreService(object):

    def __init__(self, embedding):
        """
        :param embedding: 嵌入模型的传入
        """
        self.embedding = embedding

        # 关键：添加客户端配置，解决 Streamlit 只读文件系统报错
        client_settings = Settings(
            persist_directory=config.persist_directory,
            allow_reset=False,
            is_persistent=True,
            anonymized_telemetry=False
        )

        self.vector_store = Chroma(
            collection_name=config.collection_name,
            embedding_function=self.embedding,
            persist_directory=config.persist_directory,
            client_settings=client_settings
        )

    def get_retriever(self):
        """返回向量检索器，方便加入chain"""
        return self.vector_store.as_retriever(search_kwargs={"k": config.top_k})
