"""WorkTime - local-first work activity timeline for Windows.

Captures foreground window, clipboard, focused UI text and browser page
context (via a companion extension), then segments the day into a single
timeline and labels segments into tasks/matters with an optional local LLM.

No network access leaves the machine: everything binds to 127.0.0.1 and
the database lives under the project's data directory.
"""

__version__ = "0.2.0"
