#!/usr/bin/env python3
"""
Tkinter-based sequential image selection interface.
Displays images one-by-one with navigation and individual selection per report.
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image as PILImage
import io
import numpy as np
from typing import List, Tuple, Optional
from logging_config import log_info


class TkinterImageSelector:
    def __init__(self, images_data: List[Tuple[str, bytes, dict]], report_name: str):
        self.images_data = images_data
        self.report_name = report_name
        self.current_idx = 0
        self.result = None
        self.selected_idx = None
        self.image_tk = None
        
        self.root = tk.Tk()
        self.root.title(f"Select Image from {report_name}")
        
        # Fit window to screen without being fullscreen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = int(screen_width * 0.9)
        window_height = int(screen_height * 0.9)
        self.root.geometry(f"{window_width}x{window_height}")
        
        self._create_widgets()
        self._load_image(0)
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        title_label = ttk.Label(main_frame, text=f"Report: {self.report_name}", font=("Arial", 12, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 5))
        
        self.image_label = ttk.Label(main_frame, text="", anchor="center")
        self.image_label.grid(row=1, column=0, columnspan=3, pady=5)
        
        self.info_label = ttk.Label(main_frame, text="", font=("Arial", 10))
        self.info_label.grid(row=2, column=0, columnspan=3, pady=5)
        
        self.counter_label = ttk.Label(main_frame, text="", font=("Arial", 11, "bold"))
        self.counter_label.grid(row=3, column=0, columnspan=3, pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=15)
        
        select_btn = ttk.Button(button_frame, text="SELECT THIS IMAGE", command=self._on_select)
        select_btn.grid(row=0, column=0, padx=5)
        
        skip_btn = ttk.Button(button_frame, text="Skip", command=self._on_skip)
        skip_btn.grid(row=0, column=1, padx=5)
        
        nav_frame = ttk.Frame(main_frame)
        nav_frame.grid(row=5, column=0, columnspan=3, pady=10)
        
        self.prev_btn = ttk.Button(nav_frame, text="← Previous", command=self._on_previous, state="disabled")
        self.prev_btn.grid(row=0, column=0, padx=5)
        
        self.next_btn = ttk.Button(nav_frame, text="Next →", command=self._on_next)
        self.next_btn.grid(row=0, column=1, padx=5)
        
        instruction_label = ttk.Label(main_frame, text="• SELECT to choose image • SKIP to see next", 
                                     font=("Arial", 8), foreground="gray")
        instruction_label.grid(row=6, column=0, columnspan=3, pady=(10, 0))
    
    def _load_image(self, idx: int):
        img_name, img_data, metadata = self.images_data[idx]
        
        with PILImage.open(io.BytesIO(img_data)) as img:
            if img.mode in ('RGBA', 'LA', 'P', 'L'):
                if img.mode == 'RGBA':
                    background = PILImage.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert('RGB')
            
            display_width = 750
            display_height = 500
            img.thumbnail((display_width, display_height), PILImage.LANCZOS)
            
            self.image_tk = PILImageTk.PhotoImage(img)
        
        self.image_label.configure(image=self.image_tk)
        
        dimensions = metadata.get('dimensions', 'Unknown')
        self.info_label.configure(text=f"{img_name} - {dimensions}")
        
        total = len(self.images_data)
        self.counter_label.configure(text=f"Image {idx + 1} of {total}")
        
        self.prev_btn.config(state="normal" if idx > 0 else "disabled")
        self.next_btn.config(state="normal" if idx < total - 1 else "disabled")
    
    def _on_select(self):
        self.selected_idx = self.current_idx
        self.result = self.images_data[self.current_idx][:2]
        self.root.destroy()
    
    def _on_skip(self):
        if self.current_idx < len(self.images_data) - 1:
            self.current_idx += 1
            self._load_image(self.current_idx)
        else:
            self.result = None
            self.root.destroy()
    
    def _on_previous(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self._load_image(self.current_idx)
    
    def _on_next(self):
        if self.current_idx < len(self.images_data) - 1:
            self.current_idx += 1
            self._load_image(self.current_idx)
    
    def _on_close(self):
        self.result = None
        self.root.destroy()
    
    def get_result(self) -> Optional[Tuple[str, bytes]]:
        return self.result


def sequential_single_image_selector(images_data: List[Tuple[str, bytes, dict]], report_name: str) -> Optional[Tuple[str, bytes]]:
    """
    Display images from a single report one-by-one with navigation and selection.
    
    Args:
        images_data: List of (img_name, img_data, metadata) tuples
        report_name: Name of the report being processed
    
    Returns:
        Selected image (img_name, img_data) tuple or None if skipped
    """
    if not images_data:
        return None
    
    if len(images_data) == 1:
        img_name, img_data, metadata = images_data[0]
        return (img_name, img_data)
    
    selector = TkinterImageSelector(images_data, report_name)
    return selector.get_result()


def sequential_image_selection(reports_data: List[Tuple[str, List[Tuple[str, bytes, dict]]]]) -> List[Tuple[str, bytes]]:
    """
    Process each report sequentially with Tkinter one-by-one selection.
    
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


try:
    from PIL import ImageTk as PILImageTk
except ImportError:
    PILImageTk = None
    print("Warning: PIL.ImageTk not available. Image selection may not work properly.")
