"""
Comprehensive tests for the Personal Task Manager MCP Server.
Tests all Tier 1 features: priorities, status workflow, tags, notes, subtasks, lists.
Uses a temporary DB to avoid polluting production data.
"""
import os
import sys
import json
import tempfile

# ── Point the server at a temp DB ────────────────────────────────────────────
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
TMP_DB = _tmp.name

import server as srv
srv.DB_PATH = TMP_DB

# ── Helpers ───────────────────────────────────────────────────────────────────
passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅  {label}")
    else:
        failed += 1
        print(f"  ❌  {label}  —  {detail}")


def section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_init_and_schema():
    section("Database Init & Schema")
    srv.init_db()
    schema = srv.get_schema()
    check("Schema contains tasks table", "CREATE TABLE tasks" in schema)
    check("Schema contains tags table", "CREATE TABLE tags" in schema)
    check("Schema contains subtasks table", "CREATE TABLE subtasks" in schema)
    check("Schema contains lists table", "CREATE TABLE lists" in schema)
    check("Schema contains task_tags table", "CREATE TABLE task_tags" in schema)


def test_add_task():
    section("Add Task (with new fields)")
    res = srv.add_task(title="Write tests", description="Unit tests for MCP", due_date="2026-05-10", priority="high")
    check("Add task succeeds", "successfully" in res)

    res2 = srv.add_task(title="Buy groceries", priority="low")
    check("Add low-priority task", "successfully" in res2)

    res3 = srv.add_task(title="Invalid priority", priority="critical")
    check("Reject invalid priority", "Error" in res3)


def test_set_due_date():
    section("Due Dates & Deadlines")
    res = srv.set_due_date(task_id=1, due_date="2026-06-01")
    check("Set due date", "set to 2026-06-01" in res)

    res2 = srv.set_due_date(task_id=1, due_date="")
    check("Clear due date", "cleared" in res2)

    res3 = srv.set_due_date(task_id=999, due_date="2026-01-01")
    check("Reject missing task", "not found" in res3)


def test_set_priority():
    section("Priorities")
    res = srv.set_priority(task_id=1, level="low")
    check("Set priority to low", "'low'" in res)

    res2 = srv.set_priority(task_id=1, level="HIGH")
    check("Case-insensitive priority", "'high'" in res2)

    res3 = srv.set_priority(task_id=1, level="critical")
    check("Reject invalid priority", "Error" in res3)

    res4 = srv.set_priority(task_id=999, level="high")
    check("Reject missing task", "not found" in res4)


def test_set_status():
    section("Status Workflow")
    for s in ["todo", "in_progress", "blocked", "done", "archived"]:
        res = srv.set_status(task_id=1, status=s)
        check(f"Set status '{s}'", f"'{s}'" in res)

    res2 = srv.set_status(task_id=1, status="cancelled")
    check("Reject invalid status", "Error" in res2)

    # Reset to todo for later tests
    srv.set_status(task_id=1, status="todo")


def test_tags():
    section("Tags / Labels")
    res = srv.add_tag(task_id=1, tag="work")
    check("Add tag 'work'", "'work' added" in res)

    res2 = srv.add_tag(task_id=1, tag="urgent")
    check("Add tag 'urgent'", "'urgent' added" in res2)

    # Duplicate tag is idempotent
    res3 = srv.add_tag(task_id=1, tag="work")
    check("Duplicate tag is OK", "'work' added" in res3)

    # Add same tag to task 2
    srv.add_tag(task_id=2, tag="work")

    res4 = srv.list_by_tag(tag="work")
    tasks = json.loads(res4)
    check("list_by_tag returns 2 tasks", len(tasks) == 2)

    res5 = srv.remove_tag(task_id=1, tag="work")
    check("Remove tag", "removed" in res5)

    res6 = srv.list_by_tag(tag="work")
    tasks2 = json.loads(res6)
    check("After removal, 1 task left", len(tasks2) == 1)

    res7 = srv.add_tag(task_id=999, tag="oops")
    check("Reject tag on missing task", "not found" in res7)

    res8 = srv.add_tag(task_id=1, tag="")
    check("Reject empty tag", "Error" in res8)


def test_notes():
    section("Notes & Descriptions")
    md = "## Meeting Notes\n- Discussed roadmap\n- Action items below"
    res = srv.update_notes(task_id=1, markdown_text=md)
    check("Update notes", "updated" in res)

    # Verify via query
    q = srv.run_select_query("SELECT notes FROM tasks WHERE id = 1")
    data = json.loads(q)
    check("Notes persisted", "Meeting Notes" in data[0]["notes"])

    res2 = srv.update_notes(task_id=999, markdown_text="nope")
    check("Reject notes on missing task", "not found" in res2)


