
import json
import re
from urllib.parse import quote_plus

import pandas as pd


# ============================================================
# 1. SETTINGS
# ============================================================

SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1IJvFxsH_WQar_HBeK9agJdQ_o7PoRT3xdh1QAlog30M/edit?usp=sharing"
)

SHEET_NAME = "Properties"
OUTPUT_FILE = "propertiesData.js"
EXPECTED_ROWS = 81


# ============================================================
# 2. EXPECTED GOOGLE SHEET COLUMNS
# ============================================================

REQUIRED_COLUMNS = [
    "ID",
    "Title",
    "Subtitle",
    "Location Key",
    "Location Name",
    "Type Key",
    "Type Label",
    "Latitude",
    "Longitude",
    "RERA ID",
    "Price Display",
    "Base Price (Cr)",
    "Status Tag",
    "Vastu Rating",
    "Acres",
    "Towers",
    "Total Units",
    "Possession",
    "Hero Image URL",
    "Video Embed URL",
    "Description",
    "Google Map Embed",
    "Google Map URL",
    "Gallery (JSON/Pipe)",
    "Pricing Matrix (JSON/Pipe)",
    "Connectivity (JSON/Pipe)",
    "Amenities (JSON/Pipe)"
]


# ============================================================
# 3. GOOGLE SHEETS CONNECTION
# ============================================================

def get_csv_url(sheet_url, sheet_name):

    match = re.search(
        r"/spreadsheets/d/([a-zA-Z0-9_-]+)",
        sheet_url
    )

    if not match:
        raise ValueError("Invalid Google Sheets URL.")

    spreadsheet_id = match.group(1)

    return (
        f"https://docs.google.com/spreadsheets/d/"
        f"{spreadsheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote_plus(sheet_name)}"
    )


# ============================================================
# 4. GENERAL HELPER FUNCTIONS
# ============================================================

def clean_text(value, default=""):

    if value is None:
        return default

    if pd.isna(value):
        return default

    return str(value).strip()


def to_float(value, default=0.0):

    value = clean_text(value)

    if not value:
        return default

    try:
        return float(value.replace(",", ""))

    except (ValueError, TypeError):
        return default


def to_int(value, default=0):

    try:
        return int(float(to_float(value, default)))

    except (ValueError, TypeError):
        return default


def clean_url(value):

    value = clean_text(value)

    # Convert Markdown links into ordinary URLs.
    match = re.match(
        r"^\[.*?\]\((https?://.*?)\)$",
        value
    )

    if match:
        return match.group(1).strip()

    return value


def normalize_type_key(value):

    value = clean_text(value).lower()

    mapping = {
        "plots": "plot",
        "plot": "plot",
        "residential plots": "plot",

        "apartments": "apartment",
        "apartment": "apartment",
        "flats": "apartment",

        "villas": "villa",
        "villa": "villa",

        "row houses": "row-house",
        "row house": "row-house",

        "commercial": "commercial"
    }

    if value in mapping:
        return mapping[value]

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        value
    ).strip("-")


def format_possession(value):

    value = clean_text(value)

    if not value:
        return ""

    parsed = pd.to_datetime(
        value,
        errors="coerce"
    )

    if not pd.isna(parsed):
        return parsed.strftime("%B %Y")

    return value


# ============================================================
# 5. JSON PARSING HELPER
# ============================================================

def try_json(value):

    value = clean_text(value)

    if not value:
        return None

    try:
        return json.loads(value)

    except (json.JSONDecodeError, TypeError):
        return None


# ============================================================
# 6. GALLERY PARSER
#
# OUTPUT STRUCTURE:
#
# {
#     "url": "...",
#     "title": "...",
#     "category": "..."
# }
# ============================================================

def parse_gallery(value):

    result = []

    value = clean_text(value)

    if not value:
        return result

    data = try_json(value)

    # JSON format
    if isinstance(data, list):

        for item in data:

            if not isinstance(item, dict):
                continue

            url = clean_url(
                item.get("url", "")
            )

            title = clean_text(
                item.get(
                    "title",
                    item.get("caption", "")
                )
            )

            category = clean_text(
                item.get("category", "")
            )

            if url:

                result.append({
                    "url": url,
                    "title": title,
                    "category": category
                })

        return result

    # Pipe-separated format.
    # Each record:
    # Title | Category | Image URL

    for line in value.splitlines():

        parts = [
            clean_text(part)
            for part in line.split("|")
        ]

        for i in range(0, len(parts) - 2, 3):

            title = parts[i]
            category = parts[i + 1]
            url = clean_url(parts[i + 2])

            if url:

                result.append({
                    "url": url,
                    "title": title,
                    "category": category
                })

    return result


