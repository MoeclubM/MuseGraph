"""Tests for llm_json service functions."""

from __future__ import annotations

import pytest


class TestExtractJsonObject:
    """Test JSON extraction from LLM output."""

    def test_extract_json_valid_json(self):
        """Test extracting valid JSON string."""
        from app.services.llm_json import extract_json_object

        raw = '{"name": "test", "value": 123}'
        result = extract_json_object(raw)

        assert result is not None
        assert result["name"] == "test"
        assert result["value"] == 123

    def test_extract_json_empty_string(self):
        """Test extracting from empty string."""
        from app.services.llm_json import extract_json_object

        result = extract_json_object("")
        assert result is None

    def test_extract_json_none_input(self):
        """Test extracting from None input."""
        from app.services.llm_json import extract_json_object

        result = extract_json_object(None)
        assert result is None

    def test_extract_json_whitespace_only(self):
        """Test extracting from whitespace only."""
        from app.services.llm_json import extract_json_object

        result = extract_json_object("   \n\t  ")
        assert result is None

    def test_extract_json_fenced_json_block(self):
        """Test extracting JSON from fenced code block."""
        from app.services.llm_json import extract_json_object

        raw = '''Here is the JSON:
```json
{"name": "fenced", "count": 5}
```
That's it.'''
        result = extract_json_object(raw)

        assert result is not None
        assert result["name"] == "fenced"
        assert result["count"] == 5

    def test_extract_json_fenced_without_language(self):
        """Test extracting JSON from fenced block without language."""
        from app.services.llm_json import extract_json_object

        raw = '''Result:
```
{"status": "ok"}
```'''
        result = extract_json_object(raw)

        assert result is not None
        assert result["status"] == "ok"

    def test_extract_json_embedded_in_text(self):
        """Test extracting JSON embedded in text."""
        from app.services.llm_json import extract_json_object

        raw = 'The result is {"embedded": true} and that is it.'
        result = extract_json_object(raw)

        assert result is not None
        assert result["embedded"] is True

    def test_extract_json_invalid_json(self):
        """Test extracting invalid JSON returns None."""
        from app.services.llm_json import extract_json_object

        raw = "This is not JSON at all"
        result = extract_json_object(raw)

        assert result is None

    def test_extract_json_invalid_fenced(self):
        """Test extracting invalid fenced JSON returns None."""
        from app.services.llm_json import extract_json_object

        raw = '''```
not valid json
```'''
        result = extract_json_object(raw)

        assert result is None

    def test_extract_json_nested_object(self):
        """Test extracting nested JSON object."""
        from app.services.llm_json import extract_json_object

        raw = '{"outer": {"inner": {"deep": "value"}}}'
        result = extract_json_object(raw)

        assert result is not None
        assert result["outer"]["inner"]["deep"] == "value"

    def test_extract_json_array_not_dict(self):
        """Test that JSON array returns None (only dict accepted)."""
        from app.services.llm_json import extract_json_object

        raw = '[1, 2, 3]'
        result = extract_json_object(raw)

        # Arrays are not accepted, only dicts
        assert result is None

    def test_extract_json_string_not_dict(self):
        """Test that JSON string returns None."""
        from app.services.llm_json import extract_json_object

        raw = '"just a string"'
        result = extract_json_object(raw)

        assert result is None

    def test_extract_json_with_surrounding_text(self):
        """Test extracting JSON with text before and after."""
        from app.services.llm_json import extract_json_object

        raw = '''Before text.
{"key": "value"}
After text.'''
        result = extract_json_object(raw)

        assert result is not None
        assert result["key"] == "value"

    def test_extract_json_unicode(self):
        """Test extracting JSON with unicode characters."""
        from app.services.llm_json import extract_json_object

        raw = '{"message": "你好世界", "emoji": "🎉"}'
        result = extract_json_object(raw)

        assert result is not None
        assert result["message"] == "你好世界"
        assert result["emoji"] == "🎉"

    def test_extract_json_with_newlines(self):
        """Test extracting JSON with newlines inside."""
        from app.services.llm_json import extract_json_object

        raw = '''{
            "multiline": "value",
            "nested": {
                "key": "value"
            }
        }'''
        result = extract_json_object(raw)

        assert result is not None
        assert result["multiline"] == "value"
        assert result["nested"]["key"] == "value"

    def test_extract_json_empty_object(self):
        """Test extracting empty JSON object."""
        from app.services.llm_json import extract_json_object

        raw = '{}'
        result = extract_json_object(raw)

        assert result is not None
        assert result == {}
