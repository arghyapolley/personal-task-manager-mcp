# Personal Task Manager — MCP Server

A **Model Context Protocol (MCP)** server that turns any AI assistant into a powerful task management system. Built with Python and SQLite, it exposes **19 tools** for full lifecycle task management from quick to-dos to multi project workflows with priorities, tags, subtasks, and more.

```
AI Assistant  <-->  MCP Protocol (stdio)  <-->  Task Manager Server  <-->  SQLite DB
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Due Dates & Deadlines** | Set, update, or clear deadlines on any task |
| **Priorities** | Classify tasks as `high`, `medium`, or `low` |
| **Status Workflow** | Full lifecycle: `todo` > `in_progress` > `blocked` > `done` > `archived` |
| **Tags & Labels** | Flexible many-to-many tagging (e.g. `@work`, `@home`, `urgent`) |
| **Notes & Descriptions** | Rich markdown notes attached to any task |
| **Subtasks & Checklists** | Break tasks into ordered, toggleable checklist items |
| **Lists & Projects** | Organize tasks by context — work, personal, side-project |

---

## All 19 MCP Tools

### Core CRUD

| Tool | Signature | Description |
|------|-----------|-------------|
| `get_schema` | `()` | Get the full database schema |
| `run_select_query` | `(query)` | Run a read-only SQL SELECT query |
| `add_task` | `(title, description?, due_date?, priority?, list_id?, notes?)` | Create a new task |
| `update_task` | `(task_id, title?, description?, status?, due_date?, priority?, list_id?, notes?)` | Update any task field |
| `delete_task` | `(task_id)` | Delete a task and its subtasks/tags |

### Due Dates

| Tool | Signature | Description |
|------|-----------|-------------|
| `set_due_date` | `(task_id, due_date)` | Set or clear a deadline (YYYY-MM-DD) |

### Priorities

| Tool | Signature | Description |
|------|-----------|-------------|
| `set_priority` | `(task_id, level)` | Set priority: `high` / `medium` / `low` |

### Status Workflow

| Tool | Signature | Description |
|------|-----------|-------------|
| `set_status` | `(task_id, status)` | Set status: `todo` / `in_progress` / `blocked` / `done` / `archived` |

### Tags & Labels

| Tool | Signature | Description |
|------|-----------|-------------|
| `add_tag` | `(task_id, tag)` | Add a tag to a task (creates if new) |
| `remove_tag` | `(task_id, tag)` | Remove a tag from a task |
| `list_by_tag` | `(tag)` | List all tasks with a given tag |

### Notes

| Tool | Signature | Description |
|------|-----------|-------------|
| `update_notes` | `(task_id, markdown_text)` | Set/replace markdown notes on a task |

### Subtasks & Checklists

| Tool | Signature | Description |
|------|-----------|-------------|
| `add_subtask` | `(parent_id, title)` | Add a checklist item to a task |
| `toggle_subtask` | `(subtask_id)` | Toggle completion (done / not done) |
| `delete_subtask` | `(subtask_id)` | Remove a subtask |
| `list_subtasks` | `(parent_id)` | List all subtasks of a task |

### Lists & Projects

| Tool | Signature | Description |
|------|-----------|-------------|
| `create_list` | `(name, description?)` | Create a new list/project |
| `delete_list` | `(list_id)` | Delete a list (tasks become unassigned) |
| `move_task_to_list` | `(task_id, list_id)` | Move a task to a list (use `0` to unassign) |
| `list_tasks_in_list` | `(list_id)` | List all tasks in a list |

---

## Quick Start

### Prerequisites

- Python 3.10+
- An MCP-compatible client (e.g. Claude Desktop, Cursor, VS Code + Copilot)

### Installation

```bash
# Clone the repository
git clone https://github.com/arghyapolley/personal-task-manager-mcp.git
cd personal-task-manager-mcp

# Install dependencies
pip install -r requirements.txt
```

### Run the Server

```bash
python server.py
```

The server communicates via **stdio** using the MCP protocol. It automatically creates/migrates the `tasks.db` SQLite database on startup.

### Connect to Claude Desktop

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "task-manager": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

Then restart Claude Desktop. You can now say things like:

> *"Add a high-priority task called 'Deploy v2' to my Work project, due May 10th"*
>
> *"Show me all tasks tagged @urgent"*
>
> *"Add subtasks to task 3: write tests, update docs, deploy"*
>
> *"What's overdue?"*

---

## Database Schema

```
+---------------+       +---------------+
|    lists      |       |     tags      |
+---------------+       +---------------+
| id (PK)       |       | id (PK)       |
| name (UQ)     |       | name (UQ)     |
| description   |       +-------+-------+
| created_at    |               |
+-------+-------+               |
        |                +------+------+
        | 1:N            | task_tags   |
        |                +-------------+
+-------+-------+       | task_id(FK) |--+
|    tasks      |       | tag_id(FK)  |  |
+---------------+       +-------------+  |
| id (PK)       |<-----------------------+
| title         |
| description   |       +-------------+
| status        |       |  subtasks   |
| due_date      |       +-------------+
| priority      |  1:N  | id (PK)     |
| list_id (FK)  |<------| parent_id   |
| notes         |       | title       |
| created_at    |       |is_completed |
| updated_at    |       | sort_order  |
+---------------+       | created_at  |
                        +-------------+
```

---

## Testing

Run the full test suite (63 tests, uses a temporary DB):

```bash
python test_server.py
```

```
  Results:  63 passed,  0 failed
```

Tests cover: schema creation, CRUD, priorities, status workflow, tags (add/remove/list/duplicates), notes, subtasks (add/toggle/delete/ordering), lists (create/move/unassign/delete), cascade deletes, and SQL injection guards.

---

## Project Structure

```
personal-task-manager-mcp/
|-- server.py          # MCP server -- 19 tools, DB init, schema migration
|-- test_server.py     # Comprehensive test suite (63 assertions)
|-- requirements.txt   # Python dependencies (mcp, pydantic)
|-- tasks.db           # SQLite database (auto-created on first run)
+-- README.md          # This file
```

---

