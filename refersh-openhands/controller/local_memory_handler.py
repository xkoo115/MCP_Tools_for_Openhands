import json
import os
import time


class LocalMemoryHandler:
    """
    Handles all logic for reading from and writing to the persistent local memory file.
    """

    def __init__(self, filepath: str = "task_memory.json"):
        self.memory_file = filepath

    def _load_memories(self) -> list:
        """Helper to safely load memories from the file."""
        if not os.path.exists(self.memory_file):
            return []
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                memories = json.load(f)
            if not isinstance(memories, list):
                return []
            return memories
        except (json.JSONDecodeError, IOError):
            return []  # File is corrupt or unreadable, start fresh

    def save_memory(self, content_to_save: str) -> str:
        """
        Appends a new memory entry if it's not a duplicate.
        Returns a string observation for the agent.
        """
        try:
            memories = self._load_memories()

            # 检查重复
            is_duplicate = any(
                isinstance(mem, dict) and mem.get("memory") == content_to_save
                for mem in memories
            )

            if is_duplicate:
                return f"Memory already exists, skipped: {content_to_save}"

            # 追加新记忆
            new_entry = {"timestamp": time.time(), "memory": content_to_save}
            memories.append(new_entry)

            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(memories, f, ensure_ascii=False, indent=4)

            return f"Successfully appended new memory: {content_to_save}"

        except Exception as e:
            return f"Error processing SaveTaskAction: {e}"

    def recall_all_memories(self) -> str:
        """
        Recalls all memories and formats them for the agent.
        Returns a string observation for the agent.
        """
        try:
            memories = self._load_memories()
            if not memories:
                return "No memory file found or memory is empty. Nothing to recall."

            # 格式化所有记忆
            formatted_memories = "\n".join(
                [f"- (Timestamp: {mem.get('timestamp')}) {mem.get('memory')}"
                 for mem in memories if isinstance(mem, dict)]
            )
            return f"Successfully recalled all memories:\n{formatted_memories}"

        except Exception as e:
            return f"Error recalling memories: {e}"
