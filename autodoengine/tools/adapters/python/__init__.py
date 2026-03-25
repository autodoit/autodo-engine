"""Python adapter。"""

from autodoengine.tools.public.facade import invoke_capability, list_capabilities
from autodoengine.tools.public.registry import lint_public_manifest

__all__ = ["list_capabilities", "invoke_capability", "lint_public_manifest"]
