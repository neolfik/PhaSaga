"""
Phase Reassociation Module for re-running phase association on existing data.

Handles:
- Loading existing phase associations from phase_table
- Phase file editing (add/remove phases)
- Phase reassociation with preselected phases
"""

import os
import re
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set
from openpyxl import load_workbook
import numpy as np

from constants import PHASE_TABLE_PATTERN, PHASE_FILE_PATTERN
from logging_config import log_info, log_warning, log_error
from phases import parse_phase_formula, is_range_formula, normalize, normalize_range_compositions
from phase_manager import (
    get_phase_file_path,
    validate_phase_name,
    compute_phase_composition,
    get_range_phase_endpoints,
    is_phase_range,
    get_master_phases_path,
    load_master_phases,
    get_phases_for_system_from_master
)
from xrd_assignment import (
    select_system_gui,
    load_phase_table_data,
    load_xrd_info,
    save_phase_associations_to_table,
    get_all_analyzed_systems
)


def extract_sample_number(sample_name: str) -> int:
    """Extract numeric part from sample name for sorting."""
    match = re.search(r'(\d+)$', str(sample_name))
    if match:
        return int(match.group(1))
    return 0


def compute_cluster_means(data: List[Dict], sample_name: str) -> List[Tuple[int, List[float], int]]:
    """
    Compute mean composition for each cluster in a sample.
    
    Args:
        data: Phase table data rows
        sample_name: Sample identifier
        
    Returns:
        List of (cluster_idx, mean_composition, num_points)
    """
    sample_data = [row for row in data if row.get('sample') == sample_name]
    
    cluster_data = {}
    for row in sample_data:
        phase_comp = row.get('phase_comp', [])
        if len(phase_comp) >= 3 and all(c is not None for c in phase_comp):
            cluster_idx = len(cluster_data)
            if cluster_idx not in cluster_data:
                cluster_data[cluster_idx] = []
            cluster_data[cluster_idx].append([float(c) for c in phase_comp[:3]])
    
    result = []
    for cluster_idx in sorted(cluster_data.keys()):
        points = cluster_data[cluster_idx]
        if points:
            mean_comp = [sum(p[i] for p in points) / len(points) for i in range(3)]
            result.append((cluster_idx, mean_comp, len(points)))
    
    return result


def get_current_phases(data: List[Dict], sample_name: str) -> List[str]:
    """
    Get current phase associations for a sample.
    
    Args:
        data: Phase table data rows
        sample_name: Sample identifier
        
    Returns:
        List of phase names (may have 'NA' entries)
    """
    sample_data = [row for row in data if row.get('sample') == sample_name]
    phases = []
    for row in sample_data:
        phase = row.get('phase', 'NA')
        if phase and phase != 'NA':
            phases.append(phase)
    return phases


