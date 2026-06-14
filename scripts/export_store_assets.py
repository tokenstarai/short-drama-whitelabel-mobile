#!/usr/bin/env python3
"""Export store listing metadata and publish-safe screenshots for tenants."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "store-assets"
STORE_HANDOFF = ROOT / "build" / "release-handoff" / "mobile-store-handoff.json"
PACKAGE_NAME = "mobile-store-assets"

DISALLOWED_VALUE_MARKERS = [
    "cloudflare_api_token=",
    "cloudflare-api-token:",
    "bearer ey",
    "sk_live_",
    "sk_test_",
    "appsecret:",
    "secret_ciphertext:",
    "secretciphertext:",
    "x-signature:",
    "x-app-key:",
    "client_secret",
    "stripe_secret",
    "paypal_secret",
    "private_key",
    "-----begin private key-----",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_store_handoff(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing store handoff manifest: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_data_safety(submission: dict[str, Any]) -> dict[str, Any]:
    data_safety = submission.get("dataSafety", {})
    disclosures = data_safety.get("templateDisclosures", {}) if isinstance(data_safety, dict) else {}
    return {
        "notes": data_safety.get("notes") if isinstance(data_safety, dict) else None,
        "templateDisclosures": {
            "accountCreation": bool(disclosures.get("accountCreation")),
            "accountDeletion": bool(disclosures.get("accountDeletion")),
            "purchases": bool(disclosures.get("purchases")),
            "externalPaymentsAllowed": bool(disclosures.get("externalPaymentsAllowed")),
            "consumerContentUpload": bool(disclosures.get("consumerContentUpload")),
            "clientStoresTenantCredentials": False,
        },
    }


def copy_screenshots(root: Path, output_dir: Path, flavor: str, screenshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_dir = output_dir / flavor / "screenshots"
    target_dir.mkdir(parents=True, exist_ok=True)
    exported: list[dict[str, Any]] = []
    for item in screenshots:
        source = root / str(item.get("path", ""))
        if not source.exists():
            raise SystemExit(f"Missing screenshot asset: {source.relative_to(root)}")
        target_name = f"{flavor}_{item.get('screen')}.png"
        target = target_dir / target_name
        shutil.copyfile(source, target)
        exported.append({
            "screen": item.get("screen"),
            "path": str(target.relative_to(output_dir)),
            "sourcePath": item.get("path"),
            "width": item.get("width"),
            "height": item.get("height"),
            "sizeBytes": target.stat().st_size,
            "sha256": sha256_file(target),
            "source": "publish_safe_prototype",
            "tenantShouldReplace": True,
        })
    return exported


def flavor_assets(root: Path, output_dir: Path, flavor_entry: dict[str, Any]) -> dict[str, Any]:
    flavor = str(flavor_entry["flavor"])
    submission = flavor_entry.get("storeSubmission", {})
    screenshots = submission.get("screenshotAssets", [])
    exported_screenshots = copy_screenshots(root, output_dir, flavor, screenshots)
    payload = {
        "schemaVersion": 1,
        "flavor": flavor,
        "appName": flavor_entry.get("appName"),
        "applicationId": flavor_entry.get("applicationId"),
        "bundleId": flavor_entry.get("bundleId"),
        "styleTemplate": flavor_entry.get("styleTemplate"),
        "storeComplianceMode": flavor_entry.get("storeComplianceMode"),
        "primaryChannel": flavor_entry.get("distributionChannelReadiness", {}).get("primaryChannel"),
        "listing": submission.get("listing"),
        "localizedListings": submission.get("localizedListings"),
        "reviewNotes": submission.get("reviewNotes"),
        "dataSafety": safe_data_safety(submission),
        "tenantRequiredActions": submission.get("tenantRequiredActions"),
        "screenshots": exported_screenshots,
        "publicBoundary": "store listing metadata and publish-safe prototype screenshots only",
    }
    listing_path = output_dir / flavor / "listing.json"
    listing_path.parent.mkdir(parents=True, exist_ok=True)
    listing_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload["listingPath"] = str(listing_path.relative_to(output_dir))
    payload["listingSha256"] = sha256_file(listing_path)
    return payload


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return [marker for marker in DISALLOWED_VALUE_MARKERS if marker in text]


def write_zip(output_dir: Path, zip_path: Path) -> None:
    files = sorted(path for path in output_dir.rglob("*") if path.is_file() and path != zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            rel = file_path.relative_to(output_dir)
            info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{rel.as_posix()}")
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file_path.read_bytes())


def build_assets(output_dir: Path) -> dict[str, Any]:
    handoff = load_store_handoff(STORE_HANDOFF)
    if output_dir.exists():
        for path in sorted(output_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    output_dir.mkdir(parents=True, exist_ok=True)
    flavors = [flavor_assets(ROOT, output_dir, entry) for entry in handoff.get("flavors", [])]
    manifest = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "packageType": "mobile_store_assets",
        "sourceManifest": str(STORE_HANDOFF.relative_to(ROOT)),
        "flavors": flavors,
        "publicBoundary": "Public store listing drafts, review notes, data-safety starter facts, and publish-safe prototype screenshots only.",
    }
    hits = marker_hits(manifest)
    manifest["disallowedValueMarkerHits"] = hits
    manifest_path = output_dir / "store-assets-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    zip_path = output_dir / f"{PACKAGE_NAME}.zip"
    write_zip(output_dir, zip_path)
    manifest["manifestPath"] = str(manifest_path.relative_to(ROOT))
    manifest["manifestSha256"] = sha256_file(manifest_path)
    manifest["packagePath"] = str(zip_path.relative_to(ROOT))
    manifest["packageSha256"] = sha256_file(zip_path)
    manifest["packageSizeBytes"] = zip_path.stat().st_size
    manifest["screenshotCount"] = sum(len(item.get("screenshots", [])) for item in flavors)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for store assets",
    )
    args = parser.parse_args()

    manifest = build_assets(args.output_dir.resolve())
    print(f"Wrote store assets manifest: {manifest['manifestPath']}")
    print(f"Wrote store assets package: {manifest['packagePath']}")
    print(f"Screenshots: {manifest['screenshotCount']}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
