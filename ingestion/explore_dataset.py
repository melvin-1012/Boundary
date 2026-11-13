import pandas as pd
from pathlib import Path

DATA_DIR = Path("data/raw")


def inspect_csv(file_path):

    print("\n" + "=" * 65)
    print("FILE:", file_path.name)
    print("=" * 65)

    df = pd.read_csv(file_path)

    print("\nShape:")
    print(df.shape)

    print("\nColumns:")
    print(df.columns.tolist())

    print("\nData types:")
    print(df.dtypes)

    print("\nMissing values:")
    print(df.isnull().sum())

    print("\nDuplicate rows:")
    print(df.duplicated().sum())

    print("\nFirst 5 records:")
    print(df.head())


def main():

    csv_files = list(DATA_DIR.glob("*.csv"))

    if not csv_files:
        print("No CSV files found in data/raw/")
        return

    for file_path in csv_files:
        inspect_csv(file_path)


if __name__ == "__main__":
    main()