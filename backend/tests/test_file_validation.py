import io
import unittest
import zipfile

from app.file_validation import (
    TEMPLATE_EXTENSIONS,
    UploadValidationError,
    validate_uploaded_file,
)


def _ooxml_bytes(directory: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(f"{directory}document.xml", "<document />")
    return output.getvalue()


class FileValidationTests(unittest.TestCase):
    def test_accepts_allowlisted_files_with_matching_signatures(self):
        cases = (
            ("report.pdf", b"%PDF-1.7\ncontent"),
            ("report.docx", _ooxml_bytes("word/")),
            ("model.xlsx", _ooxml_bytes("xl/")),
            ("presentation.pptx", _ooxml_bytes("ppt/")),
            ("notes.txt", b"safe UTF-8 text"),
        )
        for filename, content in cases:
            with self.subTest(filename=filename):
                self.assertEqual(validate_uploaded_file(filename, content), filename)

    def test_rejects_disallowed_extensions_and_renamed_content(self):
        with self.assertRaisesRegex(UploadValidationError, "Unsupported file type"):
            validate_uploaded_file("malware.exe", b"MZ executable")
        with self.assertRaisesRegex(UploadValidationError, "does not match"):
            validate_uploaded_file("renamed.pdf", b"MZ executable")
        with self.assertRaisesRegex(UploadValidationError, "does not match"):
            validate_uploaded_file("renamed.docx", _ooxml_bytes("xl/"))

    def test_rejects_empty_files_and_sanitizes_paths(self):
        with self.assertRaisesRegex(UploadValidationError, "empty"):
            validate_uploaded_file("empty.txt", b"")
        self.assertEqual(
            validate_uploaded_file("../../notes.txt", b"safe"), "notes.txt"
        )

    def test_template_allowlist_is_narrower(self):
        with self.assertRaisesRegex(UploadValidationError, "Unsupported file type"):
            validate_uploaded_file(
                "spreadsheet.xlsx",
                _ooxml_bytes("xl/"),
                allowed_extensions=TEMPLATE_EXTENSIONS,
            )


if __name__ == "__main__":
    unittest.main()