def get_phases_from_file(system_name: str, base_path: str) -> List[str]:
    """
    Get phases from system phase file.
    
    Args:
        system_name: System name
        base_path: Base directory path
        
    Returns:
        List of phase names from file
    """
    phase_file = get_phase_file_path(system_name, base_path)
    
    if not phase_file.exists():
        return []
    
    try:
        with open(phase_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        log_error(f"Failed to read phase file {phase_file}: {e}")
        return []


def save_phases_to_file(system_name: str, base_path: str, phases: List[str]) -> bool:
    """
    Save phases to system phase file.
    
    Args:
        system_name: System name
        base_path: Base directory path
        phases: List of phase names
        
    Returns:
        True if successful
    """
    phase_file = get_phase_file_path(system_name, base_path)
    
    try:
        phase_file.parent.mkdir(parents=True, exist_ok=True)
        with open(phase_file, 'w', encoding='utf-8') as f:
            for phase in phases:
                f.write(f"{phase}\n")
        log_info(f"Saved {len(phases)} phases to {phase_file}")
        return True
    except Exception as e:
        log_error(f"Failed to save phase file {phase_file}: {e}")
        return False


def load_phases_data(
    system_name: str,
    system_elements: List[str],
    base_path: str
) -> List[Tuple[str, np.ndarray]]:
    """
    Load phases data with compositions for a system.
    
    Args:
        system_name: System name
        system_elements: List of system elements
        base_path: Base directory path
        
    Returns:
        List of (phase_name, composition_array) tuples
    """
    phases_data = []
    
    phase_file = get_phase_file_path(system_name, base_path)
    
    if not phase_file.exists():
        log_warning(f"Phase file not found: {phase_file}")
        return []
    
    try:
        with open(phase_file, 'r', encoding='utf-8') as f:
            phase_lines = [line.strip() for line in f if line.strip()]
        
        for phase_name in phase_lines:
            is_valid, _ = validate_phase_name(phase_name, system_elements)
            if not is_valid:
                log_warning(f"Phase '{phase_name}' validation failed, including anyway")
            
            if is_phase_range(phase_name):
                endpoints = get_range_phase_endpoints(phase_name, system_elements)
                composition = compute_phase_composition(phase_name, system_elements)
                if composition is not None and endpoints is not None:
                    phases_data.append((phase_name, composition, endpoints))
                else:
                    log_warning(f"Could not compute composition/endpoints for '{phase_name}'")
            else:
                composition = compute_phase_composition(phase_name, system_elements)
                if composition is not None:
                    phases_data.append((phase_name, composition))
                else:
                    log_warning(f"Could not compute composition for '{phase_name}'")
        
        log_info(f"Loaded {len(phases_data)} phases for {system_name}")
        
    except Exception as e:
        log_error(f"Failed to load phases from {phase_file}: {e}")
    
    return phases_data


def show_reassociation_dialog(
    sample_name: str,
    cluster_means: List[Tuple[int, List[float], int]],
    available_phases: List[str],
    current_phases: List[str],
    elements: List[str]
) -> Optional[List[str]]:
    """
    Show dialog for reassociating phases for a sample.
    
    Args:
        sample_name: Sample identifier
        cluster_means: List of (cluster_idx, mean_composition, num_points)
        available_phases: List of available phase names
        current_phases: Current phase assignments
        elements: Element names
        
    Returns:
        Updated phase list or None if cancelled
    """
    root = tk.Tk()
    root.title(f"Reassociate Phases - Sample {sample_name}")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.7)
    window_height = int(screen_height * 0.6)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    result = {"value": None}
    
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text=f"Sample: {sample_name}", font=("Arial", 14, "bold")).pack(pady=(0, 10))
    
    info_frame = ttk.Frame(main_frame)
    info_frame.pack(fill=tk.BOTH, expand=True, pady=10)
    
    columns = ("Cluster", "Points", elements[0], elements[1], elements[2], "Phase")
    tree = ttk.Treeview(info_frame, columns=columns, show="headings", height=8)
    
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=100)
    
    tree.column("Phase", width=150)
    
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar = ttk.Scrollbar(info_frame, orient=tk.VERTICAL, command=tree.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=scrollbar.set)
    
    phase_vars = []
    for cluster_idx, mean_comp, num_points in cluster_means:
        phase_idx = cluster_idx if cluster_idx < len(current_phases) else 0
        current_phase = current_phases[phase_idx] if phase_idx < len(current_phases) else "NA"
        
        var = tk.StringVar(value=current_phase)
        phase_vars.append(var)
        
        values = [
            str(cluster_idx + 1),
            str(num_points),
            f"{mean_comp[0]:.2f}",
            f"{mean_comp[1]:.2f}",
            f"{mean_comp[2]:.2f}",
            current_phase
        ]
        tree.insert("", tk.END, values=values)
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=15)
    
    def on_confirm():
        result["value"] = [var.get() for var in phase_vars]
        root.destroy()
    
    def on_cancel():
        root.destroy()
    
    ttk.Button(button_frame, text="Confirm", command=on_confirm, width=15).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Cancel", command=on_cancel, width=15).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    return result["value"]


