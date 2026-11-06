import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict


def _schluessel(url: str) -> str:
    # Hash statt URL: Google-News-Links sind ~280 Zeichen lang, die Datei wäre sonst 20 MB groß
    return hashlib.md5(url.encode()).hexdigest()[:12]


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
                    # Alte Einträge mit voller URL umschlüsseln, sonst gälten sie als neu
                    self.seen_urls = {_schluessel(k) if k.startswith("http") else k: v for k, v in data.items()}
            except Exception:
                self.seen_urls = {}
        self._prune()

    def _prune(self):
        cutoff = datetime.now() - timedelta(days=self.max_age_days)
        def frisch(ts):
            try:
                return datetime.fromisoformat(ts) > cutoff
            except (TypeError, ValueError):
                return False   # kaputter Eintrag: verwerfen statt den ganzen Lauf abzubrechen
        self.seen_urls = {url: ts for url, ts in self.seen_urls.items() if frisch(ts)}

    def is_seen(self, url: str) -> bool:
        return _schluessel(url) in self.seen_urls

    def mark_seen(self, url: str):
        self.seen_urls[_schluessel(url)] = datetime.now().isoformat(timespec="seconds")

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_name(self.cache_path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.seen_urls, f, ensure_ascii=False)
        os.replace(tmp, self.cache_path)

    def cleanup_and_save(self):
        self._prune()
        self.save()

    def get_seen_count(self) -> int:
        return len(self.seen_urls)
