"""
FALCON FITNESS — payment-receipt screening
==========================================

WHAT THIS DOES
--------------
Takes a photo or screenshot somebody uploaded as "proof I paid", and answers one
question: *does this look like a genuine, unedited photo of a real receipt?*

It is a damage-and-provenance examiner, not a forgery detector. Read the section
"What this genuinely cannot do" at the bottom before trusting it with money.

Every signal below returns a 0..1 score and a plain-English note, so the admin
panel can show the owner *why* the score is what it is rather than a bare number.
Nothing here is a black box and nothing here decides anything on its own — a
human always approves or rejects.
"""

from __future__ import annotations

import hashlib
import io
import math
import struct

# Pillow is what actually reads the uploaded image. It is a big native package,
# and on a phone (Termux) installing it is a separate step that can fail. If it
# is missing we must NOT take the whole website down -- a gym that cannot show
# its home page because of an image library would be absurd. Everything below is
# importable without it; only examine() needs it, and it says so honestly.
try:
    from PIL import Image, ExifTags, ImageChops, ImageFilter, ImageStat
    PIL_OK = True
    PIL_ERR = ""
except Exception as _pil_exc:          # pragma: no cover
    PIL_OK = False
    PIL_ERR = type(_pil_exc).__name__ + ": " + str(_pil_exc)[:120]

HEIF_OK = False
if PIL_OK:
    try:                  # optional: iPhone photos are HEIC, not JPEG
        import pillow_heif
        pillow_heif.register_heif_opener()
        HEIF_OK = True
    except Exception:
        HEIF_OK = False


MAX_PIXELS = 40_000_000   # refuse absurd images before PIL eats the RAM
THUMB = 512               # working size for every statistical pass


# ---------------------------------------------------------------------------
#  helpers
# ---------------------------------------------------------------------------
def _clip01(v):
    return max(0.0, min(1.0, float(v)))


def _entropy(img):
    """Shannon entropy of the luminance histogram, in bits (0..8)."""
    g = img.convert("L")
    hist = g.histogram()
    total = sum(hist) or 1
    out = 0.0
    for n in hist:
        if n:
            p = n / total
            out -= p * math.log2(p)
    return out


def _fft_slope(img):
    """
    Radial power-spectrum slope.

    Every real photograph obeys a roughly 1/f^a falloff in its power spectrum
    (a is about 2). Perfectly smooth generated artwork, a flat colour fill, or a
    heavily-denoised composite falls off far more steeply. A sharp synthetic
    overlay on a smooth background bends the curve. We only use the middle
    frequency band, where sensor noise dominates and JPEG blocks do not.
    """
    g = img.convert("L").resize((256, 256), Image.LANCZOS)
    try:
        spec = __import__("numpy").fft.fftshift(
            __import__("numpy").abs(__import__("numpy").fft.fft2(
                __import__("numpy").asarray(g, dtype=float))))
    except Exception:
        return None, None
    import numpy as np
    h, w = spec.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.indices((h, w))
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).astype(int)
    radial = np.bincount(r.ravel(), spec.ravel()) / np.maximum(
        1, np.bincount(r.ravel()))
    band = radial[8:80]
    band = band[band > 0]
    if len(band) < 8 or not np.isfinite(band).all():
        return None, None
    x = np.log10(np.arange(8, 8 + len(band)))
    y = np.log10(band)
    a, b = np.polyfit(x, y, 1)
    return float(a), float(b)


def _blockiness(img):
    """
    JPEG blockiness: how much more the 8-pixel grid stands out than its
    neighbours. A screenshot that has been opened, edited and re-saved in a
    phone gallery gains an *uneven* block grid; a single clean save has an even
    one. We report the raw ratio and let the score judge it.
    """
    g = img.convert("L")
    w, h = g.size
    if w < 64 or h < 64:
        return 0.0
    px = g.load()
    step = 8
    on, off, n_on, n_off = 0.0, 0.0, 0, 0
    for y in range(0, h - 1, 2):
        for x in range(1, w - 1):
            d = abs(px[x, y] - px[x - 1, y])
            if x % step == 0:
                on += d; n_on += 1
            elif x % step == 4:
                off += d; n_off += 1
    for x in range(0, w - 1, 2):
        for y in range(1, h - 1):
            d = abs(px[x, y] - px[x, y - 1])
            if y % step == 0:
                on += d; n_on += 1
            elif y % step == 4:
                off += d; n_off += 1
    if not n_on or not n_off:
        return 0.0
    a, b = on / n_on, off / n_off
    if b <= 0.0001:
        return 9.9
    return round(min(9.9, a / b), 3)


