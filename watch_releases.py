#!/usr/bin/env python3
# watch_releases.py — controlla le release di repo di terzi e notifica su Telegram.
# Lo stato (ultimo tag visto per repo) è persistito in state.json nel repo stesso.

import json, os, pathlib, sys, urllib.parse, urllib.request

REPOS = [
    "MorpheApp/morphe-patches",
    "MorpheApp/MicroG-RE",
    "brosssh/morphe-patches",
    "crimera/piko"
]

STATE_FILE = pathlib.Path("state.json")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT  = os.environ.get("TELEGRAM_CHAT_ID")
GH_TOKEN = os.environ.get("GH_TOKEN")

if not TOKEN or not CHAT:
    sys.exit("Mancano TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID nei secrets.")


def gh_get(url: str) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "release-watcher",
    }
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def telegram_send(text: str) -> None:
    data = urllib.parse.urlencode({
        "chat_id": CHAT,
        "text": text,
        "disable_web_page_preview": "false",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage", data
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def latest_release(repo: str) -> dict | None:
    """Ultima release stabile (non prerelease). Include prerelease, esclude le draft."""
    # /releases/latest NON restituisce le prerelease; /releases?per_page=1 sì.
    releases = gh_get(f"https://api.github.com/repos/{repo}/releases?per_page=1")
    return releases[0] if releases else None


def is_dev_release(rel: dict) -> bool:
    """Controlla se una release è una dev/prerelease da ignorare."""
    # Ignora le prerelease ufficiali
    if rel.get("prerelease", False):
        return True
    # Ignora i tag che contengono 'dev' (case-insensitive)
    tag = rel.get("tag_name", "").lower()
    if "dev" in tag:
        return True
    return False


def main() -> None:
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            print("state.json corrotto, reset dello stato.")
            state = {}
    else:
        state = {}
    changed = False

    for repo in REPOS:
        try:
            rel = latest_release(repo)
        except Exception as e:
            print(f"[{repo}] errore: {e}")
            continue

        if not rel:
            print(f"[{repo}] nessuna release trovata (forse usa solo tag?)")
            continue

        tag = rel["tag_name"]
        previous = state.get(repo)

        if previous == tag:
            print(f"[{repo}] nessuna novità ({tag})")
            continue

        state[repo] = tag
        changed = True

        # Al primo giro non notifichiamo: registriamo solo la baseline.
        if previous is None:
            print(f"[{repo}] baseline impostata su {tag} (nessuna notifica)")
            continue

        # Ignora le release dev/prerelease
        if is_dev_release(rel):
            print(f"[{repo}] rilascio {tag} ignorato (dev/prerelease)")
            continue

        name = rel.get("name") or tag

        msg = f"🚀 Nuova release: {repo}\n\n{tag} — {name}\n{rel['html_url']}"

        try:
            telegram_send(msg)
            print(f"[{repo}] notificata {tag}")
        except Exception as e:
            print(f"[{repo}] invio Telegram fallito: {e}")

    if changed:
        STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
