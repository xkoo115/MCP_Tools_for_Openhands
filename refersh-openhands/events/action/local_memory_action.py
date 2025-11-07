# openhands/events/action/local_memory.py
from dataclasses import dataclass, field
from .action import Action
from typing import Optional # <-- 添加 Optional

@dataclass
class SaveTaskAction(Action):
    """
    Action to save the original task description with a title.
    """
    title: str               # <-- 1. 添加 title
    task_description: str
    action: str = "save_task"

    @property
    def message(self) -> str:
        return f"Saving task to memory with title '{self.title}'"

@dataclass
class RecallTaskAction(Action):
    """
    Action to recall task(s) from memory.
    If title is provided, recalls specific task.
    If title is None, recalls the outline (all titles).
    """
    # 2. 修改为 Optional[str]
    title: Optional[str] = field(default=None)
    action: str = "recall_task"

    @property
    def message(self) -> str:
        if self.title:
            return f"Recalling specific task '{self.title}' from memory..."
        else:
            return "Recalling memory outline (all titles)..."
