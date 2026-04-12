from __future__ import annotations
import json
import logging
import os
import time

from collections import Counter

logger = logging.getLogger(__name__)


class IntentMissLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.log_file = os.path.join(self.log_dir, "intent_misses.jsonl")
        os.makedirs(self.log_dir, exist_ok=True)

    def log_miss(self, raw_utterance: str, normalized_text: str):
        """Logs an utterance that failed to match any intent."""
        if not raw_utterance or not raw_utterance.strip():
            return

        record = {
            "timestamp": time.time(),
            "raw_utterance": raw_utterance,
            "normalized_text": normalized_text,
        }

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to write intent miss log: {e}")

    def get_top_misses(self, limit: int = 20) -> list[tuple[str, int]]:
        """Reads the JSONL log and surfaces the top unmatched phrases."""
        if not os.path.exists(self.log_file):
            return []

        counter = Counter()
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        text = record.get("normalized_text", "").strip()
                        if text:
                            # Use the exact normalized match
                            counter[text] += 1
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to read intent miss log: {e}")

        return counter.most_common(limit)
