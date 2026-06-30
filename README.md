# Fireflies → Drive → Claude Extraction System

Automatically extract actionable insights from meeting transcripts: todos, emails, calendar events, and more.

## What It Does

This system creates an automated pipeline:
1. **Fetch** transcripts from Fireflies.ai
2. **Extract** structured data using Claude AI:
   - Action items (with owners & deadlines)
   - Email drafts (ready to send)
   - People mentioned (with context)
   - Calendar items & meeting suggestions
   - Project themes & insights
3. **Auto-create**:
   - Todoist tasks (in your General project)
   - Gmail drafts (for review before sending)
   - Google Calendar events (for suggested meetings)

All with a single command.

## Setup

### Prerequisites
- Python 3.9+
- Fireflies.ai account (with transcripts)
- Google Cloud project with APIs enabled
- Anthropic API key (Claude access)
- Todoist API key

### 1. Get API Keys

**Fireflies API Key:**
- Log in to Fireflies.ai
- Go to Settings → API
- Copy your API key

**Anthropic API Key:**
- Visit https://console.anthropic.com
- Create an API key
- Set `ANTHROPIC_API_KEY` environment variable

**Todoist API Key:**
- Log in to Todoist
- Go to Settings → Integrations → API token
- Copy your token

**Google Cloud Setup:**
- Create OAuth credentials (Desktop application)
- Download JSON and save as `~/gmail_oauth.json`
- Enable these APIs:
  - Gmail API
  - Google Calendar API
  - Google Drive API (optional, for future enhancements)

### 2. Install Dependencies

```bash
pip install anthropic requests google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### 3. Configure Script

Edit `extract_meeting.py` and add your API keys:

```python
FIREFLIES_API_KEY = "your-fireflies-key"
TODOIST_API_KEY = "your-todoist-key"
TODOIST_GENERAL_PROJECT_ID = "your-project-id"  # Find in Todoist URL
```

Set environment variable:
```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
```

## Usage

### Extract from a Fireflies Transcript

```bash
python3 extract_meeting.py <transcript-id>
```

**Example:**
```bash
python3 extract_meeting.py 01KWA9Y40CZXZDWB7BHTDSGQMY
```

### What Happens

1. ✅ Fetches transcript from Fireflies
2. ✅ Runs Claude extraction (using Haiku for cost efficiency)
3. ✅ Creates Todoist tasks for action items
4. ✅ Generates Gmail draft with meeting summary
5. ✅ Creates Google Calendar events for suggested meetings
6. ✅ Saves full extraction as JSON

### Output

```
🔄 Fetching transcript...
✓ Got transcript: Jun 29, 02:23 PM

🤖 Running Claude extraction...

📝 Creating 10 todo(s) in Todoist...
  ✓ Task 1: [Action item]
    → https://todoist.com/app/task/...

✉️  Creating Gmail draft...
  ✓ Gmail draft created
    → https://mail.google.com/mail/u/0/#drafts?compose=...

📅 Creating calendar events (3 meeting(s))...
  ✓ Meeting 1: Stuart Heitman - Shvatim discussion
    → https://www.google.com/calendar/event?eid=...

✅ Results saved to extraction_XXXXX.json
```

## Extraction Details

### What Gets Extracted

**Todos:**
- Action items with owners and deadlines
- Context on why each action matters

**Email Drafts:**
- Recipients and suggested subject lines
- Key points to communicate

**People Mentioned:**
- Names and roles
- Context on their involvement

**Calendar Items:**
- Existing meetings/deadlines referenced
- Suggested meetings to schedule

**Meeting Suggestions:**
- People to meet with
- Topics to discuss
- Suggested dates/timeframes

**Project Themes:**
- Main topics discussed
- Key points per theme
- Sentiment (positive/neutral/negative)

**Email Draft (Full):**
- Professional summary formatted for Gmail
- Scannable in ~2 minutes
- Ready to review & send

### Extraction Prompt

See `extraction_prompt.md` for the full Claude prompt that guides the extraction. Modify it to customize extraction behavior.

## Cost Efficiency

- **Model:** Claude Haiku (most cost-effective)
- **Tokens:** ~7K input, ~2.5K output per transcript
- **Cost per extraction:** ~$0.01 USD
- **API calls:** Fireflies (free), Todoist (free), Gmail (free), Calendar (free)

## File Structure

```
.
├── extract_meeting.py          # Main script
├── extraction_prompt.md        # Claude extraction instructions
├── test_extraction.py          # Local test script
├── test_calendar.py            # Calendar integration test
├── test_transcript.json        # Example transcript
├── gmail_oauth.json            # OAuth config (gitignored)
├── README.md                   # This file
└── .gitignore                  # Credentials & tokens
```

## OAuth Authorization

The first time you run the script, it will:
1. Open your browser for Google authorization
2. Save tokens locally for future use
3. Store tokens in:
   - `~/.gmail_token.json` (Gmail & Calendar)
   - `~/.calendar_token.json` (Calendar)

These tokens auto-refresh when expired.

## Testing

### Test Calendar Integration (No Claude Cost)

```bash
python3 test_calendar.py
```

This creates test calendar events without calling Claude API.

### Test Extraction on Sample

```bash
python3 test_extraction.py
```

This runs extraction on a local sample meeting (useful for testing without real transcripts).

## Limitations & Notes

- **Phone calls:** Fireflies may not support direct cell phone integration; use manual recording + upload
- **WhatsApp:** Requires WhatsApp Business setup; manual save-to-Drive recommended
- **CRM:** Currently mentions people; future enhancement to auto-update Google Sheets CRM
- **Email sending:** Drafts are created but not auto-sent (you review first)

## Roadmap

Phase 1 (Complete):
- ✅ Fireflies → Claude extraction
- ✅ Todoist integration
- ✅ Gmail draft creation
- ✅ Calendar event creation

Phase 2 (Planned):
- Phone call recording & transcription
- WhatsApp message capture
- Google Sheets CRM updates
- Project folder organization in Drive
- Nightly automation sweeps

## Troubleshooting

**"Gmail API has not been used in project"**
- Enable Gmail API in Google Cloud Console
- Wait 1-2 minutes for activation

**"Invalid credentials"**
- Delete `~/.gmail_token.json` and `~/.calendar_token.json`
- Re-run script to re-authorize

**"Todoist task creation failed"**
- Verify API key is correct
- Check project ID matches your General project

**"Claude API error"**
- Verify `ANTHROPIC_API_KEY` env var is set
- Check your Anthropic account has available credits

## Contributing

Feel free to:
- Improve the extraction prompt
- Add new output formats
- Optimize token usage
- Add support for other tools (Slack, Outlook, etc.)

## License

MIT

---

Built for executives who want to automate meeting-to-action intelligence.
