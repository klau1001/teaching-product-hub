#!/usr/bin/env python3
"""Build a small, public-facing resource index from selected Drive folders."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

FOLDER_MIME = "application/vnd.google-apps.folder"
ALLOWED_MIMES = {
    "application/pdf": "pdf",
    "application/vnd.google-apps.document": "doc",
    "application/vnd.google-apps.spreadsheet": "sheet",
    "application/vnd.google-apps.presentation": "slide",
}

# Only these four trees are crawled. Student IA reports, past papers and the
# rest of Drive are deliberately outside the indexer's reach.
SCAN_ROOTS = [
    {"id": "1rabmE6uIN4_sbW4qlCSJTBzJpmXzDE3E", "source": "Teaching Tool", "group": "NTK"},
    {"id": "14vYLAlN5EXAwOzpd8DoF8wvQDLz5L_GB", "source": "Teaching Tool", "group": "Generated Products"},
    {"id": "1o2e4CYX2KKmi89uoX4pD31y6LEETcHYy", "source": "Academic", "group": "Comparisons"},
    {"id": "1CKaSWRb4QwBQZTuUchp9vTDaX58SvbdV", "source": "Academic", "group": "Data Booklets"},
]

CURATED_FOLDERS = [
    ["tt-root", "Teaching Tool — All files", "Teaching Tool", "Project root", "https://drive.google.com/drive/folders/1rWqZQ3bfW_bFrF3b05gvuURy-pCwc5v7", ["all", "root", "teaching"]],
    ["academic-root", "Academic — All files", "Academic", "Library root", "https://drive.google.com/drive/folders/1RJI-7fzm-Zhd46XZaWl0fNfN3m69cWkd", ["all", "root", "academic"]],
    ["past-papers", "Past Paper Workspace", "Academic", "Past papers", "https://drive.google.com/drive/folders/1QKbuVxAcym-fdHTZxGM5tWe2q3g84o6w", ["past paper", "catalog", "analysis"]],
    ["past-upload", "Past Papers — Upload Here", "Academic", "Past papers", "https://drive.google.com/drive/folders/1kaaebqt9TsQ_IsYcFTwCBFIrHXuoBXqC", ["past paper", "upload", "inbox"]],
    ["syllabus", "Syllabus Library", "Academic", "Syllabus", "https://drive.google.com/drive/folders/18m4prgYM_E1f_ehlK7h_6EQyQWY0zPFt", ["syllabus", "IB", "A-Level", "IGCSE", "GCSE", "AP", "HKDSE"]],
    ["academic-comparisons", "Academic Comparisons", "Academic", "Comparisons", "https://drive.google.com/drive/folders/1o2e4CYX2KKmi89uoX4pD31y6LEETcHYy", ["comparison", "coverage", "teacher"]],
    ["data-booklets", "Physics Data Booklet Library", "Academic", "Data booklets", "https://drive.google.com/drive/folders/16c-QA8s2pLSFCE6ys7vkyvELTu9AmiFE", ["Physics", "formula", "equation", "data booklet"]],
    ["ntk", "NTK Library", "Teaching Tool", "NTK", "https://drive.google.com/drive/folders/1rabmE6uIN4_sbW4qlCSJTBzJpmXzDE3E", ["NTK", "course", "exercise", "quiz"]],
    ["ntk-index", "NTK Master Index", "Teaching Tool", "NTK", "https://docs.google.com/spreadsheets/d/1BmqcWhhZLN616rSzBbLquOm6pbFWzKLofQx0ZMy2zxw/edit", ["NTK", "index", "course", "student"]],
    ["summer", "NTK 2026–2027 Summer CO", "Teaching Tool", "NTK", "https://drive.google.com/drive/folders/1Y5NoMEG8WSDn8B3nRg99AFiWckND4xka", ["NTK", "Summer CO", "2026", "2027"]],
    ["pl", "NTK 2026–2027 Private Lessons", "Teaching Tool", "NTK", "https://drive.google.com/drive/folders/12Z69X3sq4X8NgM_hscRQ3zxp2QxVmAgL", ["NTK", "PL", "private lesson", "student"]],
    ["ia", "IB IA Analyser", "Teaching Tool", "Tools", "https://drive.google.com/drive/folders/18KXsbh3BeDdXypIy_e_TBP9u9wUoo1Ru", ["IB", "Physics", "IA", "analysis", "report"]],
    ["products", "Generated Products", "Teaching Tool", "Generated products", "https://drive.google.com/drive/folders/14vYLAlN5EXAwOzpd8DoF8wvQDLz5L_GB", ["products", "draft", "approved", "published"]],
]

BLOCKED_SEGMENTS = {
    "source", "sources", "validation", "legacy", "legacy versions",
    "legacy - superseded quizzes", "superseded", "archive", "90 archive",
    "assets", "09 assets", "engine", "engines", "packages", "quarantine",
    "90 quarantine", "testing and validation", "project control",
    "00 project control", "prompt library", "subject rules", "generation rules",
    "design system and templates", "schemas", "operations", "source lock",
    "evaluation rules", "output templates", "template",
}
BLOCKED_NAME_PATTERNS = [
    r"instructions? for ai", r"ai entry point", r"\breadme\b", r"\baudit\b",
    r"\bvalidation\b", r"manifest", r"sha256", r"completion.report",
    r"content.reconciliation", r"change.log", r"batch.queue", r"visual.grammar",
    r"coverage.ledger", r"negative.scope", r"difficulty.default", r"render.qa",
]


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("_", " "))


def is_blocked(name: str, path_segments: list[str]) -> bool:
    normalized_path = [norm(segment) for segment in path_segments]
    if any(
        segment in BLOCKED_SEGMENTS or re.match(r"^(legacy|superseded|archive)\b", segment)
        for segment in normalized_path
    ):
        return True
    normalized = norm(name)
    # Check the current item as well as its parents. Drive folder names often
    # use an em dash, so prefix matching keeps variants such as
    # "Legacy — Superseded Quizzes" out of the crawl.
    if normalized in BLOCKED_SEGMENTS or re.match(r"^(legacy|superseded|archive)\b", normalized):
        return True
    return any(re.search(pattern, normalized) for pattern in BLOCKED_NAME_PATTERNS)


def tags_for(title: str, group: str) -> list[str]:
    text = f"{title} {group}".lower()
    candidates = [
        "Physics", "Chemistry", "IB", "HL2", "GCE AS", "GCSE", "IGCSE",
        "CIE", "Edexcel", "AQA", "NTK", "Summer CO", "PL", "student",
        "teacher", "exercise", "quiz", "handbook", "data booklet",
        "projectile motion", "thermal", "electric", "magnetic", "fields",
    ]
    return [tag for tag in candidates if tag.lower() in text]


def drive_url(file_id: str, mime_type: str, web_view_link: str | None) -> str:
    if web_view_link:
        return web_view_link
    native = {
        "application/vnd.google-apps.document": "document",
        "application/vnd.google-apps.spreadsheet": "spreadsheets",
        "application/vnd.google-apps.presentation": "presentation",
    }
    if mime_type in native:
        return f"https://docs.google.com/{native[mime_type]}/d/{file_id}/edit"
    return f"https://drive.google.com/file/d/{file_id}/view"


def list_children(service, folder_id: str) -> list[dict]:
    items, token = [], None
    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken,files(id,name,mimeType,createdTime,modifiedTime,webViewLink)",
            pageSize=1000,
            pageToken=token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        items.extend(response.get("files", []))
        token = response.get("nextPageToken")
        if not token:
            return items


def crawl(service, config: dict) -> list[dict]:
    results, stack = [], [(config["id"], [])]
    while stack:
        folder_id, path = stack.pop()
        for item in list_children(service, folder_id):
            name, mime = item["name"], item["mimeType"]
            if is_blocked(name, path):
                continue
            if mime == FOLDER_MIME:
                stack.append((item["id"], path + [name]))
                continue
            if mime not in ALLOWED_MIMES:
                continue
            group = " · ".join([config["group"], *path])
            results.append({
                "id": f"drive-{item['id']}", "title": name,
                "source": config["source"], "kind": ALLOWED_MIMES[mime],
                "group": group, "url": drive_url(item["id"], mime, item.get("webViewLink")),
                "created": item.get("modifiedTime") or item.get("createdTime"),
                "tags": tags_for(name, group),
            })
    return results


def logical_key(item: dict) -> tuple[str, str, str]:
    title = re.sub(r"\.(pdf|docx?|pptx?|xlsx?)$", "", item["title"], flags=re.I)
    # Normalize underscores before stripping versions; otherwise names such as
    # "Draft_v0.7.9_grayscale" retain the version because underscores count as
    # word characters in regular expressions.
    title = norm(title)
    title = re.sub(r"(?<![a-z0-9])v?\d+(?:\.\d+){1,3}(?![a-z0-9])", "", title, flags=re.I)
    title = re.sub(r"\b(?:draft|current|complete repair|ra[-_a-z0-9]+|b\d+)\b", "", title, flags=re.I)
    return item["source"], item["kind"], norm(title)


def keep_latest(items: list[dict]) -> list[dict]:
    latest: dict[tuple[str, str, str], dict] = {}
    for item in items:
        key = logical_key(item)
        if key not in latest or (item.get("created") or "") > (latest[key].get("created") or ""):
            latest[key] = item
    return list(latest.values())


def curated_folders() -> list[dict]:
    created = "2026-07-11T00:00:00Z"
    return [
        {"id": item_id, "title": title, "source": source, "kind": "folder",
         "group": group, "url": url, "created": created, "tags": tags}
        for item_id, title, source, group, url, tags in CURATED_FOLDERS
    ]


def build_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise SystemExit("Missing GOOGLE_SERVICE_ACCOUNT_JSON secret")
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"]
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="resources.json")
    args = parser.parse_args()
    service = build_service()
    files = []
    for config in SCAN_ROOTS:
        files.extend(crawl(service, config))
    resources = curated_folders() + keep_latest(files)
    resources.sort(key=lambda item: item.get("created") or "", reverse=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "resourceCount": len(resources), "resources": resources,
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(resources)} curated resources to {args.output}")


if __name__ == "__main__":
    main()
