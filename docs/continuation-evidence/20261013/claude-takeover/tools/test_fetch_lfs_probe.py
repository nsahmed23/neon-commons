import hashlib
import pathlib
import sys
import unittest
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fetch_lfs_probe as f  # noqa: E402

PIN_OID = f.PIN_SHA256


def pointer(oid=PIN_OID, size=f.PIN_BYTES):
    return f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {size}\n".encode()


class ParsePointerTests(unittest.TestCase):
    def test_reads_oid_and_size_from_a_spec_pointer(self):
        self.assertEqual(f.parse_pointer(pointer()), {"oid": PIN_OID, "size": f.PIN_BYTES})

    def test_rejects_raw_file_bytes(self):
        with self.assertRaises(ValueError):
            f.parse_pointer(b"PK\x03\x04" + b"\x00" * 64)

    def test_rejects_short_oid(self):
        with self.assertRaises(ValueError):
            f.parse_pointer(pointer(oid="abc123"))

    def test_rejects_extra_lines(self):
        with self.assertRaises(ValueError):
            f.parse_pointer(pointer() + b"ext-0-foo sha256:00\n")

    def test_rejects_oversized_input(self):
        with self.assertRaises(ValueError):
            f.parse_pointer(b"version https://git-lfs.github.com/spec/v1\n" + b"x" * 2000)


class VerdictTests(unittest.TestCase):
    def test_pass_needs_pointer_and_bytes_to_match_the_pin(self):
        data = b"probe bytes"
        digest = hashlib.sha256(data).hexdigest()
        ptr = {"oid": digest, "size": len(data)}
        self.assertEqual(f.verdict(ptr, data, pin_bytes=len(data), pin_sha256=digest), "PASS")

    def test_fail_when_downloaded_bytes_differ_from_pointer(self):
        data = b"probe bytes"
        digest = hashlib.sha256(data).hexdigest()
        ptr = {"oid": digest, "size": len(data)}
        self.assertEqual(f.verdict(ptr, b"other bytes", pin_bytes=len(data), pin_sha256=digest), "FAIL")

    def test_fail_when_pointer_names_another_object(self):
        data = b"probe bytes"
        digest = hashlib.sha256(data).hexdigest()
        ptr = {"oid": "0" * 64, "size": len(data)}
        self.assertEqual(f.verdict(ptr, data, pin_bytes=len(data), pin_sha256=digest), "FAIL")


class RedirectTests(unittest.TestCase):
    def test_redirects_are_refused(self):
        handler = f.NoRedirect()
        request = urllib.request.Request("https://example.invalid/a")
        self.assertIsNone(handler.redirect_request(request, None, 302, "Found", {}, "https://example.invalid/b"))


class DownloadHostTests(unittest.TestCase):
    def test_github_storage_hosts_are_allowed(self):
        for href in ("https://github-cloud.githubusercontent.com/alambic/media/x",
                     "https://github-cloud.s3.amazonaws.com/alambic/media/x",
                     "https://media.githubusercontent.com/media/x", "https://github.com/x"):
            self.assertTrue(f.allowed_href(href), href)

    def test_other_hosts_and_plain_http_are_refused(self):
        for href in ("http://github-cloud.githubusercontent.com/x", "https://evil.example/x",
                     "https://githubusercontent.com.evil.example/x", "https://github.com.evil.example/x",
                     "ftp://github.com/x"):
            self.assertFalse(f.allowed_href(href), href)

    def test_download_refuses_before_any_request(self):
        with self.assertRaises(RuntimeError) as caught:
            f.download("https://evil.example/x?sig=secret", {"Authorization": "RemoteAuth secret"}, 10)
        self.assertNotIn("secret", str(caught.exception))


class SafetyTests(unittest.TestCase):
    def test_refuses_an_existing_output_directory(self):
        here = pathlib.Path(__file__).resolve().parent
        self.assertEqual(f.main(["--out-dir", str(here)]), 2)


if __name__ == "__main__":
    unittest.main()
