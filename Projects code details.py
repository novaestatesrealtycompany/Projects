
import pandas as pd
import re
import json
from urllib.parse import quote_plus


# ============================================================
# 1. GOOGLE SHEETS CSV URL
# ============================================================

def get_csv_url(sheet_url):

    match = re.search(
        r"/spreadsheets/d/([a-zA-Z0-9_-]+)",
        sheet_url
    )

    if not match:
        raise ValueError("Invalid Google Sheets URL.")

    file_id = match.group(1)

    return (
        f"https://docs.google.com/spreadsheets/d/"
        f"{file_id}/export?format=csv"
    )


# ============================================================
# 2. GENERAL HELPER FUNCTIONS
# ============================================================

def clean_text(value, default=""):

    if pd.isna(value):
        return default

    return str(value).strip()


def to_float(value, default=0.0):

    if pd.isna(value) or str(value).strip() == "":
        return default

    try:
        return float(
            str(value).replace(",", "").strip()
        )

    except (ValueError, TypeError):
        return default


def to_int(value, default=0):

    try:
        return int(to_float(value, default))

    except (ValueError, TypeError):
        return default


# ============================================================
# 3. PROPERTY TYPE NORMALIZATION
# ============================================================

def normalize_type_key(value):

    value = clean_text(value).lower()

    type_mapping = {

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

    if value in type_mapping:
        return type_mapping[value]

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        value
    ).strip("-")


# ============================================================
# 4. GALLERY, PRICING, CONNECTIVITY AND AMENITIES
# ============================================================

def parse_pipe_field(value, field_type):

    if pd.isna(value) or not str(value).strip():
        return []

    text = str(value).strip()

    lines = text.splitlines()

    parsed_items = []


    # --------------------------------------------------------
    # GALLERY
    # Format: Title | Category | Image URL
    # --------------------------------------------------------

    if field_type == "gallery":

        for line in lines:

            parts = [
                p.strip()
                for p in line.split("|")
            ]

            if len(parts) >= 3:

                parsed_items.append({

                    "url": parts[2],
                    "title": parts[0],
                    "category": parts[1]

                })


    # --------------------------------------------------------
    # PRICING MATRIX
    # Format: Type | Carpet | SuperBuilt | Floor | Price
    # --------------------------------------------------------

    elif field_type == "pricingMatrix":

        for line in lines:

            parts = [
                p.strip()
                for p in line.split("|")
            ]

            if len(parts) >= 5:

                parsed_items.append({

                    "typ": parts[0],

                    "carpet": parts[1].replace(
                        "Carpet:", ""
                    ).strip(),

                    "superBuilt": parts[2].replace(
                        "SuperBuilt:", ""
                    ).strip(),

                    "floorBand": parts[3].replace(
                        "Floor:", ""
                    ).strip(),

                    "allInPrice": parts[4].replace(
                        "Price:", ""
                    ).strip()

                })


    # --------------------------------------------------------
    # CONNECTIVITY
    # Format: Category | Name | Distance | Time | Icon
    # --------------------------------------------------------

    elif field_type == "connectivity":

        categories = {}

        for line in lines:

            parts = [
                p.strip()
                for p in line.split("|")
            ]

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
    # Google Sheets cell format:
    #
    # Grand Clubhouse (fa-building) |
    # Infinity Swimming Pool (fa-swimming-pool) |
    # State-of-the-art Gymnasium (fa-dumbbell)
    #
    # Each amenity becomes a separate JSON object.
    # --------------------------------------------------------

    elif field_type == "amenities":

        # Split amenities using pipe or newline.
        amenities = re.split(r"[|\n]+", text)

        for amenity in amenities:

            amenity = amenity.strip()

            if not amenity:
                continue

            # Extract name and icon from parentheses.
            match = re.match(
                r"^(.*?)\s*\(([^()]*)\)\s*$",
                amenity
            )

            if match:

                name = match.group(1).strip()
                icon = match.group(2).strip()

            else:

                # If no icon is provided, use default icon.
                name = amenity
                icon = "fa-check"

            if name:

                parsed_items.append({

                    "name": name,
                    "icon": icon or "fa-check"

                })

    return parsed_items


# ============================================================
# 5. GOOGLE MAPS URL GENERATOR
# ============================================================

def generate_google_maps_urls(
    lat,
    lng,
    location_name,
    title
):

    if lat != 0 and lng != 0:

        map_query = f"{lat},{lng}"

    else:

        map_query = location_name or title

    encoded_query = quote_plus(map_query)

    google_map_embed = (
        "https://www.google.com/maps"
        f"?q={encoded_query}&z=15&output=embed"
    )

    google_map_url = (
        "https://www.google.com/maps/search/"
        f"?api=1&query={encoded_query}"
    )

    return google_map_embed, google_map_url


# ============================================================
# 6. CONVERT GOOGLE SHEET TO JAVASCRIPT
# ============================================================

def convert_google_sheet_to_js(
    sheet_url,
    output_file="propertiesData.js"
):

    csv_url = get_csv_url(sheet_url)

    print("\nConnecting to Google Sheets...")

    try:

        df = pd.read_csv(
            csv_url,
            dtype=str,
            keep_default_na=False
        )

    except Exception as error:

        raise RuntimeError(
            "Unable to read Google Sheet. "
            "Make sure the sheet is shared as "
            "'Anyone with the link - Viewer'."
        ) from error

    properties_list = []

    for _, row in df.iterrows():

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

        # Generate Google Maps URLs.
        google_map_embed, google_map_url = (
            generate_google_maps_urls(
                latitude,
                longitude,
                location_name,
                title
            )
        )

        # Create property object.
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

            # AMENITIES - INDIVIDUAL OBJECTS
            "amenities": parse_pipe_field(
                row.get("Amenities (JSON/Pipe)", ""),
                "amenities"
            )

        }

        properties_list.append(prop)


    # ========================================================
    # 7. GENERATE JAVASCRIPT FILE
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
    # 8. DISPLAY RESULTS
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

    for prop in properties_list:

        print(
            f"\n{prop['title']}: "
            f"{len(prop['amenities'])} amenities"
        )

        for amenity in prop["amenities"]:

            print(
                f"  - {amenity['name']} "
                f"({amenity['icon']})"
            )

    print("\n======================================")


# ============================================================
# 9. RUN SCRIPT
# ============================================================

if __name__ == "__main__":

    sheet_url = (
        "https://docs.google.com/spreadsheets/d/"
        "1Bzm4LqHYETZy1XVe16WCLrLTCa-GPcnlyb2jmyNYx5M/"
        "edit?usp=sharing"
    )

    convert_google_sheet_to_js(
        sheet_url,
        output_file="propertiesData.js"
    )
