"""
Phonetic and Accent-Aware String Similarity Engine for Jarvis.
Provides:
1. Vietnamese diacritic stripping, tone removal, and vowel normalization.
2. Vietnamese-English accent and phonetic transliteration mapping (e.g. 'viết code' -> 'vs code', 'chôm' -> 'chrome', 'cưa sờ' -> 'cursor').
3. Pure Python Double Metaphone and Soundex encoding.
4. Multi-metric similarity calculation (Exact, Alias, Phonetic, Token Overlap, Fuzzy).
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Sequence


# ============================================================================
# 1. VIETNAMESE DIACRITIC & VOWEL NORMALIZATION
# ============================================================================

VIETNAMESE_ACCENT_MAP = {
    'a': 'aàảãáạăằẳẵắặâầẩẫấậ',
    'A': 'AÀẢÃÁẠĂẰẲẴẮẶÂẦẨẪẤẬ',
    'd': 'dđ',
    'D': 'DĐ',
    'e': 'eèẻẽéẹêềểễếệ',
    'E': 'EÈẺẼÉẸÊỀỂỄẾỆ',
    'i': 'iìỉĩíị',
    'I': 'IÌỈĨÍỊ',
    'o': 'oòỏõóọôồổỗốộơờởỡớợ',
    'O': 'OÒỎÕÓỌÔỒỔỖỐỘƠỜỞỠỚỢ',
    'u': 'uùủũúụưừửữứự',
    'U': 'UÙỦŨÚỤƯỪỬỮỨỰ',
    'y': 'yỳỷỹýỵ',
    'Y': 'YỲỶỸÝỴ',
}

_CHAR_TO_BASE = {}
for base, chars in VIETNAMESE_ACCENT_MAP.items():
    for ch in chars:
        _CHAR_TO_BASE[ch] = base


def remove_vietnamese_diacritics(text: str) -> str:
    """
    Remove all Vietnamese tones and diacritics, returning standard ASCII equivalent.
    e.g. 'viết code' -> 'viet code', 'mở trình duyệt' -> 'mo trinh duyet'
    """
    if not text:
        return ""
    result = []
    for ch in text:
        if ch in _CHAR_TO_BASE:
            result.append(_CHAR_TO_BASE[ch])
        else:
            result.append(ch)
    normalized = "".join(result)
    # Also normalize any lingering combining unicode diacritics
    nfkd = unicodedata.normalize("NFKD", normalized)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ============================================================================
# 2. VIETNAMESE-ENGLISH PHONETIC TRANSLITERATION MAPPING
# ============================================================================

# Common Vietnamese pronunciations of English technical names, apps, and words
VIETNAMESE_PHONETIC_TRANSLITERATIONS: list[tuple[str, str]] = [
    # Visual Studio Code / VS Code / Code
    (r"\b(?:viết|viet|viets|viét|biet|vie)\s*(?:code|cốt|cot|codes|god|got|hot)\b", "vs code"),
    (r"\b(?:v\s*s|b\s*s|be\s*as|the\s*as|e\s*s|v\s*es|b\s*es)\s+(?:code|caught|cốt|cot|god|got|hot|car|on|thought)\b", "vs code"),
    (r"\b(?:bs\s*caught|bs\s*thought|be\s*as\s*caught|e\s*s\s*caught|b\s*s\s*caught|b\s*s\s*hot|the\s*as\s*car|vs\s*caught|vs\s*god|viet\s*god|b\s*god|vs\s*on|v\s*s\s*god|v\s*s\s*got|v\s*s\s*cot|b\s*s\s*code|b\s*s\s*cốt|the\s*as\s*caught|vs\s*hot)\b", "vs code"),
    (r"\b(?:v\s*s\s*code|v\s*s)\b", "vs code"),
    (r"\b(?:viết\s*cốt|viet\s*cot|viết\s*cót)\b", "vs code"),
    (r"\b(?:vi\s*ét\s*cốt|vi\s*ét\s*code)\b", "vs code"),
    (r"\b(?:bai\s*sồ|vai\s*sồ|vai\s*su)\s*(?:code|cốt)?\b", "vs code"),
    (r"\b(?:vi\s*su\s*ồ|vi\s*su\s*ần|vai\s*su\s*ồ)\s*(?:xtu\s*đi\s*ô|stu\s*đi\s*ô|studio)\s*(?:code|cốt)\b", "visual studio code"),

    # Google Chrome / Browser
    (r"\b(?:chôm|crôm|cờ\s*rôm|cờ\s*rôm|cờ\s*rom|chom|crom)\b", "chrome"),
    (r"\b(?:gu\s*gồ|gụ\s*gồ|gúc\s*gồ|gút\s*gồ|gu\s*gồ\s*chôm|gúc\s*gồ\s*chôm)\b", "google chrome"),
    (r"\b(?:graham|gra ham|braham)\b", "chrome"),
    (r"\b(?:bờ\s*rao\s*sơ|bờ\s*rao\s*xơ|bờ\s*rau\s*xơ|brao\s*xơ|trình\s*duyệt|trinh\s*duyet)\b", "browser"),

    # Window
    (r"\b(?:cửa\s*sổ|cua\s*so|cửa\s*so)\b", "window"),
    (r"\b(?:then\s*with\s*those|then\s*windows|than\s*windows|than\s*window|zen\s*window|then\s*window)\b", "switch window"),

    # Google Chrome / Web Browser
    (r"\b(?:gúc\s*gồ\s*chôm|gúc\s*gồ\s*cờ\s*rôm|gu\s*gồ\s*chôm|cờ\s*rôm|chôm\s*chôm)\b", "chrome"),
    (r"\b(?:xanh\s*chình\s*duyệt|sang\s*chình\s*duyệt|chình\s*duyệt|xanh\s*trình\s*duyệt|sang\s*trình\s*duyệt|qua\s*trình\s*duyệt|sang\s*chình\s*diệt|chình\s*diệt|kênh\s*duyệt|tình\s*duyệt|kinh\s*duyệt|rình\s*duyệt|canh\s*duyet|tinh\s*duyet)\b", "browser"),
    (r"\b(?:bao\s*sơ|sờ\s*bao|brao\s*sơ|bờ\s*rao\s*sơ)\b", "browser"),

    # Window Minimization
    (r"\b(?:many\s*my|many\s*mice|minimise|minima)\b", "minimize"),

    # Cursor
    (r"\b(?:cưa\s*sờ|cớ\s*sơ|kơ\s*sơ|cớt\s*sơ|cưa\s*sơ)\b", "cursor"),
    (r"\b(?:con\s*trỏ|con\s*tro)\b", "cursor"),

    # Discord
    (r"\b(?:đít\s*cọt|đít\s*sờ\s*cọt|đít\s*cot|dit\s*cot|dít\s*cọt|dít\s*sờ\s*cọt)\b", "discord"),
    (r"\b(?:đít\s*co|đít\s*cót|dis\s*cọt|đis\s*cọt)\b", "discord"),

    # Spotify
    (r"\b(?:sờ\s*po\s*ti\s*phai|sờ\s*po\s*ty\s*phai|sờ\s*po\s*ti\s*fai|po\s*ti\s*phai|xờ\s*po\s*ti\s*phai|sờ\s*pot\s*ti\s*phai)\b", "spotify"),
    (r"\b(?:bật\s*nhạc|mở\s*nhạc|phát\s*nhạc)\b", "play music"),

    # GitHub / Git
    (r"\b(?:gít\s*húp|gít\s*háp|ghít\s*háp|gít\s*hup|git\s*hup|gít\s*hub|git\s*háp)\b", "github"),
    (r"\b(?:gít|ghít|gịt)\b", "git"),

    # Postman
    (r"\b(?:pốt\s*man|bốt\s*man|pót\s*man|pốt\s*mần)\b", "postman"),

    # Docker
    (r"\b(?:đốc\s*cơ|đóc\s*cơ|đót\s*cơ|đốc\s*kơ|đoc\s*cơ)\b", "docker"),

    # Notion
    (r"\b(?:nốt\s*son|nô\s*sơn|nô\s*sần|nốt\s*sơn|nô\s*ti\s*on)\b", "notion"),

    # Figma
    (r"\b(?:phích\s*ma|phích\s*ga|fích\s*ma|phíc\s*ma)\b", "figma"),

    # YouTube
    (r"\b(?:du\s*túp|du\s*tup|diu\s*túp|diu\s*túp|du\s*tu\s*be|gu\s*túp)\b", "youtube"),
    (r"\b(?:you\s*too|u\s*tube|u\s*the|u\s*tip|you\s*tip|man\s*you|man\s*you\s*you|mo\s*you|mo\s*you\s*tube)\b", "youtube"),

    # YouTube Video Selection
    (r"\b(?:chẳng|trọng|chào|trông|trang|chong|chông|trong)\s+video\b", "chọn video"),
    (r"\b(?:thư\s*buông|thư\s*bộng|thư\s*bốn|thứ\s*buông|thứ\s*bộng|thứ\s*tự|thứ\s*ư|thức\s*ư)\b", "thứ 4"),
    (r"\b(?:thức\s*nầm|thư\s*nầm|thứ\s*nầm|thức\s*năm|thư\s*năm)\b", "thứ 5"),
    (r"\b(?:select\s+for\s+video|select\s+video\s+for|select\s+video\s+fall|so\s*let\s+video\s+fall|so\s*let\s+video|video\s+far|video\s+for|video\s+fall)\b", "select video 4"),

    # Window Management Phonetics
    (r"\b(?:ổng|đống|óng|ống|ông)\s+(?:cửa\s*sổ|window)(?:\s+(?:này|hiện\s*tại))?\b", "close window"),
    (r"\b(?:closed?|browse|brows|blows|gross|close),?\s*(?:cool\s*and|and|current|this)?\s*(?:window|we\s*know)\b", "close window"),
    (r"\b(?:closed?,?\s*cool\s*and\s*window)\b", "close window"),
    (r"\b(?:many\s*my\s*widow|many\s*my\s*window|mini\s*mai|mi\s*ni\s*mai)\b", "minimize window"),
    (r"\b(?:mác\s*xi\s*mai|mac\s*si\s*mai)\b", "maximize window"),

    # Page / Window Scrolling Phonetics
    (r"\b(?:throw\s+it\s+down|throw\s+down|throw\s+now|prodow|pro\s+down|hold\s+down|grow\s+now|grow\s+down|row\s+now|role\s+now|roll\s+now|glow\s+down|flow\s+down|blow\s+down)\b", "scroll down"),
    (r"\b(?:throw\s+it\s+up|throw\s+up|prod\s+up|pro\s+up|hold\s+up|grow\s+up|row\s+up|role\s+up|roll\s+up|glow\s+up|flow\s+up|blow\s+up)\b", "scroll up"),
    (r"\b(?:roll\s*đao|rôn\s*đao|rồ\s*đao|râu\s*đao|rô\s*đao|râu\s*dao|rôn\s*dao|sờ\s*cờ\s*rôn\s*đao|sờ\s*cro\s*đao|sờ\s*cờ\s*rô\s*đao|ro\s*đao|rô\s*đao)\b", "scroll down"),
    (r"\b(?:roll\s*ắp|rôn\s*ắp|rồ\s*ắp|râu\s*ắp|rô\s*ắp|sờ\s*cờ\s*rôn\s*ắp|sờ\s*cro\s*ắp|ro\s*ắp)\b", "scroll up"),
    (r"\b(?:roll\s+down|row\s+down|raw\s+down|role\s+down)\b", "scroll down"),
    (r"\b(?:roll\s+up|row\s+up|raw\s+up|role\s+up)\b", "scroll up"),
    (r"\b(?:cuộn\s*xuống|kéo\s*xuống|lướt\s*xuống)\b", "scroll down"),
    (r"\b(?:cuộn\s*lên|kéo\s*lên|lướt\s*lên)\b", "scroll up"),

    # Sleep Commands
    (r"\b(?:chạy\s+vô\s+tụi\s+xì\s+lịp|tụi\s+xì\s+lịp|tụi\s+xì\s+lip|xì\s+lịp|xì\s+lip|si\s+lip|si\s+lịp)\b", "go to sleep"),

    # Terminal / PowerShell / Command Prompt
    (r"\b(?:tơ\s*mi\s*nồ|tơ\s*min\s*nồ|tơ\s*mi\s*nần|tơ\s*mi\s*non)\b", "terminal"),
    (r"\b(?:pao\s*eo\s*sen|pao\s*sao|pao\s*sen|pao\s*uê\s*sen)\b", "powershell"),
    (r"\b(?:cê\s*mờ\s*đê|xê\s*em\s*đi|xi\s*em\s*đi)\b", "cmd"),

    # Antigravity
    (r"\b(?:an\s*ti\s*gra\s*vi\s*ti|an\s*ti\s*ga\s*vi\s*ti|an\s*ti\s*gờ\s*ra\s*vi\s*ti)\b", "antigravity"),

    # Gemini & AI Models
    (r"\b(?:jan\s*made\s*me|jan\s*me\s*night|game\s*me\s*night|jan\s*mean\s*i|can\s*night|jan\s*midnight|gemini|geminai|je\s*mi\s*ni|zê\s*mi\s*ni|dê\s*mi\s*ni)\b", "gemini"),
    (r"\b(?:cbt|see\s*the\s*right|yeah\s*cbt|chat\s*g\s*p\s*t|chát\s*g\s*p\s*t)\b", "chatgpt"),

    # Tabs
    (r"\b(?:open\s+)?(?:river\s*taff|river\s*tap|rabia\s*tap|reopen\s*tap|reopen\s*taff|re\s*open\s*tab|khôi\s*phục\s*tab|mở\s*lại\s*tab)\b", "reopen tab"),
    (r"\b(?:openly\s*new\s*tough|open\s*new\s*tough|new\s*tough|new\s*taff|open\s*new\s*taff|openly\s*new\s*tab)\b", "new tab"),
    (r"\b(?:close\s*taff|close\s*tap|đóng\s*tab|tắt\s*tab)\b", "close tab"),
    (r"\b(?:next\s*taff|next\s*tap|chuyển\s*tab|tab\s*tiếp)\b", "next tab"),
    (r"\b(?:previous\s*taff|previous\s*tap|tab\s*trước)\b", "previous tab"),

    # Action verbs (Vietnamese -> standard intent cue)
    (r"\b(?:orban|or\s*ban|oh\s*but|oh\s*been|all\s*but|all\s*one|all\s*on|albany|urban|oban|o\s*ban|orbin|mở|bật|chạy|khởi\s*động|mở\s*lên|bật\s*lên|bat|but)\b", "open"),
    (r"\b(?:đóng|tắt|thoát|tắt\s*đi|đóng\s*lại)\b", "close"),
    (r"\b(?:chuyển\s*sang|đổi\s*sang|chuyển\s*qua|qua)\b", "switch to"),
    (r"\b(?:shot|shout|shaq|shut|sat|share|sert\s*on|sert|tìm\s*kiếm|tìm|tra\s*cứu|tìm\s*cho\s*tôi)\b", "search"),
]


def transliterate_vietnamese_phonetics(text: str) -> str:
    """
    Transliterate common Vietnamese phonetic approximations of English words
    to their standard English forms.
    """
    if not text:
        return ""
    result = text
    for pattern, replacement in VIETNAMESE_PHONETIC_TRANSLITERATIONS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


# ============================================================================
# 3. PURE PYTHON METAPHONE / SOUNDEX ALGORITHM
# ============================================================================

def soundex(name: str) -> str:
    """
    Calculate Soundex code for a word (e.g. 'Code' -> 'C300', 'Viet' -> 'V300').
    """
    name = name.strip().upper()
    if not name:
        return "0000"

    # Retain first letter
    first_letter = name[0]
    tail = name[1:]

    # Soundex mapping
    mapping = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6',
    }

    encoded = []
    prev_code = mapping.get(first_letter, '0')

    for ch in tail:
        code = mapping.get(ch, '0')
        if code != '0' and code != prev_code:
            encoded.append(code)
            prev_code = code
        elif code == '0':
            prev_code = '0'

    result = first_letter + "".join(encoded)
    return (result + "0000")[:4]


def metaphone(word: str) -> str:
    """
    Pure Python Metaphone algorithm: encodes English words by their pronunciation.
    e.g. 'code' -> 'KT', 'viet' -> 'FT', 'chrome' -> 'KRM', 'cursor' -> 'KRSR'.
    """
    w = word.strip().upper()
    if not w:
        return ""

    # Drop non-alpha
    w = re.sub(r"[^A-Z]", "", w)
    if not w:
        return ""

    # Initial transforms
    if w.startswith(('KN', 'GN', 'PN', 'AE', 'WR')):
        w = w[1:]
    elif w.startswith('WH'):
        w = 'W' + w[2:]
    elif w.startswith('X'):
        w = 'S' + w[1:]

    out = []
    i = 0
    length = len(w)

    while i < length and len(out) < 6:
        ch = w[i]
        nxt = w[i + 1] if i + 1 < length else ""
        nxt2 = w[i + 2] if i + 2 < length else ""
        prev = w[i - 1] if i > 0 else ""

        # Skip duplicates except 'C'
        if ch == prev and ch != 'C':
            i += 1
            continue

        if ch in ('A', 'E', 'I', 'O', 'U', 'Y'):
            if i == 0:
                out.append(ch)
            i += 1
        elif ch == 'B':
            if not (i == length - 1 and prev == 'M'):
                out.append('B')
            i += 1
        elif ch == 'C':
            if nxt == 'H':
                if nxt2 in ('R', 'L') or w[i:i+4] in ('CHEM', 'CHIA', 'CHLO', 'CHRO'):
                    out.append('K')
                else:
                    out.append('X')
                i += 2
            elif nxt in ('I', 'E', 'Y'):
                out.append('S')
                i += 2
            elif nxt == 'I' and nxt2 == 'A':
                out.append('X')
                i += 3
            else:
                out.append('K')
                i += 1
        elif ch == 'D':
            if nxt == 'G' and nxt2 in ('E', 'I', 'Y'):
                out.append('J')
                i += 3
            else:
                out.append('T')
                i += 1
        elif ch == 'F':
            out.append('F')
            i += 1
        elif ch == 'G':
            if nxt == 'H' and i + 1 == length - 1:
                i += 2
            elif nxt in ('E', 'I', 'Y') and nxt2 != 'G':
                out.append('J')
                i += 2
            else:
                out.append('K')
                i += 1
        elif ch == 'H':
            if (i == 0 or prev in ('A', 'E', 'I', 'O', 'U')) and nxt in ('A', 'E', 'I', 'O', 'U'):
                out.append('H')
            i += 1
        elif ch in ('J', 'K'):
            out.append('K' if ch == 'K' else 'J')
            i += 1
        elif ch == 'L':
            out.append('L')
            i += 1
        elif ch in ('M', 'N'):
            out.append(ch)
            i += 1
        elif ch == 'P':
            if nxt == 'H':
                out.append('F')
                i += 2
            else:
                out.append('P')
                i += 1
        elif ch == 'Q':
            out.append('K')
            i += 1
        elif ch == 'R':
            out.append('R')
            i += 1
        elif ch == 'S':
            if nxt == 'H':
                out.append('X')
                i += 2
            elif nxt == 'I' and nxt2 in ('A', 'O'):
                out.append('X')
                i += 3
            else:
                out.append('S')
                i += 1
        elif ch == 'T':
            if nxt == 'H':
                out.append('0')  # theta
                i += 2
            elif nxt == 'I' and nxt2 in ('A', 'O'):
                out.append('X')
                i += 3
            else:
                out.append('T')
                i += 1
        elif ch == 'V':
            out.append('F')
            i += 1
        elif ch == 'W' or ch == 'Y':
            if nxt in ('A', 'E', 'I', 'O', 'U'):
                out.append(ch)
            i += 1
        elif ch == 'X':
            out.append('K')
            out.append('S')
            i += 1
        elif ch == 'Z':
            out.append('S')
            i += 1
        else:
            i += 1

    return "".join(out)


def text_metaphone_tokens(text: str) -> list[str]:
    """Return metaphone codes for each word in text."""
    words = re.findall(r"[A-Za-z0-9]+", text)
    return [metaphone(w) for w in words if w]


# ============================================================================
# 4. MULTI-METRIC STRING & PHONETIC SIMILARITY
# ============================================================================

def normalized_levenshtein(s1: str, s2: str) -> float:
    """Calculate normalized Levenshtein similarity (0.0 to 1.0) using SequenceMatcher."""
    s1, s2 = s1.strip().lower(), s2.strip().lower()
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def token_overlap_score(s1: str, s2: str) -> float:
    """Calculate Jaccard and token subset overlap between two phrases."""
    tokens1 = set(re.findall(r"\w+", s1.lower()))
    tokens2 = set(re.findall(r"\w+", s2.lower()))
    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)

    jaccard = len(intersection) / len(union) if union else 0.0
    subset_coverage = len(intersection) / min(len(tokens1), len(tokens2))

    return 0.4 * jaccard + 0.6 * subset_coverage


def phonetic_similarity(s1: str, s2: str) -> float:
    """
    Calculate similarity between two strings based on their phonetic representations.
    """
    meta1 = text_metaphone_tokens(s1)
    meta2 = text_metaphone_tokens(s2)

    if not meta1 or not meta2:
        return 0.0

    str_meta1 = " ".join(meta1)
    str_meta2 = " ".join(meta2)

    return normalized_levenshtein(str_meta1, str_meta2)


COMMAND_ACTION_VERBS = {
    "open", "launch", "start", "run", "close", "shut", "kill", "exit",
    "switch", "search", "find", "play", "select", "click", "choose", "pick",
    "show", "type", "press", "mở", "bật", "chạy", "đóng", "tắt", "thoát",
    "chọn", "nhấn", "gõ", "xem"
}


def calculate_entity_similarity(
    query: str,
    canonical_name: str,
    aliases: Sequence[str] | None = None,
) -> tuple[float, str, str]:
    """
    Compute comprehensive multi-signal similarity between a spoken query and a candidate entity.
    Returns:
        (best_score: float, matched_alias: str, match_method: str)
    """
    q_raw = query.strip().lower()
    q_no_accent = remove_vietnamese_diacritics(q_raw)

    # Command verbs alone should not be matched as application names
    if q_raw in COMMAND_ACTION_VERBS or q_no_accent in COMMAND_ACTION_VERBS:
        return (0.0, canonical_name, "none")

    q_translit = transliterate_vietnamese_phonetics(q_raw)
    q_translit_no_accent = remove_vietnamese_diacritics(q_translit)

    query_variations = list(dict.fromkeys([q_raw, q_no_accent, q_translit, q_translit_no_accent]))

    all_targets = [canonical_name]
    if aliases:
        all_targets.extend(aliases)

    best_score = 0.0
    best_alias = canonical_name
    best_method = "none"

    for target in all_targets:
        t_raw = target.strip().lower()
        t_no_accent = remove_vietnamese_diacritics(t_raw)
        target_variations = list(dict.fromkeys([t_raw, t_no_accent]))

        for q_var in query_variations:
            for t_var in target_variations:
                # 1. Exact Match
                if q_var == t_var:
                    return (1.0, target, "exact")

                # 2. Transliteration / Known Alias direct equality
                if q_translit_no_accent == t_var or q_translit == t_var:
                    if 0.96 > best_score:
                        best_score = 0.96
                        best_alias = target
                        best_method = "phonetic_translit"

                # 3. Substring Containment / Prefix Match (require at least 4 chars and 60% ratio)
                if len(q_var) >= 4 and (t_var.startswith(q_var) or q_var.startswith(t_var)):
                    contain_ratio = min(len(q_var), len(t_var)) / max(len(q_var), len(t_var))
                    if contain_ratio >= 0.60:
                        score = 0.82 + (0.12 * contain_ratio)
                        if score > best_score:
                            best_score = score
                            best_alias = target
                            best_method = "prefix_substring"

                # 4. Levenshtein / Sequence Ratio (require at least 4 chars on both sides)
                if len(q_var) >= 4 and len(t_var) >= 4:
                    lev_score = normalized_levenshtein(q_var, t_var)
                    if lev_score >= 0.82 and lev_score > best_score:
                        best_score = lev_score
                        best_alias = target
                        best_method = "levenshtein"

                # 5. Token Overlap Score
                tok_score = token_overlap_score(q_var, t_var)
                if tok_score >= 0.85 and (tok_score * 0.92) > best_score:
                    best_score = tok_score * 0.92
                    best_alias = target
                    best_method = "token_overlap"

                # 6. Phonetic Metaphone Similarity (require at least 4 chars on both sides and similar length)
                if len(q_var) >= 4 and len(t_var) >= 4 and abs(len(q_var) - len(t_var)) <= 3:
                    phon_score = phonetic_similarity(q_var, t_var)
                    if phon_score >= 0.85 and (phon_score * 0.90) > best_score:
                        best_score = phon_score * 0.90
                        best_alias = target
                        best_method = "metaphone"

    return (min(1.0, round(best_score, 4)), best_alias, best_method)
