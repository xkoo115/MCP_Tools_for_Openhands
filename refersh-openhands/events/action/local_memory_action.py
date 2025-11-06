from dataclasses import dataclass
from .action import Action

@dataclass
class SaveTaskAction(Action):
    """
    Action to save the original task description.
    """
    task_description: str
    action: str = "save_task"

    @property
    def message(self) -> str:
        return f"Saving task to memory: {self.task_description}"

@dataclass
class RecallTaskAction(Action):
    """
    Action to recall the original task description.
    """
    action: str = "recall_task"

    @property
    def message(self) -> str:
        return "Recalling task from memory..."
