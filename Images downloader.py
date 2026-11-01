import os
import requests
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright

target_url = "https://www.prestigeconstructions.com/ads/bangalore/prestige-somerville?_gl=1*1ih2b68*_up*MQ..*_gs*MQ..&gclid=CjwKCAjwxpvXBhASEiwAue4B4Tz7mm4yLVjxw8ThuYhZgymz7MLH8is9CKCERgB2YUzK12Str0v78BoCP40QAvD_BwE&gbraid=0AAAAADMzGQHUqqpNggBDFclvqZYYu8jsn"
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
output_dir = "E:/Nova Estates Projects/Prestige/Prestige-Somervile/Images"
os.makedirs(output_dir, exist_ok=True)

with sync_playwright() as p:
    print("Launching browser and loading page...")
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(target_url, wait_until="networkidle", timeout=60000)

    # Scroll down to trigger lazy loading for all 7 images
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(3000)

    # Extract img src, data-src, and background-image URLs
    extracted_urls = page.evaluate("""() => {
        let urls = [];
        
        // Check standard img elements (src and data-src)
        document.querySelectorAll('img').forEach(img => {
            let src = img.currentSrc || img.src || img.getAttribute('data-src');
            if (src) urls.push(src);
        });

        // Check CSS background images
        document.querySelectorAll('*').forEach(el => {
            let bg = window.getComputedStyle(el).backgroundImage;
            if (bg && bg !== 'none') {
                let match = bg.match(/url\\(['"]?(.*?)['"]?\\)/);
                if (match) urls.push(match[1]);
            }
        });

        return urls;
    }""")
    browser.close()

# Deduplicate URLs and filter out tracking pixels/icons
unique_urls = []
for url in extracted_urls:
    if not url:
        continue
    # Filter out tracking pixels, logos, icons, and non-image assets
    if any(ignore in url for ignore in ['facebook.com', 'analytics', 'doubleclick', 'favicon', 'logo']):
        continue
    if url not in unique_urls:
        unique_urls.append(url)

print(f"Found {len(unique_urls)} valid image candidates.")

saved_count = 0
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

for idx, img_url in enumerate(unique_urls):
    if img_url.startswith('//'):
        img_url = "https:" + img_url
    elif img_url.startswith('/'):
        img_url = "https://www.prestigeconstructions.com" + img_url

    try:
        res = requests.get(img_url, headers=headers, timeout=15)
        if res.status_code != 200:
            continue

        # Skip SVG files if any
        if img_url.lower().endswith('.svg'):
            continue

        # Open image and convert to RGB PNG
        img = Image.open(BytesIO(res.content))
        
        # Skip small 1x1 or icon-sized images
        if img.width < 100 or img.height < 100:
            continue

        img_converted = img.convert("RGB")
        file_name = f"{saved_count + 1}.png"
        file_path = os.path.join(output_dir, file_name)
        img_converted.save(file_path, "PNG")

        print(f"[{saved_count + 1}] Successfully saved: {file_name}")
        saved_count += 1

    except Exception as e:
        print(f"Failed to process {img_url}: {e}")

print(f"\nDone! All {saved_count} property images saved to: {output_dir}")