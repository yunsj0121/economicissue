"""Shared final image dimensions for rendered and externally supplied assets."""
from PIL import Image, ImageOps

IMAGE_SIZE = (1080, 1080)


def square_image(path):
    """Contain the complete image on a white square without cropping or distortion."""
    with Image.open(path) as original:
        oriented = ImageOps.exif_transpose(original)
        if oriented.size == IMAGE_SIZE and original.size == IMAGE_SIZE and original.getexif().get(274, 1) == 1:
            return
        fitted = ImageOps.contain(oriented.convert("RGBA"), IMAGE_SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", IMAGE_SIZE, "white")
    offset = ((IMAGE_SIZE[0] - fitted.width) // 2, (IMAGE_SIZE[1] - fitted.height) // 2)
    canvas.paste(fitted, offset, fitted)
    canvas.save(path)
