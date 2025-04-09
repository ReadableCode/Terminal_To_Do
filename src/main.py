# %%

import datetime
import json
import os
import platform
import sqlite3
import sys

import pandas as pd
from utils.display_tools import pprint_df, pprint_dict, pprint_ls  # noqa F401
from utils.s3_tools import (  # noqa F401
    download_file_from_s3,
    ensure_bucket_exists,
    upload_file_to_s3,
)

# %%
# Variables #

APP_NAME = "terminal_to_do"
STORAGE_BUCKET_NAME = "terminal-to-do"

grandparent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


# %%
# Config #


def merge_configs(default_config, user_config):
    """
    Recursively merges user configuration into the default configuration.
    If a key exists in both, the user's value will override the default.
    If a key exists only in the default, it will be retained.

    Args:
        default_config (dict): The default configuration.
        user_config (dict): The user configuration.

    Returns:
        dict: The merged configuration.
    """
    for key, value in default_config.items():
        if key not in user_config:
            # If the key is not in the user config, set it to the default
            user_config[key] = value
        elif isinstance(value, dict) and isinstance(user_config.get(key), dict):
            # If both default and user config have a dictionary for this key, recurse
            user_config[key] = merge_configs(value, user_config[key])
    return user_config


def load_config(app_name=APP_NAME):
    """
    Load the configuration file for the application.
    If no config is found, it loads the default config from the repo.
    User config is merged with the defaults from the repo if any keys are missing.

    Returns:
        config (dict): Merged configuration loaded from the file.
    """
    # Determine base directories for configuration files
    system = platform.system()

    if system == "Windows":
        config_home = os.path.join(os.getenv("APPDATA"), app_name)
    else:
        config_home = os.path.expanduser(f"~/.config/{app_name}")

    # User-specific config
    user_config_path = os.path.join(config_home, f"{app_name}_config.json")

    # Paths to check for configuration (first user-specific, then system-wide)
    ls_paths_to_check_for_config = [user_config_path]

    # Path to the default config in the repo
    repo_default_config_path = os.path.join(
        grandparent_dir, f"{app_name}_config_defaults.json"
    )

    # Ensure the user config directory exists
    if not os.path.exists(config_home):
        os.makedirs(config_home)

    # Load the default configuration from the repository
    with open(repo_default_config_path, "r") as default_file:
        default_config = json.load(default_file)

    # If no configuration file exists, create one from the default config
    if not any(os.path.exists(path) for path in ls_paths_to_check_for_config):
        print("No user configuration file found. Creating one with defaults.")
        with open(ls_paths_to_check_for_config[0], "w") as f:
            json.dump(default_config, f, indent=4)

    # Load the user configuration if it exists
    user_config = {}
    for config_path in ls_paths_to_check_for_config:
        if os.path.exists(config_path):
            print(f"Using user configuration file: {config_path}")
            with open(config_path, "r") as f:
                user_config = json.load(f)
            break

    # Merge user config with default config (without additional imports)
    config = merge_configs(default_config, user_config)

    # Return the merged configuration
    return config


# %%
# Database Interactions: SQLite #


def get_sqlite_connection(db_file):
    print(f"Connecting to SQLite database: {db_file}")

    if not os.path.exists(db_file):
        print(f"Database file {db_file} does not exist. Creating a new database.")
    conn = sqlite3.connect(db_file)

    # make sure the table exists
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

    return conn


# %%
# Functions: Transactions #


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
# Terminal Tools #


def print_header(task_description):
    print("Terminal-To-Do")
    print("-" * 30)
    print(f"Running with Python version: {sys.version}")
    if task_description != "":
        print(f"Most recent command: {task_description}")


def print_tasks(conn, config):
    # Get the tasks from the database
    df_tasks = get_tasks(conn)

    # if empty then print empty
    if df_tasks.empty:
        print("--- No tasks found ---")
        return

    df_tasks = df_tasks.sort_values(by=["priority"])

    # Create a dictionary with swim lanes as keys and empty lists as values
    # dict_swim_lanes[priority][swim_lane]
    dict_swim_lanes = {}

    # Populate the dictionary with tasks based on their status (swim lane)
    for _, row in df_tasks.iterrows():
        priority = row["priority"]
        task_id = row["id"]
        category = row["category"]
        title = row["title"]
        status = row["status"]

        if status in config["hide_cols"]:
            continue

        # make sure the priority and swim lane exist in the dataframe
        if priority not in dict_swim_lanes:
            dict_swim_lanes[priority] = {}

        # make sure the status exists in the dataframe for this priority
        if status not in dict_swim_lanes[priority]:
            dict_swim_lanes[priority][status] = []

        # add the task to the swim lane
        dict_swim_lanes[priority][status].append(f"{task_id}: {category} - {title}")

    ls_rows_for_dataframe = []
    for priority, dict_statuses_this_priority in dict_swim_lanes.items():
        longest_list = max([len(v) for v in dict_statuses_this_priority.values()])
        for i in range(longest_list):
            dict_this_row = {}
            dict_this_row["priority"] = priority
            for status in df_tasks["status"].unique().tolist():
                if status in dict_statuses_this_priority:
                    if i < len(dict_statuses_this_priority[status]):
                        dict_this_row[status] = dict_statuses_this_priority[status][i]
                    else:
                        dict_this_row[status] = ""
                else:
                    dict_this_row[status] = ""
            ls_rows_for_dataframe.append(dict_this_row)

        # append a row for a divider
        dict_this_row = {}
        dict_this_row["priority"] = "-" * 30
        for status in df_tasks["status"].unique().tolist():
            dict_this_row[status] = "-" * 30
        ls_rows_for_dataframe.append(dict_this_row)

    # turn the list of dictionaries into a dataframe
    df_swim_lanes = pd.DataFrame(ls_rows_for_dataframe)
    # set col order to swim lanes then any not in swim lanes
    ls_cols_to_print = config["swim_lanes"] + [
        col
        for col in df_swim_lanes.columns
        if col not in config["swim_lanes"] and col not in config["hide_cols"]
    ]
    # prevent cols that dont exist from throwing errors
    df_swim_lanes = df_swim_lanes[
        [col for col in ls_cols_to_print if col in df_swim_lanes.columns]
    ]
    pprint_df(df_swim_lanes)


