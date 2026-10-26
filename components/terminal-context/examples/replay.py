"""Offline, deterministic demonstration: no shell, credentials, API or files needed."""
import json

from terminal_context import Limits, TaskContext, TerminalEvent


def main():
    context = TaskContext(
        "demo-import-fix", "Make the application import successfully, then run its targeted tests.",
        constraints=("Do not claim task success from an import check alone.",),
        limits=Limits(recent_count=3),
    )
    for environment, command, code, stdout, stderr in [
        ("env-before", "python app.py", 1, "", "ModuleNotFoundError: No module named 'flask'"),
        ("env-before", "python app.py", 1, "", "ModuleNotFoundError: No module named 'flask'"),
        ("env-after", "python app.py", 0, "Application imported successfully", ""),
        ("env-after", "pytest tests/test_app.py", 0, "=== 2 passed in 0.12s ===", ""),
    ]:
        feedback = context.observe(TerminalEvent(
            task_id=context.task_id, command=command, exit_code=code, stdout=stdout, stderr=stderr,
            cwd="/workspace/project", workspace="code-revision-1", environment=environment,
        ))
        print(json.dumps({"event": feedback["id"], "outcome": feedback["outcome"],
                          "test_status": feedback["test_status"],
                          "stored_memories": len(context.snapshot()["memories"])}, ensure_ascii=False))
    view = context.build_prompt(query="python app.py import", max_units=10000)
    print("\nRebuilt prompt data block (replace the previous block; do not append it):")
    print(json.dumps(json.loads(view.content), indent=2, ensure_ascii=False))
    print("\nBudget:", view.units, view.unit_name)
    print("Selected memories:", view.selected_memory_ids)
    print("Storage counters:", context.snapshot()["stats"])


if __name__ == "__main__":
    main()
