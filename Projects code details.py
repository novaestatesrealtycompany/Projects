import pandas as pd
import re
import json

def get_csv_url(sheet_url):
    # Automatically extracts the file ID from your Google Sheet link
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
    if match:
        file_id = match.group(1)
        return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv"
    raise ValueError("Invalid Google Sheet URL provided.")

def parse_pipe_field(val, field_type):
    if pd.isna(val) or not str(val).strip():
        return []
    
    lines = str(val).strip().split('\n')
    parsed_items = []
    
    for line in lines:
        parts = [p.strip() for p in line.split('|')]
        
        if field_type == 'gallery' and len(parts) >= 3:
            parsed_items.append({
                "url": parts[2],
                "title": parts[0],
                "category": parts[1]
            })
        elif field_type == 'pricingMatrix' and len(parts) >= 5:
            carpet = parts[1].replace('Carpet:', '').strip()
            super_built = parts[2].replace('SuperBuilt:', '').strip()
            floor = parts[3].replace('Floor:', '').strip()
            price = parts[4].replace('Price:', '').strip()
            
            parsed_items.append({
                "typ": parts[0],
                "carpet": carpet,
                "superBuilt": super_built,
                "floorBand": floor,
                "allInPrice": price
            })
        elif field_type == 'connectivity' and len(parts) >= 4:
            parsed_items.append({
                "category": parts[0],
                "icon": parts[4] if len(parts) > 4 else "fa-briefcase",
                "items": [{
                    "name": parts[1],
                    "dist": parts[2],
                    "time": parts[3]
                }]
            })
        elif field_type == 'amenities':
            match = re.match(r'(.*?)\s*\((.*?)\)', line.strip())
            if match:
                parsed_items.append({
                    "name": match.group(1).strip(),
                    "icon": match.group(2).strip()
                })
            else:
                parsed_items.append({
                    "name": line.strip(),
                    "icon": "fa-check"
                })
    return parsed_items

def convert_google_sheet_to_js(sheet_url, output_file="propertiesData.js"):
    csv_url = get_csv_url(sheet_url)
    df = pd.read_csv(csv_url)
    
    properties_list = []
    
    for _, row in df.iterrows():
        prop = {
            "id": int(row.get("ID", 0)),
            "title": str(row.get("Title", "")),
            "subtitle": str(row.get("Subtitle", "")),
            "locationKey": str(row.get("Location Key", "")),
            "locationName": str(row.get("Location Name", "")),
            "typeKey": str(row.get("Type Key", "")),
            "typeLabel": str(row.get("Type Label", "")),
            "lat": float(row.get("Latitude", 0)),
            "lng": float(row.get("Longitude", 0)),
            "reraId": str(row.get("RERA ID", "")),
            "priceDisplay": str(row.get("Price Display", "")),
            "basePriceNum": float(row.get("Base Price (Cr)", 0)),
            "statusTag": str(row.get("Status Tag", "")),
            "vastuRating": str(row.get("Vastu Rating", "")),
            "acres": str(row.get("Acres", "")),
            "towers": str(row.get("Towers", "")),
            "totalUnits": str(row.get("Total Units", "")),
            "possession": str(row.get("Possession", "")),
            "heroImage": str(row.get("Hero Image URL", "")),
            "videoEmbedUrl": str(row.get("Video Embed URL", "")),
            "description": str(row.get("Description", "")),
            "gallery": parse_pipe_field(row.get("Gallery (JSON/Pipe)"), 'gallery'),
            "floorPlans": [],
            "pricingMatrix": parse_pipe_field(row.get("Pricing Matrix (JSON/Pipe)"), 'pricingMatrix'),
            "connectivityCategories": parse_pipe_field(row.get("Connectivity (JSON/Pipe)"), 'connectivity'),
            "googleMapEmbed": str(row.get("Google Map Embed", "")),
            "googleMapUrl": str(row.get("Google Map URL", "")),
            "amenities": parse_pipe_field(row.get("Amenities (JSON/Pipe)"), 'amenities')
        }
        properties_list.append(prop)
    
    js_content = f"const propertiesData = {json.dumps(properties_list, indent=4)};"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(js_content)
    
    print(f"✅ Successfully extracted {len(properties_list)} property items into `{output_file}`!")

# ==========================================
# PARESE YOUR GOOGLE SHEET LINK HERE:
# ==========================================
if __name__ == "__main__":
    sheet_url = "https://docs.google.com/spreadsheets/d/1Bzm4LqHYETZy1XVe16WCLrLTCa-GPcnlyb2jmyNYx5M/edit?usp=sharing"
    convert_google_sheet_to_js(sheet_url)