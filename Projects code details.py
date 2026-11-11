
import pandas as pd
import re
import json
from urllib.parse import quote_plus


# ============================================================
# 1. GOOGLE SHEETS CSV URL
# ============================================================

def get_csv_url(sheet_url):
    """
    Extracts the Google Sheet ID and generates its CSV export URL.
    """

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_url)

    if not match:
        raise ValueError("Invalid Google Sheets URL provided.")

    file_id = match.group(1)

    return (
        f"https://docs.google.com/spreadsheets/d/"
        f"{file_id}/export?format=csv"
    )


# ============================================================
# 2. GENERAL HELPER FUNCTIONS
# ============================================================

def clean_text(value, default=""):
    """
    Converts spreadsheet values into clean strings.
    Prevents NaN from appearing in the generated JavaScript.
    """

    if pd.isna(value):
        return default

    return str(value).strip()


def to_float(value, default=0.0):
    """
    Safely converts a spreadsheet value into a float.
    """

    if pd.isna(value) or str(value).strip() == "":
        return default

    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def to_int(value, default=0):
    """
    Safely converts a spreadsheet value into an integer.
    """

    number = to_float(value, default)

    try:
        return int(number)
    except (ValueError, TypeError):
        return default


def normalize_type_key(value):
    """
    Converts property types into keys expected by the website.
    """

    value = clean_text(value).lower().strip()

    type_mapping = {
        "plots": "plot",
        "plot": "plot",
        "residential plots": "plot",
        "apartments": "apartment",
        "apartment": "apartment",
        "flats": "apartment",
        "villa": "villa",
        "villas": "villa",
        "row houses": "row-house",
        "row house": "row-house",
        "commercial": "commercial"
    }

    if value in type_mapping:
        return type_mapping[value]

    # Convert other values into lowercase URL-style keys.
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


# ============================================================
# 3. GALLERY, PRICING, CONNECTIVITY AND AMENITIES PARSER
# ============================================================

def parse_pipe_field(value, field_type):

    if pd.isna(value) or not str(value).strip():
        return []

    lines = str(value).strip().splitlines()

    parsed_items = []

    # --------------------------------------------------------
    # GALLERY
    #
    # Spreadsheet format:
    # Title | Category | Image URL
    # --------------------------------------------------------

    if field_type == "gallery":

        for line in lines:

            parts = [p.strip() for p in line.split("|")]

            if len(parts) >= 3:

                parsed_items.append({
                    "url": parts[2],
                    "title": parts[0],
                    "category": parts[1]
                })

    # --------------------------------------------------------
    # PRICING MATRIX
    #
    # Spreadsheet format:
    # Type | Carpet | SuperBuilt | Floor | Price
    # --------------------------------------------------------

    elif field_type == "pricingMatrix":

        for line in lines:

            parts = [p.strip() for p in line.split("|")]

            if len(parts) >= 5:

                carpet = parts[1].replace(
                    "Carpet:", ""
                ).strip()

                super_built = parts[2].replace(
                    "SuperBuilt:", ""
                ).strip()

                floor = parts[3].replace(
                    "Floor:", ""
                ).strip()

                price = parts[4].replace(
                    "Price:", ""
                ).strip()

                parsed_items.append({
                    "typ": parts[0],
                    "carpet": carpet,
                    "superBuilt": super_built,
                    "floorBand": floor,
                    "allInPrice": price
                })

    # --------------------------------------------------------
    # CONNECTIVITY
    #
    # Spreadsheet format:
    # Category | Name | Distance | Time | Icon
    #
    # Example:
    # Transportation | Airport | 12 km | 20 mins | fa-plane
    # --------------------------------------------------------

    elif field_type == "connectivity":

        categories = {}

        for line in lines:

            parts = [p.strip() for p in line.split("|")]

            if len(parts) >= 4:

                category = parts[0]

                icon = (
                    parts[4]
                    if len(parts) > 4 and parts[4]
                    else "fa-briefcase"
                )

                item = {
                    "name": parts[1],
                    "dist": parts[2],
                    "time": parts[3]
                }

                if category not in categories:

                    categories[category] = {
                        "category": category,
                        "icon": icon,
                        "items": []
                    }

                categories[category]["items"].append(item)

        parsed_items = list(categories.values())

    # --------------------------------------------------------
    # AMENITIES
    #
    # Spreadsheet format:
    # Grand Clubhouse (fa-building)
    # Swimming Pool (fa-swimming-pool)
    # --------------------------------------------------------

    elif field_type == "amenities":

        for line in lines:

            line = line.strip()

            if not line:
                continue

            match = re.match(
                r"^(.*?)\s*\(([^()]*)\)\s*$",
                line
            )

            if match:

                parsed_items.append({
                    "name": match.group(1).strip(),
                    "icon": match.group(2).strip()
                })

            else:

                parsed_items.append({
                    "name": line,
                    "icon": "fa-check"
                })

    return parsed_items


