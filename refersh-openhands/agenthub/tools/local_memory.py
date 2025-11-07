import json
from litellm import ChatCompletionToolParam, ChatCompletionToolParamFunctionChunk

# 1. 修改 SaveTaskDetailsTool
SaveTaskDetailsTool = ChatCompletionToolParam(
    type='function',
    function=ChatCompletionToolParamFunctionChunk(
        name='save_task_details',
        description='Saves the verbatim (exact) text of a task or failure to permanent local memory under a specific title.',
        parameters={
            'type': 'object',
            'properties': {
                'title': { # <-- 添加 title
                    'type': 'string',
                    'description': 'The title for the memory, in UpperCamelCase format (e.g., MyTaskDetails).',
                },
                'task_description': {
                    'type': 'string',
                    'description': 'The exact, word-for-word task or content to save.',
                },
            },
            'required': ['title', 'task_description'], # <-- 'title' 现在是必需的
        },
    ),
)

# 2. 修改 RecallTaskDetailsTool
RecallTaskDetailsTool = ChatCompletionToolParam(
    type='function',
    function=ChatCompletionToolParamFunctionChunk(
        name='recall_task_details',
        description='Retrieves memories. If no title is given, returns an outline (list) of all memory titles. If a title is given, returns the specific content for that title.',
        parameters={
            'type': 'object',
            'properties': {
                'title': { # <-- 添加 title
                    'type': 'string',
                    'description': 'The UpperCamelCase title of the memory to recall. If omitted, returns the outline.',
                }
            },
            # 'required' 列表是空的，所以 title 是可选的
        },
    ),
)
