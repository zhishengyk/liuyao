"""Resume per-page PDF extraction; publish JSONL only when every page is present.

Machine OCR remains machine_extracted. Reviewed text is copied without rewriting.
Dependencies: rapidocr==3.9.2 onnxruntime==1.30.0 pypdf pypdfium2 pillow.
"""
import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import time

from pypdf import PdfReader
import pypdfium2 as pdfium


PARAMS = {
    "EngineConfig.onnxruntime.intra_op_num_threads": 2,
    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    "EngineConfig.onnxruntime.use_cuda": False,
    "Global.max_side_len": 2600,
}
SCRIPT_VERSION = "canonical-pages-v1"


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sha_text(value):
    return hashlib.sha256(value.encode("utf8")).hexdigest()


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf8")
    temporary.replace(path)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def image_method(page):
    objects = [v.get_object() for v in page["/Resources"].get("/XObject", {}).values()]
    images = [obj for obj in objects if obj.get("/Subtype") == "/Image"]
    native = re.sub(r"\s+", "", page.extract_text()).casefold()
    native = native.replace("更多精品领赠品加v信3051374004", "")
    if native:
        return "complete_page_render_visible_pdf_text", images
    if len(images) == 1 and "/JBIG2Decode" not in str(images[0].get("/Filter")):
        return "original_embedded_image", images
    return "complete_page_render_multiple_images_or_jbig2", images


