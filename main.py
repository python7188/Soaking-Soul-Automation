import os
import json
import random
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from google import genai


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


def get_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def connect_sheet():
    service_account_json = get_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = get_env("GOOGLE_SHEET_ID")

    creds = Credentials.from_service_account_info(
        json.loads(service_account_json),
        scopes=SCOPES,
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    return sh


def get_records(ws):
    values = ws.get_all_values()
    if not values:
        return [], {}

    headers = values[0]
    index = {h.strip(): i for i, h in enumerate(headers)}
    records = []

    for row_number, row in enumerate(values[1:], start=2):
        row = row + [""] * (len(headers) - len(row))
        record = {h: row[i] for h, i in index.items()}
        record["_row"] = row_number
        records.append(record)

    return records, index


def select_quote(records):
    available = []

    for r in records:
        status = r.get("Status", "").strip().lower()
        used = r.get("Used", "").strip().lower()

        if status in ("available", "") and used not in ("yes", "true", "1"):
            available.append(r)

    if not available:
        raise RuntimeError("No unused/available quotes found.")

    # Prefer higher AI scores, while adding a little randomness.
    def score(r):
        try:
            return int(float(r.get("AI_Score", "0") or 0))
        except ValueError:
            return 0

    available.sort(key=score, reverse=True)
    top = available[: min(20, len(available))]
    return random.choice(top)


def build_prompt(quote):
    return f"""
You are the creative director for the Instagram brand "Soaking Soul".

Create ONE complete Instagram Reel package from this quote.

QUOTE DATA:
Quote ID: {quote.get("Quote_ID")}
Quote: {quote.get("Quote")}
Author: {quote.get("Author")}
Category: {quote.get("Category")}
Mood: {quote.get("Mood")}
Intensity: {quote.get("Intensity")}
Language: {quote.get("Language")}

Return ONLY valid JSON with exactly these keys:
quote_id
hook
gemini_video_prompt
voiceover
caption
hashtags

Requirements:
- hook: short, emotionally strong, suitable for the first 1-2 seconds.
- gemini_video_prompt: a detailed vertical 9:16 cinematic prompt for generating a 20-30 second Instagram Reel.
- Describe shots, camera movement, lighting, mood, transitions and visual continuity.
- Do not include copyrighted characters or logos.
- voiceover: natural spoken narration, about 45-70 words. Include the quote and author naturally.
- caption: emotionally engaging Instagram caption, 80-150 words, with line breaks.
- hashtags: 8-12 relevant hashtags as an array of strings.
- Keep the Soaking Soul tone: reflective, cinematic, calm, meaningful.
- Do not claim the quote is authentic if attribution is uncertain.
""".strip()


def generate(client, prompt):
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
        },
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response.")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Recover if the model accidentally wrapped JSON in markdown.
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)


def ensure_output_sheet(sh):
    try:
        return sh.worksheet("REEL_OUTPUT")
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(
            title="REEL_OUTPUT",
            rows=1000,
            cols=12,
        )


def save_output(ws, result):
    headers = [
        "Run_ID",
        "Created_UTC",
        "Quote_ID",
        "Hook",
        "Gemini_Video_Prompt",
        "Voiceover",
        "Caption",
        "Hashtags",
        "Status",
    ]

    existing = ws.get_all_values()
    if not existing:
        ws.append_row(headers)

    run_id = "R" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    row = [
        run_id,
        datetime.now(timezone.utc).isoformat(),
        result["quote_id"],
        result["hook"],
        result["gemini_video_prompt"],
        result["voiceover"],
        result["caption"],
        "\n".join(result["hashtags"]),
        "READY_FOR_MANUAL_UPLOAD",
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    return run_id


def mark_used(ws, index, quote):
    row = quote["_row"]

    def col(name):
        return index.get(name)

    updates = []

    if col("Used") is not None:
        updates.append((row, col("Used") + 1, "Yes"))

    if col("Times_Used") is not None:
        old = quote.get("Times_Used", "0")
        try:
            times = int(float(old or 0)) + 1
        except ValueError:
            times = 1
        updates.append((row, col("Times_Used") + 1, str(times)))

    if col("Last_Used") is not None:
        updates.append((
            row,
            col("Last_Used") + 1,
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        ))

    if col("Status") is not None:
        updates.append((row, col("Status") + 1, "Used"))

    for r, c, value in updates:
        ws.update_cell(r, c, value)


def main():
    print("Starting Soaking Soul cloud automation...")

    sh = connect_sheet()
    print("Google Sheets connected.")

    quote_ws = sh.worksheet(os.getenv("QUOTE_SHEET_NAME", "Sheet1"))
    records, index = get_records(quote_ws)
    print(f"Quotes found: {len(records)}")

    quote = select_quote(records)
    print(f"Selected: {quote.get('Quote_ID')} - {quote.get('Quote')}")

    client = genai.Client(api_key=get_env("GEMINI_API_KEY"))

    prompt = build_prompt(quote)
    result = generate(client, prompt)

    output_ws = ensure_output_sheet(sh)
    run_id = save_output(output_ws, result)
    mark_used(quote_ws, index, quote)

    # GitHub Actions can expose this in the job log.
    print("\n================ READY REEL PACKAGE ================\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n=====================================================")
    print(f"Run ID: {run_id}")
    print("Saved to REEL_OUTPUT.")
    print("Use the Gemini video prompt manually on mobile.")
    print("Then upload the generated video to Instagram manually.")


if __name__ == "__main__":
    main()
