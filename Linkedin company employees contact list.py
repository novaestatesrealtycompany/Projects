
import asyncio
import json
import os
import csv
import re
import random

from urllib.parse import urlsplit
from playwright.async_api import async_playwright

# ================= CONFIGURATION =================

SESSION_FILE = "linkedin_session.json"

COMPANY_SLUG = "synopsys"

TARGET_LOCATIONS = ["bangalore", "bengaluru"]

SKIP_PROFILES = {
    "https://www.linkedin.com/in/himanshu-iisc"
}

MAX_SCROLLS = 80

# Optional file containing verified public/authorized contacts
CONTACTS_FILE = "public_contacts.csv"


# ================= HELPERS =================

async def random_delay(min_ms=2000, max_ms=3500):
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)


def normalize_url(url):
    if not url:
        return ""

    return urlsplit(url).path.rstrip("/")


def load_authorized_contacts():

    contacts = {}

    if not os.path.exists(CONTACTS_FILE):
        return contacts

    with open(CONTACTS_FILE, "r", encoding="utf-8-sig") as f:

        reader = csv.DictReader(f)

        for row in reader:

            profile_url = normalize_url(row.get("profile_url", ""))
            email = row.get("email", "").strip()

            if profile_url and email:
                contacts[profile_url] = {
                    "email": email,
                    "email_source": row.get(
                        "email_source",
                        "Public/authorized source"
                    )
                }

    return contacts


# ================= LOGIN =================

async def login_and_save_session(page):

    print("\nLogin required.")
    print("Please log in manually in the browser.")

    await page.goto("https://www.linkedin.com/login")

    await page.wait_for_function(
        "() => !location.pathname.includes('/login')",
        timeout=120000
    )

    await random_delay(3000, 5000)

    cookies = await page.context.cookies()

    with open(SESSION_FILE, "w") as f:
        json.dump(cookies, f)

    print("Session saved successfully.")


# ================= PROFILE COLLECTION =================

async def collect_visible_profiles(page):

    return await page.locator(
        "a[href*='/in/']"
    ).evaluate_all("""
        anchors => {

            const results = [];

            for (const a of anchors) {

                let href = a.href || "";

                if (!href.includes("linkedin.com/in/")) {
                    continue;
                }

                href = href.split("?")[0].replace(/\\/$/, "");

                let card = a;

                // Look for the nearest employee card.
                const selectors = [
                    ".org-people-profile-card",
                    "[data-view-name='people-search-result']",
                    ".entity-result",
                    "li",
                    "article"
                ];

                for (const selector of selectors) {

                    const element = a.closest(selector);

                    if (element) {
                        card = element;
                        break;
                    }
                }

                const anchorText =
                    (a.innerText || "").trim();

                const name =
                    anchorText.split("\\n")[0].trim() ||
                    a.getAttribute("aria-label") ||
                    a.getAttribute("title") ||
                    "";

                const cardText =
                    (card.innerText || "")
                    .replace(/\\n+/g, " | ")
                    .trim();

                results.push({
                    name: name,
                    profile_url: href,
                    headline_and_location: cardText
                });
            }

            return results;
        }
    """)


async def click_show_more(page):

    patterns = [
        re.compile(r"show more", re.I),
        re.compile(r"see more", re.I)
    ]

    for pattern in patterns:

        try:

            buttons = page.get_by_role(
                "button",
                name=pattern
            )

            count = await buttons.count()

            for i in range(count):

                button = buttons.nth(i)

                if await button.is_visible():

                    await button.click(timeout=3000)

                    await random_delay(2000, 3000)

                    return True

        except Exception:
            continue

    return False


async def load_all_employees(page):

    all_profiles = {}

    stable_rounds = 0
    previous_count = 0

    for scroll in range(MAX_SCROLLS):

        profiles = await collect_visible_profiles(page)

        for profile in profiles:

            url = normalize_url(profile["profile_url"])

            if not url:
                continue

            if url not in all_profiles:
                all_profiles[url] = profile

        current_count = len(all_profiles)

        print(
            f"Scroll {scroll + 1}/{MAX_SCROLLS} | "
            f"Unique profiles: {current_count}"
        )

        await click_show_more(page)

        # Scroll in increments rather than jumping immediately
        # to the bottom of the page.
        await page.evaluate("""
            window.scrollBy(
                0,
                Math.max(500, window.innerHeight * 0.75)
            );
        """)

        await random_delay(2000, 3500)

        if current_count == previous_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        previous_count = current_count

        if stable_rounds >= 8:

            print("No new profiles detected.")
            break

    # Collect the final visible profiles.
    final_profiles = await collect_visible_profiles(page)

    for profile in final_profiles:

        url = normalize_url(profile["profile_url"])

        if url:
            all_profiles[url] = profile

    return all_profiles


