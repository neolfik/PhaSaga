from docx2python import docx2python
from openpyxl import load_workbook, Workbook
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as OpenpyxlImage
from pathlib import Path
from typing import Optional, Tuple, List
from statistics import mean, stdev
from openpyxl.styles import Font
import csv
import zipfile
import numpy as np
import json
from PIL import Image as PILImage
import io
import os
import tkinter as tk
from tkinter import ttk
from elements import ELEMENTS
from constants import HANDLE_NEGATIVE_VALUES


def select_elements_gui(all_elements: List[str]) -> List[str]:
    """
    Show GUI to select which 3 elements to keep when more than 3 are detected.
    
    Args:
        all_elements: List of all detected element names
    
    Returns:
        List of exactly 3 selected element names (alphabetically sorted), 
        or original list if 3 or fewer elements
    """
    if len(all_elements) <= 3:
        return sorted(all_elements)
    
    root = tk.Tk()
    root.title("Select Elements")
    
    # Fit window to screen without being fullscreen
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.5)
    window_height = int(screen_height * 0.5)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    selected = []
    checkboxes = []
    
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text="More than 3 elements detected!", 
              font=("Arial", 14, "bold")).pack(pady=(0, 10))
    ttk.Label(main_frame, text="Select exactly 3 elements to keep:", 
              font=("Arial", 11)).pack(pady=(0, 20))
    
    for elem in sorted(all_elements):
        var = tk.BooleanVar()
        chk = ttk.Checkbutton(main_frame, text=elem, variable=var, 
                             command=lambda: update_selection())
        chk.pack(anchor=tk.W, pady=2)
        checkboxes.append((chk, var, elem))
    
    status_label = ttk.Label(main_frame, text="", font=("Arial", 10))
    status_label.pack(pady=10)
    
    def update_selection():
        nonlocal selected
        selected = [elem for _, var, elem in checkboxes if var.get()]
        if len(selected) == 3:
            status_label.config(text=f"Selected: {', '.join(selected)}", foreground="green")
        elif len(selected) > 3:
            status_label.config(text=f"Too many selected ({len(selected)}). Deselect one.", foreground="orange")
        else:
            status_label.config(text=f"Select {3 - len(selected)} more", foreground="red")
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=20)
    
    def on_confirm():
        if len(selected) == 3:
            root.destroy()
    
    def on_cancel():
        nonlocal selected
        selected = sorted(all_elements[:3])  # Default: first 3 alphabetically
        root.destroy()
    
    ttk.Button(button_frame, text="Confirm Selection", command=on_confirm).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Cancel (use first 3)", command=on_cancel).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    return sorted(selected)
import tempfile
from constants import (
    MEAN_DETECTION_MAX_COL,
    MIN_NORMALIZATION_TOTAL,
    NORMALIZATION_WARNING_LOW,
    NORMALIZATION_WARNING_HIGH,
    STUDENT_COEFF_FILE,
    STUDENT_COEFF_MAX_INDEX,
    AZTEC_IMAGE_PATH
)
from logging_config import (
    log_warning,
    log_info,
    log_error,
    log_normalization_warning,
    log_file_skipped
)

# Global config variable
_config = None

def load_config(config_path: str = "config.json") -> dict:
    """Load configuration with validation and defaults."""
    defaults = {
        "normalization": {"enabled": True, "apply_to_both_types": True},
        "images": {
            "embed_images": True, 
            "min_width_columns": 4,
            "max_width_columns": 8,
            "preserve_aspect_ratio": True
        }
    }
    
    config_full_path = Path(__file__).parent / config_path
    
    if config_full_path.exists():
        config_path = str(config_full_path)  # Convert to string
    else:
        config_path = config_path
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                return {**defaults, **user_config}
        except Exception as e:
            print(f"Error loading config, using defaults: {e}")
    
    global _config
    _config = defaults
    return defaults

def get_config() -> dict:
    """Get current configuration."""
    global _config
    if _config is None:
        _config = load_config()
    return _config

