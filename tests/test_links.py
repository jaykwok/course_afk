import unittest

from core.links import (
    extract_urls_from_text,
    is_learning_zone_url,
    split_manual_selection_urls,
)


class LinkParsingTests(unittest.TestCase):
    def test_extract_urls_from_mixed_text(self):
        text = (
            "A https://a.example.com/x，https://b.example.com/y;"
            "\nhttps://a.example.com/x"
        )
        self.assertEqual(
            extract_urls_from_text(text),
            ["https://a.example.com/x", "https://b.example.com/y"],
        )

    def test_is_learning_zone_url_detects_topic_link(self):
        self.assertTrue(
            is_learning_zone_url("https://kc.zhixueyun.com/#/topic/abc123")
        )
        self.assertTrue(
            is_learning_zone_url(
                "https://cms.mylearning.cn/safe/topic/resource/2025/zycp/pc.html"
            )
        )
        self.assertFalse(
            is_learning_zone_url(
                "https://kc.zhixueyun.com/#/study/course/detail/12345678-1234-1234-1234-123456789abc"
            )
        )

    def test_split_manual_selection_urls_separates_learning_zone_urls(self):
        learning_urls, learning_zone_urls, entry_urls = split_manual_selection_urls(
            [
                "https://kc.zhixueyun.com/#/study/course/detail/12345678-1234-1234-1234-123456789abc",
                "https://kc.zhixueyun.com/#/topic/abc123",
                "https://example.com/entry",
            ]
        )

        self.assertEqual(
            learning_urls,
            [
                "https://kc.zhixueyun.com/#/study/course/detail/12345678-1234-1234-1234-123456789abc"
            ],
        )
        self.assertEqual(
            learning_zone_urls,
            ["https://kc.zhixueyun.com/#/topic/abc123"],
        )
        self.assertEqual(entry_urls, ["https://example.com/entry"])


if __name__ == "__main__":
    unittest.main()
