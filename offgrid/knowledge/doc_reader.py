"""
Project document reader.
Reads PDF/Word/MD/TXT files, BM25 matches relevant paragraphs.
P1-RED-4: Read failure degrades gracefully, never interrupts main flow.
P1-FLEX-2: Scanned PDFs (empty text) silently skipped.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt", ".rst"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".eggs", ".offgrid"}
MAX_FILE_SIZE_MB = 10

# CJK Unicode ranges for tokenization
_CJK_RE = re.compile(
    r'([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff'
    r'\U00020000-\U0002a6df\U0002a700-\U0002ebef])'
)


def _tokenize(text: str) -> list[str]:
    """
    Simple tokenizer that handles both CJK and Latin text.
    CJK characters are split into individual chars; Latin words stay intact.
    """
    # Insert spaces around each CJK character
    spaced = _CJK_RE.sub(r' \1 ', text.lower())
    return [t for t in spaced.split() if len(t) >= 1]


class DocReader:

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self._cache: dict[str, list[str]] = {}

    def find_relevant(self, query: str, max_paragraphs: int = 5,
                      max_tokens: int = 800) -> str:
        """
        Find paragraphs most relevant to query via BM25.
        Returns concatenated text, capped at max_tokens (~4 chars/token).
        """
        all_paragraphs: list[tuple[str, str]] = []  # (filename, text)

        for doc_file in self._find_doc_files():
            try:
                paragraphs = self._read_file(doc_file)
                for p in paragraphs:
                    if len(p.strip()) > 10:
                        all_paragraphs.append((doc_file.name, p.strip()))
            except Exception as e:
                logger.debug("[doc_reader] skipping %s: %s", doc_file.name, e)
                continue  # P1-RED-4

        if not all_paragraphs:
            return ""

        # BM25 matching
        try:
            from rank_bm25 import BM25Plus
        except ImportError:
            logger.debug("[doc_reader] rank_bm25 not installed, skipping")
            return ""

        corpus = [_tokenize(p[1]) for p in all_paragraphs]
        bm25 = BM25Plus(corpus)
        query_tokens = _tokenize(query)
        scores = bm25.get_scores(query_tokens)

        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:max_paragraphs]

        relevant = [
            all_paragraphs[i] for i in top_indices if scores[i] > 0
        ]

        if not relevant:
            return ""

        # Assemble output within token budget
        parts = []
        total_chars = 0
        max_chars = max_tokens * 4
        for fname, paragraph in relevant:
            snippet = f"[{fname}]\n{paragraph}"
            if total_chars + len(snippet) > max_chars:
                break
            parts.append(snippet)
            total_chars += len(snippet)

        return "\n\n".join(parts)

    def _find_doc_files(self) -> list[Path]:
        result = []
        try:
            for path in self.project_root.rglob("*"):
                if not path.is_file():
                    continue
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                if path.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                result.append(path)
        except Exception as e:
            logger.debug("[doc_reader] scan error: %s", e)
        return result

    def _read_file(self, path: Path) -> list[str]:
        key = str(path)
        if key in self._cache:
            return self._cache[key]

        suffix = path.suffix.lower()
        paragraphs: list[str] = []

        if suffix == ".pdf":
            paragraphs = self._read_pdf(path)
        elif suffix == ".docx":
            paragraphs = self._read_docx(path)
        elif suffix in (".md", ".txt", ".rst"):
            paragraphs = self._read_text(path)

        self._cache[key] = paragraphs
        return paragraphs

    def _read_pdf(self, path: Path) -> list[str]:
        try:
            import pdfplumber
        except ImportError:
            logger.debug("[doc_reader] pdfplumber not installed")
            return []

        paragraphs = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        for para in text.split("\n\n"):
                            if len(para.strip()) > 30:
                                paragraphs.append(para.strip())
        except Exception as e:
            logger.debug("[doc_reader] PDF read error %s: %s", path.name, e)

        if not paragraphs:
            logger.debug("[doc_reader] %s: empty text (scanned PDF?), skipping", path.name)

        return paragraphs

    def _read_docx(self, path: Path) -> list[str]:
        try:
            from docx import Document
        except ImportError:
            logger.debug("[doc_reader] python-docx not installed")
            return []

        paragraphs = []
        try:
            doc = Document(path)
            for para in doc.paragraphs:
                if len(para.text.strip()) > 30:
                    paragraphs.append(para.text.strip())
        except Exception as e:
            logger.debug("[doc_reader] DOCX read error %s: %s", path.name, e)
        return paragraphs

    def _read_text(self, path: Path) -> list[str]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        paragraphs = []
        for para in text.split("\n\n"):
            if len(para.strip()) > 30:
                paragraphs.append(para.strip())
        return paragraphs
