from __future__ import annotations

import sys
from pathlib import Path
import unittest

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.stt.bilingual_stt_resolver import (
    BilingualSTTResolver,
    CandidateScorer,
    SessionLanguagePrior,
    TranscriptCandidate,
)


class TestBilingualSTTResolver(unittest.TestCase):
    """Test suite for BilingualSTTResolver candidate scoring and language prior."""

    def setUp(self):
        self.prior = SessionLanguagePrior()

    def test_candidate_scorer_code_switching_bonus(self):
        # Candidate with technical code-switch entity vs noisy alternative
        cand_code_switch = TranscriptCandidate(
            text="Mở cho tôi khóa học neural network",
            language="vi",
            language_prob=0.92,
            avg_logprob=-0.15,
            no_speech_prob=0.01,
            compression_ratio=1.1,
        )
        cand_distorted = TranscriptCandidate(
            text="Mảo tình vui quá sợ",
            language="vi",
            language_prob=0.92,
            avg_logprob=-0.55,
            no_speech_prob=0.08,
            compression_ratio=1.1,
        )

        score_cs = CandidateScorer.score_candidate(cand_code_switch, self.prior)
        score_dist = CandidateScorer.score_candidate(cand_distorted, self.prior)

        self.assertGreater(score_cs, score_dist)
        self.assertGreater(cand_code_switch.score_breakdown["code_switch_bonus"], 0.0)

    def test_candidate_scorer_command_verb_bonus(self):
        cand_valid_cmd = TranscriptCandidate(
            text="Open giúp tôi Chrome",
            language="en",
            language_prob=0.90,
            avg_logprob=-0.20,
            no_speech_prob=0.02,
            compression_ratio=1.0,
        )
        cand_broken = TranscriptCandidate(
            text="All been chrome",
            language="en",
            language_prob=0.80,
            avg_logprob=-0.50,
            no_speech_prob=0.05,
            compression_ratio=1.0,
        )

        score_valid = CandidateScorer.score_candidate(cand_valid_cmd, self.prior)
        score_broken = CandidateScorer.score_candidate(cand_broken, self.prior)

        self.assertGreater(score_valid, score_broken)

    def test_candidate_scorer_compression_penalty(self):
        # Repetitive hallucination loop
        cand_hallucination = TranscriptCandidate(
            text="open chrome open chrome open chrome open chrome",
            language="en",
            language_prob=0.95,
            avg_logprob=-0.10,
            no_speech_prob=0.01,
            compression_ratio=3.2,
        )
        score = CandidateScorer.score_candidate(cand_hallucination, self.prior)
        self.assertLess(cand_hallucination.score_breakdown["compression_penalty"], 0.0)

    def test_session_language_prior_update(self):
        prior = SessionLanguagePrior()
        self.assertAlmostEqual(prior.prior_vi, 0.65, places=2)

        # User speaks English multiple times
        for _ in range(5):
            prior.update("en")
        self.assertGreater(prior.prior_en, prior.prior_vi)
        self.assertGreater(prior.get_bias("en"), 0.0)
        self.assertLess(prior.get_bias("vi"), 0.0)

        # Context is just prior, doesn't lock: user speaks Vietnamese
        for _ in range(5):
            prior.update("vi")
        self.assertGreater(prior.prior_vi, prior.prior_en)


if __name__ == "__main__":
    unittest.main()
