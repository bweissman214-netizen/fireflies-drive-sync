#!/usr/bin/env python3
"""
Meeting Extraction Tool: Fetches Fireflies transcripts and extracts actionable insights via Claude.
"""

import json
import sys
from datetime import datetime
import anthropic
import requests
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Configuration
FIREFLIES_API_KEY = "3c188f76-309b-4304-a0ea-f80794c52412"
FIREFLIES_GRAPHQL_URL = "https://api.fireflies.ai/graphql"
TODOIST_API_KEY = "b6c1629c971c0518d154fccae61f150433214985"
TODOIST_GENERAL_PROJECT_ID = "6h2J724XVcM5gchf"

# Load the extraction prompt
EXTRACTION_PROMPT_FILE = "extraction_prompt.md"

def fetch_fireflies_transcript(transcript_id):
    """Fetch a specific transcript from Fireflies."""
    query = """
    query {
      transcript(id: "%s") {
        id
        title
        date
        duration
        sentences {
          speaker_id
          text
          start_time
        }
      }
    }
    """ % transcript_id

    response = requests.post(
        FIREFLIES_GRAPHQL_URL,
        json={"query": query},
        headers={
            "Authorization": f"Bearer {FIREFLIES_API_KEY}",
            "Content-Type": "application/json"
        }
    )

    data = response.json()
    if "errors" in data:
        print(f"Fireflies API error: {data['errors']}")
        return None

    return data.get("data", {}).get("transcript")

def format_transcript_for_extraction(fireflies_transcript):
    """Convert Fireflies format to our extraction input format."""
    if not fireflies_transcript:
        return None

    # Convert epoch ms to ISO datetime
    date_ms = fireflies_transcript.get("date", 0)
    date_str = datetime.fromtimestamp(date_ms / 1000).isoformat() + "Z"

    return {
        "metadata": {
            "title": fireflies_transcript.get("title", "Untitled"),
            "date": date_str,
            "duration_minutes": round(fireflies_transcript.get("duration", 0)),
            "attendees": ["See speakers in sentences"]
        },
        "sentences": fireflies_transcript.get("sentences", [])
    }

def extract_with_claude(transcript_data):
    """Send transcript to Claude for extraction."""

    # Read the extraction prompt
    try:
        with open(EXTRACTION_PROMPT_FILE, "r") as f:
            prompt_template = f.read()
    except FileNotFoundError:
        print(f"Error: {EXTRACTION_PROMPT_FILE} not found")
        sys.exit(1)

    # Insert transcript data into prompt
    full_prompt = prompt_template.replace(
        "[TRANSCRIPT WILL BE INSERTED HERE]",
        f"```json\n{json.dumps(transcript_data, indent=2)}\n```"
    )

    # Call Claude API
    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": full_prompt
            }
        ]
    )

    return message.content[0].text

def generate_filename(title, date_str):
    """Generate semantic filename from meeting title and date."""
    # Format: "Meeting Title - YYYY-MM-DD"
    # Remove any special characters that could cause filesystem issues
    safe_title = "".join(c if c.isalnum() or c in " -&" else "" for c in title).strip()
    return f"{safe_title} - {date_str}"

def parse_extraction_json(extraction_output):
    """Extract and parse JSON from Claude's response."""
    try:
        # Handle markdown code block wrapping
        json_start = extraction_output.find("{")
        json_end = extraction_output.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = extraction_output[json_start:json_end]
            # Try to parse - if it fails, it might be due to unescaped quotes in strings
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"  ⚠️  JSON parsing failed: {e}")
                print(f"     Trying alternative parsing...")
                # If normal parsing fails, try to clean up the string
                return None
        return None
    except Exception as e:
        print(f"  ⚠️  Error parsing: {e}")
        return None

