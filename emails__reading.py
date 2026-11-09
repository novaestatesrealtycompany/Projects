
import pandas as pd
import re
import os

EMPLOYEE_FILE = "synopsys_all_employees.csv"
CONTACT_FILE = "public_contacts.csv"

OUTPUT_FILE = "synopsys_employees_with_emails.csv"


def normalize_url(url):
    if pd.isna(url):
        return ""

    return str(url).strip().rstrip("/").lower()


def valid_email(email):

    if pd.isna(email):
        return False

    email = str(email).strip()

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            email
        )
    )


def main():

    if not os.path.exists(EMPLOYEE_FILE):
        print("Employee CSV not found.")
        return

    if not os.path.exists(CONTACT_FILE):
        print("Contact CSV not found.")
        print(
            "Create public_contacts.csv with columns: "
            "profile_url,email,email_source"
        )
        return

    employees = pd.read_csv(EMPLOYEE_FILE)

    contacts = pd.read_csv(CONTACT_FILE)

    employees["profile_key"] = (
        employees["profile_url"].apply(normalize_url)
    )

    contacts["profile_key"] = (
        contacts["profile_url"].apply(normalize_url)
    )

    contacts["email"] = contacts["email"].fillna("").str.strip()

    contacts = contacts[
        contacts["email"].apply(valid_email)
    ]

    # Match contacts using LinkedIn profile URLs.
    merged = employees.merge(
        contacts[
            ["profile_key", "email", "email_source"]
        ].drop_duplicates("profile_key"),
        on="profile_key",
        how="inner",
        suffixes=("_employee", "_contact")
    )

    # Keep only employees with valid email addresses.
    merged = merged[
        merged["email"].apply(valid_email)
    ]

    # Remove unwanted profile.
    merged = merged[
        ~merged["profile_key"].str.endswith(
            "/himanshu-iisc"
        )
    ]

    # Remove duplicate email addresses.
    merged = merged.drop_duplicates(
        subset=["email"]
    )

    output_columns = [
        "name",
        "headline_and_location",
        "profile_url",
        "email",
        "email_source"
    ]

    merged[output_columns].to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n========== RESULTS ==========")

    print("Total employees:", len(employees))

    print("Verified contact records:", len(contacts))

    print("Employees with emails:", len(merged))

    print("Output:", OUTPUT_FILE)

    print("=============================")


if __name__ == "__main__":
    main()
