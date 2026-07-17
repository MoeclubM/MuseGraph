"""Text-type packs (Phase C).

This sub-package exists so ``importlib.resources`` can locate the
``*.yaml`` pack files and the ``templates/`` directory next to it.

Re-export public API from the core loader module.
"""

from app.services.agent.pack_core import (  # noqa: F401
    TextTypePack,
    clear_cache,
    get_project_pack,
    list_packs,
    load_pack,
    set_project_pack,
)
