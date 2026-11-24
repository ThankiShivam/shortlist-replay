"""Replay structured job preferences against a fixed, labeled posting snapshot."""

import argparse
from collections import Counter
import json
from math import log1p
from pathlib import Path
import re

DEFAULT_CASE = Path(__file__).with_name("fixtures") / "remote_india.json"


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.casefold())


def bm25_scores(postings, query):
    """Score with Okapi BM25 over the same corpus for every conversation turn."""
    counts = {p["id"]: Counter(tokens(p["text"])) for p in postings}
    lengths = {key: sum(words.values()) for key, words in counts.items()}
    avg_length = sum(lengths.values()) / len(counts)
    terms = set(tokens(query))
    idf = {}
    for term in sorted(terms):
        seen = sum(term in words for words in counts.values())
        idf[term] = log1p((len(counts) - seen + 0.5) / (seen + 0.5))
    scores = {}
    for key, words in counts.items():
        norm = 1.2 * (0.25 + 0.75 * lengths[key] / avg_length)
        scores[key] = sum(weight * words[t] * 2.2 / (words[t] + norm)
                          for t, weight in idf.items() if words[t])
    return scores


def classify(posting, level, remote_country, hybrid_cities):
    """Known violations override missing evidence. Quotes come from the snapshot."""
    role = posting["role_evidence"]
    location = posting["location_evidence"]
    if posting["level"] is not None and posting["level"] != level:
        return "exclude", role
    mode = posting["mode"]
    if mode == "remote" and posting["countries"] is not None:
        eligible = remote_country.casefold() in {c.casefold() for c in posting["countries"]}
    elif mode == "hybrid" and not hybrid_cities:
        eligible = False
    elif mode == "hybrid" and posting["city"]:
        eligible = posting["city"].casefold() in hybrid_cities
    elif mode == "onsite":
        eligible = False
    else:
        return "review", location
    if not eligible:
        return "exclude", location
    if posting["level"] is None:
        return "review", role
    return "include", location


def apply_edit(cities, edit):
    if not edit:
        return
    if len(edit) != 1 or not (set(edit) <= {"allow_hybrid", "remove_hybrid"}):
        raise ValueError("each edit must add or remove one hybrid city")
    action, city = next(iter(edit.items()))
    if not isinstance(city, str) or not city.strip():
        raise ValueError("a hybrid city must be a nonempty string")
    city = city.strip().casefold()
    if action == "allow_hybrid":
        cities.add(city)
    else:
        cities.discard(city)


def replay(case):
    postings = case["postings"]
    ids = {p["id"] for p in postings}
    if not postings or len(ids) != len(postings):
        raise ValueError("postings must be nonempty and have unique IDs")
    if not case["turns"]:
        raise ValueError("provide at least one turn")
    for p in postings:
        if not tokens(p["text"]):
            raise ValueError(f"{p['id']}: posting text must contain words")
        for field in ("role_evidence", "location_evidence"):
            if not p[field] or p[field] not in p["text"]:
                raise ValueError(f"{p['id']}: {field} must quote the posting")
        if p["mode"] not in ("remote", "hybrid", "onsite", None):
            raise ValueError(f"{p['id']}: unknown work mode")
        if p["countries"] is not None and not isinstance(p["countries"], list):
            raise ValueError(f"{p['id']}: countries must be a list or null")
    pref = case["preferences"]
    cities = {c.casefold() for c in pref["hybrid_cities"]}
    scores = bm25_scores(postings, pref["query"])
    turns = []
    previous = set()
    for turn in case["turns"]:
        apply_edit(cities, turn["edit"])
        decisions = {}
        for p in postings:
            label, quote = classify(p, pref["level"], pref["remote_country"], cities)
            decisions[p["id"]] = {"decision": label, "evidence": quote}
        eligible = {key for key, item in decisions.items() if item["decision"] == "include"}
        turns.append({
            "name": turn["name"],
            "ranked": sorted(eligible, key=lambda key: (-scores[key], key)),
            "added": sorted(eligible - previous),
            "removed": sorted(previous - eligible),
            "decisions": decisions,
        })
        previous = eligible
    return turns


def mismatches(turns, case):
    errors = []
    for result, turn in zip(turns, case["turns"]):
        labels = turn["expected"]
        if set(labels) != set(result["decisions"]) or not set(labels.values()) <= {"include", "exclude", "review"}:
            raise ValueError(f"{turn['name']}: expected labels must cover every posting")
        for key, expected in labels.items():
            actual = result["decisions"][key]["decision"]
            if actual != expected:
                errors.append(f"{turn['name']} / {key}: expected {expected}, got {actual}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, nargs="?", default=DEFAULT_CASE)
    parser.add_argument("--check", action="store_true", help="compare decisions with fixture labels")
    parser.add_argument("--json", action="store_true", help="include every decision and quoted source")
    args = parser.parse_args()
    try:
        case = json.loads(args.case.read_text(encoding="utf-8"))
        turns = replay(case)
        errors = mismatches(turns, case) if args.check else []
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"Invalid case: {exc}\n")
    if args.json:
        output = {"turns": turns}
        if args.check:
            output["mismatches"] = errors
        print(json.dumps(output, indent=2))
    else:
        for t in turns:
            fmt = lambda values: ", ".join(values) or "-"
            review = [k for k, v in t["decisions"].items() if v["decision"] == "review"]
            print(f"{t['name']} | ranked {fmt(t['ranked'])} | added {fmt(t['added'])} | "
                  f"removed {fmt(t['removed'])} | review {fmt(review)}")
        if args.check:
            print("\n".join(errors) if errors else "All labeled decisions match.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