def _noise_floor(img):
    """Std-dev of the Laplacian: proxy for sensor noise / real texture."""
    g = img.convert("L").resize((THUMB, THUMB), Image.LANCZOS)
    lap = g.filter(ImageFilter.Kernel((3, 3), [0, -1, 0, -1, 4, -1, 0, -1, 0], 1, 0))
    return float(ImageStat.Stat(lap).stddev[0])


def _duplicate_region(img):
    """
    Coarse copy-move probe.

    Split the image into 32x32 blocks, take a 16-bin luminance histogram for
    each, and look for two blocks that are nearly identical but sit far apart.
    On a genuine receipt photo this essentially never fires. On a receipt where
    somebody pasted the amount field from another screenshot, it often does.
    Returns (worst_zscore, count_of_suspect_pairs).
    """
    g = img.convert("L").resize((256, 256), Image.LANCZOS)
    px = g.load()
    boxes, sigs = [], []
    for by in range(0, 256, 32):
        for bx in range(0, 256, 32):
            hist = [0] * 16
            for y in range(by, by + 32, 2):
                for x in range(bx, bx + 32, 2):
                    hist[px[x, y] >> 4] += 1
            # A block that is almost entirely one shade (blank wall, plain card
            # background) carries no information — two of them matching means
            # nothing. Only keep blocks with real tonal spread.
            if max(hist) > 0.85 * sum(hist):
                continue
            boxes.append((bx, by))
            sigs.append(hist)
    worst, pairs = 0.0, 0
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            dx = abs(boxes[i][0] - boxes[j][0])
            dy = abs(boxes[i][1] - boxes[j][1])
            if max(dx, dy) < 96:          # too close: same texture, not a copy
                continue
            a, b = sigs[i], sigs[j]
            diff = sum(abs(x - y) for x, y in zip(a, b))
            norm = max(1, sum(a) + sum(b))
            sim = 1.0 - diff / norm
            if sim > 0.985:
                pairs += 1
                worst = max(worst, sim)
    return round(worst, 4), pairs


# ---------------------------------------------------------------------------
#  the examiner
# ---------------------------------------------------------------------------
def available():
    """True when the image library is installed and screening can actually run."""
    return PIL_OK


def unavailable_reason():
    return PIL_ERR or "the image library (Pillow) is not installed"