# ============================================================
# 7. PRICING MATRIX PARSER
#
# OUTPUT STRUCTURE:
#
# {
#     "typ": "...",
#     "carpet": "...",
#     "superBuilt": "...",
#     "floorBand": "...",
#     "allInPrice": "..."
# }
# ============================================================

def parse_pricing_matrix(value):

    result = []

    value = clean_text(value)

    if not value:
        return result

    data = try_json(value)

    # JSON format
    if isinstance(data, list):

        for item in data:

            if not isinstance(item, dict):
                continue

            result.append({
                "typ": clean_text(item.get("typ", item.get("type", ""))),
                "carpet": clean_text(item.get("carpet", "")),
                "superBuilt": clean_text(item.get("superBuilt", "")),
                "floorBand": clean_text(item.get("floorBand", "")),
                "allInPrice": clean_text(
                    item.get("allInPrice", item.get("price", ""))
                )
            })

        return result

    # Pipe-separated format.
    tokens = [
        clean_text(part)
        for part in value.split("|")
        if clean_text(part)
    ]

    labels = {
        "carpet:": "carpet",
        "superbuilt:": "superBuilt",
        "floor:": "floorBand",
        "price:": "allInPrice",
        "dimension:": "carpet"
    }

    i = 0

    while i < len(tokens):

        # First token is the configuration/type.
        item = {
            "typ": tokens[i],
            "carpet": "",
            "superBuilt": "",
            "floorBand": "",
            "allInPrice": ""
        }

        i += 1

        # Read labelled values until the next configuration.
        while i < len(tokens):

            token = tokens[i]
            lower_token = token.lower()

            matched_label = None

            for label, field in labels.items():

                if lower_token.startswith(label):
                    matched_label = (label, field)
                    break

            if not matched_label:
                break

            label, field = matched_label

            item[field] = token[len(label):].strip()

            i += 1

        result.append(item)

    return result


# ============================================================
# 8. CONNECTIVITY PARSER
#
# OUTPUT STRUCTURE:
#
# [
#     {
#         "category": "...",
#         "icon": "...",
#         "items": [
#             {
#                 "name": "...",
#                 "dist": "...",
#                 "time": "..."
#             }
#         ]
#     }
# ]
# ============================================================

def parse_connectivity(value):

    result = []

    value = clean_text(value)

    if not value:
        return result

    data = try_json(value)

    # JSON format
    if isinstance(data, list):

        for category_data in data:

            if not isinstance(category_data, dict):
                continue

            items = []

            for item in category_data.get("items", []):

                if not isinstance(item, dict):
                    continue

                items.append({
                    "name": clean_text(item.get("name", "")),
                    "dist": clean_text(
                        item.get("dist", item.get("distance", ""))
                    ),
                    "time": clean_text(item.get("time", ""))
                })

            result.append({
                "category": clean_text(
                    category_data.get("category", "")
                ),
                "icon": clean_text(
                    category_data.get("icon", "fa-briefcase")
                ),
                "items": items
            })

        return result

    # Pipe-separated format.
    # Category | Name | Distance | Time | Icon

    tokens = [
        clean_text(part)
        for part in value.split("|")
    ]

    categories = {}

    for i in range(0, len(tokens) - 4, 5):

        category = tokens[i]
        name = tokens[i + 1]
        distance = tokens[i + 2]
        time = tokens[i + 3]
        icon = tokens[i + 4] or "fa-briefcase"

        if not category or not name:
            continue

        if category not in categories:

            categories[category] = {
                "category": category,
                "icon": icon,
                "items": []
            }

        categories[category]["items"].append({
            "name": name,
            "dist": distance,
            "time": time
        })

    result = list(categories.values())

    return result


# ============================================================
# 9. AMENITIES PARSER
#
# OUTPUT STRUCTURE:
#
# {
#     "name": "...",
#     "icon": "..."
# }
# ============================================================

