"""Inspect what SEC actually returns for our 3 CIKs — see the 8-K shape."""
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from foreshock.edgar import fetch_submissions

CIKS = {
    "Snowflake": "0001640147",
    "Twilio":    "0001403708",
    "AWS":       "0001018724",
}


async def main() -> None:
    today = date.today()
    cutoff_30 = today - timedelta(days=30)
    cutoff_90 = today - timedelta(days=90)
    cutoff_365 = today - timedelta(days=365)

    for vendor, cik in CIKS.items():
        print(f"\n=== {vendor} (CIK {cik}) ===")
        try:
            sub = await fetch_submissions(None, cik)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        recent = sub.get("filings", {}).get("recent", {})
        forms = recent.get("form", []) or []
        accs = recent.get("accessionNumber", []) or []
        dates = recent.get("filingDate", []) or []
        items_list = recent.get("items", []) or []
        descs = recent.get("primaryDocDescription", []) or []

        total = len(forms)
        eight_ks_30 = []
        eight_ks_90 = []
        eight_ks_365 = []
        for i, f in enumerate(forms):
            if f != "8-K":
                continue
            try:
                d = date.fromisoformat(dates[i])
            except (ValueError, IndexError):
                continue
            entry = {
                "date": d.isoformat(),
                "acc": accs[i],
                "items": items_list[i] if i < len(items_list) else "",
                "desc": descs[i] if i < len(descs) else "",
            }
            if d >= cutoff_30:
                eight_ks_30.append(entry)
            if d >= cutoff_90:
                eight_ks_90.append(entry)
            if d >= cutoff_365:
                eight_ks_365.append(entry)

        print(f"  Total filings in recent slice: {total}")
        print(f"  8-Ks in last 30d: {len(eight_ks_30)}")
        print(f"  8-Ks in last 90d: {len(eight_ks_90)}")
        print(f"  8-Ks in last 365d: {len(eight_ks_365)}")

        sample = eight_ks_30 or eight_ks_90 or eight_ks_365
        if sample:
            print(f"  Sample 8-Ks (up to 5):")
            for e in sample[:5]:
                print(f"    {e['date']}  items={e['items']:<15}  "
                      f"{e['desc'][:60]}")


asyncio.run(main())