# ================= MAIN =================

async def get_all_company_employees():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=False
        )

        context = await browser.new_context(
            viewport={
                "width": 1366,
                "height": 900
            }
        )

        if os.path.exists(SESSION_FILE):

            with open(SESSION_FILE, "r") as f:
                cookies = json.load(f)

            await context.add_cookies(cookies)

            print("Existing session loaded.")

        page = await context.new_page()

        company_url = (
            f"https://www.linkedin.com/company/"
            f"{COMPANY_SLUG}/people/"
        )

        await page.goto(company_url)

        await random_delay(4000, 6000)

        # Handle expired login sessions.
        if "/login" in page.url or "/uas/" in page.url:

            await login_and_save_session(page)

            await page.goto(company_url)

            await random_delay(5000, 7000)

        print("\nCompany directory:", page.url)
        print("Page title:", await page.title())

        if "/login" in page.url:

            print("Login unsuccessful. Cannot access directory.")
            await browser.close()
            return

        print("\nStarting employee collection...\n")

        all_profiles = await load_all_employees(page)

        print("\nTotal unique profiles discovered:", len(all_profiles))

        if len(all_profiles) == 0:

            print("\nNo profiles discovered.")

            print("Page URL:", page.url)

            body_text = await page.locator("body").inner_text()

            with open(
                "linkedin_debug.txt",
                "w",
                encoding="utf-8"
            ) as f:

                f.write(body_text[:20000])

            print("Saved page diagnostics to linkedin_debug.txt")

            await browser.close()
            return

        # Load authorized/public contact information.
        authorized_contacts = load_authorized_contacts()

        employees = []
        skipped = 0

        for url, profile in all_profiles.items():

            if url in SKIP_PROFILES:

                skipped += 1
                continue

            name = profile.get("name", "").strip()

            card_text = profile.get(
                "headline_and_location",
                ""
            )

            location_match = any(
                location in card_text.lower()
                for location in TARGET_LOCATIONS
            )

            contact = authorized_contacts.get(url, {})

            employees.append({

                "name": name,

                "headline_and_location": card_text,

                "profile_url": profile["profile_url"],

                "email": contact.get("email", "N/A"),

                "email_source": contact.get(
                    "email_source",
                    "Not publicly available"
                ),

                "phone": "N/A",

                "bengaluru_location_match": location_match

            })

        # Export all discovered employees.
        safe_company = re.sub(
            r"[^a-zA-Z0-9]+",
            "_",
            COMPANY_SLUG
        )

        json_file = f"{safe_company}_all_employees.json"

        csv_file = f"{safe_company}_all_employees.csv"

        bengaluru_file = f"{safe_company}_bengaluru_employees.csv"

        fields = [
            "name",
            "headline_and_location",
            "profile_url",
            "email",
            "email_source",
            "phone",
            "bengaluru_location_match"
        ]

        with open(
            json_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                employees,
                f,
                indent=4,
                ensure_ascii=False
            )

        with open(
            csv_file,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=fields
            )

            writer.writeheader()
            writer.writerows(employees)

        bengaluru_employees = [
            employee
            for employee in employees
            if employee["bengaluru_location_match"]
        ]

        with open(
            bengaluru_file,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=fields
            )

            writer.writeheader()
            writer.writerows(bengaluru_employees)

        email_count = sum(
            1 for employee in employees
            if employee["email"] != "N/A"
        )

        print("\n========== FINAL REPORT ==========")

        print("Discovered profiles:", len(all_profiles))

        print("Skipped profiles:", skipped)

        print("Saved employee records:", len(employees))

        print("Bengaluru matches:", len(bengaluru_employees))

        print("Verified/authorized emails:", email_count)

        print("\nOutput files:")

        print(json_file)
        print(csv_file)
        print(bengaluru_file)

        print("==================================")

        await browser.close()


if __name__ == "__main__":

    asyncio.run(get_all_company_employees())