def test_subtasks():
    section("Subtasks / Checklist")
    res = srv.add_subtask(parent_id=1, title="Write unit tests")
    check("Add subtask 1", "Subtask added" in res)

    res2 = srv.add_subtask(parent_id=1, title="Update README")
    check("Add subtask 2", "Subtask added" in res2)

    res3 = srv.list_subtasks(parent_id=1)
    items = json.loads(res3)
    check("List subtasks returns 2", len(items) == 2)
    check("Subtasks are ordered", items[0]["sort_order"] < items[1]["sort_order"])

    sub_id = items[0]["id"]
    res4 = srv.toggle_subtask(subtask_id=sub_id)
    check("Toggle subtask → completed", "completed" in res4)

    res5 = srv.toggle_subtask(subtask_id=sub_id)
    check("Toggle subtask → not completed", "not completed" in res5)

    res6 = srv.delete_subtask(subtask_id=sub_id)
    check("Delete subtask", "deleted" in res6)

    res7 = srv.list_subtasks(parent_id=1)
    items2 = json.loads(res7)
    check("After delete, 1 subtask left", len(items2) == 1)

    res8 = srv.add_subtask(parent_id=999, title="nope")
    check("Reject subtask on missing parent", "not found" in res8)

    res9 = srv.toggle_subtask(subtask_id=999)
    check("Reject toggle on missing subtask", "not found" in res9)


def test_lists():
    section("Lists / Projects")
    res = srv.create_list(name="Work", description="Office tasks")
    check("Create list 'Work'", "created" in res)

    res2 = srv.create_list(name="Personal")
    check("Create list 'Personal'", "created" in res2)

    res3 = srv.create_list(name="Work")
    check("Reject duplicate list", "Error" in res3)

    res4 = srv.move_task_to_list(task_id=1, list_id=1)
    check("Move task 1 to Work", "moved" in res4)

    res5 = srv.move_task_to_list(task_id=2, list_id=1)
    check("Move task 2 to Work", "moved" in res5)

    res6 = srv.list_tasks_in_list(list_id=1)
    tasks = json.loads(res6)
    check("List tasks in Work → 2 tasks", len(tasks) == 2)

    res7 = srv.move_task_to_list(task_id=2, list_id=0)
    check("Unassign task from list", "removed" in res7)

    res8 = srv.list_tasks_in_list(list_id=1)
    tasks2 = json.loads(res8)
    check("After unassign → 1 task in Work", len(tasks2) == 1)

    res9 = srv.delete_list(list_id=2)
    check("Delete list", "deleted" in res9)

    res10 = srv.delete_list(list_id=999)
    check("Reject delete missing list", "not found" in res10)

    res11 = srv.move_task_to_list(task_id=999, list_id=1)
    check("Reject move missing task", "not found" in res11)

    res12 = srv.move_task_to_list(task_id=1, list_id=999)
    check("Reject move to missing list", "not found" in res12)


def test_update_task_extended():
    section("Update Task (extended fields)")
    res = srv.update_task(task_id=1, priority="low", status="in_progress", notes="WIP")
    check("Update multiple fields", "updated" in res)

    q = srv.run_select_query("SELECT priority, status, notes FROM tasks WHERE id = 1")
    data = json.loads(q)
    check("Priority persisted", data[0]["priority"] == "low")
    check("Status persisted", data[0]["status"] == "in_progress")
    check("Notes persisted", data[0]["notes"] == "WIP")

    res2 = srv.update_task(task_id=1, status="invalid_status")
    check("Reject invalid status in update", "Error" in res2)

    res3 = srv.update_task(task_id=1, priority="invalid")
    check("Reject invalid priority in update", "Error" in res3)


def test_delete_cascades():
    section("Delete Cascades")
    # Add a fresh task with subtasks and tags
    srv.add_task(title="Cascade test")
    q = srv.run_select_query("SELECT MAX(id) as mid FROM tasks")
    tid = json.loads(q)[0]["mid"]
    srv.add_subtask(parent_id=tid, title="Sub A")
    srv.add_subtask(parent_id=tid, title="Sub B")
    srv.add_tag(task_id=tid, tag="cascade_test")

    srv.delete_task(task_id=tid)

    subs = srv.run_select_query(f"SELECT * FROM subtasks WHERE parent_id = {tid}")
    check("Subtasks cascaded on delete", json.loads(subs) == [])

    ttags = srv.run_select_query(f"SELECT * FROM task_tags WHERE task_id = {tid}")
    check("Task-tags cascaded on delete", json.loads(ttags) == [])


def test_select_query():
    section("Read-only Query Guard")
    res = srv.run_select_query("DELETE FROM tasks WHERE id = 1")
    check("Reject non-SELECT query", "Error" in res)


# ═══════════════════════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        test_init_and_schema()
        test_add_task()
        test_set_due_date()
        test_set_priority()
        test_set_status()
        test_tags()
        test_notes()
        test_subtasks()
        test_lists()
        test_update_task_extended()
        test_delete_cascades()
        test_select_query()

        print(f"\n{'═' * 60}")
        print(f"  Results:  {passed} passed,  {failed} failed")
        print(f"{'═' * 60}\n")
        sys.exit(1 if failed else 0)
    finally:
        # Cleanup temp DB
        try:
            os.unlink(TMP_DB)
        except OSError:
            pass
