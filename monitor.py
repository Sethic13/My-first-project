"""Email alerts for newly listed Rick's LineSkip passes. No third-party packages."""

import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import smtplib
import ssl
import subprocess
import tempfile

VENUE_ID = "T5WY8MCdL8qFulAAOIdv"
VENUE_URL = f"https://tickets.lineleap.com/venues/{VENUE_ID}"


class PageData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.inside = dict(attrs).get("id") == "__NEXT_DATA__"

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)


def parse_passes(html):
    parser = PageData()
    parser.feed(html)
    if not parser.parts:
        raise ValueError("Ticket data is missing; refusing to treat this as no tickets.")
    page = json.loads("".join(parser.parts))["props"]["pageProps"]
    if page["venue"]["id"] != VENUE_ID:
        raise ValueError("Unexpected venue in response.")
    if not isinstance(page.get("passes"), list):
        raise ValueError("Ticket format changed: passes must be a list.")
    result = {}
    for item in page["passes"]:
        if not isinstance(item, dict) or "type" not in item:
            raise ValueError("Ticket format changed: missing ticket type.")
        if item["type"] != "LineSkip":
            continue
        for field in ("productId", "productEventId", "name", "date"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ValueError(f"Ticket format changed: missing {field}.")
        price = item.get("pricePennies")
        if type(price) is not int or price < 0:
            raise ValueError("Ticket format changed: invalid price.")
        # Products may be reused on another night, so include the event/date ID.
        key = json.dumps([item["productId"], item["productEventId"]])
        result[key] = {field: item[field] for field in
                       ("name", "date", "pricePennies", "productEventId")}
    return result


def fetch_passes():
    # curl uses this cloud environment's supported HTTPS proxy configuration.
    result = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--location",
         "--connect-timeout", "10", "--max-time", "30", VENUE_URL],
        capture_output=True, text=True, check=True,
    )
    return parse_passes(result.stdout)


def load_state(path):
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    if (state.get("version") != 1 or state.get("venue_id") != VENUE_ID
            or not isinstance(state.get("seen"), dict)):
        raise ValueError("Invalid saved state; refusing to reset notification history.")
    return state


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(state, f, indent=2, sort_keys=True)
        temp_path = f.name
    os.replace(temp_path, path)


def email_settings():
    required = ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "ALERT_TO")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError("Missing email settings: " + ", ".join(missing))
    return {name: os.environ[name] for name in required}


def send_alert(passes):
    settings = email_settings()
    message = EmailMessage()
    message["Subject"] = "New Rick's LineSkip listing on LineLeap"
    message["From"] = settings["SMTP_USERNAME"]
    message["To"] = settings["ALERT_TO"]
    lines = ["New LineSkip listings appeared for Rick's American Cafe in Ann Arbor:", ""]
    for item in passes.values():
        lines.append(f"{item['name']} | event {item['productEventId']} | "
                     f"${item['pricePennies'] / 100:.2f}")
    lines += ["", VENUE_URL, "Open LineLeap to check availability and purchase.", "",
              "Prices may change and tickets may sell out before you open this email."]
    message.set_content("\n".join(lines))
    with smtplib.SMTP(settings["SMTP_HOST"], 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(settings["SMTP_USERNAME"], settings["SMTP_PASSWORD"])
        refused = smtp.send_message(message)
        if refused:
            raise RuntimeError("Email provider refused a recipient.")


def check(path, dry_run=False, fetch=fetch_passes, notify=send_alert):
    state = load_state(path)
    current = fetch()
    new = {} if state is None else {k: v for k, v in current.items() if k not in state["seen"]}
    print(f"Found {len(current)} LineSkip listing(s); {len(new)} new release(s).")
    for item in current.values():
        print(f"  {item['name']}: ${item['pricePennies'] / 100:.2f} ({item['productEventId']})")
    if dry_run:
        print("Dry run: no email sent and no state changed.")
        return
    if state is None:
        state = {"version": 1, "venue_id": VENUE_ID, "seen": {}}
        print("Initial baseline saved. Existing listings will not trigger an alert.")
    if new:
        notify(new)  # Leave history unchanged on failure so the next check retries.
        print("Email accepted by the email provider.")
    state["seen"].update(current)
    state["last_success_utc"] = datetime.now(timezone.utc).isoformat()
    write_state(path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path(".monitor-state/state.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-email", action="store_true",
                        help="Email the current listings without updating history.")
    args = parser.parse_args()
    try:
        if args.test_email:
            send_alert(fetch_passes())
            print("Test email accepted by the email provider.")
        else:
            if not args.dry_run:
                email_settings()  # Catch missing credentials even on a quiet run.
            check(args.state, dry_run=args.dry_run)
    except Exception as exc:
        # Do not log SMTP responses or authentication data.
        if isinstance(exc, (ValueError, KeyError)):
            print(f"Check failed: {exc}")
        else:
            print(f"Check failed ({type(exc).__name__}); history was not advanced.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
