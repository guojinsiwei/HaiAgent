"""Shared deployment-only disk policy; never modify frozen solver sources."""
import os


def install_disk_policy(state_class):
    original = state_class.reserve

    def reserve(self):
        if os.environ.get('LHTB_DISABLE_DISK_GUARD') != '1':
            return original(self)
        # Disabling a disk threshold must not disable trial cancellation.
        cancelled = getattr(self, 'cancelled', None)
        if cancelled is not None and cancelled.is_set():
            raise TimeoutError('Trial cancelled; refusing further container mutations')

    state_class.reserve = reserve
