#!/usr/bin/env python3
"""Test calendar event creation without calling Claude API."""

import sys
sys.path.insert(0, '/Users/blakeweissman')

from extract_meeting import create_calendar_event

# Test data - simulating what Claude would extract
test_meetings = [
    {
        "person": "Stuart Heitman",
        "topic": "Shvatim discussion",
        "suggested_date": "2026-07-15"
    },
    {
        "person": "Harold Lamb",
        "topic": "AI System rollout planning",
        "suggested_date": "next week"
    },
    {
        "person": "Sippy",
        "topic": "WhatsApp integration update",
        "suggested_date": None
    }
]

print("Testing calendar event creation...\n")

for meeting in test_meetings:
    person = meeting["person"]
    topic = meeting["topic"]
    suggested_date = meeting["suggested_date"]

    print(f"Creating event: {person} - {topic}")
    event_url = create_calendar_event(person, topic, suggested_date)

    if event_url:
        print(f"  ✓ Success!")
        print(f"    → {event_url}\n")
    else:
        print(f"  ✗ Failed\n")