def confirm_image_for_embedding(img_data: bytes, source_file: str, img_name: str) -> bool:
    """
    Enhanced image display with proper numpy array conversion to fix light blue screen issue.
    Uses matplotlib to show the image with Yes/No buttons.
    Window close is treated as NO (reject).
    
    Args:
        img_data: Raw image bytes (should be in RGB PNG format from enhanced extraction)
        source_file: Source filename for context
        img_name: Image name (e.g., 'image1.png')
    
    Returns:
        True if user confirms to embed, False to skip
    """
    import matplotlib.pyplot as plt
    from matplotlib.widgets import Button
    import numpy as np
    
    try:
        # Load image with PIL first to handle various formats
        img = PILImage.open(io.BytesIO(img_data))
        
        # Get image info for debugging
        log_info(f"Displaying image: {img_name}, mode={img.mode}, size={img.size}, format={img.format}")
        
        # CRITICAL FIX: Ensure proper format conversion for matplotlib compatibility
        if img.mode == 'RGBA':
            # Handle alpha channel properly by compositing on white background
            background = PILImage.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode in ('P', 'LA', 'L'):
            # Convert palette, grayscale, and luminance+alpha to RGB
            img = img.convert('RGB')
        elif img.mode != 'RGB':
            # Convert any other modes to RGB
            img = img.convert('RGB')
        
        # Convert to numpy array with CORRECT data type (CRITICAL for matplotlib)
        img_array = np.array(img)
        
        # CRITICAL: Ensure uint8 data type - matplotlib expects this for RGB images
        if img_array.dtype != np.uint8:
            if img_array.max() <= 1.0:  # Float image in [0,1] range
                img_array = (img_array * 255).astype(np.uint8)
            else:
                img_array = np.clip(img_array, 0, 255).astype(np.uint8)
        
        # Debug logging to troubleshoot display issues
        log_info(f"Display array: shape={img_array.shape}, dtype={img_array.dtype}, "
                f"min={img_array.min()}, max={img_array.max()}, mean={img_array.mean():.2f}")
        
        # Verify array properties before display
        if len(img_array.shape) != 3 or img_array.shape[2] != 3:
            log_error(f"Invalid array shape for RGB display: {img_array.shape}")
            # Try to fix common issues
            if len(img_array.shape) == 2:  # Grayscale
                img_array = np.stack([img_array, img_array, img_array], axis=2)
            elif img_array.shape[2] == 4:  # RGBA
                img_array = img_array[:, :, :3]  # Remove alpha
        
        # Create figure with proper backend
        fig = plt.figure(num=9999, figsize=(10, 8))
        if fig.canvas.manager:
            fig.canvas.manager.set_window_title('Image Confirmation')
        
        # Main image axes - use proper positioning
        ax = fig.add_axes((0.1, 0.25, 0.8, 0.65))
        
        # Display with explicit parameters and proper array
        ax.imshow(img_array)
        ax.axis('off')
        ax.set_title(f"Image from: {source_file}\n({img_name}) - Size: {img.size}", 
                    fontsize=12, weight='bold')
        
        # Result container (default is NO/False if window closed)
        result = {'confirmed': False, 'closed': False}
        
        # Button callbacks
        def on_yes(event):
            result['confirmed'] = True
            result['closed'] = True
            plt.close('all')  # Close all figures
        
        def on_no(event):
            result['confirmed'] = False
            result['closed'] = True
            plt.close('all')  # Close all figures
        
        # Handle window close event (treat as NO)
        def on_close(event):
            if not result['closed']:  # Only if buttons not clicked
                result['confirmed'] = False
                result['closed'] = True
        
        fig.canvas.mpl_connect('close_event', on_close)
        
        # Create buttons
        ax_yes = fig.add_axes((0.25, 0.08, 0.18, 0.08))
        ax_no = fig.add_axes((0.57, 0.08, 0.18, 0.08))
        
        btn_yes = Button(ax_yes, 'Embed (Y)', color='lightgreen', hovercolor='green')
        btn_no = Button(ax_no, 'Skip (N)', color='lightcoral', hovercolor='red')
        
        btn_yes.on_clicked(on_yes)
        btn_no.on_clicked(on_no)
        
        # Add instruction text
        fig.text(0.5, 0.18, 'Embed this image in Excel sheet?', 
                ha='center', fontsize=12, weight='bold')
        fig.text(0.5, 0.02, 'Close window = Skip (same as No)', 
                ha='center', fontsize=9, style='italic', color='gray')
        
        plt.show(block=True)  # Block until user responds
        
        return result['confirmed']
        
    except Exception as e:
        log_error(f"Enhanced image display failed: {e}", exc_info=True)
        
        # Fallback to simple PIL display method
        try:
            log_warning("Attempting PIL show() fallback")
            img = PILImage.open(io.BytesIO(img_data))
            img.show(title=f"{source_file} - {img_name}")
            response = input(f"Embed this image? (y/n): ")
            return response.lower().strip() in ['y', 'yes']
        except Exception as fallback_error:
            log_error(f"Fallback display also failed: {fallback_error}")
            # Final fallback to console input
            response = input(f"Could not display {img_name} from {source_file}. Embed anyway? (y/n): ")
            return response.lower().strip() == 'y'


def extract_aztec_images(docx_path: str) -> List[Tuple[str, bytes]]:
    """
    Enhanced image extraction from AZTEC .docx files with comprehensive error handling.
    Extracts ALL media files and converts them to standard RGB PNG format.
    
    Args:
        docx_path: Path to AZTEC .docx file
    
    Returns:
        List containing (filename, image_data) tuples in RGB PNG format
    """
    images = []
    filename = Path(docx_path).name
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as docx_zip:
            # Get ALL media files, prefer root media/ over word/media/
            root_media = [f for f in docx_zip.namelist() if f.startswith('media/')]
            word_media = [f for f in docx_zip.namelist() if f.startswith('word/media/')]
            
            # Prioritize root media/ (AZTEC main images), keep both for completeness
            media_files = root_media + [f for f in word_media if f not in [w.replace('word/', '') for w in root_media]]
            
            if not media_files:
                # Fallback to original behavior if no media files found
                log_info(f"No media files found in {filename}, trying original path {AZTEC_IMAGE_PATH}")
                media_files = [AZTEC_IMAGE_PATH] if AZTEC_IMAGE_PATH in docx_zip.namelist() else []
                
            if not media_files:
                log_info(f"No image files found in {filename}")
                return images
            
            for media_file in sorted(media_files):  # Sort for consistent ordering
                try:
                    # Extract raw bytes
                    img_data = docx_zip.read(media_file)
                    
                    # Validate file size
                    if len(img_data) == 0:
                        log_warning(f"Empty image file: {media_file}")
                        continue
                    
                    # Get clean filename with path context
                    img_path = Path(media_file)
                    img_name = img_path.name
                    
                    # If from root media/, add prefix to distinguish from word/media/
                    if media_file.startswith('media/') and not media_file.startswith('word/media/'):
                        # Extract image number and create meaningful name
                        if img_path.stem == img_path.name.replace('.png', '').replace('.jpg', '').replace('.jpeg', ''):
                            # Already has good name, just ensure extension
                            if not img_name.lower().endswith('.png'):
                                img_name += '.png'
                        else:
                            # Add media_ prefix to indicate source
                            img_name = f"media_{img_name}"
                            if not img_name.lower().endswith('.png'):
                                img_name = f"{img_name}.png"
                    else:
                        # word/media/ images - ensure proper naming
                        if not img_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                            img_name += '.png'  # Ensure PNG extension
                    
                    # Enhanced validation and format conversion
                    try:
                        with PILImage.open(io.BytesIO(img_data)) as test_img:
                            # Convert to RGB for compatibility
                            if test_img.mode in ('RGBA', 'LA'):
                                # Handle transparency by compositing on white background
                                background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                                if test_img.mode == 'RGBA':
                                    background.paste(test_img, mask=test_img.split()[-1])
                                else:  # LA mode
                                    background.paste(test_img, mask=test_img.split()[-1])
                                final_img = background
                            elif test_img.mode in ('P', 'L'):
                                # Convert palette and grayscale to RGB
                                final_img = test_img.convert('RGB')
                            elif test_img.mode == 'RGB':
                                final_img = test_img
                            else:
                                # Handle any other modes by converting to RGB
                                final_img = test_img.convert('RGB')
                            
                            # Save as optimized PNG to ensure consistency
                            output = io.BytesIO()
                            final_img.save(output, format='PNG', optimize=True)
                            final_data = output.getvalue()
                            
                            # Verify the converted image
                            try:
                                with PILImage.open(io.BytesIO(final_data)) as verify_img:
                                    if verify_img.size[0] > 0 and verify_img.size[1] > 0:
                                        images.append((img_name, final_data))
                                    else:
                                        log_warning(f"Invalid converted image: {img_name}")
                            except Exception as verify_error:
                                log_warning(f"Verification failed for {img_name}: {verify_error}")
                                
                    except Exception as pil_error:
                        log_warning(f"PIL processing failed for {img_name}: {pil_error}")
                        # Try to save original data as last resort
                        try:
                            with PILImage.open(io.BytesIO(img_data)) as raw_img:
                                if raw_img.size[0] > 0 and raw_img.size[1] > 0:
                                    output = io.BytesIO()
                                    raw_img.save(output, format='PNG', optimize=True)
                                    images.append((img_name, output.getvalue()))
                                    log_info(f"Saved original {img_name} as PNG (fallback)")
                        except Exception as fallback_error:
                            log_error(f"Fallback also failed for {img_name}: {fallback_error}")
                        
                except Exception as e:
                    log_error(f"Failed to process {media_file}: {e}")
                    
    except zipfile.BadZipFile:
        log_error(f"Invalid .docx file (not a valid zip): {filename}")
    except Exception as e:
        log_error(f"Failed to extract images from {filename}: {e}", exc_info=True)
    
        log_info(f"Total images extracted from {filename}: {len(images)}")
    return images


