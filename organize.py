import os
import json
import yaml
import time
from tqdm import tqdm
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright


def take_screenshot(url, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1000, "height": 800}
        )

        # open page
        page.goto(url, wait_until="networkidle")

        # cookies popup
        buttons = [
            "Decline optional cookies",
            "Only allow essential cookies",
            "Allow all cookies"
        ]

        for button in buttons:
            try:
                page.get_by_text(button).click(timeout=1000)
                break
            except:
                pass

        # remove dialogs
        page.evaluate("""
            document.querySelectorAll('[role="dialog"]').forEach(e => e.remove());
        """)

        # remove headers/footer
        page.evaluate("""
            document.querySelectorAll('header, footer').forEach(e => e.remove());
        """)

        # petite pause de stabilisation
        page.wait_for_timeout(300)

        # screenshot
        try:
            article = page.locator("article").first
            article.screenshot(
                path=output_path
            )
        except Exception as e:
            print(f"Article screenshot failed: {e}")
            page.screenshot(
                path=output_path,
                full_page=True,
                animations="disabled"
            )

        browser.close()


def fix_encoding(text):
    if not text:
        return ""
    try:
        return text.encode("latin1").decode("utf-8")
    except:
        return text


def extract_fields(label_values):
    url = ""
    caption = ""
    hashtags = []
    author = ""

    for item in label_values:
        label = item.get("label", "")
        title = item.get("title", "")

        # URL
        if label == "URL":
            url = item.get("href") or item.get("value", "")

        # caption
        if "L" in label and "gende" in label:
            caption = item.get("value", "")

        # hashtags
        if title == "Hashtags":
            for block in item.get("dict", []):
                for inner in block.get("dict", []):
                    if inner.get("label") == "Nom":
                        hashtags.append("#" + inner.get("value", ""))

        # author
        if title.startswith("Propri"):
            try:
                author = item["dict"][0]["dict"][1]["value"]
            except:
                author = ""

    caption = fix_encoding(caption).replace("~", "")
    author = fix_encoding(author)

    return url, caption, hashtags, author


def detect_meta_category(hashtags, stats, category_map):
    hashtags_lower = [fix_encoding(t.lower().replace("#", "")) for t in hashtags]
    if hashtags_lower:
        for hashtag in hashtags_lower:
            for category, keywords in category_map.items():
                if any(k in hashtag for k in keywords):
                    stats[category] += 1
                    return category, stats
    else:
        stats["empty"] += 1
        return "empty", stats
    stats["other"] += 1
    return "other", stats


def main():
    print("### START INSTAGRAM IMPORT ###")

    # load configuration file
    with open("config/config.yml") as config_file:
        config = yaml.safe_load(config_file)
    config_file.close()
    input_folder = config["input_folder"]
    output_folder = Path(config["output_folder"])
    category_map = config["category_map"]
    output_folder.mkdir(parents=True, exist_ok=True)

    # load template markdown file for every post
    with open(config["template_path"], "r", encoding="utf-8") as template_file:
        template_data = template_file.read()
    template_file.close()

    # initialize stats
    stats = dict.fromkeys(category_map, 0)
    stats["other"] = 0
    stats["empty"] = 0

    # parse import files
    for input_file in os.listdir(input_folder):
        # load import file
        input_path = os.path.join(input_folder, input_file)
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        posts = data
        print(f"{len(posts)} posts found")

        # parse saved posts
        for i, post in enumerate(tqdm(posts, desc="Processing Instagram posts"), start=1):
            # timestamp
            ts = post.get("timestamp")
            date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "unknown-date"

            # lightweight extraction
            label_values = post.get("label_values", [])
            url, caption, hashtags, author = extract_fields(label_values)

            # category
            category, stats = detect_meta_category(hashtags, stats, category_map)

            folder = output_folder / category
            folder.mkdir(exist_ok=True)

            # paths
            base_filename = f"{ts}_{date}"

            md_path = folder / f"{base_filename}.md"
            img_filename = f"{base_filename}.png"
            img_path = folder / img_filename

            # skip if exists
            if md_path.exists() and img_path.exists():
                continue

            # screenshot
            image_markdown = ""

            # if not img_path.exists():
            #    try:
            #        take_screenshot(url, img_path)
            #        image_markdown = f"![]({img_filename})"
            #    except Exception as e:
            #        print(f"Screenshot failed for {url}: {e}")
            # else:
            #    image_markdown = f"![]({img_filename})"

            # markdown content
            content = (
                template_data
                .replace("{post_number}", f"{i:03d}")
                .replace("{url}", url)
                .replace("{date}", date)
                .replace("{caption}", caption)
                .replace("{hashtags}", ' '.join(hashtags))
                .replace("{author}", author)
                .replace("{custom_category}", category)
                .replace("{image}", image_markdown)
            )

            # write/update markdown
            md_path.write_text(content, encoding="utf-8", errors="replace")

    print(f"🚀 Import finished with: {stats}")

    with open(os.path.join(output_folder, "main.md"), "w", encoding="utf-8") as main_file:
        for category, count in stats.items():
            main_file.write(f"- [[{category}]]: {count}\n")
    main_file.close()

    print("### END INSTAGRAM IMPORT ###")


if __name__ == "__main__":
    start_time = time.time()
    main()
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Temps écoulé : {round(elapsed_time, 2)} secondes")
