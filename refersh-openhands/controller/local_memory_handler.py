# openhands/controller/local_memory.py
import json
import os
import time


class LocalMemoryHandler:

    def __init__(self, filepath: str = "task_local_memory.json"):
        self.memory_file = filepath

    def _load_memories(self) -> dict:  # <-- 1. 返回类型改为 dict
        """Helper to safely load memories from the file."""
        if not os.path.exists(self.memory_file):
            return {}  # 文件不存在，返回空字典

        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                memories = json.load(f)

            # 校验: 检查文件内容是否为字典
            if not isinstance(memories, dict):
                return {}  # 文件已损坏或格式不正确，返回空字典

            return memories
        except (json.JSONDecodeError, IOError):
            return {}  # 文件为空或已损坏，返回空字典

    # 2. 修改 save_memory 的签名
    def save_memory(self, title: str, content_to_save: str) -> str:
        """
        Saves a new memory entry using the title as the key.
        Returns a string observation for the agent.
        """
        try:
            memories = self._load_memories()

            # 检查重复 (现在是检查 key)
            if title in memories:
                return f"Memory title '{title}' already exists, skipped."

            # 添加新记忆 (使用 title 作为 key)
            new_entry = {"timestamp": time.time(), "content": content_to_save}
            memories[title] = new_entry

            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(memories, f, ensure_ascii=False, indent=4)

            return f"Successfully saved memory with title: {title}"

        except Exception as e:
            return f"Error processing SaveTaskAction: {e}"

    # 3. 修改 recall_all_memories 为 recall_memory
    def recall_memory(self, title: str | None) -> str:
        """
        Recalls memories.
        If title is None, returns the outline (all titles).
        If title is provided, returns the specific content.
        """
        try:
            memories = self._load_memories()
            if not memories:
                return "No memory file found or memory is empty. Nothing to recall."

            # 4. 实现新的 "大纲" 或 "详情" 逻辑
            if title is None:
                # ===================
                # 逻辑: 返回大纲
                # ===================
                all_titles = list(memories.keys())
                if not all_titles:
                    return "Memory is empty. No titles to recall."

                formatted_outline = "\n".join([f"- {t}" for t in all_titles])
                return f"Successfully recalled memory outline:\n{formatted_outline}"

            else:
                # ===================
                # 逻辑: 返回详情
                # ===================
                if title not in memories:
                    return f"Error: Memory with title '{title}' not found."

                # 返回特定标题的内容
                entry = memories[title]
                content = entry.get('content', 'No content found.')
                ts = entry.get('timestamp', 'N/A')
                return f"Successfully recalled memory '{title}' (Timestamp: {ts}):\n{content}"

        except Exception as e:
            return f"Error recalling memories: {e}"