def print_task_details(conn, task_id):
    task = get_task_details(conn, task_id)
    pprint_dict(task)


def change_task_status(conn, task_id, status):
    update_task_status(conn, task_id, status)
    print(f"Task {task_id} status updated to {status}.")


def edit_a_task(conn, task_id):
    task = get_task_details(conn, task_id)
    pprint_dict(task)

    # get priority
    priority = task["priority"]
    priority = int(input(f"Enter the priority (default:[{priority}]): ") or priority)

    # get category
    category = task["category"]
    category = input(f"Enter the category (default:[{category}]): ") or category

    # get title
    title = task["title"]
    title = input(f"Enter the title (default:[{title}]): ") or title

    # get description
    description = task["description"]
    description = (
        input(f"Enter the description (default:[{description}]): ") or description
    )

    # get status
    status = task["status"]
    status = input(f"Enter the status (default:[{status}]): ") or status

    edit_task(conn, task_id, priority, category, title, description, status)


def add_task_wizard(conn):
    # get priority default 2
    priority = 2
    priority = int(input(f"Enter the priority (default:[{priority}]): ") or priority)

    # get category
    category = ""
    category = input("Enter the category: ") or category

    # get title
    title = input("Enter the title: ")

    # get description
    description = ""
    description = input("Enter the description: ") or description

    # get status default "backlog"
    status = "backlog"
    status = input(f"Enter the status (default:[{status}]): ") or status

    add_task(conn, priority, category, title, description, status)


def process_cli_command(conn, command, config):
    command = command.lower()
    task_description = ""
    if command == "print":
        print_tasks(conn, config)
    elif command == "exit":
        print("Connection closing.")
    elif command.startswith("cat "):
        task_id = int(command.split(" ")[1])
        print_task_details(conn, task_id)
    elif command.startswith("mv "):
        task_id = int(command.split(" ")[1])
        status = command.split(" ")[2]
        task_description = f"Task {task_id} status updated to {status}."
        change_task_status(conn, task_id, status)
    elif command == "add":
        add_task_wizard(conn)
    elif command.startswith("edit "):
        task_id = int(command.split(" ")[1])
        edit_a_task(conn, task_id)
    elif command == "help":
        print_help_text()
    elif command == "show config":
        pprint_dict(config)
    else:
        print("Invalid command.")
    return task_description


def print_help_text():
    print("Commands:")
    print("print -- print tasks")
    print("cat <task_id> -- print task details")
    print("mv <task_id> <status> -- move task to status")
    print("add -- add a task")
    print("exit -- exit the program")
    print("edit <task_id> -- edit a task")
    print("help -- print this help text")
    print("show config -- print the configuration")
    print("")


# %%
# Main #


def main():
    config = load_config(APP_NAME)
    pprint_dict(config)

    sqlite_db_file_path = os.path.join(data_dir, "tasks.db")

    # download sqlite from s3
    ensure_bucket_exists(STORAGE_BUCKET_NAME)
    print("Downloading sqlite from s3...")
    download_file_from_s3(
        STORAGE_BUCKET_NAME,
        "tasks.db",
        sqlite_db_file_path,
    )
    print("Download complete.")

    conn = get_sqlite_connection(sqlite_db_file_path)
    task_description = ""

    if conn is not None:
        while True:
            # clear screen
            # os.system("cls" if os.name == "nt" else "clear")
            print_header(task_description)
            print_tasks(conn, config)
            print_help_text()
            command = input("Enter a command: ")
            task_description = process_cli_command(conn, command, config)
            if command == "exit":
                break
            elif (
                command.startswith("cat")
                or command.startswith("show")
                or command.startswith("help")
            ):
                # wait so output can be seen
                input("Press Enter to continue...")

        backup_database_as_csv(conn)
        conn.close()

        print("Reuploading sqlite to s3...")
        # reupload sqlite to s3
        upload_file_to_s3(
            sqlite_db_file_path,
            STORAGE_BUCKET_NAME,
            "tasks.db",
        )
        print("Reupload complete.")


# %%
# Main #


if __name__ == "__main__":
    main()

# %%