def edit_phases_gui(
    system_name: str,
    system_elements: List[str],
    base_path: str
) -> Optional[List[str]]:
    """
    Show GUI to edit phases for a system.
    
    Args:
        system_name: System name
        system_elements: List of system elements
        base_path: Base directory path
        
    Returns:
        Updated list of phases or None if cancelled
    """
    current_phases = get_phases_from_file(system_name, base_path)
    
    master_dict = load_master_phases(base_path)
    master_phases = get_phases_for_system_from_master(system_elements, master_dict)
    
    available_phases = sorted(set(master_phases) - set(current_phases))
    
    root = tk.Tk()
    root.title(f"Edit Phases: {system_name}")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.7)
    window_height = int(screen_height * 0.7)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    result_phases = tk.Variable(value=current_phases.copy())
    
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text=f"Edit Phases: {system_name} ({', '.join(system_elements)})", 
              font=("Arial", 14, "bold")).pack(pady=(0, 10))
    ttk.Label(main_frame, text="Current phases (click to remove):", 
              font=("Arial", 11)).pack(pady=(0, 5))
    
    current_frame = ttk.Frame(main_frame)
    current_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    
    scrollbar = ttk.Scrollbar(current_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    current_listbox = tk.Listbox(current_frame, font=("Arial", 11), 
                                  yscrollcommand=scrollbar.set, height=10)
    current_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=current_listbox.yview)
    
    for phase in current_phases:
        current_listbox.insert(tk.END, phase)
    
    current_buttons = ttk.Frame(main_frame)
    current_buttons.pack(pady=5)
    
    def remove_selected():
        selection = current_listbox.curselection()
        if selection:
            idx = selection[0]
            phases_list = result_phases.get()
            phases_list.pop(idx)
            result_phases.set(phases_list)
            current_listbox.delete(idx)
    
    ttk.Button(current_buttons, text="Remove Selected", command=remove_selected).pack(side=tk.LEFT, padx=5)
    
    ttk.Label(main_frame, text="Available phases from master list (click to add):", 
              font=("Arial", 11)).pack(pady=(10, 5))
    
    available_frame = ttk.Frame(main_frame)
    available_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    
    scrollbar2 = ttk.Scrollbar(available_frame)
    scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)
    
    available_listbox = tk.Listbox(available_frame, font=("Arial", 11), 
                                    yscrollcommand=scrollbar2.set, height=10)
    available_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar2.config(command=available_listbox.yview)
    
    for phase in available_phases:
        available_listbox.insert(tk.END, phase)
    
    available_buttons = ttk.Frame(main_frame)
    available_buttons.pack(pady=5)
    
    def add_selected():
        selection = available_listbox.curselection()
        if selection:
            phases_list = result_phases.get()
            for idx in reversed(selection):
                phase = available_phases[idx]
                if phase not in phases_list:
                    phases_list.append(phase)
            phases_list.sort()
            result_phases.set(phases_list)
            current_listbox.delete(0, tk.END)
            for phase in phases_list:
                current_listbox.insert(tk.END, phase)
    
    def add_custom():
        dialog = tk.Toplevel(root)
        dialog.title("Add Custom Phase")
        dialog.geometry("400x100")
        dialog.transient(root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Phase name:").pack(pady=10)
        entry = ttk.Entry(dialog, width=40)
        entry.pack(pady=5)
        
        def on_add():
            phase = entry.get().strip()
            if phase:
                is_valid, error = validate_phase_name(phase, system_elements)
                if is_valid:
                    phases_list = result_phases.get()
                    if phase not in phases_list:
                        phases_list.append(phase)
                        phases_list.sort()
                        result_phases.set(phases_list)
                        current_listbox.delete(0, tk.END)
                        for p in phases_list:
                            current_listbox.insert(tk.END, p)
                    dialog.destroy()
                else:
                    messagebox.showerror("Invalid Phase", error, parent=dialog)
        
        ttk.Button(dialog, text="Add", command=on_add).pack(pady=5)
        entry.focus()
    
    ttk.Button(available_buttons, text="Add Selected", command=add_selected).pack(side=tk.LEFT, padx=5)
    ttk.Button(available_buttons, text="Add Custom...", command=add_custom).pack(side=tk.LEFT, padx=5)
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=15)
    
    def on_confirm():
        root.quit()
        root.destroy()
    
    def on_cancel():
        result_phases.set(None)
        root.quit()
        root.destroy()
    
    ttk.Button(button_frame, text="Confirm", command=on_confirm, width=15).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Cancel", command=on_cancel, width=15).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    phases = result_phases.get()
    if phases is None:
        return None
    
    return list(phases)


