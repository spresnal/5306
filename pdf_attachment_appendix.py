"""Compatibility imports for the retired attachment appendix module.

The active PDF exporter embeds original files with paperclip annotations.
Attachment collection lives in pdf_attachments; no appendix is generated.
"""
from pdf_attachments import PREFIX, collect_files

__all__ = ['PREFIX', 'collect_files']
