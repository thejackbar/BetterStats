# BetterCricket flyer — editable Word version

`BetterCricket_Flyer.docx` is the two-page club flyer as an ordinary Word
document: every heading, paragraph and price is real text you can edit, and the
cards and columns are tables rather than a flattened image.

## Editing it

Open it in Word, Google Docs or LibreOffice and type over the copy. The layout
holds as long as you stay roughly within the length of what you are replacing —
each page is close to full, so a paragraph that grows by several lines will push
content onto a third page.

## Exporting back to PDF

**LibreOffice** (`File -> Export as PDF`, or
`soffice --headless --convert-to pdf BetterCricket_Flyer.docx`) keeps the dark
background with no extra steps.

**Word** leaves document background colours out of print and PDF export unless
the reader has switched that option on, so the dark page is painted a second
way: a full-page rectangle sitting behind the text in the page header. That one
does print. If a PDF ever comes out with a white page, turn on
`File -> Options -> Display -> Print background colors and images`.

## Rebuilding from the script

`build_flyer_docx.py` generates the document, and is where to change a colour, a
page size or the spacing rather than hand-editing the .docx:

    pip install python-docx
    python3 docs/flyer/build_flyer_docx.py docs/flyer/BetterCricket_Flyer.docx

The palette at the top of the script is lifted from the original PDF: page
`#0B1220`, cards `#101828`, accent `#16C784`, headings `#E6E8EF`, body
`#A3AAB9`. `logo.png` is the crest, extracted from the same PDF.
