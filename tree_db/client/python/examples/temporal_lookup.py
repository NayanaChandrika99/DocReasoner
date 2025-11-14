#!/usr/bin/env python3
"""
Example: Temporal Queries and Version Management

This script demonstrates TreeStore's temporal query capabilities:
- Viewing document versions over time
- Point-in-time version lookup
- Version comparison
- Version history analysis

Usage:
    python temporal_lookup.py <policy_id>
"""

import sys
from datetime import datetime, timedelta
from treestore import TreeStoreClient


def list_all_versions(client, policy_id):
    """List all versions of a policy document."""
    print(f"=== Version History for {policy_id} ===\n")

    try:
        versions = client.list_versions(policy_id, limit=100)

        if not versions:
            print("No versions found")
            return

        print(f"Total versions: {len(versions)}\n")

        for i, version in enumerate(versions, 1):
            created_at = version.get("created_at")
            created_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "N/A"

            print(f"{i}. Version {version['version_id']}")
            print(f"   Created: {created_str}")
            if version.get('created_by'):
                print(f"   Created by: {version['created_by']}")
            if version.get('description'):
                print(f"   Description: {version['description']}")
            if version.get('tags'):
                print(f"   Tags: {', '.join(version['tags'])}")
            print()

    except Exception as e:
        print(f"Error listing versions: {e}")


