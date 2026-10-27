import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jobwatcher.app import ADZUNA_COUNTRIES, Job, fetch_adzuna, fetch_company, matches, resolve_career_url, resume_match_score, run


class MatchingTests(unittest.TestCase):
    def test_keywords_and_location_must_both_match(self):
        job = Job("Acme", "greenhouse", "1", "Platform Engineering Intern", "Bengaluru, India", "https://example.test/1")
        self.assertTrue(matches(job, ["intern", "platform"], ["India"]))
        self.assertFalse(matches(job, ["backend"], ["India"]))
        self.assertFalse(matches(job, ["intern"], ["New York"]))

    def test_empty_locations_accept_any_location(self):
        job = Job("Acme", "lever", "1", "SRE", "", "https://example.test/1")
        self.assertTrue(matches(job, ["sre"], []))

    def test_target_role_is_matched_from_description(self):
        job = Job("Acme", "lever", "1", "Technology Associate", "Remote", "https://example.test/2",
                  "Join our backend engineering team building reliable APIs.")
        self.assertTrue(matches(job, ["Backend Engineer"], ["Remote"]))

    def test_resume_keyword_overlap_is_local_and_explainable(self):
        job = Job("Acme", "greenhouse", "1", "SRE Intern", "Remote", "https://example.test/1",
                  "Required skills: Kubernetes, AWS, Terraform, Linux, Prometheus and incident response.")
        scored = resume_match_score(job, "My experience includes Kubernetes, AWS, Linux and Prometheus.")
        self.assertIsNotNone(scored.resume_match)
        self.assertIn("kubernetes", scored.matched_terms)
        self.assertGreater(scored.resume_match, 0)
        self.assertLess(scored.resume_match, 100)

    def test_direct_careers_url_resolves_supported_boards(self):
        self.assertEqual(resolve_career_url("https://boards.greenhouse.io/acme/jobs/123"), ("greenhouse", "acme"))
        self.assertEqual(resolve_career_url("https://jobs.lever.co/acme/abc"), ("lever", "acme"))

    def test_nvidia_eightfold_url_is_rejected_with_explanation(self):
        with self.assertRaisesRegex(ValueError, "Eightfold"):
            resolve_career_url("https://jobs.nvidia.com/careers?start=0&pid=893392568855&sort_by=timestamp")


class AdapterTests(unittest.TestCase):
    @patch("jobwatcher.app.fetch_json")
    def test_greenhouse_adapter_uses_public_jobs_shape(self, fetch):
        fetch.return_value = {"jobs": [{"id": 42, "title": "SRE Intern", "location": {"name": "Remote"},
                                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/42", "content": "Linux"}]}
        jobs = fetch_company({"name": "Acme", "ats": "greenhouse", "board": "acme"})
        self.assertEqual(jobs[0].id, "42")
        self.assertEqual(jobs[0].location, "Remote")
        self.assertIn("content=true", fetch.call_args.args[0])

    @patch("jobwatcher.app.fetch_json")
    def test_lever_adapter_uses_public_postings_shape(self, fetch):
        fetch.return_value = [{"id": "abc", "text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/acme/abc",
                              "categories": {"location": "Remote"}, "description": "Build services"}]
        jobs = fetch_company({"name": "Acme", "ats": "lever", "board": "acme"})
        self.assertEqual(jobs[0].id, "abc")
        self.assertIn("api.lever.co/v0/postings/acme", fetch.call_args.args[0])

    @patch("jobwatcher.app.fetch_json")
    def test_adzuna_adapter_queries_country_role_and_maps_advertiser_link(self, fetch):
        fetch.return_value = {"results": [{"id": "123", "title": "SRE", "description": "Reliability role",
                                             "redirect_url": "https://example.test/job", "company": {"display_name": "Acme"},
                                             "location": {"display_name": "London, UK"}}]}
        jobs = fetch_adzuna("gb", "SRE", "appid", "appkey")
        self.assertEqual(len(ADZUNA_COUNTRIES), 19)
        self.assertEqual(jobs[0].company, "Acme")
        self.assertEqual(jobs[0].url, "https://example.test/job")
        url = fetch.call_args.args[0]
        self.assertIn("/jobs/gb/search/1?", url)
        self.assertIn("what=SRE", url)


class DiffTests(unittest.TestCase):
    def test_only_first_matching_sighting_is_surfaced(self):
        config = {"companies": [{"name": "Acme", "ats": "greenhouse", "board": "acme"}],
                  "target_roles": ["intern"], "locations": [], "request_delay_seconds": 0, "timeout_seconds": 1}
        job = Job("Acme", "greenhouse", "42", "Backend Intern", "Remote", "https://example.test/42")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite3"
            with patch("jobwatcher.app.fetch_company", return_value=[job]), patch("time.sleep"):
                first_notifier = lambda token, chat, jobs, when: None
                second_notifier = lambda token, chat, jobs, when: self.fail("duplicate notification")
                self.assertEqual(run(config, db, notifier=first_notifier, env={})["surfaced"], 1)
                self.assertEqual(run(config, db, notifier=second_notifier, env={})["surfaced"], 0)

    def test_worldwide_source_can_run_without_company_boards(self):
        config = {"companies": [], "target_roles": ["SRE"], "locations": [], "request_delay_seconds": 0,
                  "timeout_seconds": 1, "adzuna": {"app_id": "id", "app_key": "key", "countries": ["gb"]}}
        job = Job("Acme", "adzuna", "123", "SRE", "London, UK", "https://example.test/job", "Site Reliability")
        with tempfile.TemporaryDirectory() as tmp:
            with patch("jobwatcher.app.fetch_adzuna", return_value=[job]), patch("time.sleep"):
                result = run(config, Path(tmp) / "state.sqlite3", notifier=lambda *args: None, env={})
        self.assertEqual(result, {"fetched": 1, "matching": 1, "surfaced": 1})


if __name__ == "__main__":
    unittest.main()
