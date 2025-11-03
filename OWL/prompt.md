# Agent Failure Analysis for TheAgentCompany Benchmark

Your primary objective is to analyze a set of agent behavior logs from the TheAgentCompany benchmark to identify the root causes of task failures (i.e., why points were lost) and propose concrete solutions.

## Input Data

All the information you need is located in a single folder: `messages`.

Inside this folder, you will find multiple `.txt` files. Each file represents a single task, and its filename **is the task name**.

I have pre-processed each file to contain all necessary context at the very beginning. When you open any `[task_name].txt` file, you will find the following information, in this order:

1.  **Task Description:** The full content from the original `task.md`.
2.  **Scoring Criteria:** The full content from the original `checkpoints.md`.
3.  **Scoring Results:** The full JSON content from the `eval_[task_name]-image.json` file. This provides a detailed breakdown of all checkpoint scores, allowing you to see exactly where the agent lost points.
4.  **Agent Log:** Following this header is the raw agent behavior log, containing the agent's internal "Message" and the "Content" from its LLM responses.

## Your Task

You must process each `.txt` file in that folder one by one. For each task, you must:

1.  **Analyze Failure:** Read the task description, criteria, and scoring results (`eval.json`) to understand the goal and identify exactly where the agent failed.
2.  **Identify Root Cause:** Correlate the failure points from the `eval.json` with the agent's behavior in the "Agent Log" to determine the "Problem Cause".
3.  **Propose Solution:** Based on the cause, propose a "Solution".

## Constraints & Guidelines

* **Uncertainty:** If you cannot determine a definitive root cause, you may provide a well-reasoned hypothesis, but you **must** append `(uncertain)` to your "Problem Cause" analysis.
* **Solution Categories:** When you propose a "Solution," you **must** categorize it using one or more of the following frameworks:
    * **Prompting/Guidelines:** Modifying the agent's system prompt, task-specific templates, or operational instructions.
    * **Memory:** Improving short-term (in-task) or long-term (cross-task) memory. (e.g., remembering past failures within the task, sharing successful strategies from other tasks).
    * **Orchestration:** Modifying the flow of tools or agents. (e.g., automating a sequence, creating a new orchestration, or reusing a successful plan for complex fixes).

## Output Format

Your final output must be a single Markdown table. You will analyze each task file and incrementally add a new row to this table as you complete each analysis.

The table must have exactly these four columns:

| No. | Task Name | Problem Cause | Solution |
| :-- | :-- | :-- | :-- |
| 1. | [Task 1 Name] | [Your analysis of the problem] | **[Category]:** [Your proposed solution] |
| 2. | [Task 2 Name] | [Your analysis of the problem] | **[Category]:** [Your proposed solution] |
| ... | ... | ... | ... |

Do you understand the instructions? Please begin the analysis.