def query_version_at_time(client, policy_id, target_time):
    """Query which version was active at a specific point in time."""
    print(f"=== Version Active at {target_time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    try:
        version = client.get_version_as_of(policy_id, target_time)

        if not version:
            print("No version found at that time")
            return

        created_at = version.get("created_at")
        created_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "N/A"

        print(f"Active version: {version['version_id']}")
        print(f"Created: {created_str}")
        if version.get('created_by'):
            print(f"Created by: {version['created_by']}")
        if version.get('description'):
            print(f"Description: {version['description']}")
        if version.get('tags'):
            print(f"Tags: {', '.join(version['tags'])}")
        print()

        return version

    except Exception as e:
        print(f"Error querying version: {e}")
        return None


def analyze_version_timeline(client, policy_id):
    """Analyze the version timeline and show key milestones."""
    print(f"=== Version Timeline Analysis for {policy_id} ===\n")

    try:
        versions = client.list_versions(policy_id, limit=100)

        if not versions:
            print("No versions to analyze")
            return

        # Sort by creation time
        versions_sorted = sorted(
            [v for v in versions if v.get('created_at')],
            key=lambda v: v['created_at']
        )

        if not versions_sorted:
            print("No versions with timestamps")
            return

        # Timeline analysis
        first_version = versions_sorted[0]
        latest_version = versions_sorted[-1]

        print(f"First version: {first_version['version_id']}")
        print(f"  Created: {first_version['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")

        print(f"\nLatest version: {latest_version['version_id']}")
        print(f"  Created: {latest_version['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")

        # Calculate timeline span
        span = latest_version['created_at'] - first_version['created_at']
        print(f"\nVersion history spans: {span.days} days")

        # Count versions by tag
        tag_counts = {}
        for version in versions:
            for tag in version.get('tags', []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if tag_counts:
            print(f"\nVersions by tag:")
            for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {tag}: {count}")

        # Show milestones (versions with tags)
        print(f"\nTagged milestones:")
        for version in versions_sorted:
            if version.get('tags'):
                created_str = version['created_at'].strftime('%Y-%m-%d')
                print(f"  {created_str}: {version['version_id']} [{', '.join(version['tags'])}]")
                if version.get('description'):
                    print(f"    → {version['description']}")

    except Exception as e:
        print(f"Error analyzing timeline: {e}")


def compare_versions(client, policy_id, version1_time, version2_time):
    """Compare two versions at different points in time."""
    print(f"=== Version Comparison ===\n")

    try:
        # Get both versions
        v1 = client.get_version_as_of(policy_id, version1_time)
        v2 = client.get_version_as_of(policy_id, version2_time)

        if not v1 or not v2:
            print("Could not retrieve both versions for comparison")
            return

        print(f"Version 1 (at {version1_time.strftime('%Y-%m-%d')}):")
        print(f"  ID: {v1['version_id']}")
        print(f"  Created: {v1.get('created_at', 'N/A')}")
        print(f"  Description: {v1.get('description', 'N/A')}")

        print(f"\nVersion 2 (at {version2_time.strftime('%Y-%m-%d')}):")
        print(f"  ID: {v2['version_id']}")
        print(f"  Created: {v2.get('created_at', 'N/A')}")
        print(f"  Description: {v2.get('description', 'N/A')}")

        # Check if they're the same
        if v1['version_id'] == v2['version_id']:
            print(f"\n✓ Same version active at both times")
        else:
            print(f"\n✗ Different versions:")
            print(f"  Version changed from {v1['version_id']} to {v2['version_id']}")

    except Exception as e:
        print(f"Error comparing versions: {e}")


def demonstrate_temporal_queries(client, policy_id):
    """Interactive demonstration of temporal queries."""
    print(f"\n=== Temporal Query Demonstration ===")
    print("\nDemonstrating point-in-time queries...\n")

    # Show current version
    now = datetime.now()
    print("1. Current version:")
    query_version_at_time(client, policy_id, now)

    # Show version 30 days ago
    thirty_days_ago = now - timedelta(days=30)
    print("\n2. Version 30 days ago:")
    query_version_at_time(client, policy_id, thirty_days_ago)

    # Show version 90 days ago
    ninety_days_ago = now - timedelta(days=90)
    print("\n3. Version 90 days ago:")
    query_version_at_time(client, policy_id, ninety_days_ago)

    # Compare current vs 30 days ago
    print("\n4. Comparing current vs 30 days ago:")
    compare_versions(client, policy_id, thirty_days_ago, now)


def interactive_temporal_query(client, policy_id):
    """Interactive mode for temporal queries."""
    print(f"\n=== Interactive Temporal Query Mode ===")
    print("\nCommands:")
    print("  list                    - List all versions")
    print("  at <YYYY-MM-DD>        - Show version at date")
    print("  compare <date1> <date2> - Compare two versions")
    print("  timeline               - Analyze version timeline")
    print("  demo                   - Run demonstration")
    print("  quit                   - Exit")
    print()

    while True:
        try:
            cmd = input(f"{policy_id} [temporal]> ").strip()

            if not cmd:
                continue

            if cmd == "quit":
                break

            if cmd == "list":
                list_all_versions(client, policy_id)

            elif cmd == "timeline":
                analyze_version_timeline(client, policy_id)

            elif cmd == "demo":
                demonstrate_temporal_queries(client, policy_id)

            elif cmd.startswith("at "):
                date_str = cmd[3:].strip()
                try:
                    target_time = datetime.strptime(date_str, "%Y-%m-%d")
                    query_version_at_time(client, policy_id, target_time)
                except ValueError:
                    print("Invalid date format. Use YYYY-MM-DD")

            elif cmd.startswith("compare "):
                parts = cmd[8:].strip().split()
                if len(parts) == 2:
                    try:
                        date1 = datetime.strptime(parts[0], "%Y-%m-%d")
                        date2 = datetime.strptime(parts[1], "%Y-%m-%d")
                        compare_versions(client, policy_id, date1, date2)
                    except ValueError:
                        print("Invalid date format. Use YYYY-MM-DD YYYY-MM-DD")
                else:
                    print("Usage: compare <date1> <date2>")

            else:
                print("Unknown command")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python temporal_lookup.py <policy_id>")
        print("\nThis script demonstrates temporal queries:")
        print("  - View version history")
        print("  - Query versions at specific points in time")
        print("  - Compare versions across time")
        sys.exit(1)

    policy_id = sys.argv[1]

    # Connect to TreeStore
    print("Connecting to TreeStore...")
    with TreeStoreClient(host="localhost", port=50051) as client:
        # Check health
        health = client.health()
        if not health["healthy"]:
            print("✗ TreeStore server is not healthy")
            sys.exit(1)

        print(f"✓ Connected to TreeStore v{health['version']}\n")

        # List all versions first
        list_all_versions(client, policy_id)

        # Analyze timeline
        analyze_version_timeline(client, policy_id)

        # Interactive mode
        interactive_temporal_query(client, policy_id)


if __name__ == "__main__":
    main()
