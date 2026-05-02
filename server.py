from typing import Any, Optional
import sqlite3
import json
import os
from contextlib import contextmanager
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("Personal Task Management")

DB_PATH = "tasks.db"

# ── Valid enum values ──────────────────────────────────────────────────────────
VALID_STATUSES = {"todo", "in_progress", "blocked", "done", "archived"}
VALID_PRIORITIES = {"high", "medium", "low"}


# ── Database helpers ──────────────────────────────────────────────────────────

@contextmanager
def get_db():
    """Context manager that returns a sqlite3 connection with Row factory and
    foreign-key enforcement.  Commits on success, rolls back on error."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _task_exists(conn: sqlite3.Connection, task_id: int) -> bool:
    row = conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row is not None


def init_db():
    """Create all tables and migrate the existing schema if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # ── Lists / Projects ──────────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Tasks (create if brand-new DB) ────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'todo',
            due_date TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            list_id INTEGER REFERENCES lists(id) ON DELETE SET NULL,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Migrate legacy tasks table (add missing columns) ──────────────────
    existing_cols = {
        row[1] for row in cur.execute("PRAGMA table_info(tasks)").fetchall()
    }
    migrations = {
        "priority": "ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'medium'",
        "list_id":  "ALTER TABLE tasks ADD COLUMN list_id INTEGER REFERENCES lists(id) ON DELETE SET NULL",
        "notes":    "ALTER TABLE tasks ADD COLUMN notes TEXT DEFAULT ''",
    }
    for col, ddl in migrations.items():
        if col not in existing_cols:
            cur.execute(ddl)

    # Migrate legacy status values
    cur.execute("UPDATE tasks SET status = 'todo' WHERE status = 'pending'")
    cur.execute("UPDATE tasks SET status = 'done' WHERE status = 'completed'")

    # ── Tags ──────────────────────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS task_tags (
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
            PRIMARY KEY (task_id, tag_id)
        )
    ''')

    # ── Subtasks ──────────────────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            is_completed BOOLEAN DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  MCP TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

# ── Schema & raw query ────────────────────────────────────────────────────────

@mcp.tool()
def get_schema() -> str:
    """Get the full schema of the task-management database (tasks, tags, subtasks, lists)."""
    return '''
-- Lists / Projects
CREATE TABLE lists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tasks
CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    status      TEXT DEFAULT 'todo',       -- todo | in_progress | blocked | done | archived
    due_date    TEXT DEFAULT '',            -- Format: YYYY-MM-DD
    priority    TEXT DEFAULT 'medium',      -- high | medium | low
    list_id     INTEGER REFERENCES lists(id) ON DELETE SET NULL,
    notes       TEXT DEFAULT '',            -- Markdown-formatted notes
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tags (many-to-many via task_tags)
CREATE TABLE tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE task_tags (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
);

-- Subtasks / Checklist items
CREATE TABLE subtasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    is_completed BOOLEAN DEFAULT 0,
    sort_order   INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''.strip()


@mcp.tool()
def run_select_query(query: str) -> str:
    """Run a read-only SQL SELECT query on the tasks database."""
    if not query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."
    try:
        with get_db() as conn:
            rows = conn.execute(query).fetchall()
            return json.dumps([dict(r) for r in rows], indent=2)
    except Exception as e:
        return f"Error executing query: {str(e)}"


# ── Task CRUD ─────────────────────────────────────────────────────────────────

