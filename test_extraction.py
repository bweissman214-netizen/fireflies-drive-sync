#!/usr/bin/env python3
"""
Test the extraction prompt on a local transcript example.
"""

import json
import sys
import os
from datetime import datetime
import anthropic

EXTRACTION_PROMPT_FILE = "extraction_prompt.md"

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
    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": full_prompt
            }
        ]
    )

    return message.content[0].text

def main():
    # Load test transcript
    try:
        with open("test_transcript.json", "r") as f:
            transcript_data = json.load(f)
    except FileNotFoundError:
        print("Error: test_transcript.json not found")
        sys.exit(1)

    print(f"📋 Testing extraction on: {transcript_data['metadata']['title']}")
    print(f"   Duration: {transcript_data['metadata']['duration_minutes']} minutes")
    print(f"   Attendees: {', '.join(transcript_data['metadata']['attendees'])}")
    print()
    print("🤖 Running Claude extraction...")
    extraction = extract_with_claude(transcript_data)

    # Print the extraction
    print("\n" + "="*70)
    print("EXTRACTION OUTPUT:")
    print("="*70)
    print(extraction)

    # Parse and analyze
    print("\n" + "="*70)
    print("ANALYSIS:")
    print("="*70)

    try:
        json_start = extraction.find("{")
        json_end = extraction.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = extraction[json_start:json_end]
            data = json.loads(json_str)

            print(f"\n✅ Extracted {len(data.get('todos', []))} todos")
            for i, todo in enumerate(data.get('todos', []), 1):
                print(f"   {i}. {todo['action']}")
                print(f"      Owner: {todo.get('owner', 'N/A')}")
                print(f"      Deadline: {todo.get('deadline', 'N/A')}")

            print(f"\n✅ Identified {len(data.get('people_mentioned', []))} people")
            for person in data.get('people_mentioned', []):
                print(f"   - {person['name']} ({person.get('role', 'Unknown role')})")

            print(f"\n✅ Found {len(data.get('calendar_items', []))} calendar items")
            for item in data.get('calendar_items', []):
                print(f"   - {item['event']} on {item.get('date', 'TBD')}")

            print(f"\n✅ Identified {len(data.get('project_themes', []))} themes")
            for theme in data.get('project_themes', []):
                print(f"   - {theme['theme']} ({theme['sentiment']})")
    except:
        pass

if __name__ == "__main__":
    main()