def create_todoist_task(todo, transcript_id, transcript_title):
    """Create a task in Todoist from an extracted todo."""
    headers = {
        "Authorization": f"Bearer {TODOIST_API_KEY}",
        "Content-Type": "application/json"
    }

    # Build task description with context
    description = f"From: {transcript_title}\n\nContext: {todo.get('context', 'N/A')}"
    if todo.get('owner') and todo['owner'] != 'Unclear':
        description = f"Owner: {todo['owner']}\n\n{description}"

    task_data = {
        "content": todo["action"],
        "project_id": TODOIST_GENERAL_PROJECT_ID,
        "description": description
    }

    # Add due date if specified
    if todo.get("deadline") and todo["deadline"] != "Not specified":
        task_data["due_date"] = todo["deadline"]

    response = requests.post(
        "https://api.todoist.com/api/v1/tasks",
        json=task_data,
        headers=headers
    )

    if response.status_code == 200:
        task = response.json()
        task_id = task["id"]
        task_url = f"https://todoist.com/app/task/{task_id}"
        return task_id, task_url
    else:
        print(f"  ⚠️  Failed to create task: {response.status_code}")
        print(f"     Response: {response.text}")
        return None, None

def get_drive_service():
    """Authenticate and get Google Drive service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    SCOPES = ['https://www.googleapis.com/auth/drive.file']  # Write access to Drive
    OAUTH_FILE = os.path.expanduser('~/gmail_oauth.json')
    TOKEN_FILE = os.path.expanduser('~/.drive_token.json')

    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_FILE, SCOPES)
            creds = flow.run_local_server(port=8080, open_browser=True)

        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def find_file_in_drive(folder_path, search_term):
    """Find a file in Google Drive by folder path and search term.

    folder_path: e.g., "AI System/Zoom"
    search_term: e.g., "bonobo"
    """
    try:
        service = get_drive_service()

        # Navigate folder path
        folder_id = 'root'
        for folder_name in folder_path.split('/'):
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{folder_id}' in parents"
            results = service.files().list(q=query, spaces='drive', fields='files(id, name)', pageSize=1).execute()
            files = results.get('files', [])
            if not files:
                print(f"  ✗ Folder '{folder_name}' not found")
                return None
            folder_id = files[0]['id']

        # Search for file with search term
        query = f"name contains '{search_term}' and trashed=false and '{folder_id}' in parents"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)', pageSize=10).execute()
        files = results.get('files', [])

        if files:
            return files[0]['id'], files[0]['name']
        else:
            print(f"  ✗ No file found with '{search_term}' in {folder_path}")
            return None
    except Exception as e:
        print(f"  ✗ Error searching Drive: {e}")
        return None

def read_file_from_drive(file_id):
    """Read text content from a Google Drive file."""
    try:
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        content = request.execute()
        return content.decode('utf-8') if isinstance(content, bytes) else content
    except Exception as e:
        print(f"  ✗ Error reading file from Drive: {e}")
        return None

def get_calendar_service():
    """Authenticate and get Google Calendar service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    SCOPES = ['https://www.googleapis.com/auth/calendar']
    OAUTH_FILE = os.path.expanduser('~/gmail_oauth.json')
    TOKEN_FILE = os.path.expanduser('~/.calendar_token.json')

    creds = None

    # Load existing token if it exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # If no valid credentials, do OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_FILE, SCOPES)
            creds = flow.run_local_server(port=8080, open_browser=True)

        # Save the token for next time
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)


def create_calendar_event(person, topic, suggested_date, attendee_email=None):
    """Create a calendar event for a meeting with optional attendees."""
    try:
        service = get_calendar_service()
        from datetime import datetime as dt, timedelta

        # Parse suggested date
        if suggested_date is None or suggested_date == "null":
            event_date = dt.now() + timedelta(days=7)  # Default to next week
        elif suggested_date.lower() in ["next week", "asap", "soon"]:
            event_date = dt.now() + timedelta(days=7)
        elif suggested_date.lower() == "tomorrow":
            event_date = dt.now() + timedelta(days=1)
        else:
            try:
                event_date = dt.fromisoformat(suggested_date)
            except:
                event_date = dt.now() + timedelta(days=7)

        # Only use email if explicitly provided (from transcript)
        resolved_email = attendee_email

        # Create event
        event = {
            'summary': f'Sync: {topic}' if topic else f'Meet with {person}',
            'description': f'Meeting with {person} to discuss: {topic}' if topic else f'Follow-up with {person}',
            'start': {
                'date': event_date.strftime('%Y-%m-%d'),
            },
            'end': {
                'date': (event_date + timedelta(days=1)).strftime('%Y-%m-%d'),
            },
            'transparency': 'opaque',
        }

        # Add attendee ONLY if email was explicitly provided in transcript
        if resolved_email:
            event['attendees'] = [
                {'email': resolved_email, 'displayName': person}
            ]

        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return created_event.get('htmlLink'), resolved_email
    except Exception as e:
        print(f"  ⚠️  Failed to create calendar event: {e}")
        return None, None

