#!/usr/bin/env python3
"""
Sync extraction JSON files to Google Drive (AI Systems/Zoom/).
Watches for new extraction_*.json files and uploads them automatically.
"""

import os
import glob
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_service():
    """Get authenticated Google Drive service."""
    token_path = os.path.expanduser('~/token.pickle')

    if not os.path.exists(token_path):
        print("✗ No credentials found. Run create_ai_system_folders.py first")
        return None

    with open(token_path, 'rb') as token:
        creds = pickle.load(token)

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build('drive', 'v3', credentials=creds)

def find_folder(service, name):
    """Find a folder by name."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id)', pageSize=1).execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None

def upload_file_to_drive(service, file_path, folder_id):
    """Upload a file to Google Drive."""
    filename = os.path.basename(file_path)

    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }

    media = MediaFileUpload(file_path, mimetype='application/json')
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    return file.get('webViewLink')

def main():
    service = get_service()
    if not service:
        return

    # Find AI Systems/Zoom folder
    ai_systems_id = find_folder(service, 'AI Systems')
    if not ai_systems_id:
        print("✗ AI Systems folder not found")
        return

    zoom_id = find_folder(service, 'Zoom')
    if not zoom_id:
        print("✗ Zoom folder not found inside AI Systems")
        return

    print("=" * 60)
    print("Syncing Extractions & Transcripts to Google Drive")
    print("=" * 60)

    # Find all extraction and transcript files (both old and new naming schemes)
    extraction_files = glob.glob("extraction_*.json") + glob.glob("*[0-9].json")  # New semantic names
    transcript_files = glob.glob("transcript_*.md") + glob.glob("*[0-9].md")  # New semantic names

    # Remove duplicates
    all_files = list(set(extraction_files + transcript_files))
    # Filter to only relevant files
    all_files = [f for f in all_files if f.endswith(('.json', '.md')) and not f.startswith('.')]

    if not all_files:
        print("\nℹ️  No files to sync")
        return

    print(f"\nFound {len(extraction_files)} extraction(s) + {len(transcript_files)} transcript(s):\n")

    # Track which files were already uploaded
    uploaded_file = ".sync_history"
    uploaded = set()
    if os.path.exists(uploaded_file):
        with open(uploaded_file, 'r') as f:
            uploaded = set(line.strip() for line in f)

    # Upload each file
    for file_path in all_files:
        if file_path in uploaded:
            print(f"  ⊘ {file_path} (already uploaded)")
            continue

        try:
            link = upload_file_to_drive(service, file_path, zoom_id)
            print(f"  ✓ {file_path}")
            print(f"    → {link}\n")

            # Mark as uploaded
            with open(uploaded_file, 'a') as f:
                f.write(file_path + '\n')
        except Exception as e:
            print(f"  ✗ {file_path} - {str(e)}\n")

    print("=" * 60)
    print("✓ Sync complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()