def edit_phase_association_gui(
    data: List[Dict],
    phases_data: List[Tuple[str, np.ndarray]],
    system_elements: List[str]
) -> Dict[str, List[str]]:
    """
    Show GUI for editing phase associations with preselected phases.
    
    Args:
        data: Phase table data with sample, phase, etc.
        phases_data: Available phases data
        system_elements: List of system elements
        
    Returns:
        Dict mapping sample_id -> [phase_1, phase_2, phase_3]
    """
    unique_samples = list(dict.fromkeys(d['sample'] for d in data))
    
    phase_names = [p[0] for p in phases_data]
    
    sample_phases = {}
    for row in data:
        sample = row['sample']
        phase = row.get('phase', 'NA')
        if sample not in sample_phases:
            sample_phases[sample] = []
        if phase and phase != 'NA':
            sample_phases[sample].append(phase)
    
    root = tk.Tk()
    root.title("Phase Reassociation")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.8)
    window_height = int(screen_height * 0.8)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    current_phases = tk.Variable()
    current_phases.set({})
    
    main_canvas = tk.Canvas(root)
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=main_canvas.yview)
    scrollable_frame = ttk.Frame(main_canvas)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
    )
    
    main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    main_canvas.configure(yscrollcommand=scrollbar.set)
    
    main_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    ttk.Label(scrollable_frame, text="Phase Reassociation", 
              font=("Arial", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=(15, 5))
    
    ttk.Label(scrollable_frame, text="Select phase for each sample's clusters", 
              font=("Arial", 11)).grid(row=1, column=0, columnspan=2, pady=(0, 15))
    
    phase_vars = {}
    phase_labels = {}
    
    for i, sample in enumerate(unique_samples):
        row_idx = 2 + i * 3
        
        sample_frame = ttk.LabelFrame(scrollable_frame, text=f"Sample: {sample}", padding="10")
        sample_frame.grid(row=row_idx, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        
        sample_phases_list = sample_phases.get(sample, [])
        
        phase_vars[sample] = []
        phase_labels[sample] = []
        
        sample_data = [d for d in data if d['sample'] == sample]
        num_clusters = len(sample_data)
        
        for cluster_idx in range(min(num_clusters, 3)):
            cluster_frame = ttk.Frame(sample_frame)
            cluster_frame.grid(row=cluster_idx, column=0, columnspan=2, pady=2)
            
            ttk.Label(cluster_frame, text=f"Cluster {cluster_idx + 1}:").grid(row=0, column=0, padx=5)
            
            var = tk.StringVar(value=sample_phases_list[cluster_idx] if cluster_idx < len(sample_phases_list) else "NA")
            phase_vars[sample].append(var)
            
            combo = ttk.Combobox(cluster_frame, textvariable=var, values=["NA"] + sorted(phase_names), 
                                width=20, state="readonly")
            combo.grid(row=0, column=1, padx=5)
            
            label = ttk.Label(cluster_frame, text=f"Current: {var.get()}", font=("Arial", 9))
            label.grid(row=0, column=2, padx=5)
            phase_labels[sample].append(label)
            
            def update_label(s=sample, c=cluster_idx):
                phase_labels[s][c].config(text=f"Current: {phase_vars[s][c].get()}")
            
            combo.bind('<<ComboboxSelected>>', lambda e, s=sample, c=cluster_idx: update_label(s, c))
    
    button_frame = ttk.Frame(scrollable_frame)
    button_frame.grid(row=1000, column=0, columnspan=2, pady=20)
    
    result = {}
    
    def on_confirm():
        nonlocal result
        for sample in unique_samples:
            result[sample] = [var.get() for var in phase_vars[sample]]
        root.destroy()
    
    def on_cancel():
        nonlocal result
        result = {}
        root.destroy()
    
    ttk.Button(button_frame, text="Confirm", command=on_confirm, width=15).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Cancel", command=on_cancel, width=15).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    return result


def show_sample_list_gui(
    data: List[Dict],
    phases_data: List[Tuple[str, np.ndarray]],
    system_elements: List[str],
    system_name: str,
    temp: str,
    phase_table_path: Path
) -> Dict[str, List[str]]:
    """
    Show GUI with list of samples and Reassociate buttons.
    
    Args:
        data: Phase table data
        phases_data: Available phases data
        system_elements: List of system elements
        system_name: System name
        temp: Temperature
        phase_table_path: Path to phase_table
        
    Returns:
        Dict mapping sample_id -> updated phase list (only for reassociated samples)
    """
    unique_samples = sorted(list(dict.fromkeys(d['sample'] for d in data)), key=extract_sample_number)
    phase_names = [p[0] for p in phases_data]
    
    sample_phases = {}
    for row in data:
        sample = row['sample']
        phase = row.get('phase', 'NA')
        if sample not in sample_phases:
            sample_phases[sample] = []
        if phase and phase != 'NA':
            sample_phases[sample].append(phase)
    
    root = tk.Tk()
    root.title(f"Phase Reassociation - {system_name}/{temp}")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.8)
    window_height = int(screen_height * 0.8)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    updated_samples = {}
    
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text=f"Phase Reassociation: {system_name} / {temp}", 
              font=("Arial", 16, "bold")).pack(pady=(0, 10))
    ttk.Label(main_frame, text="Click 'Reassociate' to change phase assignments for a sample", 
              font=("Arial", 10)).pack(pady=(0, 15))
    
    list_frame = ttk.Frame(main_frame)
    list_frame.pack(fill=tk.BOTH, expand=True)
    
    columns = ("Sample", "Current Phases")
    tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=20)
    
    tree.heading("Sample", text="Sample")
    tree.heading("Current Phases", text="Current Phases")
    tree.column("Sample", width=100)
    tree.column("Current Phases", width=300)
    
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=scrollbar.set)
    
    for sample in unique_samples:
        phases = sample_phases.get(sample, [])
        phase_str = ", ".join(phases) if phases else "None"
        tree.insert("", tk.END, values=(sample, phase_str), tags=("sample",))
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=15)
    
    def on_reassociate():
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a sample to reassociate")
            return
        
        item = tree.item(selection[0])
        sample = item['values'][0]
        
        cluster_means = compute_cluster_means(data, sample)
        current = sample_phases.get(sample, ["NA", "NA", "NA"])
        
        result_phases = show_reassociation_dialog(
            sample, cluster_means, phase_names, current, system_elements
        )
        
        if result_phases is not None:
            updated_samples[sample] = result_phases
            phase_str = ", ".join(result_phases)
            tree.item(selection[0], values=(sample, phase_str))
            log_info(f"Updated phases for sample {sample}: {result_phases}")
    
    def on_confirm():
        root.destroy()
    
    def on_cancel():
        nonlocal updated_samples
        updated_samples = {}
        root.destroy()
    
    ttk.Button(button_frame, text="Reassociate", command=on_reassociate, width=15).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Confirm", command=on_confirm, width=15).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Cancel", command=on_cancel, width=15).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    return updated_samples


