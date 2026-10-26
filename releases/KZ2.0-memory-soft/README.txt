KZ2.0 memory-prose-soft-retry1
This overlay changes only memory_injection.py relative to KZ2.0 low4.
400/300 character guidance is advisory. Long prose cannot reject an otherwise
valid action or increment fatal protocol-error counters. Original explanations,
evidence IDs, argv and stdin are retained, without automatic truncation.
Type, nonempty, NUL, visible IDs and actual action validation remain enforced.
The recovery-rejection hard stop remains disabled. No loop-breaking algorithm,
model, memory retrieval, routing, subgoals, or request/tool budgets are changed.
Fresh mmap/cmu_p2 retry uses two concurrent fresh containers with empty memories.
cow/lock continue on their existing frozen source; old artifacts are preserved.
deepseek-flash, thinking disabled, temperature 0; 800 API / 600 tool / 2h,
1M context, 32768 output; CNY50 conservative pre-request cap per task.
Fixing prose length alone is not a guarantee of escaping mmap's action loop.
