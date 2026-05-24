"""
Seed test candidates via the HTTP API only.
Run with:  API_KEY=testkey123 python scripts/seed_candidates.py
"""
import asyncio
import os
import httpx

BASE = "http://127.0.0.1:8000"
API_KEY = os.environ.get("API_KEY", "testkey123")

import time as _time
_TAG = str(int(_time.time()))[-4:]   # unique suffix per run to avoid duplicate email errors

CANDIDATES = [
    # (name, email, github, override_state_or_None)
    ("Arjun Mehta",    f"arjun.mehta+{_TAG}@example.com",    "arjunm",    None),
    ("Priya Sharma",   f"priya.sharma+{_TAG}@example.com",   "priyacode", None),
    ("David Chen",     f"david.chen+{_TAG}@example.com",     "dchen",     "AWAITING_RESUBMISSION"),
    ("Sofia Torres",   f"sofia.torres+{_TAG}@example.com",   "soto",      "AWAITING_RESUBMISSION"),
    ("Kenji Nakamura", f"kenji.n+{_TAG}@example.com",        "kenjin",    "HIRE_RECOMMENDED"),
    ("Aisha Okonkwo",  f"aisha.ok+{_TAG}@example.com",       "aishao",    "HIRE_RECOMMENDED"),
    ("Marcus Webb",    f"marcus.webb+{_TAG}@example.com",    "mwebb",     "WARM_HOLD"),
    ("Elena Volkov",   f"elena.v+{_TAG}@example.com",        "elenav",    "WARM_HOLD"),
    ("James Osei",     f"james.osei+{_TAG}@example.com",     "jkosei",    "HIRED"),
    ("Neha Patel",     f"neha.patel+{_TAG}@example.com",     "neha_p",    "WITHDRAWN"),
]


async def main():
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient(base_url=BASE, headers=headers, timeout=15) as client:
        for name, email, github, override in CANDIDATES:
            r = await client.post("/candidates/intake", json={
                "name": name,
                "email": email,
                "github_handle": github,
                "source": "founder_added",
            })
            if r.status_code not in (200, 201):
                print(f"  SKIP {name}: {r.status_code} — {r.text[:100]}")
                continue

            cid = r.json()["candidate_id"]
            print(f"  + {name} ({cid[:8]}…) → ENGAGED", end="")

            if override:
                ro = await client.post(f"/gate/{cid}/override", json={
                    "target_state": override,
                    "reviewer": "seed_script",
                    "reason": "UI demo seed",
                })
                if ro.status_code == 200:
                    print(f" → {override}", end="")
                else:
                    print(f" [override failed: {ro.text[:60]}]", end="")

            print()

    print("\nDone — refresh http://127.0.0.1:8000")


if __name__ == "__main__":
    asyncio.run(main())