def parse_amenities(value):

    result = []

    value = clean_text(value)

    if not value:
        return result

    data = try_json(value)

    # JSON format
    if isinstance(data, list):

        for item in data:

            if isinstance(item, dict):

                name = clean_text(item.get("name", ""))
                icon = clean_text(
                    item.get("icon", "fa-check")
                )

            else:

                name = clean_text(item)
                icon = "fa-check"

            if name:

                result.append({
                    "name": name,
                    "icon": icon
                })

        return result

    # Pipe-separated format.
    amenities = re.split(r"[|\n]+", value)

    for amenity in amenities:

        amenity = clean_text(amenity)

        if not amenity:
            continue

        match = re.match(
            r"^(.*?)\s*\(([^()]*)\)\s*$",
            amenity
        )

        if match:

            name = match.group(1).strip()
            icon = match.group(2).strip()

        else:

            name = amenity
            icon = "fa-check"

        if name:

            result.append({
                "name": name,
                "icon": icon or "fa-check"
            })

    return result


# ============================================================
# 10. GOOGLE MAPS URL FALLBACK
#
# Existing spreadsheet URLs are preserved.
# These URLs are generated only when a source URL is empty.
# ============================================================

def generate_google_maps_urls(
    latitude,
    longitude,
    location_name,
    title
):

    if latitude != 0 and longitude != 0:

        map_query = f"{latitude},{longitude}"

        embed_url = (
            "https://www.google.com/maps"
            f"?q={quote_plus(map_query)}"
            "&z=15&output=embed"
        )

        share_url = (
            "https://www.google.com/maps/search/"
            f"?api=1&query={latitude},{longitude}"
        )

    else:

        map_query = location_name or title

        encoded_query = quote_plus(map_query)

        embed_url = (
            "https://www.google.com/maps"
            f"?q={encoded_query}&z=15&output=embed"
        )

        share_url = (
            "https://www.google.com/maps/search/"
            f"?api=1&query={encoded_query}"
        )

    return embed_url, share_url


# ============================================================
# 11. READ GOOGLE SHEET
# ============================================================

def read_google_sheet(sheet_url):

    csv_url = get_csv_url(
        sheet_url,
        SHEET_NAME
    )

    print("\nConnecting to Google Sheets...")

    try:

        df = pd.read_csv(
            csv_url,
            dtype=str,
            keep_default_na=False
        )

    except Exception as error:

        raise RuntimeError(
            "Unable to read Google Sheets. "
            "Check that the spreadsheet is accessible "
            "and shared with Viewer permission."
        ) from error

    # Remove accidental whitespace from headers.
    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    # Check all expected columns.
    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            "The following required columns are missing:\n"
            + "\n".join(missing_columns)
        )

    # Keep only the required columns, in the expected order.
    df = df[REQUIRED_COLUMNS].copy()

    # Remove completely empty rows.
    df = df[
        df["ID"].astype(str).str.strip().ne("")
        | df["Title"].astype(str).str.strip().ne("")
    ].copy()

    return df


# ============================================================
# 12. CONVERT EACH ROW INTO YOUR EXACT JSON STRUCTURE
# ============================================================

