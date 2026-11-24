# Shortlist Replay

A job-search benchmark for one question. When a candidate changes a preference, which recommendations should change, and can the system explain why?

**Current status — design and five hand-labeled examples.** This README contains the first test case and its expected answers. Implementation, model runs and benchmark results are planned.

## One conversation, two shortlists

A student in India asks, “Find backend engineering internships I can do remotely from India. I’d prefer Python and SQL.” Later the student adds, “I can also work hybrid in Gurugram.” The second message adds an option. The earlier request for an internship and the preference for Python and SQL still apply.

These five postings are fictional. The table gives their complete text and expected eligibility. A posting with missing work-location evidence goes into a separate review list.

| ID | Posting text | First request | After the change |
| --- | --- | --- | --- |
| A | Backend intern. Build Python and SQL services. Remote anywhere in India. | Include | Include |
| B | Platform engineering internship. Maintain Python APIs and PostgreSQL. Hybrid in Gurugram. | Exclude | Include |
| C | Backend intern. Build Python services. Remote within the United States only. | Exclude | Exclude |
| D | Senior backend engineer, full-time. Write Python and SQL. Remote anywhere in India. | Exclude | Exclude |
| E | Backend intern. Maintain Python APIs. Work from home available. Eligible countries unspecified. | Review | Review |

Only B enters. A stays eligible, C fails the location requirement, D fails the role-level requirement and E still needs clarification. If the student later withdraws permission for hybrid work, the shortlist should return to A. For B, the reviewer can check the reason directly against “Hybrid in Gurugram.”

## Proposed implementation

1. Store immutable posting snapshots in PostgreSQL. Keep candidate preferences as a sequence of typed edits so every result can be replayed against the same inputs.
2. Use a Python service to apply hard constraints on role level and location. Store each as **eligible**, **ineligible** or **needs clarification**. Rank eligible roles by the candidate’s softer preferences.
3. Compare a BM25 keyword baseline with a hybrid ranker that merges BM25 and sentence-embedding results using reciprocal rank fusion. Give both rankers the same postings, filters and cutoff.
4. Ask an LLM to return a structured match reason with a posting ID, a short quoted span and the preference it supports. Check that the span occurs in that posting, then review whether it actually supports the claim. A missing or misleading citation goes to review.

## How to evaluate it

| Check | What to report |
| --- | --- |
| Hard constraints | Count recommendations that violate a stated requirement and divide by all returned recommendations. Report empty lists separately. |
| Preference updates | Compare the IDs that entered and left with the labeled changes. Report the fraction of conversation turns with both sets exactly correct. |
| Ranking quality | On a larger, separately labeled set, compare nDCG@5 for BM25 and hybrid retrieval using graded relevance. Group train and test splits by conversation to keep revisions together. |
| Explanation quality | Count claims independently judged to be supported by the cited text, divided by all claims reviewed. Track missing citations separately. |

The first implementation milestone is a reproducible run of the five postings above with a per-posting diff. A larger evaluation would add changes to pay, seniority and work location, include paraphrases, and publish failure examples alongside the aggregate scores.

## Motivation and related work

A job seeker reported that a remote-only alert began returning on-site and hybrid roles. The report supplied a concrete test case. [Reddit discussion](https://www.reddit.com/r/linkedin/comments/1vcir3a/linkedins_ai_rollout_has_destroyed_the_job_search/)

Elip describes a search product that remembers candidate preferences and explains matches. That makes a change of preference a natural unit of evaluation. [Elip on LinkedIn](https://www.linkedin.com/company/elipai)

Vyas, Chakraborty and Gupta combine lexical and semantic retrieval for job matching and publish the JobSearch-XS benchmark. Shortlist Replay uses a changing preference with a fixed set of postings to make a different failure visible. [JobMatchAI, ACL 2026](https://aclanthology.org/2026.acl-demo.52/)
