# %%

import os
import sys

import pandas as pd
from utils.display_tools import pprint_df, pprint_dict
from utils.sqlite_tools import (
    add_task,
    backup_database_as_csv,
    create_connection,
    edit_task,
    get_task_details,
    get_tasks,
    initialize_database,
    update_task_status,
)

# %%
# Variables #

grandparent_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
data_dir = os.path.join(grandparent_dir, "data")
ls_swim_lanes = ["priority", "backlog", "todo", "prog", "validation", "done"]

print(f"Python Version: {sys.version}")


# %%
# Terminal Tools #


def print_tasks(conn):
    df_tasks = get_tasks(conn)

    df_display_tasks = pd.DataFrame(columns=ls_swim_lanes)
    for i, row in df_tasks.iterrows():
        task_id = row["id"]
        category = row["category"]
        title = row["title"]
        status = row["status"]
        priority = row["priority"]
        df_display_tasks.loc[i, status] = f"({task_id}) {category} - {title}"
        df_display_tasks.loc[i, "priority"] = priority

    df_display_tasks = df_display_tasks.sort_values(by="priority")

    # Use infer_objects() to infer better types
    df_display_tasks = df_display_tasks.infer_objects()
    df_display_tasks = df_display_tasks.fillna("")
    pprint_df(df_display_tasks)


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


def process_cli_command(conn, command):
    command = command.lower()
    if command == "print":
        print_tasks(conn)
    elif command == "exit":
        print("Connection closing.")
    elif command.startswith("cat "):
        task_id = int(command.split(" ")[1])
        print_task_details(conn, task_id)
    elif command.startswith("mv "):
        task_id = int(command.split(" ")[1])
        status = command.split(" ")[2]
        change_task_status(conn, task_id, status)
    elif command == "add":
        add_task_wizard(conn)
    elif command.startswith("edit "):
        task_id = int(command.split(" ")[1])
        edit_a_task(conn, task_id)
    else:
        print("Invalid command.")


def print_help_text():
    print("Commands:")
    print("print -- print tasks")
    print("cat <task_id> -- print task details")
    print("mv <task_id> <status> -- move task to status")
    print("add -- add a task")
    print("exit -- exit the program")
    print("edit <task_id> -- edit a task")
    print("")


# %%
# Main #


def main():
    database = os.path.join(data_dir, "tasks.db")
    initialize_database(database)
    conn = create_connection(database)

    if conn is not None:
        while True:
            # clear screen
            os.system("cls" if os.name == "nt" else "clear")
            print_tasks(conn)
            print_help_text()
            command = input("Enter a command: ")
            process_cli_command(conn, command)
            if command == "exit":
                break
            elif command.startswith("cat"):
                # wait so output can be seen
                input("Press Enter to continue...")

        backup_database_as_csv(conn)
        conn.close()


# %%
# Main #


if __name__ == "__main__":
    main()

# %%
