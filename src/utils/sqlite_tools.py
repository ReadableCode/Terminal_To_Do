# %%
# Imports #

import datetime
import os
import sqlite3
from sqlite3 import Error

import pandas as pd

# %%
# Variables #

grandparent_dir = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
)
data_dir = os.path.join(grandparent_dir, "data")


# %%
# Functions #


def create_connection(db_file):
    """Create a database connection to an SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        print(f"Connected to SQLite database: {db_file}")
    except Error as e:
        print(f"Error: {e}")
    return conn


def create_table(conn):
    """Create a table for tasks if it doesn't exist."""
    try:
        sql_create_tasks_table = """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            priority INTEGER DEFAULT 0,
            category TEXT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL
        );
        """
        cursor = conn.cursor()
        cursor.execute(sql_create_tasks_table)
        print("Tasks table created or already exists.")
    except Error as e:
        print(f"Error: {e}")


def initialize_database(db_file):
    """Initialize the database and create the tasks table."""
    if not os.path.exists(db_file):
        conn = create_connection(db_file)
        if conn is not None:
            create_table(conn)
            conn.close()
        else:
            print("Error! Cannot create the database connection.")
    else:
        print("Database already exists.")


def add_task(conn, priority, category, title, description, status):
    """Add a new task to the tasks table.

    Args:
        conn (sqlite3.Connection): The SQLite database connection.
        priority (int): The priority of the task.
        category (str): The category of the task.
        title (str): The title of the task.
        description (str): The description of the task.
        status (str): The status of the task.

    """
    sql = """
    INSERT INTO tasks (priority, category, title, description, status) 
    VALUES (?, ?, ?, ?, ?);
    """
    cursor = conn.cursor()
    cursor.execute(sql, (priority, category, title, description, status))
    conn.commit()
    print("Task added successfully.")


def edit_task(conn, task_id, priority, category, title, description, status):
    """Edit an existing task in the tasks table.

    Args:
        conn (sqlite3.Connection): The SQLite database connection.
        task_id (int): The id of the task to edit.
        priority (int): The priority of the task.
        category (str): The category of the task.
        title (str): The title of the task.
        description (str): The description of the task.
        status (str): The status of the task.

    """
    sql = """
    UPDATE tasks 
    SET priority = ?, category = ?, title = ?, description = ?, status = ?
    WHERE id = ?;
    """
    cursor = conn.cursor()
    cursor.execute(sql, (priority, category, title, description, status, task_id))
    conn.commit()
    print("Task edited successfully.")


def get_tasks(conn):
    """Retrieve all tasks from the tasks table as a list of dictionaries."""
    sql = """SELECT * FROM tasks;"""
    cursor = conn.cursor()
    cursor.execute(sql)
    # get with pandas
    tasks = pd.read_sql_query(sql, conn)

    return tasks


def get_task_details(conn, task_id):
    """Retrieve the details of a task by task_id."""
    sql = """SELECT * FROM tasks WHERE id = ?;"""
    cursor = conn.cursor()
    cursor.execute(sql, (task_id,))
    task = cursor.fetchone()
    # convert to dict
    task = {
        "id": task[0],
        "priority": task[1],
        "category": task[2],
        "title": task[3],
        "description": task[4],
        "status": task[5],
    }
    return task


def update_task_status(conn, task_id, status):
    """Update the status of a task."""
    sql = """UPDATE tasks SET status = ? WHERE id = ?;"""
    cursor = conn.cursor()
    cursor.execute(sql, (status, task_id))
    conn.commit()
    print("Task status updated successfully.")


def delete_task(conn, task_id):
    """Delete a task by task_id."""
    sql = """DELETE FROM tasks WHERE id = ?;"""
    cursor = conn.cursor()
    cursor.execute(sql, (task_id,))
    conn.commit()
    print("Task deleted successfully.")


def backup_database_as_csv(conn):
    """Backup the database as a CSV file."""
    tasks = get_tasks(conn)
    current_date_stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    archive_dir = os.path.join(data_dir, "archive")
    # mkdirs
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir, exist_ok=True)
    tasks.to_csv(os.path.join(data_dir, "tasks_backup_most_recent.csv"), index=False)
    tasks.to_csv(
        os.path.join(data_dir, "archive", f"tasks_backup_{current_date_stamp}.csv"),
        index=False,
    )
    conn.close()
    print("Database backed up as CSV.")


# %%
