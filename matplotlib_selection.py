#!/usr/bin/env python3
"""
Simplified matplotlib-based sequential image selection interface.
Displays images one-by-one with navigation and individual selection per report.
"""

import matplotlib.pyplot as plt
from matplotlib.widgets import Button
from PIL import Image as PILImage
import io
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from logging_config import log_info, log_error


def sequential_single_image_selector(images_data: List[Tuple[str, bytes, dict]], report_name: str) -> Optional[Tuple[str, bytes]]:
    """
    Display images from a single report one-by-one with immediate selection on click.
    
    Args:
        images_data: List of (img_name, img_data, metadata) tuples
        report_name: Name of the report being processed
    
    Returns:
        Selected image (img_name, img_data) tuple or None if skipped
    """
    if not images_data:
        return None
    
    # Auto-select if only one image
    if len(images_data) == 1:
        img_name, img_data, metadata = images_data[0]
        return (img_name, img_data)
    
    # Create figure - smaller window size
    fig = plt.figure(figsize=(8, 7))
    
    try:
        if hasattr(fig.canvas, 'manager') and fig.canvas.manager is not None:
            fig.canvas.manager.set_window_title(f'Select Image from {report_name}')
    except:
        pass  # Handle gracefully if no canvas manager
    
    # Store selection state - use class-like structure to avoid scoping issues
    class State:
        def __init__(self):
            self.selected_idx: Optional[int] = None
            self.current_idx: int = 0  # Always start at first image
            self.action: Optional[str] = None
    
    state = State()
    
    # Convert images to numpy arrays for display
    image_arrays = []
    for img_name, img_data, metadata in images_data:
        try:
            with PILImage.open(io.BytesIO(img_data)) as img:
                # Convert to RGB for matplotlib compatibility
                if img.mode in ('RGBA', 'LA', 'P', 'L'):
                    if img.mode == 'RGBA':
                        background = PILImage.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    else:
                        img = img.convert('RGB')
                
                img_array = np.array(img)
                if img_array.dtype != np.uint8:
                    img_array = np.clip(img_array, 0, 255).astype(np.uint8)
                
                image_arrays.append(img_array)
                
        except Exception as e:
            log_error(f"Failed to process image {img_name}: {e}")
            return None
    
    if len(image_arrays) != len(images_data):
        log_error("Failed to process some images")
        return None
    
    # Simple interactive loop
    while True:
        # Clear and recreate plot
        plt.clf()
        
        # Display current image
        img_name, img_data, metadata = images_data[state.current_idx]
        
        # Main image subplot - leave more space for buttons
        ax = plt.subplot(1, 1, 1)
        ax.imshow(image_arrays[state.current_idx])
        ax.axis('off')
        
        # Add title with metadata
        title = f"{metadata['source_file']}\n{metadata['dimensions']}"
        ax.set_title(title, fontsize=10, pad=3)
        
        # Main selection button with better spacing
        select_ax = plt.axes((0.3, 0.15, 0.4, 0.06))
        select_btn = Button(select_ax, 'SELECT THIS IMAGE', color='lightblue')
        
        # Navigation buttons at bottom with increased spacing
        nav_y = 0.05
        button_width = 0.18
        button_height = 0.04
        
        # Previous button (left)
        prev_ax = plt.axes((0.1, nav_y, button_width, button_height))
        prev_btn = Button(prev_ax, '← Previous', 
                         color='lightgray' if state.current_idx == 0 else 'white')
        
        # Skip button (center)
        skip_ax = plt.axes((0.41, nav_y, button_width, button_height))
        skip_btn = Button(skip_ax, 'Skip', color='lightcoral')
        
        # Button handlers using the state object
        def on_select(event):
            state.action = 'select'
            state.selected_idx = state.current_idx
            plt.close(fig)
        
        def on_skip(event):
            state.action = 'skip'
            plt.close(fig)
        
        def on_next(event):
            state.action = 'next'
            if state.current_idx < len(image_arrays) - 1:
                state.current_idx += 1
            plt.close(fig)
        
        def on_previous(event):
            state.action = 'prev'
            if state.current_idx > 0:
                state.current_idx -= 1
            plt.close(fig)
        
        # Connect handlers
        select_btn.on_clicked(on_select)
        skip_btn.on_clicked(on_skip)
        prev_btn.on_clicked(on_previous)
        
        # Add next button if not at last image
        if state.current_idx < len(image_arrays) - 1:
            next_ax = plt.axes((0.72, nav_y, button_width, button_height))
            next_btn = Button(next_ax, 'Next →', color='white')
            next_btn.on_clicked(on_next)
        
        # Image counter and report name - positioned with better spacing
        counter_text = f"Image {state.current_idx + 1} of {len(image_arrays)}"
        
        # Add text elements with improved spacing
        plt.figtext(0.5, 0.25, counter_text, ha='center', fontsize=14, weight='bold')
        plt.figtext(0.5, 0.22, f'Report: {report_name}', ha='center', fontsize=10, style='italic')
        
        # Instructions
        plt.figtext(0.5, 0.01, '• SELECT to choose image • SKIP to see next • Use ← → to navigate', 
                   ha='center', fontsize=8, va='top')
        
        # Adjust spacing for improved layout - more space at bottom
        plt.subplots_adjust(bottom=0.25)
        
        # Show blocking until user decides
        plt.show(block=True)
        
        # Handle button actions after window closes
        if state.action == 'select':
            # Immediate selection - return selected image
            img_name, img_data, metadata = images_data[state.selected_idx]
            log_info(f"Selected image {state.selected_idx + 1} from {report_name}: {img_name}")
            return (img_name, img_data)
        
        elif state.action == 'next':
            state.action = None
            continue  # Show next image
        
        elif state.action == 'prev':
            state.action = None
            continue  # Show previous image
        
        elif state.action == 'skip':
            # Smart skip: next image or skip report if at last image
            if state.current_idx < len(image_arrays) - 1:
                state.current_idx += 1
                state.action = None
                continue  # Show next image
            else:
                log_info(f"Skipped report {report_name} (at last image)")
                return None  # Skip entire report
        
        else:
            # Window was closed without action
            log_info(f"Image selection cancelled for {report_name}")
            return None


def sequential_image_selection(reports_data: List[Tuple[str, List[Tuple[str, bytes, dict]]]]) -> List[Tuple[str, bytes]]:
    """
    Process each report sequentially with matplotlib one-by-one selection.
    Each report gets its own selection window and the current report process ends when user makes a decision.
    
    Args:
        reports_data: List of (report_name, images_data) tuples
    
    Returns:
        List of selected (img_name, img_data) tuples from all reports
    """
    selected_images = []
    
    for report_name, images_data in reports_data:
        selected_image = sequential_single_image_selector(images_data, report_name)
        
        if selected_image:
            selected_images.append(selected_image)
    
    log_info(f"Total images selected from {len(reports_data)} reports: {len(selected_images)}")
    return selected_images