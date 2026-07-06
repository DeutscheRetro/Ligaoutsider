import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict


class URLCache:
    def __init__(self, cache_path: str = "data/seen_urls.json", max_age_days: int = 30):
        self.cache_path = Path(cache_path)
        self.max_age_days = max_age_days
        self.seen_urls: Dict[str, str] = {}
        self._load()

    def _load(self):
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.seen_urls = data
            except Exception:
                self.seen_urls = {}
        self._prune()

    def _prune(self):
        cutoff = datetime.now() - timedelta(days=self.max_age_days)
        self.seen_urls = {
            url: ts for url, ts in self.seen_urls.items()
            if datetime.fromisoformat(ts) > cutoff
        }

    def is_seen(self, url: str) -> bool:
        return url in self.seen_urls

    def mark_seen(self, url: str):
        self.seen_urls[url] = datetime.now().isoformat()

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.seen_urls, f, ensure_ascii=False)

    def cleanup_and_save(self):
        self._prune()
        self.save()

    def get_seen_count(self) -> int:
        return len(self.seen_urls)
