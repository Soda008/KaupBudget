"""Convert uploads (PDF, JPEG, PNG, WebP) into one JPEG per receipt."""
from io import BytesIO

from PIL import Image, ImageOps

ACCEPTED = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_EDGE = 4000          # keeps tall receipts readable without huge files
MAX_BYTES = 4_500_000    # AI providers cap images around 5 MB
MAX_PDF_PAGES = 5


class ImageError(ValueError):
    pass


def _render_pdf(data: bytes) -> list:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as e:  # noqa: BLE001 - pdfium raises its own error types
        raise ImageError(f"Couldn't open PDF: {e}") from e
    pages = []
    for i in range(min(len(pdf), MAX_PDF_PAGES)):
        pages.append(pdf[i].render(scale=2).to_pil())
    if not pages:
        raise ImageError("PDF has no pages.")
    return pages


def _stack(pages: list) -> Image.Image:
    if len(pages) == 1:
        return pages[0]
    width = max(p.width for p in pages)
    height = sum(p.height for p in pages)
    canvas = Image.new("RGB", (width, height), "white")
    y = 0
    for p in pages:
        canvas.paste(p.convert("RGB"), (0, y))
        y += p.height
    return canvas


def to_jpeg(data: bytes, filename: str) -> bytes:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        img = _stack(_render_pdf(data))
    else:
        try:
            img = Image.open(BytesIO(data))
            img = ImageOps.exif_transpose(img)  # phone photos come in sideways otherwise
        except Exception as e:  # noqa: BLE001
            raise ImageError("That file isn't a supported image (use PDF, JPEG, PNG or WebP).") from e

    if img.mode != "RGB":
        background = Image.new("RGB", img.size, "white")
        background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = background

    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE))

    for quality in (85, 75, 65, 55):
        buf = BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    img.thumbnail((MAX_EDGE // 2, MAX_EDGE // 2))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=70, optimize=True)
    return buf.getvalue()