def get_gmail_service():
    """Authenticate and get Gmail service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    SCOPES = ['https://www.googleapis.com/auth/gmail.compose']
    OAUTH_FILE = os.path.expanduser('~/gmail_oauth.json')
    TOKEN_FILE = os.path.expanduser('~/.gmail_token.json')

    creds = None

    # Load existing token if it exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # If no valid credentials, do OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_FILE, SCOPES)
            print("\n🔐 Opening browser for Gmail authorization...")
            print("   If browser doesn't open, visit the URL shown in the terminal")
            creds = flow.run_local_server(port=8080, open_browser=True)

        # Save the token for next time
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def send_todos_for_review(todos, transcript_title, extraction_json):
    """Send extracted todos via email for review."""
    try:
        service = get_gmail_service()

        # Build email body
        todos_html = "<ul style='line-height: 1.8;'>"
        for i, todo in enumerate(todos, 1):
            owner = todo.get('owner', 'Unclear')
            deadline = todo.get('deadline', 'Not specified')
            context = todo.get('context', '')

            todos_html += f"""
            <li style='margin-bottom: 15px; padding: 10px; background: #f5f5f5; border-left: 3px solid #4285f4;'>
                <strong>{i}. {todo['action']}</strong><br/>
                <small>Owner: {owner} | Deadline: {deadline}</small><br/>
                <em style='color: #666;'>{context}</em>
            </li>
            """
        todos_html += "</ul>"

        subject = f"📝 Review Todos: {transcript_title}"

        body_html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
    <h2>Todo Review for: {transcript_title}</h2>

    <p>The following todos were extracted from the meeting. Please review and approve before adding to Todoist.</p>

    <h3>Extracted Todos ({len(todos)})</h3>
    {todos_html}

    <hr style='margin: 20px 0; border: none; border-top: 1px solid #ddd;'/>

    <p style='color: #666; font-size: 12px;'>
        <strong>Next steps:</strong> Review the todos above. Once approved, you can manually add them to Todoist or reply to this email with any changes.
    </p>
</div>
"""

        # Create MIME message
        msg = MIMEMultipart('alternative')
        msg['To'] = 'bweissman214@gmail.com'
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html'))

        # Encode and create draft
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw_message}}
        ).execute()

        draft_url = f"https://mail.google.com/mail/u/0/#drafts?compose={draft['id']}"
        return draft_url
    except Exception as e:
        print(f"  ⚠️  Failed to send review email: {e}")
        return None

