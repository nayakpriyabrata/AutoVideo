"""Pre-render exposure budget. Looping is not a repair for missing coverage."""
import hashlib
import os


def audit_coverage(segments, total):
    issues, exposures, details = [], {}, []
    hashes = {}
    for segment in segments:
        shot = segment.get("shot_id", "unknown")
        duration = float(segment.get("dur", 0)) + float(segment.get("freeze", 0))
        extension = float(segment.get("freeze", 0))
        path = os.path.realpath(segment["src"])
        if path not in hashes:
            digest = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[path] = digest.hexdigest()
        key = hashes[path]
        exposures[key] = exposures.get(key, 0) + duration
        details.append({"shot_id": shot, "source": path, "sha256": key,
                        "duration": round(duration, 3), "extension": round(extension, 3)})
        if segment.get("borrowed_visual"):
            issues.append(f"{shot}: missing accepted media; neighbouring footage is not an editorial replacement")
        # Long-form single-take movies/interviews are legitimate; repeated short
        # media is not. Apply length cap only when extending a short source.
        if extension > max(3.0, float(segment.get("dur", 0)) * .5):
            issues.append(f"{shot}: {duration:.1f}s window exceeds source by {extension:.1f}s; supply longer relevant media or replan")
    for key, exposure in exposures.items():
        rows = [x for x in details if x["sha256"] == key]
        if total >= 60 and len(rows) > 1 and exposure / total > .20:
            issues.append(f"Repeated source occupies {exposure/total:.0%} of timeline in " +
                          ", ".join(x["shot_id"] for x in rows))
    return {"passed": not issues, "issues": issues, "sources": details,
            "note": "Exact-file repetition and extension checks; not a semantic relevance guarantee."}
