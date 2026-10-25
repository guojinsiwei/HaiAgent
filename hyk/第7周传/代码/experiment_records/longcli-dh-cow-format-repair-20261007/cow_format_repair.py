"""Repair only an overlong, non-executable memory-review reason.

The original model response remains in the wire audit. The accepted action and
conversation record share this bounded reason, so no extra model call is needed
for a formatting-only error. Other validation and decision rules are unchanged.
"""


def bounded_review(action, visible, enabled, validate, limit=400):
    if enabled and visible and isinstance(action, dict):
        review = action.get("memory_review")
        if isinstance(review, dict):
            reason = review.get("reason")
            if isinstance(reason, str) and "\x00" not in reason and len(reason.strip()) > limit:
                review["reason"] = reason.strip()[:limit].rstrip()
    return validate(action, visible, enabled)


def install():
    from bestfgs import lean_runtime

    original = lean_runtime.validate_review
    if getattr(original, "_cow_reason_bound", False):
        return

    def validate_with_bound(action, visible, enabled):
        return bounded_review(action, visible, enabled, original)

    validate_with_bound._cow_reason_bound = True
    lean_runtime.validate_review = validate_with_bound
