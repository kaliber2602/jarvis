import difflib

def deduplicate_phrase(text: str) -> str:
    t = text.strip()
    if not t:
        return ""
    words = t.split()
    n = len(words)
    if n >= 2:
        if n % 2 == 0:
            half = n // 2
            if words[:half] == words[half:]:
                return " ".join(words[:half])
        if n >= 4:
            half = n // 2
            first_part = " ".join(words[:half])
            second_part = " ".join(words[half:])
            sim = difflib.SequenceMatcher(None, first_part, second_part).ratio()
            if sim >= 0.60:
                return first_part
            h1 = (n + 1) // 2
            first_part1 = " ".join(words[:h1])
            second_part1 = " ".join(words[h1:])
            if difflib.SequenceMatcher(None, first_part1, second_part1).ratio() >= 0.60:
                return first_part1
    dedup_words = []
    for w in words:
        if not dedup_words or dedup_words[-1] != w:
            dedup_words.append(w)
    return " ".join(dedup_words)

test_cases = [
    "close the window closed the window",
    "open youtube open youtube",
    "open open youtube",
    "have open youtube open youtube",
    "select know second video the lechner second video",
    "shot lady gaga dirt lady gaga",
    "lay dead task video lay that task video",
    "later first video blade no first video",
    "close we know blouse we know",
    "search lady gaga",
]

for tc in test_cases:
    print(f"'{tc}' -> '{deduplicate_phrase(tc)}'")