def collect_all_images_for_sample(files_data: List[Tuple[str, Path, str]], config: dict) -> List[Tuple[str, bytes, dict]]:
    """
    Collect ALL images from ALL AZTEC files for a sample before any confirmation.
    
    Args:
        files_data: List of (target_path, file_obj, table_type) tuples for the sample
        config: Configuration dictionary
    
    Returns:
        List of (img_name, img_data, metadata) tuples where metadata contains:
        - source_file: Original filename
        - image_name: Extracted image name
        - file_type: Table type (AZTEC/INCA)
        - dimensions: Image dimensions
    """
    from PIL import Image as PILImage
    
    all_images = []
    
    for target, file_obj, t_type in files_data:
        # Only extract from AZTEC files as requested
        if t_type == 'AZTEC' and config['images']['embed_images']:
            try:
                # Extract images from this file
                file_images = extract_aztec_images(str(target))
                
                for img_name, img_data in file_images:
                    try:
                        # Get image dimensions
                        with PILImage.open(io.BytesIO(img_data)) as img:
                            dimensions = f"{img.size[0]}x{img.size[1]}"
                        
                        # Get filename properly
                        source_filename = file_obj.name
                        
                        metadata = {
                            'source_file': source_filename,
                            'image_name': img_name,
                            'file_type': t_type,
                            'dimensions': dimensions,
                            'size': len(img_data)
                        }
                        
                        all_images.append((img_name, img_data, metadata))
                        log_info(f"Collected image {img_name} from {source_filename} ({dimensions})")
                        
                    except Exception as e:
                        log_warning(f"Failed to get metadata for {img_name} from {file_obj}: {e}")
                        # Still add image even if metadata extraction fails
                        source_filename = file_obj.name
                        metadata = {
                            'source_file': source_filename,
                            'image_name': img_name,
                            'file_type': t_type,
                            'dimensions': 'Unknown',
                            'size': len(img_data)
                        }
                        all_images.append((img_name, img_data, metadata))
                
                source_filename = file_obj.name
                log_info(f"Collected {len(file_images)} images from {source_filename}")
                
            except Exception as e:
                source_filename = file_obj.name
                log_error(f"Failed to extract images from {source_filename}: {e}")
        else:
            source_filename = file_obj.name
            if t_type != 'AZTEC':
                log_info(f"Skipping image extraction from non-AZTEC file: {source_filename} (type: {t_type})")
            elif not config['images']['embed_images']:
                log_info(f"Image embedding disabled in config for {source_filename}")
    
    # Sort by filename for consistent ordering as requested
    all_images.sort(key=lambda x: x[2]['source_file'])
    
    log_info(f"Total images collected for sample: {len(all_images)}")
    return all_images

def resize_image_to_excel(img_data: bytes, config: dict) -> bytes:
    """Resize image for Excel embedding with configurable width and aspect preservation."""
    try:
        with PILImage.open(io.BytesIO(img_data)) as img:
            # Use max width for better display, but constrained by min
            target_width = min(
                config['images']['max_width_columns'] * 60,  # ~480px max
                max(img.width, config['images']['min_width_columns'] * 60)  # ~240px min
            )
            
            if config['images']['preserve_aspect_ratio']:
                aspect_ratio = img.height / img.width
                target_height = int(target_width * aspect_ratio)
                resized = img.resize((target_width, target_height), PILImage.Resampling.LANCZOS)
            else:
                # Fixed size without aspect preservation
                target_height = int(target_width * 0.75)  # 4:3 ratio
                resized = img.resize((target_width, target_height), PILImage.Resampling.LANCZOS)
            
            # Convert back to bytes
            output = io.BytesIO()
            resized.save(output, format='PNG', optimize=True)
            return output.getvalue()
    except Exception:
        return img_data  # Return original if resize fails

def calculate_image_layout(num_images: int, config: dict) -> Tuple[int, int]:
    """Calculate optimal side-by-side layout for images."""
    if num_images == 0:
        return 0, 0
    
    # Try to fit images side-by-side within reasonable width
    max_cols = 6  # Maximum 6 images side-by-side
    cols = min(num_images, max_cols)
    rows = (num_images + cols - 1) // cols  # Ceiling division
    
    return cols, rows