# ============================================================
# 4. GOOGLE MAPS URL GENERATOR
# ============================================================

def generate_google_maps_urls(lat, lng, location_name, title):
    """
    Generates:
    1. A Google Maps URL suitable for an iframe.
    2. A Google Maps link for opening the location.

    Uses coordinates when available.
    Falls back to the project location/title otherwise.
    """

    if lat != 0 and lng != 0:

        map_query = f"{lat},{lng}"

    else:

        map_query = location_name or title

    encoded_query = quote_plus(map_query)

    google_map_embed = (
        f"https://www.google.com/maps"
        f"?q={encoded_query}&z=15&output=embed"
    )

    google_map_url = (
        f"https://www.google.com/maps/search/"
        f"?api=1&query={encoded_query}"
    )

    return google_map_embed, google_map_url


# ============================================================
# 5. MAIN GOOGLE SHEETS CONVERTER
# ============================================================

def convert_google_sheet_to_js(
    sheet_url,
    output_file="propertiesData.js"
):

    csv_url = get_csv_url(sheet_url)

    print("Connecting to Google Sheets...")

    try:
        df = pd.read_csv(csv_url)
    except Exception as error:
        raise RuntimeError(
            "Unable to read Google Sheet. "
            "Check that the sheet is shared with "
            "'Anyone with the link' as Viewer."
        ) from error

    properties_list = []

    print(f"Found {len(df)} spreadsheet rows.")

    for _, row in df.iterrows():

        # ----------------------------------------------------
        # BASIC PROPERTY INFORMATION
        # ----------------------------------------------------

        property_id = to_int(row.get("ID", 0))

        title = clean_text(row.get("Title", ""))

        location_name = clean_text(
            row.get("Location Name", "")
        )

        latitude = to_float(
            row.get("Latitude", 0)
        )

        longitude = to_float(
            row.get("Longitude", 0)
        )

        # ----------------------------------------------------
        # GOOGLE MAPS
        # Generate valid embed and external URLs automatically.
        # The spreadsheet's short Google Maps URL is not used.
        # ----------------------------------------------------

        google_map_embed, google_map_url = (
            generate_google_maps_urls(
                latitude,
                longitude,
                location_name,
                title
            )
        )

        # ----------------------------------------------------
        # PROPERTY DATA OBJECT
        # ----------------------------------------------------

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

            "possession": clean_text(
                row.get("Possession", "")
            ),

            "heroImage": clean_text(
                row.get("Hero Image URL", "")
            ),

            "videoEmbedUrl": clean_text(
                row.get("Video Embed URL", "")
            ),

            "description": clean_text(
                row.get("Description", "")
            ),

            # GALLERY
            "gallery": parse_pipe_field(
                row.get("Gallery (JSON/Pipe)", ""),
                "gallery"
            ),

            # FLOOR PLANS
            # Kept empty because no floor-plan parser
            # or spreadsheet column was specified.
            "floorPlans": [],

            # PRICING MATRIX
            "pricingMatrix": parse_pipe_field(
                row.get("Pricing Matrix (JSON/Pipe)", ""),
                "pricingMatrix"
            ),

            # CONNECTIVITY
            "connectivityCategories": parse_pipe_field(
                row.get("Connectivity (JSON/Pipe)", ""),
                "connectivity"
            ),

            # GOOGLE MAPS
            "googleMapEmbed": google_map_embed,

            "googleMapUrl": google_map_url,

            # AMENITIES
            "amenities": parse_pipe_field(
                row.get("Amenities (JSON/Pipe)", ""),
                "amenities"
            )
        }

        properties_list.append(prop)

    # ========================================================
    # 6. GENERATE JAVASCRIPT
    # ========================================================

    # IMPORTANT:
    # The corrected website uses PROPERTIES.
    # Therefore, we generate const PROPERTIES here.

    js_content = (
        "const PROPERTIES = "
        + json.dumps(
            properties_list,
            indent=4,
            ensure_ascii=False
        )
        + ";"
    )

    with open(output_file, "w", encoding="utf-8") as file:

        file.write(js_content)

    print("\n======================================")
    print("SUCCESS!")
    print("======================================")

    print(
        f"Extracted {len(properties_list)} properties."
    )

    print(
        f"JavaScript file created: {output_file}"
    )

    print(
        "Google Maps URLs generated using "
        "project coordinates."
    )

    print("======================================")


# ============================================================
# 7. RUN THE SCRIPT
# ============================================================

if __name__ == "__main__":

    # Paste your actual Google Sheets URL here.
    # Do not put Markdown link formatting around it.

    sheet_url = (
        "https://docs.google.com/spreadsheets/d/"
        "1Bzm4LqHYETZy1XVe16WCLrLTCa-GPcnlyb2jmyNYx5M/"
        "edit?usp=sharing"
    )

    convert_google_sheet_to_js(
        sheet_url,
        output_file="propertiesData.js"
    )
