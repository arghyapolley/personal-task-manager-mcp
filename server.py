from typing import Any, Optional
import sqlite3
import json
import os
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("Personal Task Management")

DB_PATH = "tasks.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            due_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

@mcp.tool()
def get_schema() -> str:
    """Get the schema of the tasks database. Useful for constructing SQL queries."""
    return '''CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending', -- Can be 'pending', 'in_progress', 'completed'
    due_date TEXT,                 -- Format: YYYY-MM-DD
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)'''

@mcp.tool()
def run_select_query(query: str) -> str:
    """Run a read-only SQL SELECT query on the tasks database. This is used to query tasks in natural language (by generating SQL)."""
    if not query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        result = [dict(row) for row in rows]
        conn.close()
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error executing query: {str(e)}"

@mcp.tool()
def add_task(title: str, description: str = "", due_date: str = "") -> str:
    """Add a new task to the task management system."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tasks (title, description, due_date)
            VALUES (?, ?, ?)
        ''', (title, description, due_date))
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()
        return f"Task added successfully with ID {task_id}"
    except Exception as e:
        return f"Error adding task: {str(e)}"

@mcp.tool()
def update_task(task_id: int, status: Optional[str] = None, title: Optional[str] = None, description: Optional[str] = None, due_date: Optional[str] = None) -> str:
    """Update an existing task in the system. Only provide the arguments you want to change."""
    updates = []
    params = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if due_date is not None:
        updates.append("due_date = ?")
        params.append(due_date)
        
    if not updates:
        return "No updates provided."
        
    updates.append("updated_at = CURRENT_TIMESTAMP")
    
    query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
    params.append(task_id)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        if cursor.rowcount == 0:
            conn.close()
            return f"Error: Task with ID {task_id} not found."
        conn.close()
        return f"Task {task_id} updated successfully."
    except Exception as e:
        return f"Error updating task: {str(e)}"

@mcp.tool()
def delete_task(task_id: int) -> str:
    """Delete a task from the system by ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        if cursor.rowcount == 0:
            conn.close()
            return f"Error: Task with ID {task_id} not found."
        conn.close()
        return f"Task {task_id} deleted successfully."
    except Exception as e:
        return f"Error deleting task: {str(e)}"

if __name__ == "__main__":
    init_db()
    mcp.run(transport='stdio')