def embed_images_side_by_side(ws, images: List[Tuple[str, bytes]], 
                          start_row: int, config: dict, tmpdir: str):
    """
    Embed images side-by-side in Excel worksheet using provided temporary directory.
    
    Args:
        ws: openpyxl worksheet object
        images: List of (filename, image_bytes) tuples
        start_row: Starting row in Excel sheet
        config: Configuration dict with image settings
        tmpdir: Path to temporary directory (must exist)
    """
    if not images or not config['images']['embed_images']:
        log_info("No images to embed or embedding disabled")
        return
    
    # Allow all images from AZTEC reports
    # No longer limiting images to allow comprehensive selection
        
    cols, rows = calculate_image_layout(len(images), config)
    if cols == 0 or rows == 0:
        log_warning("Invalid image layout calculated, skipping image embedding")
        return
    
    # Calculate cell positions for side-by-side layout
    img_width = config['images']['max_width_columns'] * 60
    
    # Use provided temporary directory
    try:
        # Grid positioning: each image spans multiple columns/rows
        for i, (img_name, img_data) in enumerate(images):
            try:
                row_offset = (i // cols) * 8  # 8 rows per image row
                col_offset = (i % cols) * 4  # 4 columns per image
                
                # Resize and embed
                resized_img_data = resize_image_to_excel(img_data, config)
                
                # Create temp file with safe name
                temp_img_path = os.path.join(tmpdir, f"img_{i}_{img_name}")
                
                try:
                    with open(temp_img_path, 'wb') as f:
                        f.write(resized_img_data)
                    
                    # Verify file was written
                    if not os.path.exists(temp_img_path):
                        log_error(f"Failed to create temp file: {temp_img_path}")
                        continue
                    
                    # Load image with openpyxl
                    try:
                        img = OpenpyxlImage(temp_img_path)
                        img.width = img_width
                        if config['images']['preserve_aspect_ratio']:
                            # Only set width, let height scale with aspect ratio
                            pass
                        
                        cell_ref = f"{get_column_letter(1 + col_offset)}{start_row + row_offset}"
                        ws.add_image(img, cell_ref)
                        
                        # Add image label below each image
                        label_row = start_row + row_offset + 6
                        ws.cell(row=label_row, column=1 + col_offset, value=f"Image {i+1}")
                        
                        log_info(f"Successfully embedded image {i+1} at {cell_ref}")
                        
                    except Exception as e:
                        log_error(f"openpyxl failed to load image {i+1} ({img_name}): {e}", exc_info=True)
                        continue
                        
                except IOError as e:
                    log_error(f"Failed to write temp image file {i+1}: {e}", exc_info=True)
                    continue
                    
            except Exception as e:
                log_error(f"Failed to process image {i+1} ({img_name}): {e}", exc_info=True)
                continue
        
        log_info(f"Finished embedding {len(images)} images")
        
    except Exception as e:
        log_error(f"Failed during image embedding: {e}", exc_info=True)
        raise  # Re-raise to handle in caller


def normalize_composition(comp_data: List[List[float]],
                        min_total: float = MIN_NORMALIZATION_TOTAL,
                        handle_negative: bool = HANDLE_NEGATIVE_VALUES,
                        log_warnings: bool = True) -> List[List[float]]:
    """
    Normalize composition data to sum to 100% for each spectrum.

    Args:
        comp_data: List of composition vectors [ [el1%, el2%, el3%, ...], ... ]
        min_total: Minimum total sum to consider valid (avoid division by very small numbers)
        handle_negative: If True, set negative values to 0 before normalization
        log_warnings: If True, log warnings for unusual compositions

    Returns:
        List of normalized composition vectors summing to 100%
    """
    normalized = []

    for idx, spectrum in enumerate(comp_data):
        # Convert to numpy array for easier manipulation
        arr = np.array(spectrum, dtype=float)

        # Handle negative values if requested
        if handle_negative:
            has_negative = np.any(arr < 0)
            if has_negative and log_warnings:
                log_warning(f"Spectrum {idx + 1}: Negative values detected and set to 0")
            arr = np.where(arr < 0, 0, arr)

        total = np.sum(arr)

        # Log warning for unusual totals
        if log_warnings and (total < NORMALIZATION_WARNING_LOW or total > NORMALIZATION_WARNING_HIGH):
            if total > min_total:
                log_normalization_warning(idx + 1, total, arr.tolist())

        # Handle edge cases
        if total <= min_total:
            # If total is too small or zero, create equal distribution
            # or keep as zeros if that's more appropriate
            if total == 0:
                if log_warnings:
                    log_warning(f"Spectrum {idx + 1}: Zero composition sum, setting all to 0")
                normalized.append([0.0] * len(arr))
            else:
                # For very small totals, scale proportionally but warn
                if log_warnings:
                    log_warning(f"Spectrum {idx + 1}: Very small total ({total:.4f}), normalizing cautiously")
                normalized_arr = arr * (100.0 / total) if total > 0 else arr
                normalized.append(normalized_arr.tolist())
        else:
            # Normal case: scale to 100%
            normalized_arr = arr * (100.0 / total)
            normalized.append(normalized_arr.tolist())

    return normalized


def weight_to_atomic_percent(comp_data: List[List[float]], elements: List[str]) -> List[List[float]]:
    """
    Convert weight percent to atomic percent using molar weights from ELEMENTS.

    Formula: at%_i = (wt%_i / AW_i) / Σ(wt%_j / AW_j) × 100

    Args:
        comp_data: List of composition vectors in weight percent
        elements: List of element symbols corresponding to each column

    Returns:
        List of composition vectors converted to atomic percent
    """
    converted = []
    for idx, spectrum in enumerate(comp_data):
        arr = np.array(spectrum, dtype=float)
        atomic_fractions = []
        for i, el in enumerate(elements):
            if el in ELEMENTS:
                aw = ELEMENTS[el]["weight"]
                atomic_fractions.append(arr[i] / aw if i < len(arr) else 0.0)
            else:
                atomic_fractions.append(0.0)
        total = sum(atomic_fractions)
        if total > 0:
            atomic_percent = [(frac / total) * 100.0 for frac in atomic_fractions]
        else:
            atomic_percent = [0.0] * len(arr)
        converted.append(atomic_percent)
    return converted


## Checks the table type, whether INCA or AZTEC basic report type was used and returns None if no
# file type fits
def table_type(file_path):
    doc = docx2python(file_path)
    try:
        for idx, body_element in enumerate(doc.body):
            if not hasattr(body_element, '__getitem__') or len(body_element) == 0:
                continue
            try:
                if body_element[0][0][0] == 'Spectrum':
                    print("Table in INCA format")
                    return 'INCA'
                elif body_element[0][0][0] == 'Result Type':
                    print("Table in Lyra format")
                    return 'AZTEC'
            except (IndexError, TypeError):
                continue
        print('Extraction not possible, the file format is not in default INCA or AZTEC report format')
        return None
    except Exception as e:
        print(f"Extraction not possible, the file format is not in default INCA or AZTEC report format: {e}")
        return None





## Extracts table from the files according to the report type, returns None in case of unknown file
# format. Contains magic numbers specific for each of the file types this program is meant for, If it keeps Failing 
# on one of those individual checks of the report structure viewed by python is needed
def find_table_indices(doc, t_type):
    if t_type == 'INCA':
        table_idx = None
        atomic_idx = None
        for idx, body_element in enumerate(doc.body):
            if not hasattr(body_element, '__getitem__') or len(body_element) == 0:
                continue
            try:
                if body_element[0][0][0] == 'Spectrum':
                    table_idx = idx
                elif body_element[0][0][2] == 'All results in atomic%':
                    atomic_idx = idx
                if table_idx is not None and atomic_idx is not None:
                    break
            except (IndexError, TypeError):
                continue
        return table_idx, atomic_idx
    elif t_type == 'AZTEC':
        table_idx = None
        atomic_idx = None
        for idx, body_element in enumerate(doc.body):
            if not hasattr(body_element, '__getitem__') or len(body_element) == 0:
                continue
            try:
                if body_element[0][0][0] == 'Result Type' or body_element[0][0][0] == 'Result Type':
                    atomic_idx = idx
                elif body_element[0][0][0] == 'Spectrum Label' or body_element[0][0][0] == 'Label':
                    table_idx = idx
                if table_idx is not None and atomic_idx is not None:
                    break
            except (IndexError, TypeError):
                continue
        return table_idx, atomic_idx
    return None, None

def extract_table(file_path):
    t_type = table_type(file_path)
    if not t_type:
        return None
    doc = docx2python(file_path)
    table_idx, atomic_idx = find_table_indices(doc, t_type)
    
    if t_type == 'INCA':
        if table_idx is None or atomic_idx is None:
            log_error(f"INCA: Could not find table or atomic% row in document")
            return None

        table = doc.body[table_idx]

        comp_data = []
        elem = []
        spectrum_info = []
        spectrum_counter = 1

        pct_type = str(doc.body[atomic_idx][0][0][2]).strip()
        if 'atomic' in pct_type.lower():
            at = True
            is_weight = False
        elif 'weight' in pct_type.lower() or 'wt%' in pct_type.lower():
            at = False
            is_weight = True
        else:
            at = False
            is_weight = False

        for row in table:
            if str(row[0])[2:-2] == 'Spectrum':
                elem = [str(cell)[2:-2] for cell in row[2:-2]]
            if str(row[1])[2:-2] == 'Yes':
                try:
                    data = [float(str(cell)[2:-2]) for cell in row[2:-2]]
                    comp_data.append(data)
                    spectrum_info.append(f"INCA-{spectrum_counter}")
                    spectrum_counter += 1
                except (ValueError, IndexError) as e:
                    log_warning(f"INCA table: Failed to parse row data: {e}")
                    continue
        
        # Validate that spectrum_info matches comp_data
        if len(spectrum_info) != len(comp_data):
            log_error(f"INCA: spectrum_info length ({len(spectrum_info)}) != comp_data length ({len(comp_data)})")
        
        # Filter elements to only valid element symbols from ELEMENTS dictionary
        if elem:
            valid_elem = [e for e in elem if e.strip() and e in ELEMENTS]
            filtered_out = set(elem) - set(valid_elem)
            if filtered_out:
                log_warning(f"INCA: Filtered non-element entries: {filtered_out}")
            elem = valid_elem
        
        # Handle elements - if more than 3, ask user which to keep
        if elem and len(elem) > 3:
            selected_elem = select_elements_gui(elem)
        else:
            # Sort elements alphabetically for consistent ordering
            selected_elem = sorted(elem[:3]) if elem else []
        
        # Reorder composition data to match sorted element order
        if selected_elem and elem and len(selected_elem) > 0:
            original_elem = elem[:len(selected_elem)]
            if original_elem != selected_elem:
                # Find mapping from original order to sorted order
                try:
                    reorder_indices = [original_elem.index(e) for e in selected_elem]
                    comp_data = [[row[i] for i in reorder_indices] for row in comp_data]
                except (ValueError, IndexError) as e:
                    log_warning(f"INCA: Failed to reorder composition data: {e}")
        
        elem = selected_elem

        # Convert weight% to atomic% if needed
        if is_weight and elem:
            comp_data = weight_to_atomic_percent(comp_data, elem)
            at = True
            log_info(f"INCA: Converted weight% to atomic% for elements {elem}")
        
        # Normalize composition data to 100%
        comp_data_normalized = normalize_composition(comp_data, log_warnings=True)
        
        return comp_data, comp_data_normalized, elem, at, spectrum_info
    elif t_type == 'AZTEC':
        if table_idx is None or atomic_idx is None:
            log_error(f"AZTEC: Could not find table or atomic% row in document")
            return None

        comp_data = []
        elem = []

        pct_label = str(doc.body[atomic_idx][0][1][0]).strip()
        if 'atomic' in pct_label.lower():
            at = True
            is_weight = False
        elif 'weight' in pct_label.lower() or 'wt%' in pct_label.lower():
            at = False
            is_weight = True
        else:
            at = False
            is_weight = False

        table = doc.body[table_idx]

        # Extract spectrum labels from the first row (header row), skipping "Spectrum Label"
        spectrum_labels_raw = [str(cell)[2:-2] for cell in table[0][1:]]  # Skip first cell "Spectrum Label"

        # Clean spectrum labels and extract actual spectrum numbers
        spectrum_info = []
        for label in spectrum_labels_raw:
            label = label.strip()
            if label:
                # Extract spectrum number from label like "Spectrum 32" -> "AZTEC-32"
                import re
                match = re.search(r'Spectrum\s+(\d+)', label, re.IGNORECASE)
                if match:
                    spec_num = match.group(1)
                    spectrum_info.append(f"AZTEC-{spec_num}")
                else:
                    # If no spectrum number pattern, use the label as-is or create fallback
                    spectrum_info.append(label if label else f"AZTEC-{len(spectrum_info)+1}")
            else:
                # Empty label, use fallback
                spectrum_info.append(f"AZTEC-{len(spectrum_info)+1}")

        # Extract element labels from the first column (skip header row)
        elem_all = [str(r[0])[2:-2] for r in table[1:]]  # Skip "Spectrum Label" row
        
        # Filter elements to only valid element symbols from ELEMENTS dictionary
        if elem_all:
            valid_elem_all = [e for e in elem_all if e.strip() and e in ELEMENTS]
            filtered_out = set(elem_all) - set(valid_elem_all)
            if filtered_out:
                log_warning(f"AZTEC: Filtered non-element entries: {filtered_out}")
            elem_all = valid_elem_all
        
        # If more than 3 elements, ask user which to keep
        if len(elem_all) > 3:
            selected_elem = select_elements_gui(elem_all)
        else:
            # Sort elements alphabetically for consistent ordering
            selected_elem = sorted(elem_all[:3]) if elem_all else []

        # Get the indices of selected elements in original order for data extraction
        if selected_elem:
            # Find which columns in the original table correspond to our selected elements
            elem_indices = []
            for e in selected_elem:
                try:
                    idx = elem_all.index(e)
                    elem_indices.append(idx)
                except ValueError:
                    log_warning(f"AZTEC: Element {e} not found in original list")
        else:
            elem_indices = []

        num_spectra = len(spectrum_info)
        num_elements = len(selected_elem)

        # Data is transposed - need to read column-wise
        comp_data = []
        for s in range(num_spectra):
            spectrum_values = []
            for e_idx in elem_indices:
                # table[e_idx+1][s+1] - element row, spectrum column
                raw = str(table[e_idx+1][s+1])[2:-2].strip()
                if raw == "":
                    val = 0.0
                else:
                    try:
                        val = float(raw)
                    except ValueError:
                        log_warning(f"AZTEC: Invalid value '{raw}' in spectrum {spectrum_info[s]}, using 0.0")
                        val = 0.0
                spectrum_values.append(val)
            comp_data.append(spectrum_values)
        
        elem = selected_elem

        # Convert weight% to atomic% if needed
        if is_weight and elem:
            comp_data = weight_to_atomic_percent(comp_data, elem)
            at = True
            log_info(f"AZTEC: Converted weight% to atomic% for elements {elem}")

        # Normalize composition data to 100% for AZTEC as well
        config = get_config()
        should_normalize = config['normalization']['enabled'] and config['normalization']['apply_to_both_types']
        comp_data_normalized = normalize_composition(comp_data, log_warnings=True) if should_normalize else comp_data
        
        return comp_data, comp_data_normalized, elem, at, spectrum_info

## Does exactly what the function is called
def remove_empty_sheets(wb):
    """Remove empty sheets in a workbook."""
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        if ws.max_row == 1 and ws.max_column == 1 and ws["A1"].value is None:
            wb.remove(ws)

## Writes sheet in the SEM_results .xlsx file containing specific sample data, for the exact structure run the code 
# and check, it uses columns for each clustered phase and overall measurements. The standart deviation is broadened by 
# Student coefficients to better incorporate the number of measurements. In the sheet there is no formula added so in case 
# of adding measurements manually you need to change the mean and standart deviation calculation along with the Student
# coefficients used, they are not needed and erasing them will result in the error to lower at most by 30 % when there 
# were originally only three measurements. For better explanation find the definition of student coefficients and for 
# list of student coefficients for 68 % of probability for standart deviation go to file student.csv
def write_sample_sheet(xlsx_path: str, sample_name: str, sample_full_name: str,
                       elements: List[str], overall: List[List[float]],
                       measurements: List[List[float]], cluster_labels: List[int],
                       spectrum_info: List[str] = [], 
                       sample_images: List[Tuple[str, bytes]] = [],
                       cluster_phase_names: Optional[List[str]] = None):
    t_values = []  # list to store all 't' values

    if cluster_phase_names is None:
        cluster_phase_names = []

    try:
        with open(STUDENT_COEFF_FILE, newline='') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=',')
            for row in reader:
                t_values.append(row['t'])
    except FileNotFoundError:
        log_error(f"Student coefficient file '{STUDENT_COEFF_FILE}' not found. Using default t=1.0")
        t_values = ['1.0'] * (STUDENT_COEFF_MAX_INDEX + 1)


    p = Path(xlsx_path)
    if p.exists():
        try:
            # Test if file is a valid zip
            with zipfile.ZipFile(p, 'r') as test_zip:
                test_zip.testzip()
            wb = load_workbook(p)
        except (zipfile.BadZipFile, KeyError) as e:
            print(f"Corrupted Excel file {p}, creating new workbook: {e}")
            p.unlink()  # Remove corrupted file
            wb = Workbook()
    else:
        wb = Workbook()
    remove_empty_sheets(wb)

    # Ensure sheet for this sample exists
    if sample_name in wb.sheetnames:
        ws = wb[sample_name]
    else:
        ws = wb.create_sheet(title=sample_name)

    # Clear old data
    for row in ws.iter_rows():
        for cell in row:
            cell.value = None

    # Write full name in A1
    ws.cell(row=1, column=1, value=sample_full_name)

    # Starting coordinates
    start_col = 3
    start_row = 3

    bold_font = Font(bold=True)

    def round2(x):
        return round(x, 2) if x is not None else None

    def write_block(title: str, values_list: List[List[float]], spectrum_list: List[str] = [], phase_name: Optional[str] = None):
        """Write one labeled block of data (overall, cluster, outliers)."""
        nonlocal start_col

        # Use phase name as title if provided (for cluster blocks), otherwise use title
        block_title = phase_name if phase_name else title
        ws.cell(row=start_row, column=start_col, value=block_title)

        # Header row (elements)
        for j, el in enumerate(elements):
            ws.cell(row=start_row + 1, column=start_col + j, value=el)

        # Data rows with spectrum info in first column, composition in subsequent columns
        for i, vals in enumerate(values_list):
            # Write spectrum info in first column of data block
            if spectrum_list and i < len(spectrum_list):
                ws.cell(row=start_row + 2 + i, column=start_col-1, value=spectrum_list[i])
            
            # Write composition data starting from second column
            for j, v in enumerate(vals):
                ws.cell(row=start_row + 2 + i, column=start_col + j, value=round2(v))

        if values_list:
            # Column means

            if len(values_list) <= STUDENT_COEFF_MAX_INDEX:
                t_value = t_values[len(values_list)]
            else:
                t_value = '1.0'  # For large samples, Student coefficient approaches 1

            col_means = [mean([vals[j] for vals in values_list if vals[j] is not None]) for j in range(len(elements))]
            # Column std devs (handle len < 2)
            col_stds = [
                stdev([vals[j] for vals in values_list if vals[j] is not None]) if len(values_list) > 1 else 0
                for j in range(len(elements))
            ]

            mean_row = start_row + 2 + len(values_list)
            std_row = mean_row + 1

            ws.cell(row=mean_row, column=start_col - 1, value="mean")
            ws.cell(row=std_row, column=start_col - 1, value="Broadened dev")


            for j, m in enumerate(col_means):
                cell = ws.cell(row=mean_row, column=start_col + j, value=round2(m))
                cell.font = bold_font
            for j, s in enumerate(col_stds):
                ws.cell(row=std_row, column=start_col + j, value=round2(s*float(t_value)))

        # Move start_col for next block (skip two columns)
        start_col += len(elements) + 2

    # Validate spectrum_info length - should already be correct from extraction
    if spectrum_info and len(spectrum_info) != len(measurements):
        log_error(
            f"Spectrum info count ({len(spectrum_info)}) doesn't match measurements count ({len(measurements)}). "
            f"This indicates a bug in extract_table()."
        )
        # Pad with generic labels as last resort
        if len(spectrum_info) < len(measurements):
            spectrum_info.extend([f"Unknown-{i}" for i in range(len(spectrum_info) + 1, len(measurements) + 1)])
        else:
            spectrum_info = spectrum_info[:len(measurements)]

    # --- Overall block ---
    if overall:
        write_block("overall", overall)

    # --- Clusters (always reserve 3 sections) ---
    existing_labels = sorted(set([lbl for lbl in cluster_labels if lbl != -1]))
    for lbl in range(3):  # always 3 clusters (0,1,2)
        if lbl in existing_labels:
            cluster_values = [m for m, l in zip(measurements, cluster_labels) if l == lbl]
            cluster_spectra = [s for s, l in zip(spectrum_info, cluster_labels) if l == lbl] if spectrum_info else []
            phase_name = cluster_phase_names[lbl] if cluster_phase_names and lbl < len(cluster_phase_names) else None
            title = f"cluster {lbl}"
            write_block(title, cluster_values, cluster_spectra, phase_name)
        else:
            phase_name = cluster_phase_names[lbl] if cluster_phase_names and lbl < len(cluster_phase_names) else None
            title = f"cluster {lbl}"
            write_block(title, [], [], phase_name)

    # --- Outliers (if any) ---
    outliers = [m for m, l in zip(measurements, cluster_labels) if l == -1]
    if outliers:
        outlier_spectra = [s for s, l in zip(spectrum_info, cluster_labels) if l == -1] if spectrum_info else []
        write_block("outliers", outliers, outlier_spectra)

    # Adjust column widths for data area
    for i in range(1, start_col + 2):
        ws.column_dimensions[get_column_letter(i)].width = 14

    remove_empty_sheets(wb)
    
    # Save workbook - with or without images
    # Critical: If images present, save INSIDE temp context to keep files alive
    if sample_images:
        config = get_config()
        image_start_row = start_row + len(elements) + 15  # After all data blocks
        ws.cell(row=image_start_row, column=1, value="SEM Images")
        
        # Create temporary directory that stays alive until save completes
        with tempfile.TemporaryDirectory(prefix='sem_images_') as tmpdir:
            log_info(f"Embedding {len(sample_images)} images using temp directory: {tmpdir}")
            
            # Adjust column widths for image area
            for col in range(1, 25):  # Up to 25 columns for side-by-side images
                ws.column_dimensions[get_column_letter(col)].width = 15
            
            # Embed images using the temp directory
            embed_images_side_by_side(ws, sample_images, image_start_row + 2, config, tmpdir)
            
            # Save INSIDE context - temp files still exist and openpyxl can read them
            log_info(f"Saving workbook with {len(sample_images)} embedded images")
            wb.save(p)
            log_info(f"Workbook saved successfully, temp directory will now be cleaned up")
    else:
        # No images, save normally
        log_info(f"Saving workbook without images")
        wb.save(p)


