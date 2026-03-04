import re
import unicodedata


class TextUtils:
    """Lightweight text normalisation helpers."""

    @staticmethod
    def normalize(text: str) -> str:
        """Normalise unicode, collapse whitespace, and strip outer spaces."""
        text = unicodedata.normalize('NFC', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
