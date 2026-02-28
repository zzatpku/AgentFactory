"""
Skills Module - Utilities for managing and loading skills.

This module provides functions to:
- Parse SKILL.md files (extract metadata and instructions)
- List available skills (tools and subagents)
- Load skill instructions on demand
- Execute skills

Skills follow a three-level loading pattern:
- Level 1: Metadata (name, description) - loaded at startup
- Level 2: Instructions (full SKILL.md body) - loaded on demand
- Level 3: Execution - run the actual skill code
"""

import os
import re
from typing import Dict, Any, List, Optional

# Get the base directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(SCRIPT_DIR, "skills")
TOOLS_SKILLS_DIR = os.path.join(SKILLS_DIR, "tools")
SUBAGENT_SKILLS_DIR = os.path.join(SKILLS_DIR, "subagents")
META_SKILLS_DIR = os.path.join(SKILLS_DIR, "meta")


def parse_skill_md(skill_path: str) -> Optional[Dict[str, Any]]:
    """
    Parse a SKILL.md file and extract metadata and instructions.

    Args:
        skill_path: Path to the SKILL.md file

    Returns:
        Dict with 'name', 'description', and 'instructions' keys,
        or None if parsing fails
    """
    if not os.path.exists(skill_path):
        return None

    with open(skill_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse YAML frontmatter
    match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not match:
        return None

    frontmatter = match.group(1)
    instructions = match.group(2).strip()

    # Extract name and description from frontmatter
    name_match = re.search(r'^name:\s*(.+)$', frontmatter, re.MULTILINE)
    desc_match = re.search(r'^description:\s*(.+)$', frontmatter, re.MULTILINE)
    entry_file_match = re.search(r'^entry_file:\s*(.+)$', frontmatter, re.MULTILINE)

    if not name_match or not desc_match:
        return None

    result = {
        "name": name_match.group(1).strip(),
        "description": desc_match.group(1).strip(),
        "instructions": instructions
    }
    if entry_file_match:
        result["entry_file"] = entry_file_match.group(1).strip()

    return result


def get_skill_metadata(skill_path: str) -> Optional[Dict[str, str]]:
    """
    Get only the metadata (Level 1) from a skill.
    This is lightweight and used for listing skills.

    Args:
        skill_path: Path to the SKILL.md file

    Returns:
        Dict with 'name' and 'description' keys, or None if parsing fails
    """
    parsed = parse_skill_md(skill_path)
    if parsed:
        return {
            "name": parsed["name"],
            "description": parsed["description"]
        }
    return None


def list_tool_skills() -> List[Dict[str, str]]:
    """
    List all available tool skills with their metadata (Level 1).

    Returns:
        List of dicts with 'name', 'description', and 'directory' keys
    """
    skills = []
    if not os.path.exists(TOOLS_SKILLS_DIR):
        return skills

    for dirname in os.listdir(TOOLS_SKILLS_DIR):
        skill_dir = os.path.join(TOOLS_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue

        skill_md = os.path.join(skill_dir, "SKILL.md")
        metadata = get_skill_metadata(skill_md)
        if metadata:
            skills.append({
                "name": metadata["name"],
                "description": metadata["description"],
                "directory": dirname
            })

    return skills


def list_meta_skills() -> List[Dict[str, str]]:
    """
    List all available meta skills (for meta agent) with their metadata.

    Returns:
        List of dicts with 'name', 'description', and 'directory' keys
    """
    skills = []
    if not os.path.exists(META_SKILLS_DIR):
        return skills

    for dirname in os.listdir(META_SKILLS_DIR):
        skill_dir = os.path.join(META_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue

        skill_md = os.path.join(skill_dir, "SKILL.md")
        metadata = get_skill_metadata(skill_md)
        if metadata:
            skills.append({
                "name": metadata["name"],
                "description": metadata["description"],
                "directory": dirname
            })

    return skills


def get_meta_skill_instructions(skill_name: str) -> Optional[str]:
    """
    Get the full instructions (Level 2) for a meta skill.

    Args:
        skill_name: Name of the skill

    Returns:
        The instructions string, or None if not found
    """
    if not os.path.exists(META_SKILLS_DIR):
        return None

    for dirname in os.listdir(META_SKILLS_DIR):
        skill_dir = os.path.join(META_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue

        skill_md = os.path.join(skill_dir, "SKILL.md")
        parsed = parse_skill_md(skill_md)
        if parsed and (parsed["name"] == skill_name or dirname == skill_name):
            return parsed["instructions"]

    return None


def list_subagent_skills() -> List[Dict[str, str]]:
    """
    List all available subagent skills with their metadata (Level 1).

    Returns:
        List of dicts with 'name', 'description', and 'directory' keys
    """
    skills = []
    if not os.path.exists(SUBAGENT_SKILLS_DIR):
        return skills

    for dirname in os.listdir(SUBAGENT_SKILLS_DIR):
        skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue

        skill_md = os.path.join(skill_dir, "SKILL.md")
        metadata = get_skill_metadata(skill_md)
        if metadata:
            skills.append({
                "name": metadata["name"],
                "description": metadata["description"],
                "directory": dirname
            })

    return skills


def get_tool_skill_instructions(skill_name: str) -> Optional[str]:
    """
    Get the full instructions (Level 2) for a tool skill.

    Args:
        skill_name: Name of the skill

    Returns:
        The instructions string, or None if not found
    """
    # Try to find by name or directory
    for dirname in os.listdir(TOOLS_SKILLS_DIR):
        skill_dir = os.path.join(TOOLS_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue

        skill_md = os.path.join(skill_dir, "SKILL.md")
        parsed = parse_skill_md(skill_md)
        if parsed and (parsed["name"] == skill_name or dirname == skill_name):
            return parsed["instructions"]

    return None


def get_subagent_skill_instructions(skill_name: str) -> Optional[str]:
    """
    Get the full instructions (Level 2) for a subagent skill.

    Args:
        skill_name: Name of the skill

    Returns:
        The instructions string, or None if not found
    """
    if not os.path.exists(SUBAGENT_SKILLS_DIR):
        return None

    for dirname in os.listdir(SUBAGENT_SKILLS_DIR):
        skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue

        skill_md = os.path.join(skill_dir, "SKILL.md")
        parsed = parse_skill_md(skill_md)
        if parsed and (parsed["name"] == skill_name or dirname == skill_name):
            return parsed["instructions"]

    return None


def list_all_skills() -> List[Dict[str, str]]:
    """
    List all available skills (meta + tool + saved subagents) with names only.
    This is the unified function for meta agent to discover all skills.

    Returns:
        List of dicts with 'name' and 'type' keys
    """
    all_skills = []

    # Add meta skills
    for skill in list_meta_skills():
        all_skills.append({"name": skill["name"], "type": "meta"})

    # Add tool skills
    for skill in list_tool_skills():
        all_skills.append({"name": skill["name"], "type": "tool"})

    # Add saved subagent skills
    for skill in list_subagent_skills():
        all_skills.append({"name": skill["name"], "type": "saved_subagent"})

    return all_skills


def get_skill_instructions(skill_name: str) -> Optional[str]:
    """
    Get the full instructions for any skill (meta, tool, or saved subagent).
    This is the unified function for meta agent to get skill details.

    Args:
        skill_name: Name of the skill

    Returns:
        The instructions string, or None if not found
    """
    # Try meta skills first
    instructions = get_meta_skill_instructions(skill_name)
    if instructions:
        return instructions

    # Try tool skills
    instructions = get_tool_skill_instructions(skill_name)
    if instructions:
        return instructions

    # Try saved subagent skills
    instructions = get_subagent_skill_instructions(skill_name)
    if instructions:
        return instructions

    return None
