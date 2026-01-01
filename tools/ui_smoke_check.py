import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5001").rstrip("/")
TIMEOUT = 10


def fetch_text(path):
    url = BASE_URL + path
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {url} ({exc})") from exc


def fetch_json(path):
    url = BASE_URL + path
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            data = resp.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {url} ({exc})") from exc
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid json from {url}") from exc


def main():
    errors = []

    try:
        ui_utils = fetch_text("/ui_utils.js")
        if "normalizeFlow" not in ui_utils:
            errors.append("ui_utils.js missing normalizeFlow")
    except Exception as exc:
        errors.append(str(exc))

    try:
        app_js = fetch_text("/app.js")
        if "selectUpload" not in app_js:
            errors.append("app.js missing selectUpload")
        if "normalizeFlow" not in app_js:
            errors.append("app.js missing normalizeFlow")
    except Exception as exc:
        errors.append(str(exc))

    try:
        status = fetch_json("/admin/status")
        if "db" not in status:
            errors.append("/admin/status missing db")
    except Exception as exc:
        errors.append(str(exc))

    try:
        uploads = fetch_json("/admin/list_uploads")
        if "uploads" not in uploads:
            errors.append("/admin/list_uploads missing uploads")
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1

    print("OK: ui js and endpoints responded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
