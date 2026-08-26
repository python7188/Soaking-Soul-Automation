# Soaking Soul — Free Cloud Automation

This version intentionally does NOT use Veo API and does NOT publish to Instagram.

Every scheduled run:
1. Reads the quote database from Google Sheets.
2. Selects an unused quote.
3. Sends the creative request to Gemini.
4. Generates:
   - hook
   - Gemini video-generation prompt
   - voiceover
   - caption
   - hashtags
5. Saves everything into `REEL_OUTPUT`.
6. Marks the quote as used.

You then use your phone to:
1. Copy `Gemini_Video_Prompt` into Gemini/Veo.
2. Generate the Reel.
3. Copy the caption and hashtags.
4. Upload to Instagram manually.

## GitHub secrets

Create these repository secrets:

- `GEMINI_API_KEY`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `QUOTE_SHEET_NAME` (usually `Sheet1`)

`GOOGLE_SERVICE_ACCOUNT_JSON` is the complete service-account JSON as one secret.

Important:
- Share the Google Sheet with the service-account email as Editor.
- GitHub Actions runs even when your PC is OFF.
- The free GitHub Actions allowance and Gemini free quota depend on your accounts/usage. No paid Veo API is used here.
