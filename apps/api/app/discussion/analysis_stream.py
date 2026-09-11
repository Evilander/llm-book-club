"""Expose only the discussion text while a structured response is arriving."""
import json


class AnalysisStream:
    def __init__(self):
        self.raw = ""
        self.mode = None
        self.cursor = None
        self.finished = False
        self.sent_plain = 0

    def feed(self, delta: str) -> str:
        self.raw += delta
        raw = self.raw.lstrip()
        if self.mode is None:
            if not raw or raw in {"`", "``"}:
                return ""
            self.mode = "json" if raw.startswith(("{", "```")) else "plain"
        if self.mode == "plain":
            result = self.raw[self.sent_plain:]
            self.sent_plain = len(self.raw)
            return result
        if self.finished:
            return ""
        if self.cursor is None:
            self.cursor = self._analysis_start()
            if self.cursor is None:
                return ""
        output = []
        escapes = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
        while self.cursor < len(self.raw):
            char = self.raw[self.cursor]
            consumed = 1
            if char == '"':
                self.finished = True
                break
            if char == '\\':
                if self.cursor + 1 >= len(self.raw):
                    break
                escape = self.raw[self.cursor + 1]
                if escape == 'u':
                    if self.cursor + 6 > len(self.raw):
                        break
                    try:
                        number = int(self.raw[self.cursor + 2:self.cursor + 6], 16)
                        consumed = 6
                        if 0xD800 <= number <= 0xDBFF:
                            if self.cursor + 12 > len(self.raw):
                                break
                            if self.raw[self.cursor + 6:self.cursor + 8] != '\\u':
                                raise ValueError("Missing low surrogate")
                            low = int(self.raw[self.cursor + 8:self.cursor + 12], 16)
                            if not 0xDC00 <= low <= 0xDFFF:
                                raise ValueError("Invalid low surrogate")
                            number = 0x10000 + ((number - 0xD800) << 10) + low - 0xDC00
                            consumed = 12
                        elif 0xDC00 <= number <= 0xDFFF:
                            raise ValueError("Unpaired surrogate")
                        char = chr(number)
                    except ValueError:
                        self.finished = True
                        break
                elif escape in escapes:
                    char, consumed = escapes[escape], 2
                else:
                    self.finished = True
                    break
            elif ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF:
                self.finished = True
                break
            output.append(char)
            self.cursor += consumed
        return "".join(output)

    def _analysis_start(self):
        """Find a root property, ignoring quoted or nested lookalike keys."""
        start = len(self.raw) - len(self.raw.lstrip())
        if self.raw[start:].startswith('```'):
            start = self.raw.find('\n', start)
            if start < 0:
                return None
        depth, cursor = 0, start
        decoder = json.JSONDecoder()
        while cursor < len(self.raw):
            char = self.raw[cursor]
            if char == '"':
                try:
                    value, end = decoder.raw_decode(self.raw, cursor)
                except ValueError:
                    return None
                cursor = end
                if depth == 1 and value == 'analysis':
                    while cursor < len(self.raw) and self.raw[cursor].isspace():
                        cursor += 1
                    if cursor >= len(self.raw):
                        return None
                    if self.raw[cursor] == ':':
                        cursor += 1
                        while cursor < len(self.raw) and self.raw[cursor].isspace():
                            cursor += 1
                        return cursor + 1 if cursor < len(self.raw) and self.raw[cursor] == '"' else None
                continue
            if char in '{[':
                depth += 1
            elif char in '}]':
                depth -= 1
            cursor += 1
        return None
