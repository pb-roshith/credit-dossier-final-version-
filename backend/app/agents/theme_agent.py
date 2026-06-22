import logging
import io
import json
from typing import Optional
from pydantic import BaseModel
from colorthief import ColorThief
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

class ThemeExtractionResponse(BaseModel):
    primary_color: str
    secondary_color: str
    theme_palette: list[str]

def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])

def extract_theme_from_document_bytes(file_bytes: bytes, filename: str) -> Optional[ThemeExtractionResponse]:
    """
    Extracts visual colors directly from the uploaded document using PyMuPDF and ColorThief.
    """
    try:
        # If it's a PDF, render the first page to get corporate branding
        if filename.lower().endswith(".pdf"):
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            if len(doc) == 0:
                return None
                
            page = doc.load_page(0)
            pix = page.get_pixmap()
            
            # Save the pixmap to a memory buffer as PNG
            img_bytes = pix.tobytes("png")
            img_io = io.BytesIO(img_bytes)
        else:
            # Assume it's an image file directly
            img_io = io.BytesIO(file_bytes)
            
        color_thief = ColorThief(img_io)
        
        # Build palette of 5 colors, ignoring pure white backgrounds
        # get_palette returns a list of RGB tuples
        palette_rgb = color_thief.get_palette(color_count=6, quality=1)
        
        # Filter out near-white and near-black colors to find actual brand colors
        vibrant_colors = []
        for rgb in palette_rgb:
            r, g, b = rgb
            # Filter out whites/grays
            if r > 240 and g > 240 and b > 240:
                continue
            # Filter out black
            if r < 15 and g < 15 and b < 15:
                continue
            vibrant_colors.append(rgb_to_hex((r, g, b)))
            
        # If we didn't find enough colors, just use whatever was extracted
        if not vibrant_colors:
            vibrant_colors = [rgb_to_hex(rgb) for rgb in palette_rgb]
            
        # Pad palette up to 5 colors if necessary
        default_palette = ["#002060", "#800020", "#1e293b", "#3b82f6", "#f59e0b"]
        final_palette = vibrant_colors[:5]
        while len(final_palette) < 5:
            final_palette.append(default_palette[len(final_palette)])
            
        return ThemeExtractionResponse(
            primary_color=final_palette[0],
            secondary_color=final_palette[1],
            theme_palette=final_palette
        )
        
    except Exception as e:
        logger.error(f"Error during visual theme extraction: {e}")
        return None
