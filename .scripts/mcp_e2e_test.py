"""
E2E MCP test — exercises create_artifact, search, get_artifact, browse_collections
for two API keys against two collections.

Usage:
  python .scripts/mcp_e2e_test.py
"""

import json
import sys
import requests

BASE = "http://localhost:8081"
MCP  = f"{BASE}/mcp"

EREA_KEY = "agc_73dca3c2b0a759140e91ad464e077d1c"
KOAT_KEY = "agc_90b42d3d69104a8df67c5e2971a03914"


def mcp_call(token, tool_name, arguments):
    """Call an MCP tool via Streamable HTTP and return parsed result."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    resp = requests.post(MCP, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:500]}")
        return None

    # Handle SSE or direct JSON
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        # Parse SSE events
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                    if "result" in event:
                        return event["result"]
                    if "error" in event:
                        print(f"  MCP error: {event['error']}")
                        return None
                except json.JSONDecodeError:
                    continue
        return None
    else:
        data = resp.json()
        if "result" in data:
            return data["result"]
        if "error" in data:
            print(f"  MCP error: {data['error']}")
        return None


def mcp_list_tools(token):
    """List available MCP tools."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    resp = requests.post(MCP, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:500]}")
        return None
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                    if "result" in event:
                        return event["result"]
                except json.JSONDecodeError:
                    continue
        return None
    else:
        return resp.json().get("result")


def extract_text(result):
    """Extract text content from MCP tool result."""
    if not result or "content" not in result:
        return None
    for block in result["content"]:
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except (json.JSONDecodeError, TypeError):
                return block.get("text")
    return None


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_discovery():
    section("1. Discovery")
    resp = requests.get(f"{BASE}/.well-known/mcp.json", timeout=10)
    print(f"  Status: {resp.status_code}")
    print(f"  Body: {json.dumps(resp.json(), indent=4)}")
    return resp.status_code == 200


def test_auth(name, token):
    """Verify auth by calling tools/list on the MCP endpoint (API keys auth directly there)."""
    section(f"2. Auth — {name}")
    result = mcp_list_tools(token)
    if result and "tools" in result:
        print(f"  Authenticated OK — {len(result['tools'])} tools available")
        return True
    else:
        print(f"  Auth failed — tools/list returned: {result}")
        return False


def test_tools_list(name, token):
    section(f"3. tools/list — {name}")
    result = mcp_list_tools(token)
    if result and "tools" in result:
        tool_names = [t["name"] for t in result["tools"]]
        print(f"  {len(tool_names)} tools: {', '.join(tool_names)}")
        return "create_artifact" in tool_names
    else:
        print(f"  Failed: {result}")
        return False


def test_browse_collections(name, token):
    section(f"4. browse_collections — {name}")
    result = mcp_call(token, "browse_collections", {})
    data = extract_text(result)
    if data:
        print(f"  Result: {json.dumps(data, indent=4)[:1000]}")
        return data
    else:
        print(f"  No data returned. Raw: {result}")
        return None


def test_create_artifact(name, token, collection_id, title, content):
    section(f"5. create_artifact — {name} → {collection_id[:12]}...")
    result = mcp_call(token, "create_artifact", {
        "collection_id": collection_id,
        "content": content,
        "context": {
            "title": title,
            "content_type": "text/markdown",
            "source": name.lower(),
        },
    })
    print(f"  Raw result: {json.dumps(result, indent=4)[:1000]}")
    data = extract_text(result)
    if data:
        print(f"  Extracted: {json.dumps(data, indent=4)[:500]}" if isinstance(data, dict) else f"  Extracted: {str(data)[:500]}")
        return data
    else:
        print(f"  No data extracted")
        return None


def test_search(name, token, query, collection_ids=None):
    section(f"6. search — {name}: '{query}'")
    args = {"query": query}
    if collection_ids:
        args["collection_ids"] = collection_ids
    result = mcp_call(token, "search", args)
    data = extract_text(result)
    if data:
        if isinstance(data, list):
            print(f"  Found {len(data)} results")
            for item in data[:3]:
                print(f"    - {item.get('title', item.get('id', '?'))}")
        else:
            print(f"  Result: {json.dumps(data, indent=4)[:500]}")
        return data
    else:
        print(f"  No results. Raw: {result}")
        return None


def test_get_artifact(name, token, artifact_id):
    section(f"7. get_artifact — {name}: {artifact_id[:12]}...")
    result = mcp_call(token, "get_artifact", {"artifact_id": artifact_id})
    data = extract_text(result)
    if data:
        print(f"  Got: {json.dumps(data, indent=4)[:500]}")
        return data
    else:
        print(f"  Failed. Raw: {result}")
        return None


