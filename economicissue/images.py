"""Create square delivery images without altering the source capture."""
from PIL import Image, ImageOps

IMAGE_SIZE = (1080, 1080)


def square_image(path):
    with Image.open(path) as original:
        oriented = ImageOps.exif_transpose(original)
        if oriented.size == IMAGE_SIZE and original.getexif().get(274, 1) == 1:
            return
        fitted = ImageOps.contain(oriented.convert("RGBA"), IMAGE_SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", IMAGE_SIZE, "white")
    canvas.paste(fitted, ((1080 - fitted.width) // 2, (1080 - fitted.height) // 2), fitted)
    canvas.save(path, format="PNG")
