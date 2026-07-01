#!/usr/bin/env python3
"""
Transcribe phone call recordings from Google Drive using Google Cloud Speech-to-Text API.
Monitors AI Systems/Calls/ and Audio/ folders, transcribes audio files via the synchronous API.
"""

import os
import pickle
import requests
import base64
from datetime import datetime
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Get authenticated Google Drive service."""
    token_path = os.path.expanduser('~/token.pickle')

    if not os.path.exists(token_path):
        print("✗ No credentials found. Run create_ai_system_folders.py first")
        return None

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build('drive', 'v3', credentials=creds)

def find_folder(service, name):
    """Find a folder by name."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id)', pageSize=1).execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None

def list_folder_contents(service, folder_id):
    """List all files in a folder."""
    results = service.files().list(
        q=f"parents='{folder_id}' and trashed=false",
        spaces='drive',
        fields='files(id, name, mimeType, createdTime)',
        pageSize=100
    ).execute()
    return results.get('files', [])

def download_file(service, file_id, file_name):
    """Download a file from Drive."""
    request = service.files().get_media(fileId=file_id)
    with open(file_name, 'wb') as f:
        f.write(request.execute())
    return file_name

def transcribe_with_google_speech(audio_file_path):
    """Transcribe audio using Google Cloud Speech-to-Text API (Long Running Operation)."""
    api_key_path = os.path.expanduser('~/speech_api_key.txt')

    if not os.path.exists(api_key_path):
        print("✗ speech_api_key.txt not found")
        return None

    with open(api_key_path, 'r') as f:
        api_key = f.read().strip()

    # Read audio file and encode to base64
    with open(audio_file_path, 'rb') as f:
        audio_content = f.read()

    audio_base64 = base64.b64encode(audio_content).decode()

    # Call Google Cloud Speech-to-Text Sync API
    url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"

    headers = {'Content-Type': 'application/json'}

    body = {
        'config': {
            'encoding': 'MP3',
            'languageCode': 'en-US',
            'enableAutomaticPunctuation': True,
        },
        'audio': {
            'content': audio_base64
        }
    }

    try:
        response = requests.post(url, json=body, headers=headers, timeout=300)

        if response.status_code != 200:
            print(f"  ⚠️  API Error ({response.status_code}): {response.text[:200]}")
            return None

        result = response.json()

        if 'error' in result:
            print(f"  ⚠️  API Error: {result['error']['message']}")
            return None

        # Extract transcript from results
        transcript_text = ""
        for result_item in result.get('results', []):
            for alternative in result_item.get('alternatives', []):
                transcript_text += alternative.get('transcript', '') + " "

        return transcript_text.strip() if transcript_text.strip() else None

    except Exception as e:
        print(f"  ⚠️  Transcription failed: {e}")
        return None

def save_transcript(transcript_text, audio_file_name):
    """Save transcript as markdown file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    filename = audio_file_name.rsplit('.', 1)[0] + '.md'

    content = f"""# Phone Call Recording - {audio_file_name}

**Transcribed:** {timestamp}

---

## Transcript

{transcript_text}

"""

    with open(filename, 'w') as f:
        f.write(content)

    return filename

def upload_to_drive(service, file_path, folder_id):
    """Upload file to Google Drive."""
    from googleapiclient.http import MediaFileUpload

    filename = os.path.basename(file_path)
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }

    media = MediaFileUpload(file_path, mimetype='text/markdown')
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    return file.get('webViewLink')

def main():
    service = get_drive_service()
    if not service:
        return

    # Find folders
    ai_systems_id = find_folder(service, 'AI Systems')

    # Look for Calls folder (could be under AI Systems or at root)
    calls_id = find_folder(service, 'Calls')

    # Look for Audio folder under AI Systems
    audio_id = None
    if ai_systems_id:
        query = f"name='Audio' and parents='{ai_systems_id}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id)', pageSize=1).execute()
        audio_id = results['files'][0]['id'] if results.get('files') else None

    print("=" * 60)
    print("Transcribing Phone Call Recordings")
    print("=" * 60)

    # List audio files (check Calls, Audio, and AI Systems folders)
    files = []
    if calls_id:
        files.extend(list_folder_contents(service, calls_id))
    if audio_id:
        files.extend(list_folder_contents(service, audio_id))
    if ai_systems_id:
        # Also check for audio directly in AI Systems
        ai_files = list_folder_contents(service, ai_systems_id)
        audio_files_in_ai = [f for f in ai_files if f['mimeType'].startswith('audio/')]
        files.extend(audio_files_in_ai)

    # Filter for audio files (m4a shows as audio/x-m4a or audio/mp4)
    audio_files = [f for f in files if f['mimeType'] in [
        'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/m4a',
        'audio/ogg', 'audio/x-m4a', 'application/octet-stream'
    ] or f['name'].endswith(('.mp3', '.m4a', '.wav', '.ogg', '.mp4'))]

    if not audio_files:
        print("\nℹ️  No audio files found in Calls folder")
        return

    print(f"\nFound {len(audio_files)} audio file(s):\n")

    for audio_file in audio_files:
        file_name = audio_file['name']
        file_id = audio_file['id']

        print(f"Processing: {file_name}")

        # Download audio file
        print(f"  ↓ Downloading...")
        local_path = download_file(service, file_id, file_name)

        # Transcribe
        print(f"  🎙️  Transcribing...")
        transcript = transcribe_with_google_speech(local_path)

        if transcript:
            print(f"  ✓ Transcription complete")

            # Save transcript
            transcript_file = save_transcript(transcript, file_name)
            print(f"  ✓ Transcript saved: {transcript_file}")

            # Upload transcript to Drive (Audio folder)
            print(f"  ↑ Uploading to Drive...")
            link = upload_to_drive(service, transcript_file, audio_id)
            print(f"    → {link}\n")

            # Clean up local files
            os.remove(local_path)
            os.remove(transcript_file)
        else:
            print(f"  ✗ Transcription failed\n")
            os.remove(local_path)

    print("=" * 60)
    print("✓ Transcription complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()
