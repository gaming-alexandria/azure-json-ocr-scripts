#!/usr/bin/env python3
import fitz  # PyMuPDF
import json
import os
import sys
import numpy as np
import argparse
from pathlib import Path
from collections import namedtuple

# --- CONFIGURATION ---
FURIGANA_HEIGHT_THRESHOLD_PERCENT = 70
MAIN_TEXT_BENCHMARK_PERCENTILE = 90
DEFAULT_FONT_NAME = "NotoSansJP-Regular.ttf"

FilePair = namedtuple('FilePair', ['pdf', 'json'])

# --- Helper Functions ---
def get_polygon_height(polygon):
    if not polygon or len(polygon) < 8: return 0
    y_coords = [polygon[i] for i in range(1, len(polygon), 2)]; return max(y_coords) - min(y_coords)

def get_pages_from_json(data):
    if "pages" in data and data["pages"]: return data["pages"]
    if "analyzeResult" in data and isinstance(data.get("analyzeResult"), dict) and "pages" in data["analyzeResult"]: return data["analyzeResult"]["pages"]
    if "readResults" in data and data["readResults"]: return data["readResults"]
    return []

def get_item_poly(item):
    return item.get('polygon') or item.get('boundingBox')

def get_item_text(item):
    return item.get('content') or item.get('text')

# --- Main Processing Logic ---
def process_full_workflow(file_pair, pdf_out_path, text_out_path, font_path, height_cutoff, font_name="UserFont"):
    """
    MODE 1: Does everything. Rebuilds the PDF to remove furigana and creates the RAG JSON.
    """
    print(f"Processing '{os.path.basename(file_pair.pdf)}' (Full PDF & Text Workflow)...")

    # STAGE 1: Sanitize PDF
    print("  - Step 1: Rebuilding PDF from images...")
    original_doc, clean_base_doc = None, fitz.open()
    try:
        original_doc = fitz.open(str(file_pair.pdf))
        for i, original_page in enumerate(original_doc):
            new_page = clean_base_doc.new_page(width=original_page.rect.width, height=original_page.rect.height)
            for img_info in original_page.get_images(full=True):
                xref = img_info[0]; base_image = original_doc.extract_image(xref)
                new_page.insert_image(original_page.get_image_bbox(img_info), stream=base_image["image"])
    finally:
        if original_doc: original_doc.close()

    # STAGE 2: Generate Outputs
    print("  - Step 2: Generating new PDF text layer and RAG JSON...")
    try:
        with open(file_pair.json, 'r', encoding='utf-8-sig') as f: data = json.load(f)
        pages_data = get_pages_from_json(data)
        if not pages_data:
             clean_base_doc.save(pdf_out_path, garbage=4, deflate=True); return

        font_buffer = open(font_path, "rb").read()
        scale_factor = 72.0 if pages_data[0].get("unit") == "inch" else 1.0
        
        rag_output = { "source_file": os.path.basename(file_pair.pdf), "content_chunks": [] }
        
        for i, page_data in enumerate(pages_data):
            page_num = page_data['pageNumber']
            if i >= len(clean_base_doc): break
            pdf_page = clean_base_doc[i]
            pdf_page.insert_font(fontname=font_name, fontbuffer=font_buffer)
            
            main_text_lines = [line for line in page_data.get("lines", []) if get_polygon_height(get_item_poly(line)) >= height_cutoff]
            
            page_text_for_rag = "\n".join([get_item_text(line) for line in main_text_lines if get_item_text(line)])
            if page_text_for_rag:
                rag_output["content_chunks"].append({ "page_number": page_num, "type": "page_content", "content": page_text_for_rag })
            
            for line in main_text_lines:
                for line_span in line.get("spans", []):
                    line_start, line_end = line_span["offset"], line_span["offset"] + line_span["length"]
                    for word in page_data.get("words", []):
                        word_span = word.get("span", {}); word_start = word_span.get("offset", -1)
                        if word_start >= line_start and word_start < line_end:
                            word_poly = get_item_poly(word); word_text = get_item_text(word)
                            if not word_poly or not word_text: continue
                            scaled_points = [p * scale_factor for p in word_poly]
                            pdf_page.insert_text(fitz.Point(scaled_points[6], scaled_points[7]), word_text, fontname=font_name, fontsize=11, render_mode=3)

        print(f"  - Saving final PDF to '{pdf_out_path}'")
        clean_base_doc.save(pdf_out_path, garbage=4, deflate=True, linear=True)
        
        if rag_output["content_chunks"]:
            print(f"  - Saving RAG JSON to '{text_out_path}'")
            with open(text_out_path, 'w', encoding='utf-8') as f: json.dump(rag_output, f, ensure_ascii=False, indent=2)

    finally:
        if clean_base_doc: clean_base_doc.close()