def run_phase_reassociation(base_path: str) -> bool:
    """
    Main function to run phase reassociation workflow.
    
    Args:
        base_path: Base directory path
        
    Returns:
        True if completed successfully, False if cancelled or error
    """
    selection = select_system_gui(base_path, "Phase Reassociation - Select System", multi_select=False)
    
    if selection is None:
        return False
    
    if len(selection) != 1:
        log_warning("Please select exactly one system for phase reassociation")
        return False
    
    system, temp, phase_table_path = selection[0]
    
    data, xrd_samples, phase_notes = load_phase_table_data(phase_table_path)
    
    if not data:
        log_warning(f"No data found in phase table: {phase_table_path}")
        return False
    
    system_elements = sorted(list(set(
        e for row in data 
        for e in row.get('overall', []) 
        if e is not None and isinstance(e, (int, float))
    )))
    
    if len(system_elements) < 3:
        system_dir = phase_table_path.parent.parent
        phase_file = system_dir / f"phases_{system}.txt"
        if phase_file.exists():
            try:
                with open(phase_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not is_phase_range(line):
                            try:
                                parsed, _ = parse_phase_formula(line)
                                system_elements = sorted(list(parsed.keys()))
                                if len(system_elements) == 3:
                                    break
                            except:
                                continue
            except:
                pass
    
    if not system_elements:
        system_elements = [chr(65 + i) for i in range(3)]
    
    system_elements = sorted(system_elements)
    
    if messagebox.askyesno(
        "Edit Phases",
        f"Do you want to edit the phases for system {system}?\n\n"
        "Click 'Yes' to add/remove phases, or 'No' to use existing phases."
    ):
        new_phases = edit_phases_gui(system, system_elements, base_path)
        
        if new_phases is None:
            return False
        
        if save_phases_to_file(system, base_path, new_phases):
            log_info(f"Updated phases for system {system}")
    
    phases_data = load_phases_data(system, system_elements, base_path)
    
    if not phases_data:
        log_warning("No phases available for reassociation")
        return False
    
    updated_samples = show_sample_list_gui(
        data, phases_data, system_elements, system, temp, phase_table_path
    )
    
    if not updated_samples:
        log_info("No samples were reassociated")
        return True
    
    save_phase_associations_to_table(phase_table_path, updated_samples, xrd_samples, phase_notes)
    
    system_dir = phase_table_path.parent
    sem_results_path = system_dir / f"SEM_results_{system}_{temp}.xlsx"
    predic_exp_path = system_dir / f"{system}_{temp}_phase_predic.exp"
    report_dat_path = system_dir / f"REPORT_{system}_{temp}.dat"
    
    try:
        from tables import update_sample_cluster_phases
        for sample, phases in updated_samples.items():
            if sem_results_path.exists():
                update_sample_cluster_phases(str(sem_results_path), sample, phases)
                log_info(f"Updated SEM_results for sample {sample}")
    except Exception as e:
        log_error(f"Failed to update SEM_results: {e}")
    
    try:
        from to_exp import update_predic_exp_for_samples
        if predic_exp_path.exists():
            phase_name_composition = {}
            for phase_data in phases_data:
                if len(phase_data) >= 2:
                    phase_name, composition = phase_data[:2]
                    phase_name_composition[phase_name] = composition
            update_predic_exp_for_samples(
                str(predic_exp_path),
                updated_samples,
                phase_name_composition,
                system_elements
            )
            log_info("Updated phase_predic.exp file")
    except Exception as e:
        log_error(f"Failed to update phase_predic.exp: {e}")
    
    try:
        from reports import update_report_dat_phases
        if report_dat_path.exists():
            update_report_dat_phases(str(report_dat_path), updated_samples)
            log_info("Updated REPORT.dat file")
    except Exception as e:
        log_error(f"Failed to update REPORT.dat: {e}")
    
    log_info(f"Phase reassociation complete for {system}/{temp}")
    log_info(f"Updated {len(updated_samples)} sample(s)")
    
    return True