def create_phase_table(sem_results_path: str, phase_table_path: str, elements: List[str]) -> bool:
    """
    Create phase table from SEM_results xlsx file.
    
    Args:
        sem_results_path: Path to SEM_results_{system}_{temp}.xlsx
        phase_table_path: Path to output phase_table_{system}_{temp}.xlsx
        elements: List of element names in order (e.g., ['Ge', 'Sb', 'Zn'])
    
    Returns:
        True if successful, False otherwise
    """
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Alignment
    import pandas as pd
    
    try:
        if not Path(sem_results_path).exists():
            log_warning(f"SEM_results file not found: {sem_results_path}")
            return False
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        
        # Column mapping (0-based index):
        # 0 = T_No/Annealing time (A)
        # 1-3 = Overall composition (B-D)
        # 4 = Phase (E)
        # 5-7 = Phase composition (F-H)
        # 8 = Note (I)
        
        # Write header row 1 with merged cells
        ws.merge_cells('A1:A2')
        ws.merge_cells('B1:D1')
        ws.merge_cells('E1:E2')
        ws.merge_cells('F1:H1')
        ws.merge_cells('I1:I2')
        
        ws['A1'] = "T_No/Annealing time"
        ws['B1'] = "Overall composition [at. %]"
        ws['E1'] = "Phase"
        ws['F1'] = "Phase composition [at. %]"
        ws['I1'] = "Note"
        
        # Center align merged headers
        for cell in ['A1', 'B1', 'E1', 'F1', 'I1']:
            ws[cell].alignment = Alignment(horizontal='center', vertical='center')
        
        # Write header row 2 (element names)
        # A2 is empty (T_No column)
        ws['B2'] = elements[0] if len(elements) > 0 else ""
        ws['C2'] = elements[1] if len(elements) > 1 else ""
        ws['D2'] = elements[2] if len(elements) > 2 else ""
        # E2 is empty (Phase column)
        ws['F2'] = elements[0] if len(elements) > 0 else ""
        ws['G2'] = elements[1] if len(elements) > 1 else ""
        ws['H2'] = elements[2] if len(elements) > 2 else ""
        # I2 is empty (Note column)
        
        # Read SEM_results
        all_sheets = pd.read_excel(sem_results_path, sheet_name=None, header=None)
        
        current_row = 3
        
        for sheet_name in all_sheets.keys():
            df = pd.read_excel(sem_results_path, sheet_name=sheet_name, header=None)
            csvfile = df.astype(str).fillna("").values.tolist()
            
            # Sample name from sheet (e.g., "1", "2")
            sample_t_no = sheet_name
            
            # Find blocks and extract data
            overall_comp = [None, None, None]
            cluster_data = []
            
            # Find the start column for each block by scanning for block titles
            block_cols = {}
            
            for i, row in enumerate(csvfile):
                for j, cell in enumerate(row):
                    cell_str = str(cell).strip() if cell else ""
                    if cell_str.lower() == "overall":
                        block_cols['overall'] = j
                    elif cell_str.startswith("cluster ") or (cell_str and cell_str not in ["mean", "std", "std%"]):
                        # Check if it's a cluster block title
                        parts = cell_str.split()
                        if len(parts) >= 2 and parts[0] == "cluster" and parts[1].isdigit():
                            block_cols[f"cluster_{parts[1]}"] = j
            
            # Now extract data for each block
            for i, row in enumerate(csvfile):
                for j, cell in enumerate(row):
                    cell_str = str(cell).strip().lower() if cell else ""
                    
                    if cell_str == "mean":
                        # Check which block this belongs to
                        for block_name, start_col in block_cols.items():
                            if j == start_col + 1:  # mean is in the element column
                                try:
                                    if block_name == "overall":
                                        # Get composition from columns after "mean"
                                        for k in range(len(elements)):
                                            val_col = start_col + 2 + k  # Skip "mean" and first element column
                                            if val_col < len(row):
                                                val = row[val_col]
                                                if val and val.strip():
                                                    try:
                                                        overall_comp[k] = round(float(val), 2)
                                                    except ValueError:
                                                        pass
                                    else:
                                        # Cluster block
                                        cluster_id = block_name.split("_")[1]
                                        comp = []
                                        for k in range(len(elements)):
                                            val_col = start_col + 2 + k
                                            if val_col < len(row):
                                                val = row[val_col]
                                                if val and val.strip():
                                                    try:
                                                        comp.append(round(float(val), 2))
                                                    except ValueError:
                                                        comp.append(None)
                                                else:
                                                    comp.append(None)
                                            else:
                                                comp.append(None)
                                        
                                        if comp and any(c is not None for c in comp):
                                            # Get phase name from block title row
                                            phase_name = None
                                            title_row_idx = None
                                            for r_idx, r in enumerate(csvfile):
                                                if r and start_col < len(r):
                                                    cell_val = str(r[start_col]).strip() if r[start_col] else ""
                                                    if cell_val.startswith("cluster "):
                                                        title_row_idx = r_idx
                                                        break
                                            
                                            if title_row_idx is not None and title_row_idx < len(csvfile):
                                                title = str(csvfile[title_row_idx][start_col]).strip() if csvfile[title_row_idx][start_col] else ""
                                                # Check if title is a phase name (not "cluster X")
                                                if title and not title.startswith("cluster "):
                                                    phase_name = title
                                            
                                            cluster_data.append({
                                                'cluster_id': cluster_id,
                                                'phase_name': phase_name,
                                                'composition': comp
                                            })
                                except (ValueError, IndexError) as e:
                                    log_warning(f"Error parsing {block_name} in sheet {sheet_name}: {e}")
            
            # Write data rows
            if cluster_data:
                # Write overall composition (first row only)
                ws.cell(row=current_row, column=1, value=sample_t_no)
                ws.cell(row=current_row, column=2, value=overall_comp[0])
                ws.cell(row=current_row, column=3, value=overall_comp[1])
                ws.cell(row=current_row, column=4, value=overall_comp[2])
                
                first_cluster = cluster_data[0]
                phase_name = first_cluster.get('phase_name') or 'NA'
                ws.cell(row=current_row, column=5, value=phase_name)
                comp = first_cluster.get('composition', [])
                ws.cell(row=current_row, column=6, value=comp[0] if len(comp) > 0 else None)
                ws.cell(row=current_row, column=7, value=comp[1] if len(comp) > 1 else None)
                ws.cell(row=current_row, column=8, value=comp[2] if len(comp) > 2 else None)
                
                current_row += 1
                
                # Write remaining clusters (no sample name, no overall)
                for cluster in cluster_data[1:]:
                    # Leave sample name and overall empty for subsequent rows
                    ws.cell(row=current_row, column=1, value="")
                    ws.cell(row=current_row, column=2, value="")
                    ws.cell(row=current_row, column=3, value="")
                    ws.cell(row=current_row, column=4, value="")
                    
                    phase_name = cluster.get('phase_name') or 'NA'
                    ws.cell(row=current_row, column=5, value=phase_name)
                    comp = cluster.get('composition', [])
                    ws.cell(row=current_row, column=6, value=comp[0] if len(comp) > 0 else None)
                    ws.cell(row=current_row, column=7, value=comp[1] if len(comp) > 1 else None)
                    ws.cell(row=current_row, column=8, value=comp[2] if len(comp) > 2 else None)
                    
                    current_row += 1
            else:
                log_warning(f"No cluster data found in sheet {sheet_name}")
        
        # Adjust column widths
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 12
        ws.column_dimensions['G'].width = 12
        ws.column_dimensions['H'].width = 12
        ws.column_dimensions['I'].width = 12
        
        # Save workbook
        wb.save(phase_table_path)
        log_info(f"Phase table created: {phase_table_path}")
        return True
        
    except Exception as e:
        log_error(f"Failed to create phase table: {e}", exc_info=True)
        return False


