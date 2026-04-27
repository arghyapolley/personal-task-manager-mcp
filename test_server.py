from server import init_db, add_task, run_select_query, get_schema, update_task, delete_task

def test():
    # Initialize DB
    init_db()
    print("DB initialized")
    
    # Check schema
    schema = get_schema()
    print("Schema:", schema[:50], "...")
    
    # Add a task
    res = add_task(title="Buy milk", description="Need to buy milk from the store", due_date="2026-05-01")
    print("Add Task Result:", res)
    
    # Run a select query
    res2 = run_select_query("SELECT * FROM tasks;")
    print("Query Result:", res2)
    
    # Update the task
    res3 = update_task(task_id=1, status="completed")
    print("Update Result:", res3)
    
    # Delete the task
    res4 = delete_task(task_id=1)
    print("Delete Result:", res4)

if __name__ == "__main__":
    test()