def examine(path):
    """
    Run every check on an uploaded image.

    Returns a dict:
      score       0..100        higher = more likely a real, unedited photo
      verdict     str           'looks-legit' | 'needs-a-look' | 'likely-not-genuine'
      flags       list[str]     machine flags, e.g. 'edited'
      notes       list[dict]    {key, label, value, verdict, text} for the panel
      meta        dict          width, height, format, megapixels, sha256
      reencoded   bytes|None    a normalised JPEG thumbnail for the panel
    """
    # --- 0. can we screen at all? -------------------------------------------
    if not PIL_OK:
        return {
            "available": False,
            "score": None,
            "verdict": "not-screened",
            "flags": ["screening-unavailable"],
            "notes": [{
                "key": "unavailable", "label": "Automatic screening",
                "value": "unavailable", "verdict": "warn",
                "text": "The image library (Pillow) is not installed on this server, "
                        "so the receipt could not be examined automatically. The "
                        f"upload was still accepted. Reason: {PIL_ERR}",
            }],
            "meta": {"sha256": "", "bytes": 0},
            "reencoded": None,
            "width": 0,
            "height": 0,
        }

    notes = []
    flags = []
    score = 100.0

    raw = open(path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()

    def add(key, label, value, verdict, text, penalty=0.0):
        nonlocal score
        notes.append({"key": key, "label": label, "value": value,
                      "verdict": verdict, "text": text})
        score -= penalty

    # ---- 0. is it even an image, and is it sane -----------------------------
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        return {
            "available": True,
            "score": 0, "verdict": "likely-not-genuine", "flags": ["unreadable"],
            "notes": [{"key": "file", "label": "File", "value": type(exc).__name__,
                       "verdict": "bad",
                       "text": "This is not an image the site can read. Ask for a "
                               "normal JPG or PNG screenshot."}],
            "meta": {"sha256": sha}, "reencoded": None, "width": 0, "height": 0,
        }

    fmt = (img.format or "?").upper()
    w, h = img.size
    if w * h > MAX_PIXELS:
        return {
            "available": True,
            "score": 0, "verdict": "likely-not-genuine", "flags": ["too-large"],
            "notes": [{"key": "size", "label": "Image size", "value": f"{w}x{h}",
                       "verdict": "bad", "text": "Image is too large to screen safely."}],
            "meta": {"sha256": sha}, "reencoded": None, "width": w, "height": h,
        }

    megapixels = w * h / 1e6
    add("format", "File type", fmt, "info",
        "Read as %s, %.1f megapixels." % (fmt, megapixels))

    if megapixels < 0.05:
        add("resolution", "Resolution", f"{w}x{h}", "warn",
            "Very small — too small to read a receipt from. Ask for the original.",
            penalty=35)
        flags.append("too-small")
    elif megapixels < 0.25:
        add("resolution", "Resolution", f"{w}x{h}", "warn",
            "Low resolution. Probably a heavily compressed forward.", penalty=10)
    else:
        add("resolution", "Resolution", f"{w}x{h}", "good",
            "Enough pixels to read the details.")

    work = img.convert("RGB")
    if max(work.size) > THUMB:
        work.thumbnail((THUMB, THUMB), Image.LANCZOS)

    # ---- 1. EXIF ------------------------------------------------------------
    try:
        exif = img.getexif()
        exif_n = len(list(exif.items())) if exif else 0
    except Exception:
        exif, exif_n = None, 0
    edit_software = None
    if exif:
        for tag_id, val in exif.items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            if name in ("Software", "ProcessingSoftware") and val:
                edit_software = str(val)[:60]
    if edit_software:
        bad = any(k in edit_software.lower() for k in (
            "photoshop", "lightroom", "gimp", "snapseed", "picsart", "canva",
            "pixlr", "facetune", "meitu", "inshot", "vsco"))
        if bad:
            add("exif", "Editing software stamp", edit_software, "bad",
                "The file itself says it was saved by an editing app. Ask for the "
                "untouched original.", penalty=40)
            flags.append("edited-software-stamp")
        else:
            add("exif", "Editing software stamp", edit_software, "warn",
                "A camera or gallery app stamped this file. Not necessarily edited.")
    elif exif_n:
        add("exif", "EXIF data", f"{exif_n} tags", "good",
            "Camera metadata present — consistent with a photo taken on a phone.")
    else:
        add("exif", "EXIF data", "none", "warn",
            "No camera metadata. Normal for a screenshot; a photo of a paper "
            "receipt usually still has some. Worth a second look.")

    # ---- 2. is there anything on it at all? ---------------------------------
    # A UPI receipt is *mostly white*. Entropy alone therefore punishes the most
    # common legitimate upload, so the real question is whether the image has
    # any ink on it: text, lines, a logo. A blank canvas has essentially none.
    ent = _entropy(work)
    hist_l = work.convert("L").histogram()
    n_px = sum(hist_l) or 1
    ink = sum(hist_l[:110]) / n_px          # fraction of clearly dark pixels
    if ink < 0.0008:
        add("entropy", "Content on the image", f"{ink * 100:.3f}% ink", "bad",
            "There is essentially nothing on this image — no text, no lines, no "
            "receipt. It looks blank.", penalty=50)
        flags.append("near-blank")
    elif ink > 0.60:
        add("entropy", "Content on the image", f"{ink * 100:.0f}% ink", "warn",
            "Almost the whole image is dark. A receipt is normally mostly light.",
            penalty=20)
        flags.append("mostly-dark")
    else:
        add("entropy", "Content on the image", f"{ink * 100:.1f}% ink", "good",
            "Text or graphics present, as a receipt should have.")
    if ent < 0.75:
        add("entropy_bits", "Detail level", f"{ent:.2f} bits", "bad",
            "Far too uniform to be a receipt.", penalty=25)
        flags.append("near-blank")
    else:
        add("entropy_bits", "Detail level", f"{ent:.2f} bits", "good",
            "Consistent with a screenshot: a mostly light page with text on it.")

    # ---- 3. pure-white / pure-black flood -----------------------------------
    g = work.convert("L")
    hist = g.histogram()
    total = sum(hist) or 1
    blown = (sum(hist[248:]) + sum(hist[:8])) / total
    if blown > 0.93:
        add("exposure", "Clipped pixels", f"{blown * 100:.0f}%", "bad",
            "Nearly the whole image is pure white or pure black — typical of a "
            "screenshot pasted onto a blank canvas.", penalty=30)
        flags.append("blank-canvas")
    else:
        add("exposure", "Clipped pixels", f"{blown * 100:.0f}%", "good",
            "Light and dark areas are distributed normally.")

    # ---- 4. sensor noise ----------------------------------------------------
    noise = _noise_floor(work)
    if noise < 1.2:
        add("noise", "Texture / sensor noise", f"{noise:.2f}", "warn",
            "Unusually smooth for a photograph. Could be a perfectly clean "
            "screenshot, or a smoothed composite.", penalty=18)
        flags.append("suspiciously-smooth")
    else:
        add("noise", "Texture / sensor noise", f"{noise:.2f}", "good",
            "Natural grain present, as expected in a real image.")

    # ---- 5. JPEG grid -------------------------------------------------------
    block = _blockiness(work)
    if block > 2.6:
        add("jpeg", "JPEG block uniformity", f"{block:.2f}x", "warn",
            "The compression grid is uneven, which happens when an image is "
            "saved, edited and saved again. Worth a close look.", penalty=15)
        flags.append("recompressed")
    else:
        add("jpeg", "JPEG block uniformity", f"{block:.2f}x", "good",
            "Even compression grid — consistent with a single save.")

    # ---- 6. copy-move probe -------------------------------------------------
    similar, pairs = _duplicate_region(work)
    if pairs >= 3 and similar > 0.99:
        add("copy", "Repeated regions", f"{pairs} pairs", "bad",
            "Several separate areas are near-identical. That is what pasting one "
            "part of an image into another looks like — e.g. a copied amount field.",
            penalty=28)
        flags.append("repeated-regions")
    elif pairs >= 1:
        add("copy", "Repeated regions", f"{pairs} pair", "warn",
            "Two areas look very similar. Often harmless (a repeated logo or "
            "border), but check the amount field by eye.")
    else:
        add("copy", "Repeated regions", "none", "good",
            "No suspiciously duplicated areas.")

    # ---- 7. spectral slope / original vs resaved ----------------------------
    slope_a, slope_b = _fft_slope(work)
    # Thresholds measured against the club's own 11 photographs, which all land
    # between -1.13 and -1.44 after downscaling. Anything flatter than -0.90 is
    # synthetic-looking; anything steeper than -1.80 is unnaturally smooth.
    if slope_a is not None:
        if slope_a > -0.90:
            add("spectrum", "Power spectrum", f"a={slope_a:.2f}", "warn",
                "The frequency falloff is flatter than a camera capture — "
                "consistent with synthetic or generated content.", penalty=18)
            flags.append("synthetic-spectrum")
        elif slope_a < -1.80:
            add("spectrum", "Power spectrum", f"a={slope_a:.2f}", "warn",
                "Smoother than a camera capture normally is — possibly heavily "
                "denoised or resaved.", penalty=10)
            flags.append("over-smoothed")
        else:
            add("spectrum", "Power spectrum", f"a={slope_a:.2f}", "good",
                "Frequency falloff matches a real camera image.")

    # ---- 8. does the file carry a screenshot's fingerprint? -----------------
    looks_screenshot = (not exif_n) and (fmt in ("PNG", "WEBP") or noise < 1.4)
    if looks_screenshot:
        add("provenance", "Likely a screenshot", "yes", "info",
            "This looks like a screen capture rather than a photo of a paper "
            "receipt. That is completely normal for a UPI payment — just make "
            "sure the UPI reference and amount are visible.")

    # ---- verdict ------------------------------------------------------------
    score = max(0, min(100, round(score)))
    if flags and any(f in flags for f in ("near-blank", "unreadable", "blank-canvas")) \
       and score < 40:
        verdict = "likely-not-genuine"
    elif score >= 78 and not any(f in flags for f in ("edited-software-stamp",)):
        verdict = "looks-legit"
    else:
        verdict = "needs-a-look"

    # normalised thumbnail for the approval panel (never the original)
    thumb = None
    try:
        t = img.convert("RGB")
        t.thumbnail((720, 720), Image.LANCZOS)
        buf = io.BytesIO()
        t.save(buf, "JPEG", quality=78, optimize=True)
        thumb = buf.getvalue()
    except Exception:
        pass

    return {
        "available": True,
        "score": score,
        "verdict": verdict,
        "flags": flags,
        "notes": notes,
        "meta": {
            "sha256": sha,
            "format": fmt,
            "width": w,
            "height": h,
            "megapixels": round(megapixels, 2),
            "entropy_bits": round(ent, 2),
            "noise": round(noise, 2),
            "blockiness": block,
            "spectrum_slope": None if slope_a is None else round(slope_a, 3),
            "exif_tags": exif_n,
            "exif_software": edit_software,
            "bytes": len(raw),
        },
        "reencoded": thumb,
    }


# ---------------------------------------------------------------------------
#  OCR: reading the amount and date off the receipt
# ---------------------------------------------------------------------------
# Tesseract is optional. If it is installed we read the image and compare the
# amount and date to what the member claimed. If it is not installed we say so
# honestly rather than pretending. Nothing is created by this function — it only
# reports what it could read.
def ocr_text(path):
    """
    Return (text, status) where status is 'ok', 'no-engine', or 'failed'.
    Install the engine with:  pip install pytesseract   and install the system
    package `tesseract-ocr` (on Termux:  pkg install tesseract).
    """
    if not PIL_OK:
        return "", "no-engine"
    try:
        import pytesseract
    except ImportError:
        return "", "no-engine"
    try:
        img = Image.open(path)
        if max(img.size) > 2400:
            img.thumbnail((2400, 2400), Image.LANCZOS)
        return pytesseract.image_to_string(img.convert("L")), "ok"
    except Exception as exc:
        app_note = type(exc).__name__
        return "", "failed:" + app_note


def scrape_amount_date(text):
    """
    Pull the most likely rupee amount and the first plausible date out of OCR
    text. Deliberately conservative: a wrong amount is worse than no amount.
    """
    import re
    amount = None
    # ₹1,049 | Rs.1049 | INR 1049 | 1049.00
    for m in re.finditer(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]{1,7})(?:\.\d{2})?", text, re.I):
        try:
            v = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if 50 <= v <= 200000:
            amount = v if amount is None else max(amount, v)
    if amount is None:
        for m in re.finditer(r"\b([0-9]{1,6})\.00\b", text):
            v = int(m.group(1))
            if 100 <= v <= 200000:
                amount = v if amount is None else max(amount, v)

    date = None
    pats = [
        r"\b([0-3]?[0-9])[/-]([01]?[0-9])[/-](20[0-9]{2})\b",   # 31/10/2026
        r"\b(20[0-9]{2})-([01][0-9])-([0-3][0-9])\b",           # 2026-10-31
        r"\b([0-3]?[0-9])\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20[0-9]{2})\b",
    ]
    import datetime as _dt
    for p in pats:
        m = re.search(p, text, re.I)
        if not m:
            continue
        try:
            if p.startswith(r"\b(20"):
                date = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif m.group(2).isalpha():
                mon = ["jan", "feb", "mar", "apr", "may", "jun",
                       "jul", "aug", "sep", "oct", "nov", "dec"].index(
                           m.group(2).lower()[:3]) + 1
                date = _dt.date(int(m.group(3)), mon, int(m.group(1)))
            else:
                date = _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            break
        except ValueError:
            continue
    return amount, date


# ---------------------------------------------------------------------------
#  honesty box — printed in the admin guide as well
# ---------------------------------------------------------------------------
CANNOT = (
    "This screening cannot prove a receipt is real. A determined forger can "
    "defeat JPEG, FFT and blockiness analysis, and no amount of image science "
    "fixes that. What it does do is catch the common cases — a screenshot of "
    "somebody else's payment, an obviously edited file, a blank or unreadable "
    "image — and it tells you which specific signals fired so you can look "
    "yourself. Always cross-check the amount and UTR against your own UPI app "
    "before you approve."
)