def update_sample_cluster_phases(xlsx_path: str, sample_name: str, phases: List[str]) -> bool:
    """
    Update cluster phase names in existing SEM_results sheet.
    
    Args:
        xlsx_path: Path to SEM_results_{system}_{temp}.xlsx
        sample_name: Sample identifier (e.g., "1", "2")
        phases: List of phase names for clusters [phase1, phase2, phase3]
    
    Returns:
        True if successful
    """
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    
    try:
        if not Path(xlsx_path).exists():
            log_warning(f"SEM_results file not found: {xlsx_path}")
            return False
        
        wb = load_workbook(xlsx_path)
        
        if sample_name not in wb.sheetnames:
            log_warning(f"Sheet for sample {sample_name} not found")
            return False
        
        ws = wb[sample_name]
        
        start_col = 3
        start_row = 3
        
        for cluster_idx in range(3):
            block_title_cell = ws.cell(row=start_row, column=start_col + cluster_idx * 5)
            phase_name = phases[cluster_idx] if cluster_idx < len(phases) else "NA"
            block_title_cell.value = phase_name
        
        wb.save(xlsx_path)
        log_info(f"Updated cluster phases for sample {sample_name}: {phases}")
        return True
        
    except Exception as e:
        log_error(f"Failed to update cluster phases for sample {sample_name}: {e}")
        return False
