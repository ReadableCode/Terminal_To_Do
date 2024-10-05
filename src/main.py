# %%

import json
import os
import platform
import sys

import pandas as pd
from utils.display_tools import pprint_df, pprint_dict, pprint_ls  # noqa F401
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

APP_NAME = "terminal_to_do"
grandparent_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
data_dir = os.path.join(grandparent_dir, "data")


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
# Terminal Tools #


def print_header():
    print("Terminal-To-Do")
    print("-" * 30)
    print(f"Running with Python version: {sys.version}")


def print_tasks(conn, config):
    # Get the tasks from the database
    df_tasks = get_tasks(conn)
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
    df_swim_lanes = df_swim_lanes[
        config["swim_lanes"]
        + [
            col
            for col in df_swim_lanes.columns
            if col not in config["swim_lanes"] and col not in config["hide_cols"]
        ]
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
    config = load_config(APP_NAME)
    pprint_dict(config)

    database = os.path.join(data_dir, "tasks.db")
    initialize_database(database)
    conn = create_connection(database)

    if conn is not None:
        while True:
            # clear screen
            os.system("cls" if os.name == "nt" else "clear")
            # temp
            pprint_dict(config)
            print_header()
            print_tasks(conn, config)
            print_help_text()
            command = input("Enter a command: ")
            process_cli_command(conn, command, config)
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
