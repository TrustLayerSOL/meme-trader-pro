import time


class TokenAgeTracker:
    def __init__(self):
        self.first_seen = {}

    def mark_seen(self, mint):
        now = time.time()

        if mint not in self.first_seen:
            self.first_seen[mint] = now

        return self.first_seen[mint]

    def get_age_seconds(self, mint):
        if mint not in self.first_seen:
            return None

        return time.time() - self.first_seen[mint]