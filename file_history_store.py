import os
import json
from typing import Sequence
from langchain_core.messages import (
    BaseMessage,
    message_to_dict,
    messages_from_dict,
)
from langchain_core.chat_history import BaseChatMessageHistory

def get_history(session_id):
    return FileChatMessageHistory(session_id, storage_path="./chat_history")


class FileChatMessageHistory(BaseChatMessageHistory):
    """
    基于本地 JSON 文件的会话历史存储类
    继承自 BaseChatMessageHistory，实现了持久化到磁盘的对话记忆
    """

    def __init__(self, session_id: str, storage_path: str):
        """
        初始化文件会话历史
        :param session_id: 会话唯一标识（用于区分不同用户/对话）
        :param storage_path: 历史文件存放的文件夹路径
        """
        # 保存会话ID
        self.session_id = session_id
        # 保存文件存储的根目录
        self.storage_path = storage_path
        # 拼接出完整的文件路径：存储路径 + 会话ID
        self.file_path = os.path.join(self.storage_path, self.session_id)
        # 确保文件所在的文件夹存在（不存在则自动创建）
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        """
        批量添加消息到历史记录（必须实现的抽象方法）
        :param messages: 要添加的消息序列（list/tuple 等可迭代对象）
        """
        # 先获取当前已有的所有消息（从文件中读取）
        all_messages = list(self.messages)
        # 将新消息合并到已有消息列表中
        all_messages.extend(messages)

        # 将所有消息对象转换为字典格式（方便 JSON 序列化）
        new_messages = [message_to_dict(message) for message in all_messages]

        # 将转换后的字典写入 JSON 文件（覆盖原有内容）
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(new_messages, f, ensure_ascii=False, indent=2)

    @property
    def messages(self) -> list[BaseMessage]:
        """
        获取当前会话的所有历史消息（必须实现的抽象属性）
        使用 @property 装饰器，让这个方法像成员变量一样被访问
        :return: 消息对象列表
        """
        try:
            # 尝试打开并读取历史文件
            with open(self.file_path, "r", encoding="utf-8") as f:
                # 加载 JSON 数据，得到 list[字典]
                messages_data = json.load(f)
            # 将字典格式还原为 LangChain 消息对象列表
            return messages_from_dict(messages_data)
        except FileNotFoundError:
            # 如果文件不存在（第一次使用），返回空列表
            return []

    def clear(self) -> None:
        """
        清空当前会话的所有历史消息（必须实现的抽象方法）
        """
        # 打开文件并写入空列表，实现清空
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump([], f)