---
name: execute_shell_command
description: Execute standard Bash shell commands in a non-interactive environment. Supports file system navigation, reading, pip installation and so on. The current work_dir for shell command executing will be a temp dir.
---

# Shell Command Tool

⚠️ **IMPORTANT RESTRICTION**: You CANNOT use this tool directly! To execute shell commands, you MUST first create a subagent (using `create_subagent` skill) and then run it (using `run_subagent` skill). Direct execution of shell commands is not allowed.

execute_shell_command: A bridge to the local operating system shell. Allows execution of standard Bash commands.

## Usage

```python
from tools import execute_shell_command

# List files
output = execute_shell_command("ls -la")

# Read a file
content = execute_shell_command("cat -n README.md")
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| command | str | required | The Bash command to execute |

## Returns

Returns a single string containing the command's standard output (stdout) and standard error (stderr) combined.

**Note**: 1. Safety Interception: Commands like `rm`, `rmdir`, `shred` are strictly forbidden and will return an error string. 2. Output Truncation: If the output exceeds 5000 characters, it will be truncated. Use `head`, `tail`, or `grep` for large files.

## Example

```python
from tools import execute_shell_command

# 1. Inspect current directory
print(execute_shell_command("ls -F"))

# 2. Install a package (if network is available)
print(execute_shell_command("pip install pandas"))

# 3. Read a specific part of a file (safe for large files)
print(execute_shell_command("head -n 20 data.csv"))
```

## Tips

- Non-Interactive: Do NOT use interactive tools like `vim`, `nano`, or `python` (without `-c`). The process will hang.
- Reading Files: Prefer `cat -n filename` to see line numbers, which is helpful for editing later.
- Large Files: Avoid `cat` on large files. Use `head -n 50 filename` to peek, or `grep` to search.
- Environment: You are in a standard Bash environment. You can use pipes: `ls -la | grep .py`.
- State: The working directory is persistent. `cd folder` works for subsequent commands.
- Environment Setup: Use this tool to install Python packages and other dependencies needed by your subagent. For example: `pip install playwright && playwright install chromium`, `pip install pandas`, etc.
