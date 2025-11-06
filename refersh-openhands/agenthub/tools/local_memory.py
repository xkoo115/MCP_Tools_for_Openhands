import json
from litellm import ChatCompletionToolParam, ChatCompletionToolParamFunctionChunk

# 定义任务保存工具的 "说明书"
SaveTaskDetailsTool = ChatCompletionToolParam(
    type='function',
    function=ChatCompletionToolParamFunctionChunk(
        name='save_task_details',
        description='Saves the verbatim (exact) text of a task to permanent local memory. Use this as your first action.',
        parameters={
            'type': 'object',
            'properties': {
                'task_description': {
                    'type': 'string',
                    'description': 'The exact, word-for-word task given by the user.',
                },
            },
            'required': ['task_description'],
        },
    ),
)

# 定义任务回忆工具的 "说明书"
RecallTaskDetailsTool = ChatCompletionToolParam(
    type='function',
    function=ChatCompletionToolParamFunctionChunk(
        name='recall_task_details',
        description='Retrieves the original, verbatim task details from permanent local memory. Use this if you are unsure about the original goal.',
        parameters={
            'type': 'object',
            'properties': {}, # 此工具不需要参数
        },
    ),
)
