# %%
# Imports #

import datetime
import os

import pandas as pd
from readable_utils.display_tools import pprint_df, print_logger  # noqa: F401
from readable_utils.s3_tools import (
    download_file_from_s3,
    ensure_bucket_exists,
    list_bucket_contents,
    upload_file_to_s3,
)

# %%
# Tests #


def test_write_to_bucket(tmp_path):
    current_datetime_string = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # create dataframe
    df = pd.DataFrame(
        {
            "A": [1, 2, 3, 4],
            "B": [5, 6, 7, 8],
            "C": [9, 10, 11, 12],
            "Datetime": [
                current_datetime_string,
                current_datetime_string,
                current_datetime_string,
                current_datetime_string,
            ],
        }
    )
    pprint_df(df)

    # write to a temp dir as csv
    df.to_csv(os.path.join(tmp_path, "test.csv"), index=False)

    # ensure bucket
    ensure_bucket_exists("test-bucket")
    # list bucket contents
    list_bucket_contents("test-bucket")

    # upload to s3
    upload_file_to_s3(
        os.path.join(tmp_path, "test.csv"),  # local file path
        "test-bucket",  # bucket name
        "test.csv",  # S3 key (remote filename)
    )

    # download from s3
    download_file_from_s3(
        "test-bucket",
        "test.csv",
        os.path.join(tmp_path, "test_downloaded.csv"),
    )
    # read from s3
    df_re_read = pd.read_csv(
        os.path.join(tmp_path, "test_downloaded.csv"),
    )
    print("Re-read DataFrame")
    pprint_df(df_re_read.head())

    # Convert both the current_datetime_string and the Datetime column values to datetime objects
    sheet_datetimes = [
        datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
        for dt in df["Datetime"].values.tolist()
    ]
    current_datetime_parsed = datetime.datetime.strptime(
        current_datetime_string, "%Y-%m-%d %H:%M:%S"
    )

    # check that datetime in dataframe columns
    assert current_datetime_parsed in sheet_datetimes


# %%
