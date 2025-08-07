# Azure JSON OCR Scripts + Furigana Removal from PDFs

Azure-ReadOCR-PDFScript.ps1

Script that scans for PDFs in a folder and automatically submits them to Azure Document Intelligence to be OCR'd by the Read Model and outputs both a searchable PDF and a JSON file. Requires you use an API Key from Azure as these models aren't free. Your Azure tenant this ties to will need proper stuff installed for Azure Document Intelligence to function. This changes constantly so you'll have to research and set this up yourself.

remove_furigana.py

Python script built to remove furigana characters from OCR'd Japanese materials and re-insert the text properly to a searchable PDF without the furigana. It prompts for this, and if no is selected (The Default) it will only output a JSON file that strips out everything but the text content from whatever you feed it that was OCR'd with the Azure Read Model. This could be potentially useful down the road for querying from various databases or even AI Chat bot questions or anything with RAG capabilities. Due to limitations of the Read OCR model it doesn't break out paragraphs as well as I'd like but still seems pretty useful. Layout model could probably do a much better job and identify separate sections of documents.

remove_ocr_textlayer.py

Removes all text layers from any PDF. This is useful because if you shove a new text layer on top of an existing one in a PDF that will have pretty bad results when you copy and paste from it. The remove_furigana script also does this by default. But if you only want to remove OCR layers this is useful.

NotoSansJP-Regular.ttf

Necessary for the remove_furigana.py script to insert text back into PDFs after furigana is removed.