@mcp.tool()
def add_task(
    title: str,
    description: str = "",
    due_date: str = "",
    priority: str = "medium",
    list_id: Optional[int] = None,
    notes: str = "",
) -> str:
    """Add a new task. Priority must be high/medium/low. Status defaults to 'todo'."""
    priority = priority.lower()
    if priority not in VALID_PRIORITIES:
        return f"Error: priority must be one of {VALID_PRIORITIES}"
    try:
        with get_db() as conn:
            cur = conn.execute(
                '''INSERT INTO tasks (title, description, due_date, priority, list_id, notes)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (title, description, due_date, priority, list_id, notes),
            )
            return f"Task added successfully with ID {cur.lastrowid}"
    except Exception as e:
        return f"Error adding task: {str(e)}"


@mcp.tool()
def update_task(
    task_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: Optional[str] = None,
    list_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> str:
    """Update an existing task. Only provide the arguments you want to change.
    Status must be one of: todo, in_progress, blocked, done, archived.
    Priority must be one of: high, medium, low."""
    if status is not None and status.lower() not in VALID_STATUSES:
        return f"Error: status must be one of {VALID_STATUSES}"
    if priority is not None and priority.lower() not in VALID_PRIORITIES:
        return f"Error: priority must be one of {VALID_PRIORITIES}"

    updates, params = [], []
    for col, val in [
        ("title", title),
        ("description", description),
        ("status", status.lower() if status else None),
        ("due_date", due_date),
        ("priority", priority.lower() if priority else None),
        ("list_id", list_id),
        ("notes", notes),
    ]:
        if val is not None:
            updates.append(f"{col} = ?")
            params.append(val)

    if not updates:
        return "No updates provided."

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(task_id)

    try:
        with get_db() as conn:
            cur = conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
            )
            if cur.rowcount == 0:
                return f"Error: Task with ID {task_id} not found."
            return f"Task {task_id} updated successfully."
    except Exception as e:
        return f"Error updating task: {str(e)}"


@mcp.tool()
def delete_task(task_id: int) -> str:
    """Delete a task (and its subtasks/tags) by ID."""
    try:
        with get_db() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cur.rowcount == 0:
                return f"Error: Task with ID {task_id} not found."
            return f"Task {task_id} deleted successfully."
    except Exception as e:
        return f"Error deleting task: {str(e)}"


# ── Due dates ─────────────────────────────────────────────────────────────────

@mcp.tool()
def set_due_date(task_id: int, due_date: str) -> str:
    """Set or update the due date for a task. Use YYYY-MM-DD format.
    Pass an empty string to clear the due date."""
    try:
        with get_db() as conn:
            if not _task_exists(conn, task_id):
                return f"Error: Task with ID {task_id} not found."
            conn.execute(
                "UPDATE tasks SET due_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (due_date, task_id),
            )
            if due_date:
                return f"Due date for task {task_id} set to {due_date}."
            return f"Due date for task {task_id} cleared."
    except Exception as e:
        return f"Error setting due date: {str(e)}"


# ── Priorities ────────────────────────────────────────────────────────────────

@mcp.tool()
def set_priority(task_id: int, level: str) -> str:
    """Set the priority of a task. Level must be 'high', 'medium', or 'low'."""
    level = level.lower()
    if level not in VALID_PRIORITIES:
        return f"Error: priority must be one of {VALID_PRIORITIES}"
    try:
        with get_db() as conn:
            if not _task_exists(conn, task_id):
                return f"Error: Task with ID {task_id} not found."
            conn.execute(
                "UPDATE tasks SET priority = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (level, task_id),
            )
            return f"Priority for task {task_id} set to '{level}'."
    except Exception as e:
        return f"Error setting priority: {str(e)}"


# ── Status workflow ───────────────────────────────────────────────────────────

@mcp.tool()
def set_status(task_id: int, status: str) -> str:
    """Set the status of a task.
    Valid statuses: todo, in_progress, blocked, done, archived."""
    status = status.lower()
    if status not in VALID_STATUSES:
        return f"Error: status must be one of {VALID_STATUSES}"
    try:
        with get_db() as conn:
            if not _task_exists(conn, task_id):
                return f"Error: Task with ID {task_id} not found."
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, task_id),
            )
            return f"Status for task {task_id} set to '{status}'."
    except Exception as e:
        return f"Error setting status: {str(e)}"


# ── Tags / Labels ────────────────────────────────────────────────────────────

@mcp.tool()
def add_tag(task_id: int, tag: str) -> str:
    """Add a tag/label to a task. Creates the tag if it doesn't exist yet."""
    tag = tag.strip().lower()
    if not tag:
        return "Error: tag name cannot be empty."
    try:
        with get_db() as conn:
            if not _task_exists(conn, task_id):
                return f"Error: Task with ID {task_id} not found."
            # Upsert the tag
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
            tag_id = tag_row["id"]
            # Link task ↔ tag
            conn.execute(
                "INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)",
                (task_id, tag_id),
            )
            return f"Tag '{tag}' added to task {task_id}."
    except Exception as e:
        return f"Error adding tag: {str(e)}"


@mcp.tool()
def remove_tag(task_id: int, tag: str) -> str:
    """Remove a tag from a task."""
    tag = tag.strip().lower()
    try:
        with get_db() as conn:
            if not _task_exists(conn, task_id):
                return f"Error: Task with ID {task_id} not found."
            tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
            if not tag_row:
                return f"Error: Tag '{tag}' does not exist."
            cur = conn.execute(
                "DELETE FROM task_tags WHERE task_id = ? AND tag_id = ?",
                (task_id, tag_row["id"]),
            )
            if cur.rowcount == 0:
                return f"Tag '{tag}' was not on task {task_id}."
            return f"Tag '{tag}' removed from task {task_id}."
    except Exception as e:
        return f"Error removing tag: {str(e)}"


@mcp.tool()
def list_by_tag(tag: str) -> str:
    """List all tasks that have a given tag."""
    tag = tag.strip().lower()
    try:
        with get_db() as conn:
            rows = conn.execute(
                '''SELECT t.* FROM tasks t
                   JOIN task_tags tt ON t.id = tt.task_id
                   JOIN tags tg ON tg.id = tt.tag_id
                   WHERE tg.name = ?
                   ORDER BY
                       CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                       t.due_date ASC''',
                (tag,),
            ).fetchall()
            if not rows:
                return f"No tasks found with tag '{tag}'."
            return json.dumps([dict(r) for r in rows], indent=2)
    except Exception as e:
        return f"Error listing by tag: {str(e)}"


# ── Notes & descriptions ─────────────────────────────────────────────────────

@mcp.tool()
def update_notes(task_id: int, markdown_text: str) -> str:
    """Set or replace the notes (markdown) for a task."""
    try:
        with get_db() as conn:
            if not _task_exists(conn, task_id):
                return f"Error: Task with ID {task_id} not found."
            conn.execute(
                "UPDATE tasks SET notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (markdown_text, task_id),
            )
            return f"Notes updated for task {task_id}."
    except Exception as e:
        return f"Error updating notes: {str(e)}"


# ── Subtasks / Checklist ─────────────────────────────────────────────────────

@mcp.tool()
def add_subtask(parent_id: int, title: str) -> str:
    """Add a subtask / checklist item to a parent task."""
    try:
        with get_db() as conn:
            if not _task_exists(conn, parent_id):
                return f"Error: Parent task with ID {parent_id} not found."
            # Auto-set sort_order
            row = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM subtasks WHERE parent_id = ?",
                (parent_id,),
            ).fetchone()
            next_order = row["next_order"]
            cur = conn.execute(
                "INSERT INTO subtasks (parent_id, title, sort_order) VALUES (?, ?, ?)",
                (parent_id, title, next_order),
            )
            return f"Subtask added with ID {cur.lastrowid} under task {parent_id}."
    except Exception as e:
        return f"Error adding subtask: {str(e)}"


@mcp.tool()
def toggle_subtask(subtask_id: int) -> str:
    """Toggle a subtask's completion state (done ↔ not done)."""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_completed FROM subtasks WHERE id = ?", (subtask_id,)
            ).fetchone()
            if not row:
                return f"Error: Subtask with ID {subtask_id} not found."
            new_state = 0 if row["is_completed"] else 1
            conn.execute(
                "UPDATE subtasks SET is_completed = ? WHERE id = ?",
                (new_state, subtask_id),
            )
            label = "completed" if new_state else "not completed"
            return f"Subtask {subtask_id} marked as {label}."
    except Exception as e:
        return f"Error toggling subtask: {str(e)}"


@mcp.tool()
def delete_subtask(subtask_id: int) -> str:
    """Delete a subtask by ID."""
    try:
        with get_db() as conn:
            cur = conn.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))
            if cur.rowcount == 0:
                return f"Error: Subtask with ID {subtask_id} not found."
            return f"Subtask {subtask_id} deleted."
    except Exception as e:
        return f"Error deleting subtask: {str(e)}"


@mcp.tool()
def list_subtasks(parent_id: int) -> str:
    """List all subtasks / checklist items for a parent task."""
    try:
        with get_db() as conn:
            if not _task_exists(conn, parent_id):
                return f"Error: Task with ID {parent_id} not found."
            rows = conn.execute(
                "SELECT * FROM subtasks WHERE parent_id = ? ORDER BY sort_order",
                (parent_id,),
            ).fetchall()
            if not rows:
                return f"No subtasks found for task {parent_id}."
            return json.dumps([dict(r) for r in rows], indent=2)
    except Exception as e:
        return f"Error listing subtasks: {str(e)}"


# ── Lists / Projects ─────────────────────────────────────────────────────────

@mcp.tool()
def create_list(name: str, description: str = "") -> str:
    """Create a new list / project for organising tasks."""
    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO lists (name, description) VALUES (?, ?)",
                (name, description),
            )
            return f"List '{name}' created with ID {cur.lastrowid}."
    except sqlite3.IntegrityError:
        return f"Error: A list named '{name}' already exists."
    except Exception as e:
        return f"Error creating list: {str(e)}"


@mcp.tool()
def delete_list(list_id: int) -> str:
    """Delete a list / project. Tasks in the list are NOT deleted – their
    list_id is set to NULL."""
    try:
        with get_db() as conn:
            cur = conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
            if cur.rowcount == 0:
                return f"Error: List with ID {list_id} not found."
            return f"List {list_id} deleted. Tasks previously in this list are now unassigned."
    except Exception as e:
        return f"Error deleting list: {str(e)}"


@mcp.tool()
def move_task_to_list(task_id: int, list_id: int) -> str:
    """Move a task into a list / project. Use list_id = 0 to unassign."""
    try:
        with get_db() as conn:
            if not _task_exists(conn, task_id):
                return f"Error: Task with ID {task_id} not found."
            if list_id == 0:
                conn.execute(
                    "UPDATE tasks SET list_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (task_id,),
                )
                return f"Task {task_id} removed from its list."
            # Verify list exists
            if not conn.execute("SELECT 1 FROM lists WHERE id = ?", (list_id,)).fetchone():
                return f"Error: List with ID {list_id} not found."
            conn.execute(
                "UPDATE tasks SET list_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (list_id, task_id),
            )
            return f"Task {task_id} moved to list {list_id}."
    except Exception as e:
        return f"Error moving task: {str(e)}"


@mcp.tool()
def list_tasks_in_list(list_id: int) -> str:
    """List all tasks in a given list / project, sorted by priority then due date."""
    try:
        with get_db() as conn:
            if not conn.execute("SELECT 1 FROM lists WHERE id = ?", (list_id,)).fetchone():
                return f"Error: List with ID {list_id} not found."
            rows = conn.execute(
                '''SELECT * FROM tasks WHERE list_id = ?
                   ORDER BY
                       CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                       due_date ASC''',
                (list_id,),
            ).fetchall()
            if not rows:
                return f"No tasks found in list {list_id}."
            return json.dumps([dict(r) for r in rows], indent=2)
    except Exception as e:
        return f"Error listing tasks: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    mcp.run(transport='stdio')
