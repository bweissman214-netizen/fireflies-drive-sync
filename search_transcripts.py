#!/usr/bin/env python3
"""Intelligent Drive transcript search using natural language queries."""

import sys
sys.path.insert(0, '/Users/blakeweissman')

from extract_meeting import get_drive_service, read_file_from_drive
from datetime import datetime, timedelta
import re

def parse_query(query):
    """Parse natural language query to extract search parameters."""

    result = {
        'person': None,
        'date': None,
        'topic': None,
        'raw_query': query
    }

    # Extract person (capitalized names, skip question words)
    question_words = {'What', 'Who', 'How', 'When', 'Where', 'Why', 'Did', 'Do', 'Can', 'Is', 'Are', 'Find', 'Show', 'Get'}
    person_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
    people = re.findall(person_pattern, query)
    if people:
        # Filter out question words
        for p in people:
            if p not in question_words:
                result['person'] = p
                break

    # Extract date references
    today = datetime.now()

    if 'today' in query.lower():
        result['date'] = today.strftime('%Y-%m-%d')
    elif 'yesterday' in query.lower():
        result['date'] = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    elif 'tomorrow' in query.lower():
        result['date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        # Look for explicit dates like "June 30", "2026-06-30", "06-30"
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
            r'([A-Z][a-z]+)\s+(\d{1,2})',  # Month Day
        ]

        for pattern in date_patterns:
            match = re.search(pattern, query)
            if match:
                if pattern == r'(\d{4}-\d{2}-\d{2})':
                    result['date'] = match.group(1)
                else:
                    # Parse "Month Day" format
                    month_str = match.group(1)
                    day = match.group(2)
                    month_map = {
                        'January': '01', 'February': '02', 'March': '03', 'April': '04',
                        'May': '05', 'June': '06', 'July': '07', 'August': '08',
                        'September': '09', 'October': '10', 'November': '11', 'December': '12'
                    }
                    if month_str in month_map:
                        year = today.year if int(day) >= today.day else today.year
                        result['date'] = f"{year}-{month_map[month_str]}-{day.zfill(2)}"
                break

    # Extract topic (words after "about", "regarding", "on", etc.)
    topic_patterns = [
        r'about\s+([^.?!]+)',
        r'regarding\s+([^.?!]+)',
        r'on\s+([^.?!]+)',
        r'topic[s]?\s+(?:of|around)\s+([^.?!]+)',
    ]

    for pattern in topic_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            result['topic'] = match.group(1).strip()
            break

    return result

def build_drive_query(params):
    """Build a Google Drive search query from parsed parameters."""

    queries = []

    # Base query - search both markdown and plain text files
    queries.append("(mimeType='text/markdown' or mimeType='text/plain') and trashed=false")

    # Add date to query if available (date is the strongest signal)
    if params['date']:
        queries.append(f"name contains '{params['date']}'")

    # Only add person to filename search if date is NOT available
    # (because most files have dates but not all have person names in filename)
    elif params['person']:
        queries.append(f"name contains '{params['person']}'")

    return " and ".join(queries)

def search_files(params):
    """Search Drive for files matching the parameters."""

    try:
        service = get_drive_service()
        query = build_drive_query(params)

        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=10
        ).execute()

        files = results.get('files', [])
        return files
    except Exception as e:
        print(f"❌ Error searching Drive: {e}")
        return []

def search_in_content(content, person, topic, time_str=None):
    """Search within file content for relevant sections."""

    lines = content.split('\n')
    results = []

    for i, line in enumerate(lines):
        # Look for person mentions
        if person and person.lower() in line.lower():
            # Get context (surrounding lines)
            start = max(0, i - 1)
            end = min(len(lines), i + 3)
            context = '\n'.join(lines[start:end])
            results.append(context)

        # Look for topic mentions
        if topic and topic.lower() in line.lower():
            start = max(0, i - 1)
            end = min(len(lines), i + 3)
            context = '\n'.join(lines[start:end])
            results.append(context)

    return results

def search_transcript(query):
    """
    Main function: Search transcripts using natural language query.

    Examples:
        search_transcript("What did Charlie say today?")
        search_transcript("Meetings with Avi in June")
        search_transcript("Find files about Product Roadmap")
    """

    print(f"\n🔍 Searching: {query}\n")

    # Parse the query
    params = parse_query(query)
    print(f"📝 Parsed query:")
    print(f"   Person: {params['person'] or '(any)'}")
    print(f"   Date: {params['date'] or '(any)'}")
    print(f"   Topic: {params['topic'] or '(any)'}")
    print()

    # Search Drive
    print(f"🔎 Searching Drive...")
    files = search_files(params)

    if not files:
        print("❌ No files found matching your query")
        return None

    print(f"✓ Found {len(files)} file(s):\n")

    all_results = []

    for file in files:
        name = file['name']
        file_id = file['id']

        print(f"📄 {name}")

        # Read file content
        content = read_file_from_drive(file_id)

        if content:
            # Search within content
            matches = search_in_content(content, params['person'], params['topic'])

            if matches:
                print(f"   Found {len(matches)} match(es):")
                for match in matches[:2]:  # Show first 2 matches
                    match_preview = match.replace('\n', ' ')[:100]
                    print(f"   → {match_preview}...")
                    all_results.append({
                        'file': name,
                        'content': match
                    })
            else:
                # If no specific matches, return full content preview
                preview = content[:200].replace('\n', ' ')
                print(f"   Content preview: {preview}...")
                all_results.append({
                    'file': name,
                    'content': content
                })

        print()

    # Return formatted results
    if all_results:
        print("="*70)
        print("📊 SEARCH RESULTS:")
        print("="*70)

        for i, result in enumerate(all_results, 1):
            print(f"\n{i}. From: {result['file']}")
            print(f"   {result['content']}")

        return all_results

    return None

if __name__ == '__main__':
    # Example usage
    if len(sys.argv) > 1:
        user_query = ' '.join(sys.argv[1:])
        search_transcript(user_query)
    else:
        print("Usage: python3 search_transcripts.py 'Your query here'")
        print("\nExamples:")
        print("  python3 search_transcripts.py 'What did Charlie say today?'")
        print("  python3 search_transcripts.py 'Meetings with Avi in June'")
        print("  python3 search_transcripts.py 'Find files about Product Roadmap'")