def extract_image(reader, rendered, number, target, font_directory):
    page = reader.pages[number - 1]
    method, images = image_method(page)
    if method == "original_embedded_image":
        image = page.images[0].image.convert("RGB")
    else:
        # Preserve overlaid cover titles, extra images and JBIG2 content.
        pdf_page = rendered[number - 1]
        width = max((int(obj["/Width"]) for obj in images), default=1800)
        bitmap = pdf_page.render(scale=width / pdf_page.get_width())
        image = bitmap.to_pil().convert("RGB")
        bitmap.close()
        pdf_page.close()
    temporary = target.with_suffix(".tmp")
    image.save(temporary, format="PNG")
    temporary.replace(target)
    return {"method": method, "path": str(target.resolve()), "sha256": sha_file(target),
            "width": image.width, "height": image.height, "image_objects": len(images),
            "font_directory": font_directory if method.startswith("complete_page_render") else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--pdf-sha256", required=True)
    parser.add_argument("--pages", type=int, required=True)
    parser.add_argument("--proofread-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pdf-font-dir", type=Path,
                        default=Path("/mnt/c/Windows/Fonts") if Path("/mnt/c/Windows/Fonts").is_dir() else None)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cache = args.cache_dir or root / ".local/canonical-extraction" / args.source_id
    output = args.output or root / "data/canonical" / f"{args.source_id}.jsonl"
    proof_dir = args.proofread_dir or root / "data/proofread_pages" / args.source_id
    font_directory = str(args.pdf_font_dir.resolve()) if args.pdf_font_dir else None
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.monotonic()
    versions = {name: importlib.metadata.version(name)
                for name in ("rapidocr", "onnxruntime", "pypdf", "pypdfium2", "pillow")}
    configuration = {"script_version": SCRIPT_VERSION, "versions": versions, "params": PARAMS}
    config_sha = sha_text(json.dumps(configuration, sort_keys=True))

    def progress(status, error=None):
        value = {"source_id": args.source_id, "pid": os.getpid(), "status": status,
                 "original_pdf_sha256": args.pdf_sha256, "total_pages": args.pages,
                 "completed_pages": len(rows), "last_page": rows[-1]["page"] if rows else None,
                 "reviewed_pages": sum(r["provenance"]["review_status"] == "visually_reviewed" for r in rows),
                 "machine_pages": sum(r["provenance"]["review_status"] == "machine_extracted" for r in rows),
                 "elapsed_seconds": round(time.monotonic() - started, 2),
                 "missing_pages": list(range(len(rows) + 1, args.pages + 1)),
                 "output": str(output.resolve()), "error": error}
        write_json(cache / "progress.json", value)
        if status != "running" or len(rows) % 10 == 0:
            print(json.dumps({k: v for k, v in value.items() if k != "missing_pages"}, ensure_ascii=False), flush=True)

    try:
        if args.proofread_dir is not None and not proof_dir.is_dir():
            raise ValueError(f"Explicit proofread directory does not exist: {proof_dir}")
        if sha_file(args.pdf) != args.pdf_sha256:
            raise ValueError("Original PDF SHA-256 mismatch; extraction was not started")
        reader = PdfReader(args.pdf)
        if len(reader.pages) != args.pages:
            raise ValueError(f"Expected {args.pages} pages, found {len(reader.pages)}")
        if args.pdf_font_dir is not None:
            if not args.pdf_font_dir.is_dir():
                raise ValueError(f"PDF font directory does not exist: {args.pdf_font_dir}")
            # Configure PDFium before opening any documents. Linux otherwise
            # omits these covers' non-embedded Chinese title fonts.
            font_paths = (ctypes.c_char_p * 2)(os.fsencode(font_directory), None)
            font_config = pdfium.raw.FPDF_LIBRARY_CONFIG(version=2, m_pUserFontPaths=
                ctypes.cast(font_paths, ctypes.POINTER(ctypes.POINTER(ctypes.c_char))))
            pdfium.raw.FPDF_DestroyLibrary()
            pdfium.raw.FPDF_InitLibraryWithConfig(font_config)
        rendered = pdfium.PdfDocument(args.pdf)
        proofs = {}
        for path in sorted(proof_dir.glob("*.json")):
            proof = json.loads(path.read_text(encoding="utf8"))
            number = proof["pdf_page"]
            if proof["source_id"] != args.source_id or proof["pdf_sha256"] != args.pdf_sha256:
                raise ValueError(f"Proofread source/hash mismatch: {path}")
            if proof["status"] not in ("visually_checked", "visually_reviewed"):
                raise ValueError(f"Unreviewed record in proofread directory: {path}")
            if not 1 <= number <= args.pages or number in proofs:
                raise ValueError(f"Invalid or duplicate proofread page: {path}")
            proofs[number] = (path, proof)
        write_json(cache / "configuration.json", {**configuration, "configuration_sha256": config_sha,
                    "original_pdf_path": str(args.pdf.resolve()), "original_pdf_sha256": args.pdf_sha256,
                    "pdf_font_directory": font_directory,
                    "proofread_pages": sorted(proofs)})
        engine = None
        progress("running")
        for number in range(1, args.pages + 1):
            target = cache / f"{number:04d}.json"
            image_path = cache / f"{number:04d}.png"
            proof_path, proof = proofs.get(number, (None, None))
            proof_sha = sha_file(proof_path) if proof_path else None
            expected_image_method = image_method(reader.pages[number - 1])[0]
            review_status = "visually_reviewed" if proof is not None else "machine_extracted"
            proof_metadata = {k: v for k, v in proof.items() if k != "text"} if proof is not None else None
            if target.exists():
                saved = json.loads(target.read_text(encoding="utf8"))
                canonical = saved["canonical"]
                provenance = canonical["provenance"]
                if (canonical["source_id"] == args.source_id and canonical["page"] == number
                        and provenance["source_page"] == number
                        and provenance["original_pdf_sha256"] == args.pdf_sha256
                        and provenance["review_status"] == review_status
                        and saved["configuration_sha256"] == config_sha
                        and provenance.get("proofread_record_sha256") == proof_sha
                        and (proof is None or (canonical["text"] == proof["text"]
                             and provenance.get("proofread_metadata") == proof_metadata))
                        and canonical["text_sha256"] == sha_text(canonical["text"])
                        and provenance["image_sha256"] == saved["image"]["sha256"]
                        and saved["image"]["method"] == expected_image_method
                        and (not expected_image_method.startswith("complete_page_render")
                             or saved["image"].get("font_directory") == font_directory)
                        and image_path.exists() and sha_file(image_path) == saved["image"]["sha256"]):
                    rows.append(canonical)
                    progress("running")
                    continue
            image_info = extract_image(reader, rendered, number, image_path, font_directory)
            provenance = {"original_pdf_sha256": args.pdf_sha256, "source_page": number,
                          "image_sha256": image_info["sha256"], "image_method": image_info["method"],
                          "cache_page": str(target.resolve()), "proofread_record_sha256": proof_sha}
            ocr = None
            if proof is not None:
                text = proof["text"]
                provenance.update(method="reviewed_text_copy", review_status="visually_reviewed",
                                  proofread_record_path=str(proof_path.resolve()),
                                  proofread_metadata=proof_metadata)
            else:
                if engine is None:
                    from rapidocr import RapidOCR
                    engine = RapidOCR(params=PARAMS)
                before = time.monotonic()
                result = engine(str(image_path))
                lines = [{"box": box.tolist(), "text": value, "score": float(score)}
                         for box, value, score in zip(result.boxes if result.boxes is not None else [],
                                                     result.txts if result.txts is not None else [],
                                                     result.scores if result.scores is not None else [])]
                text = "\n".join(line["text"] for line in lines)
                ocr = {"wall_seconds": time.monotonic() - before, "lines": lines,
                       "configuration_sha256": config_sha}
                provenance.update(method="rapidocr_ppocrv6_small_cpu", review_status="machine_extracted",
                                  engine_versions=versions, configuration_sha256=config_sha)
                if not text:
                    provenance["extraction_note"] = "No OCR text detected; original page image retained"
            canonical = {"source_id": args.source_id, "page": number, "text": text,
                         "text_sha256": sha_text(text), "provenance": provenance}
            write_json(target, {"canonical": canonical, "configuration_sha256": config_sha,
                                "image": image_info, "ocr": ocr})
            rows.append(canonical)
            progress("running")
        if [row["page"] for row in rows] != list(range(1, args.pages + 1)):
            raise ValueError("Missing pages; final JSONL was not published")
        atomic_write(output, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
        progress("complete")
        rendered.close()
    except BaseException as exc:
        progress("interrupted" if isinstance(exc, KeyboardInterrupt) else "failed", repr(exc))
        raise


if __name__ == "__main__":
    main()
