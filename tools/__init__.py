"""Import tool modules to trigger MCP registration."""

from . import append_entry  # noqa: F401
from . import delete_project  # noqa: F401
from . import generate_doc_templates  # noqa: F401
from . import get_project  # noqa: F401
from . import list_projects  # noqa: F401
from . import query_entries  # noqa: F401
from . import read_recent  # noqa: F401
from . import rotate_log  # noqa: F401
from . import set_project  # noqa: F401
from . import manage_docs  # noqa: F401
from . import vector_search  # noqa: F401

__all__ = [
    "append_entry",
    "delete_project",
    "generate_doc_templates",
    "get_project",
    "list_projects",
    "query_entries",
    "read_recent",
    "rotate_log",
    "set_project",
    "manage_docs",
    "vector_search",
]
