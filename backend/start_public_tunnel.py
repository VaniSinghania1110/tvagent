"""
TravelVerse Public Web Tunnel Helper
Exposes local port 8000 to a free, secure public HTTPS URL on the internet,
so anyone worldwide can open trip itineraries and booking pages from their phone, tablet, or web browser!
"""

import os
import re
import sys
import time
import subprocess
from dotenv import load_dotenv, set_key

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

env_file = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_file)

print("=" * 65)
print("  TRAVELVERSE SECURE PUBLIC WEB ACCESS TUNNEL")
print("=" * 65)
print("Establishing encrypted public tunnel for port 8000...")

# Primary: localhost.run SSH reverse tunnel (zero install, HTTPS instant)
cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-R", "80:localhost:8000", "nokey@localhost.run"]

try:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    public_url = None
    start_time = time.time()

    while time.time() - start_time < 20:
        line = proc.stdout.readline()
        if not line:
            break
        cleaned = line.strip()
        if cleaned:
            print("  [Tunnel]", cleaned)
        match = re.search(r"https://[a-zA-Z0-9\-\.]+\.lhr\.life", cleaned)
        if match:
            public_url = match.group(0)
            break

    if public_url:
        print("\n" + "*" * 65)
        print("  SUCCESS! Your Public Web Address is Live:")
        print(f"  --> {public_url}")
        print("*" * 65)

        print("\n[CONFIG] Saving APP_URL to TravelverseAI/backend/.env...")
        set_key(env_file, "APP_URL", public_url)
        print("  Updated .env successfully!")

        print("\n[PUBLIC LINKS] Anyone worldwide on phone or computer can now open:")
        print(f"  • PDF Brochure: {public_url}/trip-itinerary.pdf?trip_id=110")
        print(f"  • Web Dossier:  {public_url}/trip-itinerary.html?trip_id=110")
        print(f"  • Agent Portal: {public_url}/agent-dashboard.html")
        print("\nKeep this process running to keep the public URL alive.")
        proc.wait()
    else:
        print("\n[NOTE] Could not auto-detect localhost.run within 20s.")
        print("You can also run Pinggy or LocalTunnel:")
        print("  npx --yes localtunnel --port 8000")
        print("Then set APP_URL=<your-tunnel-url> in TravelverseAI/backend/.env")

except KeyboardInterrupt:
    print("\nTunnel closed by user.")
except Exception as e:
    print("\nTunnel error:", e)