def generate_rag_json_only(json_path, text_out_path):
    print(f"Processing '{os.path.basename(json_path)}' (RAG JSON-Only)...")
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f: data = json.load(f)
        pages_data = get_pages_from_json(data)
        if not pages_data: return

        rag_output = { "source_file": Path(json_path).stem + '.pdf', "content_chunks": [] }
        for page_data in pages_data:
            page_paras = [get_item_text(para) for para in page_data.get("paragraphs", []) if get_item_text(para)]
            if page_paras:
                rag_output["content_chunks"].append({ "page_number": page_data.get('pageNumber'), "type": "page_content", "content": "\n\n".join(page_paras) })

        if rag_output["content_chunks"]:
            print(f"  - Saving RAG JSON to '{text_out_path}'")
            with open(text_out_path, 'w', encoding='utf-8') as f: json.dump(rag_output, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"  [ERROR] An unexpected error occurred while processing '{os.path.basename(json_path)}': {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="A definitive tool to process OCR'd documents. It can remove furigana and create a clean PDF, or simply generate a structured JSON for RAG.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--input_dir', type=str, default='.', help="Directory for PDF/JSON files.")
    # *** CHANGE 1: A single output directory ***
    parser.add_argument('--output_dir', type=str, default='output', help="Directory for processed PDFs and/or RAG JSON files.")
    parser.add_argument('--font_path', type=str, help=f"Path to .ttf font file for PDF creation.")
    args = parser.parse_args()

    print("-" * 60)
    # *** CHANGE 2: Furigana removal is now opt-in ***
    user_choice = input("Enable furigana removal? (This will create new PDFs) (y/n) [default: n]: ").lower().strip()
    remove_furigana_enabled = user_choice == 'y'
    
    input_path = Path(args.input_dir)
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_pairs = [FilePair(p, p.with_suffix('.json')) for p in input_path.glob('*.pdf') if p.with_suffix('.json').is_file()]
    if not file_pairs: print("No matching PDF/JSON pairs found in the input directory."); return

    if remove_furigana_enabled:
        print("Mode: Full Processing (New PDF + RAG JSON).")
        
        if args.font_path:
            font_path = Path(args.font_path)
            if not font_path.is_file(): print(f"Error: Font file not found at '{font_path}'", file=sys.stderr); sys.exit(1)
        else:
            script_dir = Path(__file__).resolve().parent; font_path = script_dir / DEFAULT_FONT_NAME
            print(f"INFO: --font_path not specified. Searching for '{DEFAULT_FONT_NAME}'...")
            if not font_path.is_file(): print(f"ERROR: Default font not found. Please place it next to the script or use --font_path.", file=sys.stderr); sys.exit(1)
            print(f"INFO: Found and using default font: {font_path}")

        print("-" * 60); print("Performing global analysis...")
        all_lines = []
        for pair in file_pairs:
            try:
                with open(pair.json, 'r', encoding='utf-8-sig') as f: data = json.load(f)
                pages = get_pages_from_json(data)
                if pages:
                    for page in pages: all_lines.extend(page.get("lines", []))
            except Exception as e:
                print(f"Warning: Could not parse {pair.json} for analysis. Skipping. Error: {e}", file=sys.stderr)
        
        if not all_lines: print("Error: Could not extract any text lines from JSON files for analysis.", file=sys.stderr); sys.exit(1)
        
        all_heights = np.array([get_polygon_height(get_item_poly(l)) for l in all_lines])
        all_heights = all_heights[all_heights > 0]
        
        global_height_cutoff = 0.0
        if all_heights.size > 0:
            main_text_height_benchmark = np.percentile(all_heights, MAIN_TEXT_BENCHMARK_PERCENTILE)
            global_height_cutoff = main_text_height_benchmark * (FURIGANA_HEIGHT_THRESHOLD_PERCENT / 100.0)
            print(f"Global Furigana Height Cutoff determined to be: {global_height_cutoff:.4f}")
        else:
            print("Warning: No valid line heights found. Furigana removal may not be effective.", file=sys.stderr)
        
        print("-" * 60)
        
        for pair in file_pairs:
            # Both outputs now go to the same directory
            pdf_out = output_path / pair.pdf.name
            text_out = output_path / pair.json.with_suffix('.json').name
            process_full_workflow(pair, str(pdf_out), str(text_out), str(font_path), global_height_cutoff)
    else:
        print("Mode: RAG JSON-Only (Original PDFs will not be modified).")
        print("-" * 60)
        for pair in file_pairs:
            # Output goes to the single output directory
            text_out = output_path / pair.json.with_suffix('.json').name
            generate_rag_json_only(str(pair.json), str(text_out))

    print("-" * 60); print("Processing complete.")
    print(f"Output files saved to: {output_path.resolve()}")

if __name__ == '__main__':
    main()