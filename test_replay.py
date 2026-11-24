import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from replay import DEFAULT_CASE, bm25_scores, classify, mismatches, replay


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.case = json.loads(DEFAULT_CASE.read_text())

    def test_labels_replay_and_reversal(self):
        result = replay(self.case)
        self.assertEqual(mismatches(result, self.case), [])
        first, widened, final = result
        self.assertEqual(first["ranked"], ["A"])
        self.assertEqual(widened["added"], ["B"])
        self.assertEqual(widened["removed"], [])
        self.assertEqual(final["removed"], ["B"])
        self.assertEqual(final["decisions"], first["decisions"])
        self.assertEqual(final["decisions"]["E"]["decision"], "review")
        for turn in result:
            for post in self.case["postings"]:
                self.assertIn(turn["decisions"][post["id"]]["evidence"], post["text"])

    def test_expected_labels_do_not_influence_predictions(self):
        first = replay(self.case)
        for turn in self.case["turns"]:
            del turn["expected"]
        self.assertEqual(first, replay(self.case))

    def test_reject_bad_source_quote_and_duplicate_ids(self):
        broken = copy.deepcopy(self.case)
        broken["postings"][0]["location_evidence"] = "No such quote"
        with self.assertRaises(ValueError):
            replay(broken)
        self.case["postings"].append(self.case["postings"][0])
        with self.assertRaises(ValueError):
            replay(self.case)

    def test_unknown_role_and_known_location_conflict(self):
        post = dict(self.case["postings"][2], level=None)
        self.assertEqual(classify(post, "internship", "IN", set())[0], "exclude")
        post["countries"] = ["IN"]
        self.assertEqual(classify(post, "internship", "IN", set())[0], "review")

    def test_ranker_orders_terms_and_handles_ties(self):
        posts = [{"id": "X", "text": "Python SQL"}, {"id": "Y", "text": "Cooking"}]
        s = bm25_scores(posts, "SQL")
        self.assertGreater(s["X"], s["Y"])
        self.case["preferences"]["query"] = "term_not_in_any_post"
        self.assertEqual(replay(self.case)[1]["ranked"], ["A", "B"])

    def test_edits_are_idempotent_and_case_insensitive(self):
        repeat = copy.deepcopy(self.case["turns"][1])
        repeat["edit"]["allow_hybrid"] = "GURUGRAM"
        self.case["turns"].insert(2, repeat)
        result = replay(self.case)
        self.assertEqual(result[2]["added"], [])
        self.assertEqual(result[3]["removed"], ["B"])

    def test_cli_rejects_label_drift(self):
        self.case["turns"][1]["expected"]["B"] = "exclude"
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp) / "case.json"
            case.write_text(json.dumps(self.case))
            proc = subprocess.run([sys.executable, str(DEFAULT_CASE.parents[1] / "replay.py"),
                                   str(case), "--check", "--json"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(json.loads(proc.stdout)["mismatches"]), 1)


if __name__ == "__main__":
    unittest.main()
