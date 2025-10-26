"""Jinja2-based template engine with security sandboxing and custom template support."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from jinja2 import (
    Environment,
    FileSystemLoader,
    Template,
    TemplateNotFound,
    TemplateRuntimeError,
    TemplateSyntaxError,
    StrictUndefined,
)
from jinja2.exceptions import TemplateNotFound as TemplateNotFoundError
from jinja2.sandbox import ImmutableSandboxedEnvironment, SandboxedEnvironment

# Standalone implementations to avoid circular import hell
def get_template_root():
    """Get template root directory - standalone implementation."""
    # Use relative imports to avoid MCP_SPINE import issues
    current_dir = Path(__file__).parent.parent / "templates"
    return current_dir

def slugify_project_name(name: str) -> str:
    """Slugify project name - standalone implementation."""
    import re
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', str(name)).strip().lower()
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

# Setup logging for template engine
template_logger = logging.getLogger(__name__)

# Legacy template pattern for backward compatibility
LEGACY_PATTERN = r'\{(\w+)\}'

# Default template variables available in all templates
DEFAULT_VARIABLES = {
    "project_name": "",
    "project_slug": "",
    "timestamp": "",
    "agent": "",
    "utcnow": "",
    "version": "1.0",
    "status": "active",
}

# Restricted builtins for security
RESTRICTED_BUILTINS = {
    "abs": abs,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
}


class TemplateEngineError(Exception):
    """Base exception for template engine errors."""
    pass


class TemplateValidationError(TemplateEngineError):
    """Raised when template validation fails."""
    pass


class TemplateRenderError(TemplateEngineError):
    """Raised when template rendering fails."""
    pass


class Jinja2TemplateEngine:
    """Jinja2-based template engine with security sandboxing and custom templates."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        project_name: Optional[str] = None,
        security_mode: str = "sandbox"
    ):
        """
        Initialize the Jinja2 template engine.

        Args:
            project_root: Root directory of the project
            project_name: Name of the project
            security_mode: Security mode - "sandbox", "immutable", or "none"
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.project_name = project_name or ""
        self.project_slug = slugify_project_name(project_name or "")

        # Template directories
        self.template_dirs = self._discover_template_directories()

        # Security mode setup
        self.security_mode = security_mode
        self.env = self._create_jinja2_environment()

        # Custom variables cache
        self._custom_variables: Optional[Dict[str, Any]] = None

        template_logger.debug(f"Initialized template engine for project '{project_name}' with {len(self.template_dirs)} template directories")

    def _discover_template_directories(self) -> List[Path]:
        """Discover template directories in order of precedence."""
        template_dirs = []

        # 1. Project-specific custom templates (.scribe/templates/)
        project_templates_dir = self.project_root / ".scribe" / "templates"
        if project_templates_dir.exists():
            template_dirs.append(project_templates_dir)
            template_logger.debug(f"Found project templates: {project_templates_dir}")

        # 2. Global custom templates (MCP_SPINE/scribe_mcp/templates/custom/)
        try:
            template_root_path = get_template_root()
            global_custom_dir = template_root_path.parent / "templates" / "custom"
            if global_custom_dir.exists():
                template_dirs.append(global_custom_dir)
                template_logger.debug(f"Found global custom templates: {global_custom_dir}")

            # 3. Built-in fragments (MCP_SPINE/scribe_mcp/templates/fragments/)
            fragments_dir = template_root_path.parent / "fragments"
            if fragments_dir.exists():
                template_dirs.append(fragments_dir)
                template_logger.debug(f"Found built-in fragments: {fragments_dir}")
        except Exception as e:
            template_logger.warning(f"Could not load built-in templates: {e}")

        return template_dirs

    def _create_jinja2_environment(self) -> Environment:
        """Create Jinja2 environment with appropriate security settings."""
        # Common environment configuration
        common_kwargs = dict(
            loader=FileSystemLoader([str(d) for d in self.template_dirs]),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            undefined=StrictUndefined,  # Enable strict undefined checking
        )

        # Normalize security mode - accept both "none" and "unrestricted"
        normalized_mode = self.security_mode.lower()
        if normalized_mode in ("none", "unrestricted"):
            normalized_mode = "none"

        if normalized_mode == "immutable":
            # Most restrictive - no mutable operations
            env = ImmutableSandboxedEnvironment(**common_kwargs)
            template_logger.debug("Created immutable sandboxed environment with strict undefined")
        elif normalized_mode == "sandbox":
            # Balanced security - limited operations allowed
            env = SandboxedEnvironment(**common_kwargs)
            template_logger.debug("Created sandboxed environment with strict undefined")
        else:  # "none" or unrestricted
            env = Environment(**common_kwargs)
            template_logger.debug("Created unrestricted environment with strict undefined")

        # Add custom filters and globals
        self._add_custom_filters(env)
        self._add_custom_globals(env)

        return env

    def _add_custom_filters(self, env: Environment) -> None:
        """Add custom Jinja2 filters."""
        def slugify(text: str) -> str:
            """Convert text to URL-friendly slug."""
            return slugify_project_name(text)

        def format_bytes(size: int) -> str:
            """Format bytes in human-readable format."""
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} TB"

        env.filters['slugify'] = slugify
        env.filters['format_bytes'] = format_bytes

    def _add_custom_globals(self, env: Environment) -> None:
        """Add custom global functions and variables."""
        project_root = self.project_root.resolve()

        def include_file(path: str) -> str:
            """Include file content safely, locked to project directory."""
            try:
                # Resolve path relative to project root and validate it stays within project
                target_path = (project_root / path).resolve()

                # Security check: ensure the resolved path is still within project_root
                if project_root not in target_path.parents and target_path != project_root:
                    return f"[Security: path '{path}' outside project directory]"

                if not target_path.exists():
                    return f"[File not found: {path}]"

                return target_path.read_text(encoding='utf-8')
            except Exception as e:
                return f"[Error reading file {path}: {e}]"

        env.globals['include_file'] = include_file
        env.globals['restricted_builtins'] = RESTRICTED_BUILTINS

    def load_custom_variables(self) -> Dict[str, Any]:
        """Load custom variables from .scribe/variables.json."""
        if self._custom_variables is not None:
            return self._custom_variables

        variables_file = self.project_root / ".scribe" / "variables.json"
        custom_vars = {}

        if variables_file.exists():
            try:
                with open(variables_file, 'r', encoding='utf-8') as f:
                    custom_vars = json.load(f)
                template_logger.debug(f"Loaded {len(custom_vars)} custom variables from {variables_file}")
            except json.JSONDecodeError as e:
                template_logger.warning(f"Invalid JSON in variables file {variables_file}: {e}")
            except Exception as e:
                template_logger.error(f"Error loading variables file {variables_file}: {e}")

        self._custom_variables = custom_vars
        return custom_vars

    def _build_context(self, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build template context from defaults, custom variables, and metadata."""
        context = DEFAULT_VARIABLES.copy()

        # Add project-specific defaults
        context.update({
            "project_name": self.project_name,
            "project_slug": self.project_slug,
        })

        # Add time variables that were declared in defaults but never populated
        now = datetime.now(timezone.utc)
        context.update({
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "utcnow": now.isoformat(),
        })

        # Add custom variables
        custom_vars = self.load_custom_variables()
        context.update(custom_vars)

        # Add runtime metadata
        if metadata:
            context.update(metadata)

        return context

    def _render_legacy_template(self, template_string: str, context: Dict[str, Any]) -> str:
        """
        Legacy fallback for old {variable} template syntax.

        This provides backward compatibility with the old string-based templating system.
        """
        try:
            # Create a safe dictionary for str.format_map that returns empty string for missing keys
            class SafeDict(dict):
                def __missing__(self, key):
                    return f"{{?{key}}}"  # Mark missing variables

            safe_context = SafeDict(context)
            result = template_string.format_map(safe_context)
            template_logger.debug("Legacy template rendering successful")
            return result
        except Exception as e:
            template_logger.warning(f"Legacy template rendering failed: {e}")
            return template_string  # Return original if fallback fails

    def render_template(
        self,
        template_name: str,
        metadata: Optional[Dict[str, Any]] = None,
        strict: bool = False,
        fallback: bool = True
    ) -> str:
        """
        Render a template with the given context.

        Args:
            template_name: Name of the template file
            metadata: Additional variables for template rendering
            strict: Whether to raise errors for undefined variables

        Returns:
            Rendered template content

        Raises:
            TemplateNotFoundError: If template file is not found
            TemplateSyntaxError: If template has syntax errors
            TemplateRenderError: If rendering fails
        """
        try:
            # Load template
            template = self.env.get_template(template_name)

            # Build context
            context = self._build_context(metadata)

            # Render template (environment already has StrictUndefined configured)
            result = template.render(**context)

            template_logger.debug(f"Successfully rendered template '{template_name}' ({len(result)} chars)")
            return result

        except TemplateNotFound as e:
            raise TemplateNotFoundError(f"Template '{template_name}' not found in template directories: {self.template_dirs}")
        except (TemplateSyntaxError, TemplateRuntimeError) as e:
            if fallback:
                template_logger.warning(f"Jinja2 rendering failed for '{template_name}', attempting legacy fallback: {e}")
                try:
                    # Try to get template source and use legacy rendering
                    source, _, _ = self.env.loader.get_source(self.env, template_name)
                    context = self._build_context(metadata)
                    return self._render_legacy_template(source, context)
                except Exception as fallback_error:
                    template_logger.error(f"Legacy fallback also failed for '{template_name}': {fallback_error}")
                    raise TemplateRenderError(f"Both Jinja2 and legacy rendering failed for '{template_name}': {e}")
            else:
                if isinstance(e, TemplateSyntaxError):
                    raise TemplateValidationError(f"Template syntax error in '{template_name}': {e}")
                else:
                    raise TemplateRenderError(f"Template runtime error in '{template_name}': {e}")
        except Exception as e:
            raise TemplateRenderError(f"Unexpected error rendering template '{template_name}': {e}")

    def render_string(
        self,
        template_string: str,
        metadata: Optional[Dict[str, Any]] = None,
        strict: bool = False,
        fallback: bool = True
    ) -> str:
        """
        Render a template string with the given context.

        Args:
            template_string: Jinja2 template string
            metadata: Additional variables for template rendering
            strict: Whether to raise errors for undefined variables

        Returns:
            Rendered content
        """
        try:
            template = self.env.from_string(template_string)
            context = self._build_context(metadata)

            # Render template string (environment already has StrictUndefined configured)
            result = template.render(**context)

            template_logger.debug(f"Successfully rendered template string ({len(result)} chars)")
            return result

        except (TemplateSyntaxError, TemplateRuntimeError) as e:
            if fallback:
                template_logger.warning(f"Jinja2 rendering failed for template string, attempting legacy fallback: {e}")
                try:
                    context = self._build_context(metadata)
                    return self._render_legacy_template(template_string, context)
                except Exception as fallback_error:
                    template_logger.error(f"Legacy fallback also failed for template string: {fallback_error}")
                    raise TemplateRenderError(f"Both Jinja2 and legacy rendering failed for template string: {e}")
            else:
                if isinstance(e, TemplateSyntaxError):
                    raise TemplateValidationError(f"Template syntax error: {e}")
                else:
                    raise TemplateRenderError(f"Template runtime error: {e}")
        except Exception as e:
            raise TemplateRenderError(f"Unexpected error rendering template string: {e}")

    def validate_template(self, template_name: str) -> Dict[str, Any]:
        """
        Validate a template without rendering it.

        Returns:
            Validation result with success status and any errors
        """
        result = {
            "template": template_name,
            "valid": False,
            "errors": [],
            "warnings": [],
            "line_count": 0,
            "size_bytes": 0,
        }

        try:
            # Resolve source via loader for proper parsing and stats
            source, filename, uptodate = self.env.loader.get_source(self.env, template_name)

            # Get template stats
            if filename:
                result["size_bytes"] = Path(filename).stat().st_size if Path(filename).exists() else 0
                result["line_count"] = len(source.splitlines())

            # Parse without rendering to validate syntax
            self.env.parse(source)

            result["valid"] = True
            template_logger.debug(f"Template '{template_name}' validation passed")

        except TemplateNotFound:
            result["errors"].append(f"Template '{template_name}' not found")
        except TemplateSyntaxError as e:
            result["errors"].append(f"Syntax error at line {e.lineno}: {e.message}")
        except Exception as e:
            result["errors"].append(f"Validation error: {e}")

        return result

    def list_templates(self, extension: str = ".md") -> List[str]:
        """List all available templates with the given extension (recursive)."""
        templates = []

        for template_dir in self.template_dirs:
            # Use rglob for recursive discovery
            for template_path in template_dir.rglob(f"*{extension}"):
                relative_path = template_path.relative_to(template_dir)
                templates.append(str(relative_path))

        # Remove duplicates while preserving order
        seen = set()
        unique_templates = []
        for template in templates:
            if template not in seen:
                seen.add(template)
                unique_templates.append(template)

        return unique_templates

    def get_template_info(self, template_name: str) -> Dict[str, Any]:
        """Get detailed information about a template."""
        info = {
            "name": template_name,
            "found": False,
            "path": None,
            "size_bytes": 0,
            "line_count": 0,
            "last_modified": None,
            "template_type": "unknown",
        }

        for template_dir in self.template_dirs:
            template_path = template_dir / template_name
            if template_path.exists():
                info["found"] = True
                info["path"] = str(template_path)
                info["size_bytes"] = template_path.stat().st_size
                info["line_count"] = len(template_path.read_text(encoding='utf-8').splitlines())
                info["last_modified"] = template_path.stat().st_mtime

                # Determine template type based on directory
                if ".scribe/templates" in str(template_dir):
                    info["template_type"] = "project_custom"
                elif "templates/custom" in str(template_dir):
                    info["template_type"] = "global_custom"
                elif "fragments" in str(template_dir):
                    info["template_type"] = "built_in"
                break

        return info