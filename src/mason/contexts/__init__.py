"""
Context management for agent prompts.

Each agent's complete context (system prompt, output field descriptions,
user prompt templates) is defined in a single Markdown file with YAML
frontmatter in ``src/ria/contexts/``.

Format
------
    ---
    agent: AgentClassName
    output_fields:
      field_name:
        description: >-
          Field description text.
    user_prompts:
      template_name: |
        User prompt with {placeholder} variables.
    ---
    # System prompt body (markdown)
    ...

Usage
-----
    from ria.contexts import load_context

    ctx = load_context("design_driver")
    system_prompt = ctx.system_prompt
    user_prompt = ctx.render_user_prompt("initial", material="stone")

Includes
--------
    Use ``<!-- @include: module_name -->`` in the system prompt body
    to inline the contents of ``_modules/module_name.md``.
"""

import os
import re

import yaml
from pydantic import BaseModel, Field, create_model

CONTEXTS_DIR = os.path.dirname(__file__)
MODULES_DIR = os.path.join(CONTEXTS_DIR, "_modules")


class _SafeDict(dict):
    """Dict that returns the ``{key}`` placeholder for missing keys."""

    def __missing__(self, key):
        return "{" + key + "}"


def _resolve_includes(text: str) -> str:
    """Replace ``<!-- @include: name -->`` with the module file contents."""

    def _replacement(match):
        module_name = match.group(1).strip()
        module_path = os.path.join(MODULES_DIR, f"{module_name}.md")
        if os.path.exists(module_path):
            with open(module_path, "r", encoding="utf-8") as f:
                return f.read()
        return match.group(0)  # leave marker as-is when file missing

    return re.sub(r"<!-- @include:\s*(\S+)\s*-->", _replacement, text)


class ContextFile:
    """Parsed context file with frontmatter metadata and system prompt body."""

    def __init__(self, filepath: str):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        self._filepath = filepath
        self._frontmatter, self._body = self._parse(content)
        self._body = _resolve_includes(self._body)

    @staticmethod
    def _parse(content: str) -> tuple[dict, str]:
        # Match --- on its own line at the start, then --- on its own line
        m = re.match(r"\A---[ \t]*\r?\n(.*?\r?\n)---[ \t]*\r?\n", content, re.DOTALL)
        if m:
            fm = yaml.safe_load(m.group(1)) or {}
            body = content[m.end() :].strip()
            return fm, body
        return {}, content.strip()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        """Raw system prompt body (no variable substitution)."""
        return self._body

    @property
    def agent(self) -> str:
        return self._frontmatter.get("agent", "")

    @property
    def model(self) -> str:
        return self._frontmatter.get("model", "")

    @property
    def output_fields(self) -> dict:
        return self._frontmatter.get("output_fields", {})

    @property
    def user_prompts(self) -> dict:
        return self._frontmatter.get("user_prompts", {})

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def get_system_prompt(self, **kwargs) -> str:
        """Return system prompt, optionally formatting ``{placeholders}``."""
        if kwargs:
            return self._body.format_map(_SafeDict(kwargs))
        return self._body

    def render_user_prompt(self, name: str, **kwargs) -> str:
        """Render a named user prompt template with keyword arguments."""
        template = self.user_prompts.get(name)
        if template is None:
            raise KeyError(f"No user prompt template '{name}' in {self._filepath}")
        if kwargs:
            return template.format_map(_SafeDict(kwargs))
        return template

    def get_field_descriptions(self) -> dict[str, str]:
        """Return ``{field_name: description}`` for all output fields."""
        result = {}
        for name, info in self.output_fields.items():
            if isinstance(info, dict):
                result[name] = info.get("description", "")
            else:
                result[name] = str(info)
        return result

    # ------------------------------------------------------------------
    # Preview / debug
    # ------------------------------------------------------------------

    def preview(self, prompt_name: str | None = None, **kwargs) -> str:
        """Return a human-readable preview of the full agent context."""
        lines: list[str] = []
        lines.append(f"# Context: {os.path.basename(self._filepath)}")
        lines.append(f"**Agent:** {self.agent}")
        lines.append("")

        lines.append("## System Prompt")
        lines.append(self.get_system_prompt(**kwargs))
        lines.append("")

        if self.output_fields:
            lines.append("## Output Fields")
            for name, info in self.output_fields.items():
                desc = info.get("description", "") if isinstance(info, dict) else str(info)
                lines.append(f"- **{name}**: {desc}")
            lines.append("")

        if prompt_name:
            lines.append(f"## User Prompt: {prompt_name}")
            lines.append(self.render_user_prompt(prompt_name, **kwargs))
        elif self.user_prompts:
            lines.append("## User Prompt Templates")
            for name, template in self.user_prompts.items():
                lines.append(f"### {name}")
                if kwargs:
                    lines.append(template.format_map(_SafeDict(kwargs)))
                else:
                    lines.append(template)
                lines.append("")

        return "\n".join(lines)


def load_context(name: str) -> ContextFile:
    """Load a context file by name (without ``.md`` extension)."""
    filepath = os.path.join(CONTEXTS_DIR, f"{name}.md")
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Context file not found: {filepath}")
    return ContextFile(filepath)


def apply_context_descriptions(model_cls: type[BaseModel], context: ContextFile) -> type[BaseModel]:
    """Return a new model class with field descriptions loaded from *context*.

    Field types and defaults are preserved from *model_cls*; only the
    ``description`` of each field is replaced with the value defined in the
    context file's ``output_fields``.
    """
    field_descs = context.get_field_descriptions()
    field_definitions = {}
    for name, field_info in model_cls.model_fields.items():
        desc = field_descs.get(name, field_info.description or "")
        field_kwargs: dict = {"description": desc}
        if not field_info.is_required():
            field_kwargs["default"] = field_info.default
        field_definitions[name] = (field_info.annotation, Field(**field_kwargs))
    return create_model(model_cls.__name__, **field_definitions)