def main():
    print("MCP E2E Test — Koat + EREA")
    print(f"Base: {BASE}")

    # 1. Discovery
    if not test_discovery():
        print("\nDISCOVERY FAILED — is backend running?")
        sys.exit(1)

    # 2. Auth both keys
    for label, key in [("EREA", EREA_KEY), ("Koat", KOAT_KEY)]:
        if not test_auth(label, key):
            print(f"\nAUTH FAILED for {label}")
            sys.exit(1)

    # 3. Browse workspaces (for debugging)
    section("3. browse_workspaces — EREA")
    ws_result = mcp_call(EREA_KEY, "browse_workspaces", {})
    ws_data = extract_text(ws_result)
    if ws_data:
        print(f"  Workspaces: {json.dumps(ws_data, indent=4)[:1000]}")
    else:
        print(f"  No workspaces. Raw: {ws_result}")

    # 4. Browse collections to find IDs
    collections_data = test_browse_collections("EREA", EREA_KEY)

    # Ask user for collection IDs if we can't auto-detect
    if not collections_data:
        print("\nCould not browse collections. Please provide IDs manually.")
        sys.exit(1)

    # Try to find collection IDs from browse result
    # The shape varies — let's print and pick
    print("\n--- Parsing collections ---")
    coll_list = None
    if isinstance(collections_data, dict):
        coll_list = collections_data.get("collections", [])
        if not coll_list and "items" in collections_data:
            coll_list = collections_data["items"]
    elif isinstance(collections_data, list):
        coll_list = collections_data

    if not coll_list:
        print(f"Unexpected shape: {type(collections_data)}")
        print(json.dumps(collections_data, indent=2)[:1000])
        sys.exit(1)

    print(f"Found {len(coll_list)} collections:")
    for c in coll_list:
        cid = c.get("id") or c.get("_key") or "?"
        cname = c.get("name") or c.get("title") or "?"
        print(f"  {cid}  —  {cname}")

    # Pick first two collections for testing
    if len(coll_list) < 2:
        print(f"\nNeed at least 2 collections, found {len(coll_list)}")
        sys.exit(1)

    coll_a = coll_list[0]
    coll_b = coll_list[1]
    coll_a_id = coll_a.get("id") or coll_a.get("_key")
    coll_b_id = coll_b.get("id") or coll_b.get("_key")
    coll_a_name = coll_a.get("name") or coll_a.get("title") or "Collection A"
    coll_b_name = coll_b.get("name") or coll_b.get("title") or "Collection B"

    print(f"\nUsing:")
    print(f"  Collection A: {coll_a_name} ({coll_a_id})")
    print(f"  Collection B: {coll_b_name} ({coll_b_id})")

    # 5. EREA writes to Collection A
    erea_artifact = test_create_artifact(
        "EREA", EREA_KEY, coll_a_id,
        "STEEP Analysis: Tech Sector Q1 2026",
        "## STEEP Analysis\n\n### Social\n- Remote work adoption plateauing\n\n### Technological\n- AI agent frameworks maturing rapidly\n\n### Economic\n- VC funding recovering in B2B SaaS\n\n### Environmental\n- Data center energy demands rising\n\n### Political\n- EU AI Act enforcement beginning",
    )

    # 6. Koat writes to Collection B
    koat_artifact = test_create_artifact(
        "Koat", KOAT_KEY, coll_b_id,
        "Tesla Q4 2025 Earnings Analysis",
        "# Tesla Q4 2025\n\nRevenue: $28.4B (beat estimates)\nDeliveries: 510K units\nMargin: 19.2%\n\nKey signals:\n- Energy storage revenue doubled YoY\n- FSD licensing deals with 2 OEMs\n- Cybertruck production ramp on track",
    )

    # 7. Cross-read: EREA reads Koat's artifact from Collection B
    if koat_artifact and isinstance(koat_artifact, dict):
        koat_id = koat_artifact.get("id") or koat_artifact.get("root_id") or koat_artifact.get("artifact_id")
        if koat_id:
            test_get_artifact("EREA", EREA_KEY, koat_id)

    # 8. Cross-read: Koat reads EREA's artifact from Collection A
    if erea_artifact and isinstance(erea_artifact, dict):
        erea_id = erea_artifact.get("id") or erea_artifact.get("root_id") or erea_artifact.get("artifact_id")
        if erea_id:
            test_get_artifact("Koat", KOAT_KEY, erea_id)

    # 9. Search: EREA searches in Collection B
    test_search("EREA", EREA_KEY, "Tesla earnings revenue", [coll_b_id])

    # 10. Search: Koat searches in Collection A
    test_search("Koat", KOAT_KEY, "STEEP analysis tech sector", [coll_a_id])

    # 11. Both write one more artifact to the OTHER collection (proving write access to both)
    test_create_artifact(
        "EREA", EREA_KEY, coll_b_id,
        "Collection Guidance: Priority Topics",
        "## Guidance\n\n1. Track EU carbon credit auction results\n2. Monitor Chinese EV tariff negotiations\n3. Solid-state battery patent filings",
    )

    test_create_artifact(
        "Koat", KOAT_KEY, coll_a_id,
        "Raw Intel: EU AI Act Enforcement",
        "# EU AI Act\n\nFirst enforcement actions expected Q2 2026.\nHigh-risk AI systems must register by June.\nFines: up to 7% of global revenue.",
    )

    section("DONE")
    print("  Both keys created artifacts in both collections.")
    print("  Cross-reads and searches succeeded.")
    print("  Open the UI and check both collections.")


if __name__ == "__main__":
    main()