def convert_row_to_property(row):

    property_id = to_int(
        row.get("ID", 0)
    )

    title = clean_text(
        row.get("Title", "")
    )

    location_name = clean_text(
        row.get("Location Name", "")
    )

    latitude = to_float(
        row.get("Latitude", 0)
    )

    longitude = to_float(
        row.get("Longitude", 0)
    )

    # Preserve Maps URLs from the spreadsheet.
    google_map_embed = clean_text(
        row.get("Google Map Embed", "")
    )

    google_map_url = clean_text(
        row.get("Google Map URL", "")
    )

    # Generate only if the spreadsheet field is empty.
    fallback_embed, fallback_url = generate_google_maps_urls(
        latitude,
        longitude,
        location_name,
        title
    )

    if not google_map_embed:
        google_map_embed = fallback_embed

    if not google_map_url:
        google_map_url = fallback_url

    # Build the property object.
    # Do not rename or remove these output keys.

    prop = {

        "id": property_id,

        "title": title,

        "subtitle": clean_text(
            row.get("Subtitle", "")
        ),

        "locationKey": clean_text(
            row.get("Location Key", "")
        ),

        "locationName": location_name,

        "typeKey": normalize_type_key(
            row.get("Type Key", "")
        ),

        "typeLabel": clean_text(
            row.get("Type Label", "")
        ),

        "lat": latitude,

        "lng": longitude,

        "reraId": clean_text(
            row.get("RERA ID", "")
        ),

        "priceDisplay": clean_text(
            row.get("Price Display", "")
        ),

        "basePriceNum": to_float(
            row.get("Base Price (Cr)", 0)
        ),

        "statusTag": clean_text(
            row.get("Status Tag", "")
        ),

        "vastuRating": clean_text(
            row.get("Vastu Rating", "")
        ),

        "acres": clean_text(
            row.get("Acres", "")
        ),

        "towers": clean_text(
            row.get("Towers", "")
        ),

        "totalUnits": clean_text(
            row.get("Total Units", "")
        ),

        "possession": format_possession(
            row.get("Possession", "")
        ),

        "heroImage": clean_url(
            row.get("Hero Image URL", "")
        ),

        "videoEmbedUrl": clean_url(
            row.get("Video Embed URL", "")
        ),

        "description": clean_text(
            row.get("Description", "")
        ),

        "gallery": parse_gallery(
            row.get("Gallery (JSON/Pipe)", "")
        ),

        "floorPlans": [],

        "pricingMatrix": parse_pricing_matrix(
            row.get("Pricing Matrix (JSON/Pipe)", "")
        ),

        "connectivityCategories": parse_connectivity(
            row.get("Connectivity (JSON/Pipe)", "")
        ),

        "googleMapEmbed": google_map_embed,

        "googleMapUrl": google_map_url,

        "amenities": parse_amenities(
            row.get("Amenities (JSON/Pipe)", "")
        )

    }

    return prop


# ============================================================
# 13. CONVERT GOOGLE SHEET TO JAVASCRIPT
# ============================================================

def convert_google_sheet_to_js(
    sheet_url,
    output_file=OUTPUT_FILE
):

    df = read_google_sheet(sheet_url)

    print("\nProcessing property records...")

    properties_list = []

    for _, row in df.iterrows():

        prop = convert_row_to_property(row)

        properties_list.append(prop)

    # ========================================================
    # VALIDATION
    # ========================================================

    print("\n========== VALIDATION REPORT ==========")

    print(
        f"Spreadsheet rows read: {len(df)}"
    )

    print(
        f"Property objects created: {len(properties_list)}"
    )

    if len(properties_list) != EXPECTED_ROWS:

        print(
            f"WARNING: Expected {EXPECTED_ROWS} properties, "
            f"but found {len(properties_list)}."
        )

    missing_titles = [
        p["id"]
        for p in properties_list
        if not p["title"]
    ]

    missing_ids = [
        p["title"]
        for p in properties_list
        if not p["id"]
    ]

    if missing_titles:
        print("Rows with missing titles:", missing_titles)

    if missing_ids:
        print("Properties with missing IDs:", missing_ids)

    print("\nArray data summary:")

    for prop in properties_list:

        print(
            f"{prop['id']}. {prop['title']} | "
            f"Gallery: {len(prop['gallery'])} | "
            f"Pricing: {len(prop['pricingMatrix'])} | "
            f"Connectivity: {sum(len(c['items']) for c in prop['connectivityCategories'])} | "
            f"Amenities: {len(prop['amenities'])} | "
            f"Floor Plans: {len(prop['floorPlans'])}"
        )

    # ========================================================
    # GENERATE JAVASCRIPT
    # ========================================================

    js_content = (
        "const PROPERTIES = "
        + json.dumps(
            properties_list,
            indent=4,
            ensure_ascii=False
        )
        + ";"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(js_content)

    # ========================================================
    # SUCCESS MESSAGE
    # ========================================================

    print("\n======================================")
    print("SUCCESS!")
    print("======================================")

    print(
        f"Total properties extracted: {len(properties_list)}"
    )

    print(
        f"JavaScript file created: {output_file}"
    )

    print("Output format: const PROPERTIES = [...]")

    print("JSON field structure: Preserved")

    print("======================================")


# ============================================================
# 14. RUN SCRIPT
# ============================================================

if __name__ == "__main__":

    convert_google_sheet_to_js(
        SHEET_URL,
        output_file=OUTPUT_FILE
    )
