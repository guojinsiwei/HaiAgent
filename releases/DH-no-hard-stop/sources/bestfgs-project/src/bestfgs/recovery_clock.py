"""Recovery scheduling clock; never an execution or evidence counter."""


def recovery_steps(runner):
    # Both refusals return control to the actor without issuing a task tool.
    # Count those attempts for cooldowns, but keep tool budgets, evidence IDs
    # and episode execution caps tied to actual executor calls.
    return sum(runner.counts.get(key, 0) for key in
               ('tool_calls', 'action_loop_blocks', 'contrastive_rejections'))
