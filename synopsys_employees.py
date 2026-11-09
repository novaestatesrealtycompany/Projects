
import asyncio
import csv
import json
import os
import random
import re
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright

# =========================================================
# CONFIGURATION
# =========================================================

SESSION_FILE = "linkedin_session.json"

COMPANY_SLUG = "synopsys"

COMPANY_URL = (
    f"https://www.linkedin.com/company/{COMPANY_SLUG}/people/"
)

CONTACTS_FILE = "public_contacts.csv"

OUTPUT_CSV = "synopsys_employees_with_emails.csv"
OUTPUT_JSON = "synopsys_employees_with_emails.json"

SKIP_PROFILES = {
    "https://www.linkedin.com/in/himanshu-iisc"
}

LOCATION_KEYWORDS = [
    "bangalore",
    "bengaluru"
]

# Set False if you want employees from all locations.
REQUIRE_BENGALURU = True

MAX_SCROLL_ROUNDS = 80


# =========================================================
# HELPER FUNCTIONS
# =========================================================

async def random_delay(min_seconds=2, max_seconds=4):
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))


def normalize_profile_url(url):
    if not url:
        return ""

    url = url.strip()

    if not url.startswith("http"):
        url = "https://www.linkedin.com" + url

    parsed = urlsplit(url)

    path = parsed.path.rstrip("/")

    return urlunsplit((
        "https",
        "www.linkedin.com",
        path,
        "",
        ""
    )).lower()


def is_valid_email(email):
    if not email:
        return False

    email = email.strip()

    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"

    return bool(re.match(pattern, email))


def matches_bengaluru(location):
    location = (location or "").lower()

    return any(
        keyword in location
        for keyword in LOCATION_KEYWORDS
    )


# =========================================================
# LINKEDIN LOGIN AND SESSION MANAGEMENT
# =========================================================

async def login_and_save_session(page, context):

    print("\n--------------------------------")
    print("LINKEDIN LOGIN REQUIRED")
    print("--------------------------------")

    print("Opening LinkedIn login page...")

    await page.goto(
        "https://www.linkedin.com/login",
        wait_until="domcontentloaded"
    )

    print("\nPlease log in manually using your LinkedIn account.")
    print("Complete any security verification if requested.")

    print("Waiting for successful login...")

    await page.wait_for_url(
        lambda url: "/login" not in str(url),
        timeout=180000
    )

    await random_delay(3, 5)

    print("Login successful!")

    await context.storage_state(path=SESSION_FILE)

    print("LinkedIn session saved successfully.")


async def create_linkedin_session(browser):

    if os.path.exists(SESSION_FILE):

        print("Existing LinkedIn session found.")

        context = await browser.new_context(
            storage_state=SESSION_FILE
        )

    else:

        print("No saved session found.")

        context = await browser.new_context()

    page = await context.new_page()

    await page.goto(
        "https://www.linkedin.com/feed/",
        wait_until="domcontentloaded"
    )

    await random_delay(2, 4)

    current_url = page.url.lower()

    if "/login" in current_url or "/checkpoint" in current_url:

        print("Session expired or login required.")

        await login_and_save_session(page, context)

    else:

        print("Existing LinkedIn session is active.")

    return context, page


# =========================================================
# COLLECT EMPLOYEE PROFILES
# =========================================================

async def collect_synopsys_employees(page):

    print("\nOpening Synopsys employee page...")

    await page.goto(
        COMPANY_URL,
        wait_until="domcontentloaded"
    )

    await random_delay(4, 6)

    employees = {}

    previous_count = 0
    unchanged_rounds = 0

    print("\nCollecting employee profiles...")

    for round_number in range(1, MAX_SCROLL_ROUNDS + 1):

        # Collect visible profile links and nearby card text.
        profiles = await page.evaluate("""
        () => {
            const results = [];

            const links = document.querySelectorAll(
                'a[href*="/in/"]'
            );

            for (const link of links) {

                const href = link.href;

                if (!href.includes('/in/')) {
                    continue;
                }

                let container =
                    link.closest('li') ||
                    link.closest('[data-view-name]') ||
                    link.parentElement;

                let text = container
                    ? container.innerText
                    : link.innerText;

                results.push({
                    url: href,
                    text: text || '',
                    linkText: link.innerText || ''
                });
            }

            return results;
        }
        """)

        for profile in profiles:

            profile_url = normalize_profile_url(
                profile.get("url", "")
            )

            if not profile_url:
                continue

            if profile_url in SKIP_PROFILES:
                continue

            text = profile.get("text", "").strip()

            link_text = profile.get("linkText", "").strip()

            name = link_text.split("\\n")[0].strip()

            if not name:
                name = text.split("\\n")[0].strip()

            if not name:
                continue

            lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ]

            location = ""

            for line in lines:

                lower_line = line.lower()

                if (
                    "bangalore" in lower_line
                    or "bengaluru" in lower_line
                ):
                    location = line
                    break

            if profile_url not in employees:

                employees[profile_url] = {
                    "name": name,
                    "profile_url": profile_url,
                    "headline": text,
                    "location": location,
                    "bengaluru_location_match":
                        matches_bengaluru(location)
                }

        current_count = len(employees)

        print(
            f"Scroll {round_number}: "
            f"{current_count} unique profiles collected"
        )

        if current_count == previous_count:
            unchanged_rounds += 1
        else:
            unchanged_rounds = 0

        if unchanged_rounds >= 5:
            print("No new profiles found after several scrolls.")
            break

        previous_count = current_count

        # Scroll the employee page normally.
        await page.evaluate("""
            window.scrollTo(
                0,
                document.body.scrollHeight
            );
        """)

        await random_delay(3, 5)

    print(
        f"\nTotal unique profiles collected: {len(employees)}"
    )

    return list(employees.values())


