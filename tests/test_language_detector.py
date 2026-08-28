from __future__ import annotations

from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.language.detector import LanguageDetector, LanguageType


def test_language_detection():
    detector = LanguageDetector.get_instance()

    # 1. Pure English
    lang, conf, _ = detector.detect("Open Google Chrome and search for machine learning tutorials")
    assert lang == LanguageType.ENGLISH
    assert conf >= 0.70

    # 2. Pure Vietnamese
    lang, conf, _ = detector.detect("Mở cửa sổ trình duyệt và tìm bài hát mới")
    assert lang == LanguageType.VIETNAMESE
    assert conf >= 0.70

    # 3. Mixed Vietnamese + English
    lang, conf, _ = detector.detect("Mở visual studio code và bật spotify lên giúp tôi")
    assert lang in (LanguageType.MIXED, LanguageType.VIETNAMESE)
    assert conf >= 0.70

    # 4. Vietnamese diacritics
    lang, conf, _ = detector.detect("đóng cửa sổ này lại")
    assert lang == LanguageType.VIETNAMESE


if __name__ == "__main__":
    test_language_detection()
    print("All Language Detection tests passed successfully!")
