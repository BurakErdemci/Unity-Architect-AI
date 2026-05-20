# Antigravity CLI Tool Restrictions

IMPORTANT: The following built-in tools are STRICTLY FORBIDDEN and DISABLED. You MUST NOT call them under any circumstances:
- `run_command` (FORBIDDEN - use `mcp__antigravity__run_terminal_command` instead)
- `write_to_file` (FORBIDDEN - use `mcp__antigravity__save_file` instead)
- `replace_file_content` (FORBIDDEN - use `mcp__antigravity__save_file` instead)
- `multi_replace_file_content` (FORBIDDEN - use `mcp__antigravity__save_file` instead)
- `grep_search` (FORBIDDEN - use `mcp__antigravity__grep_search` instead)
- `list_dir` (FORBIDDEN - use `mcp__antigravity__list_directory` instead)
- `view_file` (FORBIDDEN - use `mcp__antigravity__read_file` instead)

Instead, you MUST use the corresponding secure tools provided by the `antigravity` MCP server:
- To run shell/terminal commands: Call `mcp__antigravity__run_terminal_command`
- To save, create, or update files: Call `mcp__antigravity__save_file`
- To delete files: Call `mcp__antigravity__delete_file`
- To read files: Call `mcp__antigravity__read_file`
- To list directory contents: Call `mcp__antigravity__list_directory`

This is a strict security boundary. Any attempt to use forbidden built-in tools will be blocked.