# =========================================================
# LOAD AUTHORIZED / PUBLIC EMAIL CONTACTS
# =========================================================

def load_public_contacts():

    contacts = {}

    if not os.path.exists(CONTACTS_FILE):

        print(
            f"\nWARNING: {CONTACTS_FILE} was not found."
        )

        print(
            "Create this CSV with profile_url, email, "
            "and email_source columns."
        )

        return contacts

    with open(
        CONTACTS_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            profile_url = normalize_profile_url(
                row.get("profile_url", "")
            )

            email = (
                row.get("email", "")
                .strip()
            )

            email_source = (
                row.get("email_source", "")
                .strip()
            )

            if not profile_url or not is_valid_email(email):
                continue

            contacts[profile_url] = {
                "email": email,
                "email_source": email_source
            }

    print(
        f"\nAuthorized/public email contacts loaded: "
        f"{len(contacts)}"
    )

    return contacts


# =========================================================
# MATCH EMPLOYEES WITH EMAILS
# =========================================================

def match_employees_with_emails(employees, contacts):

    matched_employees = []

    for employee in employees:

        profile_url = normalize_profile_url(
            employee.get("profile_url", "")
        )

        if profile_url in SKIP_PROFILES:
            continue

        contact = contacts.get(profile_url)

        if not contact:
            continue

        email = contact.get("email", "")

        if not is_valid_email(email):
            continue

        if (
            REQUIRE_BENGALURU
            and not employee.get("bengaluru_location_match")
        ):
            continue

        result = {
            "name": employee.get("name", ""),
            "profile_url": profile_url,
            "location": employee.get("location", ""),
            "headline": employee.get("headline", ""),
            "email": email,
            "email_source": contact.get("email_source", "")
        }

        matched_employees.append(result)

    return matched_employees


# =========================================================
# SAVE RESULTS
# =========================================================

def save_results(employees):

    # CSV output
    if employees:

        with open(
            OUTPUT_CSV,
            "w",
            encoding="utf-8-sig",
            newline=""
        ) as file:

            fieldnames = [
                "name",
                "profile_url",
                "location",
                "headline",
                "email",
                "email_source"
            ]

            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames
            )

            writer.writeheader()
            writer.writerows(employees)

    else:

        print(
            "\nNo employees matched with valid email addresses."
        )

    # JSON output
    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            employees,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n--------------------------------")
    print("RESULTS SAVED")
    print("--------------------------------")

    print(f"Matched employees: {len(employees)}")

    if employees:
        print(f"CSV: {OUTPUT_CSV}")

    print(f"JSON: {OUTPUT_JSON}")


# =========================================================
# MAIN PROGRAM
# =========================================================

async def main():

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=False
        )

        context = None

        try:

            # Login or reuse saved session.
            context, page = await create_linkedin_session(
                browser
            )

            # Collect employee profiles.
            employees = await collect_synopsys_employees(
                page
            )

            # Load authorized/public email contacts.
            contacts = load_public_contacts()

            # Match employees with email addresses.
            matched_employees = match_employees_with_emails(
                employees,
                contacts
            )

            # Save only employees with valid emails.
            save_results(matched_employees)

        except Exception as error:

            print("\nAn error occurred:")
            print(error)

        finally:

            if context:
                await context.close()

            await browser.close()


if __name__ == "__main__":

    asyncio.run(main())
