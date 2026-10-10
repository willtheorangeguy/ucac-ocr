"""Operator-approved character substitutions, limited to count expressions."""
import re

OCR_DIGITS = {
    **dict.fromkeys('OoQqDd', '0'),
    **dict.fromkeys('IiLl|', '1'),
    **dict.fromkeys('Zz', '2'),
    **dict.fromkeys('Ss', '5'),
    'G': '6', 'B': '8',
}


def numeric_text(raw):
    text=(raw or '').strip().translate(str.maketrans(OCR_DIGITS))
    return text if re.fullmatch(r'\d+(?:\s*\+\s*\d+)*',text,flags=re.ASCII) else None


def is_carry_mark(raw,reason=None):
    text=(raw or '').strip()
    if text.casefold() in {'arrow','down arrow','up arrow','ditto','ditto marks','quote','quotes','quotation marks','same as above','copy down'}:return True
    compact=''.join(text.split())
    if compact and all(c in '\"\x27“”‘’″〃↧⬇⬆⮟' or 0x2190<=ord(c)<=0x21ff or 0x2900<=ord(c)<=0x297f for c in compact):return True
    if compact in ('->','<-','=>','↓','↑'):return True
    return text in ('','?') and bool(re.search(r'\b(arrow|ditto|quotation marks)\b',reason or '',re.IGNORECASE))


def likely_blank(raw,kind,reason=None):
    text=(raw or '').strip()
    if not text and kind=='blank':return True
    if text.casefold() in {'blank','empty','likely blank','probably blank','blank?','(blank)'}:return True
    return text in ('','?') and bool(re.search(r'\b(?:likely|probably|looks|seems|appears)\s+(?:to be\s+)?(?:blank|empty)\b',reason or '',re.IGNORECASE))
