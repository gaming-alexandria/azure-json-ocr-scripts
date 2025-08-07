#!/usr/bin/env python3
import fitz  # PyMuPDF
import os
import sys
import argparse
import shutil
from pathlib import Path

def rebuild_from_images(pdf_path: Path, create_backup: bool):
    """
    Creates a new PDF by extracting the raw, original images from the source
    and placing them in a new file. This is a truly lossless method for
    image-based PDFs, discarding all text, metadata, and other objects.

    Args:
        pdf_path (Path): The path to the PDF file to process.
        create_backup (bool): If True, creates a backup of the original file.
    """
    if not pdf_path.is_file():
        print(f"  [SKIP] File not found: {pdf_path}")
        return

    if create_backup:
        backup_path = pdf_path.with_suffix('.bak.pdf')
        print(f"  - Creating backup: {backup_path.name}")
        shutil.copy2(pdf_path, backup_path)

    temp_output_path = pdf_path.with_suffix('.tmp.pdf')
    original_doc = None
    new_doc = None

    try:
        original_doc = fitz.open(str(pdf_path))
        new_doc = fitz.open()

        for i, original_page in enumerate(original_doc):
            print(f"    - Extracting images from page {i + 1}/{len(original_doc)}...", end='\r')
            
            # Create a new page with the same dimensions as the original
            new_page = new_doc.new_page(
                width=original_page.rect.width, 
                height=original_page.rect.height
            )

            # Get a list of all images on the page
            img_list = original_page.get_images(full=True)
            if not img_list:
                print(f"\n  [WARN] No images found on page {i+1}. It will be blank.")
                continue

            for img_info in img_list:
                xref = img_info[0]
                try:
                    # Extract the raw, un-recompressed image stream
                    base_image = original_doc.extract_image(xref)
                    img_bytes = base_image["image"]
                    
                    # Get the original position and size of the image
                    img_rect = original_page.get_image_bbox(img_info)
                    
                    # Insert the raw image into the new page, preserving quality
                    new_page.insert_image(img_rect, stream=img_bytes)
                except Exception as e:
                    print(f"\n  [WARN] Could not process an image on page {i+1}. Skipping it. Error: {e}")
        
        print("\n  - Saving new PDF from extracted images...")
        new_doc.save(str(temp_output_path), garbage=4, deflate=True)

    except Exception as e:
        print(f"\n  [ERROR] Failed to process {pdf_path.name}: {e}")
        if temp_output_path.exists(): os.remove(temp_output_path)
        return
    finally:
        if original_doc: original_doc.close()
        if new_doc: new_doc.close()
    
    try:
        print("  - Replacing original file with clean version...")
        shutil.move(str(temp_output_path), str(pdf_path))
        print(f"  [SUCCESS] PDF rebuilt from original images. All extra data removed from {pdf_path.name}")
    except Exception as e:
        print(f"\n  [ERROR] Failed to replace original file: {e}")
        if temp_output_path.exists(): os.remove(temp_output_path)

def main():
    parser = argparse.ArgumentParser(
        description="A script to losslessly rebuild PDFs from their original images, stripping all text and metadata.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--input_dir', type=str, default='.', help="Directory containing PDF files. Defaults to current directory.")
    parser.add_argument('--backup', action='store_true', help="Create a backup of each original PDF before modifying it.")
    args = parser.parse_args()
    
    input_path = Path(args.input_dir).resolve()
    if not input_path.is_dir():
        print(f"Error: Input directory not found: '{input_path}'", file=sys.stderr)
        sys.exit(1)

    pdf_files = [f for f in input_path.glob('*.pdf') if not f.name.endswith(('.bak.pdf', '.tmp.pdf'))]
    if not pdf_files:
        print(f"No PDF files found in '{input_path}'.")
        return

    print("-" * 60)
    print(f"Target Directory: {input_path}")
    print(f"Files to process: {len(pdf_files)}")
    print(f"Mode: Rebuilding from Images (100% Lossless for JPEGs)")
    print("-" * 60)

    if not args.backup:
        confirm = input("You have not enabled backups. This will PERMANENTLY modify your files. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled by user.")
            sys.exit(0)
    
    for pdf_file in pdf_files:
        print(f"Processing '{pdf_file.name}'...")
        rebuild_from_images(pdf_file, args.backup)
    
    print("-" * 60)
    print("Processing complete.")

if __name__ == '__main__':
    main()