def create_gmail_draft(email_content, transcript_title):
    """Create a Gmail draft from extracted email content."""
    try:
        service = get_gmail_service()

        # Extract subject from content or use title
        subject = transcript_title if "Meeting" in transcript_title else f"Meeting Summary: {transcript_title}"

        # Convert markdown-style formatting to HTML
        import re
        body_text = email_content
        body_text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', body_text)  # **bold** to <strong>
        body_text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', body_text)  # *italic* to <em>

        # Format body with proper line breaks and styling for Gmail
        body_html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333;">
{body_text.replace(chr(10), '<br>')}
</div>
"""

        # Create MIME message
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart('alternative')
        msg['To'] = 'bweissman214@gmail.com'
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html'))

        # Encode and create draft
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw_message}}
        ).execute()

        draft_url = f"https://mail.google.com/mail/u/0/#drafts?compose={draft['id']}"
        return draft_url
    except Exception as e:
        print(f"  ⚠️  Failed to create Gmail draft: {e}")
        return None

def get_file_naming(fireflies_data, extraction_json):
    """Generate semantic filename from transcript title and date (not speaker names)."""
    # Get date from Fireflies data
    date_ms = fireflies_data.get('date', 0)
    date_str = datetime.fromtimestamp(date_ms / 1000).strftime('%Y-%m-%d')

    # Use meeting title from Fireflies as the primary identifier
    title = fireflies_data.get('title', 'Meeting')

    # Clean up title: remove special chars but keep alphanumeric, spaces, and hyphens
    safe_title = "".join(c if c.isalnum() or c in " -&" else "" for c in title).strip()

    # Fallback to generic name if title is empty or just special chars
    if not safe_title:
        safe_title = "Meeting"

    # Format: [Topic/Title] - [YYYY-MM-DD]
    filename_base = f"{safe_title} - {date_str}"

    return filename_base

def save_results(transcript_id, transcript_title, extraction_output, fireflies_data=None):
    """Save extraction results AND raw transcript to files and create Todoist tasks."""
    timestamp = datetime.now().isoformat()

    # Parse the extraction JSON
    extraction_json = parse_extraction_json(extraction_output)

    if not extraction_json:
        extraction_json = {"raw_output": extraction_output}

    # Generate semantic filename
    filename_base = get_file_naming(fireflies_data, extraction_json)

    # Save extraction to JSON file
    extraction_filename = f"{filename_base}.json"
    with open(extraction_filename, "w") as f:
        json.dump({
            "timestamp": timestamp,
            "transcript_id": transcript_id,
            "extraction": extraction_json
        }, f, indent=2)

    print(f"\n✅ Extraction saved to {extraction_filename}")

    # Save raw transcript to file
    if fireflies_data and "sentences" in fireflies_data and fireflies_data["sentences"]:
        transcript_filename = f"{filename_base}.md"
        with open(transcript_filename, "w") as f:
            date_obj = datetime.fromtimestamp(fireflies_data.get('date', 0)/1000)

            # Header with clean formatting
            f.write(f"\n{'*' * 70}\n")
            f.write(f"*  {transcript_title.upper()}\n")
            f.write(f"{'*' * 70}\n\n")

            # Meeting metadata
            f.write(f"DATE:          {date_obj.strftime('%B %d, %Y')}\n")
            f.write(f"TIME:          {date_obj.strftime('%I:%M %p')}\n")
            f.write(f"DURATION:      {fireflies_data.get('duration', 0):.1f} minutes\n")
            f.write(f"TRANSCRIPT ID: {transcript_id}\n")
            f.write(f"\n{'─' * 70}\n\n")

            # Executive Summary
            if extraction_json and ("project_themes" in extraction_json or "todos" in extraction_json or "email_draft_ready" in extraction_json):
                f.write("EXECUTIVE SUMMARY\n")
                f.write("─" * 70 + "\n\n")

                # Extract key themes
                themes = extraction_json.get("project_themes", [])
                if themes:
                    f.write("KEY TOPICS:\n")
                    for theme in themes[:3]:  # First 3 themes
                        theme_name = theme.get("theme", "")
                        sentiment = theme.get("sentiment", "")
                        if theme_name:
                            f.write(f"  • {theme_name}")
                            if sentiment:
                                f.write(f" ({sentiment})")
                            f.write("\n")
                    f.write("\n")

                # Extract action items
                todos = extraction_json.get("todos", [])
                if todos:
                    f.write("ACTION ITEMS:\n")
                    for todo in todos[:5]:  # First 5 todos
                        action = todo.get("action", "")
                        owner = todo.get("owner", "")
                        deadline = todo.get("deadline", "")
                        if action:
                            f.write(f"  • {action}")
                            if owner and owner != "Unclear":
                                f.write(f" (Owner: {owner})")
                            if deadline and deadline != "Not specified":
                                f.write(f" [Due: {deadline}]")
                            f.write("\n")
                    f.write("\n")

                # Extract key points from email draft
                if extraction_json.get("email_draft_ready"):
                    email_text = extraction_json["email_draft_ready"]
                    # Extract first meaningful sentence or line
                    lines = [l.strip() for l in email_text.split('\n') if l.strip() and not l.startswith('**')]
                    if lines:
                        summary_line = next((l for l in lines if len(l) > 20), lines[0])
                        f.write(f"OVERVIEW: {summary_line[:150]}\n")

                f.write(f"\n{'─' * 70}\n\n")

            # Extract key concepts for bolding
            key_concepts = set()
            if extraction_json:
                # Get themes
                for theme in extraction_json.get("project_themes", []):
                    if theme.get("theme"):
                        key_concepts.add(theme["theme"])
                # Get people mentioned
                for person in extraction_json.get("people_mentioned", []):
                    if isinstance(person, dict) and person.get("name"):
                        key_concepts.add(person["name"])
                    elif isinstance(person, str):
                        key_concepts.add(person)

            current_speaker = None
            for sentence in fireflies_data["sentences"]:
                speaker = str(sentence.get("speaker_id", "Unknown"))
                text = sentence.get("text", "")

                if speaker != current_speaker:
                    if current_speaker is not None:
                        f.write("\n")
                    speaker_label = f"SPEAKER {speaker}" if speaker.isdigit() else speaker
                    f.write(f"\n>>> {speaker_label.upper()} <<<\n\n")
                    current_speaker = speaker

                # Bold key concepts in the text
                bolded_text = text
                for concept in key_concepts:
                    # Case-insensitive replacement with word boundaries
                    import re
                    pattern = r'\b' + re.escape(concept) + r'\b'
                    bolded_text = re.sub(pattern, f"**{concept}**", bolded_text, flags=re.IGNORECASE)

                f.write(f"{bolded_text}\n")

            f.write(f"\n{'─' * 70}\n")
            f.write(f"END OF TRANSCRIPT\n")
            f.write(f"{'─' * 70}\n")

        print(f"✅ Transcript saved to {transcript_filename}")

    # Send todos via email for review
    if extraction_json and "todos" in extraction_json:
        todos = extraction_json["todos"]
        if todos:
            print(f"\n📝 Sending {len(todos)} todo(s) for email review...")
            email_url = send_todos_for_review(todos, transcript_title, extraction_json)
            if email_url:
                print(f"  ✓ Review email sent")
                print(f"    → {email_url}")
            else:
                print(f"  ⚠️  Failed to send review email")
        else:
            print("\nℹ️  No todos extracted from this meeting")

    # Create Gmail draft from email_draft_ready
    if extraction_json and "email_draft_ready" in extraction_json:
        email_content = extraction_json["email_draft_ready"]
        if email_content:
            print(f"\n✉️  Creating Gmail draft...")
            draft_url = create_gmail_draft(email_content, transcript_title)
            if draft_url:
                print(f"  ✓ Gmail draft created")
                print(f"    → {draft_url}")
            else:
                print(f"  ✗ Failed to create Gmail draft (check permissions)")
        else:
            print("\nℹ️  No email draft generated")

    # Create calendar events from meeting suggestions
    if extraction_json and "meeting_suggestions" in extraction_json:
        suggestions = extraction_json["meeting_suggestions"]
        if suggestions:
            print(f"\n📅 Creating calendar events ({len(suggestions)} meeting(s))...")
            for i, suggestion in enumerate(suggestions, 1):
                person = suggestion.get("person", "Unknown")
                topic = suggestion.get("topic", "")
                suggested_date = suggestion.get("suggested_date")
                attendee_email = suggestion.get("email")  # Only use if explicitly in transcript

                event_url, resolved_email = create_calendar_event(person, topic, suggested_date, attendee_email)
                if event_url:
                    if resolved_email:
                        print(f"  ✓ Meeting {i}: {person} - {topic}")
                        print(f"    Inviting: {resolved_email}")
                        print(f"    → {event_url}")
                    else:
                        print(f"  ✓ Meeting {i}: {person} - {topic}")
                        print(f"    (No email in transcript - create event without attendee)")
                        print(f"    → {event_url}")
                else:
                    print(f"  ✗ Meeting {i}: {person} (failed to create)")
        else:
            print("\nℹ️  No meeting suggestions extracted")

    return filename_base

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_meeting.py <transcript_id>")
        print("\nExample:")
        print("  python extract_meeting.py 01KWCG8NRGKRYSYS4SDY9BZG98")
        sys.exit(1)

    transcript_id = sys.argv[1]

    print(f"🔄 Fetching transcript {transcript_id} from Fireflies...")
    fireflies_data = fetch_fireflies_transcript(transcript_id)

    if not fireflies_data:
        print("❌ Failed to fetch transcript")
        sys.exit(1)

    print(f"✓ Got transcript: {fireflies_data.get('title')}")

    # Format for extraction
    transcript_input = format_transcript_for_extraction(fireflies_data)

    print("🤖 Running Claude extraction...")
    extraction = extract_with_claude(transcript_input)

    # Print the extraction
    print("\n" + "="*60)
    print("EXTRACTION OUTPUT:")
    print("="*60)
    print(extraction)

    # Save results and create Todoist tasks
    transcript_title = fireflies_data.get('title', 'Untitled Meeting')
    save_results(transcript_id, transcript_title, extraction, fireflies_data)

if __name__ == "__main__":
    main()
