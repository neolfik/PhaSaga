import shutil
import io
import csv
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union
from PIL import Image as PILImage
from elements import ELEMENTS
from structure import create_structure, get_sample_reports_path, get_diagrams_path
from tables import extract_table, write_sample_sheet, extract_aztec_images, get_config, confirm_image_for_embedding, table_type
from tkinter_selection import sequential_image_selection
from tkinter_clustering import show_clustering_phase_selection
from clustering import one_cluster
import numpy as np
import pandas as pd
from to_exp import create_exp_from_xlsx as c_exp
from openpyxl import load_workbook
import re
from constants import (
    SAMPLE_NAME_PARTS,
    MIN_SAMPLE_IDENTIFIER_LENGTH,
    TERNARY_DIAGRAM_PATTERN,
    ACCEPTABLE_IMAGE_SIZES,
    PHASE_DISTANCE_THRESHOLD
)
from logging_config import (
    log_info,
    log_warning,
    log_error,
    log_file_processed,
    log_file_skipped,
    setup_logging
)
from phase_manager import load_phases_for_system


def point_to_line_segment_distance(point: np.ndarray, line_start: np.ndarray, line_end: np.ndarray) -> float:
    """
    Calculate the minimum distance from a point to a line segment.
    
    Args:
        point: The point to measure distance from (3D composition vector)
        line_start: Start of the line segment (3D composition vector)
        line_end: End of the line segment (3D composition vector)
    
    Returns:
        Minimum distance from point to any point on the line segment
    """
    line_vec = line_end - line_start
    point_vec = point - line_start
    
    line_len = np.linalg.norm(line_vec)
    if line_len == 0:
        return np.linalg.norm(point - line_start)
    
    line_unitvec = line_vec / line_len
    proj_length = np.dot(point_vec, line_unitvec)
    
    proj_length = np.clip(proj_length, 0, line_len)
    
    nearest_point = line_start + proj_length * line_unitvec
    
    return np.linalg.norm(point - nearest_point)


def find_closest_phases(cluster_averages: List[np.ndarray], phases_data: List, 
                        threshold: float = PHASE_DISTANCE_THRESHOLD,
                        elements: Optional[List[str]] = None) -> List[Tuple[str, List[Tuple[str, float]]]]:
    """
    Find the closest 5 phases to each cluster average, including pure elements.
    Handles both regular phases and range phases (solid solution lines).
    
    Args:
        cluster_averages: List of cluster average positions (normalized compositions)
        phases_data: List of phase data tuples (can be 2 or 3 elements)
                     - 2 elements: (phase_name, composition_array) for regular phases
                     - 3 elements: (phase_name, composition_array, (endpoint1, endpoint2)) for range phases
        threshold: Maximum distance for a phase to be considered "in range"
        elements: List of element names for pure element compositions
    
    Returns:
        List of (cluster_idx, [(phase_name, distance), ...]) for each cluster,
        or empty list if no phases in range
    """
    all_candidates = []
    
    for phase_data in phases_data:
        if len(phase_data) >= 2:
            phase_name, composition = phase_data[:2]
            if len(phase_data) >= 3 and isinstance(phase_data[2], tuple):
                endpoints = phase_data[2]
                all_candidates.append((phase_name, None, True, endpoints))
            else:
                all_candidates.append((phase_name, composition, False, None))
    
    if elements:
        for i, elem in enumerate(elements):
            pure_comp = np.zeros(len(elements))
            pure_comp[i] = 1.0
            all_candidates.append((elem, pure_comp, False, None))
    
    results = []
    for cluster_idx, cluster_avg in enumerate(cluster_averages):
        if cluster_avg is None:
            results.append((cluster_idx, []))
            continue
            
        distances = []
        for phase_name, composition, is_range, endpoints in all_candidates:
            if is_range and endpoints is not None:
                endpoint1, endpoint2 = endpoints
                dist = point_to_line_segment_distance(cluster_avg, endpoint1, endpoint2)
            else:
                dist = np.linalg.norm(cluster_avg - composition)
            distances.append((phase_name, dist))
        
        distances.sort(key=lambda x: x[1])
        closest_5 = distances[:5]
        
        in_range = [(name, dist) for name, dist in closest_5 if dist <= threshold]
        
        if in_range:
            results.append((cluster_idx, in_range))
        else:
            results.append((cluster_idx, []))
    
    return results


from clustering_history import load_clustering_history, save_clustering_result

config = get_config()

setup_logging()


import tkinter as tk
from tkinter import ttk


def select_phases_for_clusters(cluster_averages: List[np.ndarray], phases_data: List[Tuple[str, np.ndarray]],
                               sample_name: str, elements: Optional[List[str]] = None) -> List[str]:
    """
    Show interactive Tkinter UI for user to select phase for each cluster.
    Shows all clusters in a single window with sections for each.
    
    Args:
        cluster_averages: List of cluster average positions (normalized compositions)
        phases_data: List of (phase_name, composition_array) tuples
        sample_name: Name of the sample for display
        elements: List of element names for pure element compositions
    
    Returns:
        List of chosen phase names (one per cluster), "NA" if no phases in range or skipped
    """
    if not phases_data or not cluster_averages:
        log_info(f"No phases data available for selection in {sample_name}")
        return ["NA"] * 3
    
    closest_phases = find_closest_phases(cluster_averages, phases_data, elements=elements)
    
    cluster_phase_names = ["NA"] * 3
    
    has_selectable = any(len(cps) > 0 for _, cps in closest_phases)
    
    if not has_selectable:
        log_info(f"No phases within {PHASE_DISTANCE_THRESHOLD} range for any cluster in {sample_name}")
        return cluster_phase_names
    
    root = tk.Tk()
    root.title(f"Phase Selection: {sample_name}")
    
    # Fit window to screen without being fullscreen
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.8)
    window_height = int(screen_height * 0.8)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    selections: List[Optional[str]] = [None, None, None]
    selection_labels: List[Optional[ttk.Label]] = [None, None, None]
    
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
    
    title_label = ttk.Label(scrollable_frame, text=f"Phase Selection: {sample_name}", 
                           font=("Arial", 16, "bold"))
    title_label.grid(row=0, column=0, columnspan=2, pady=(15, 20))
    
    instruction_label = ttk.Label(scrollable_frame, text="Select a phase for each cluster, then click Done", 
                                   font=("Arial", 11))
    instruction_label.grid(row=1, column=0, columnspan=2, pady=(0, 15))
    
    for cluster_idx in range(3):
        row_offset = cluster_idx * 4
        
        cluster_avg = cluster_averages[cluster_idx] if cluster_idx < len(cluster_averages) else None
        
        if cluster_avg is None:
            continue
        
        closest = next((cps for idx, cps in closest_phases if idx == cluster_idx), [])
        
        if not closest:
            continue
        
        cluster_frame = ttk.LabelFrame(scrollable_frame, text=f"Cluster {cluster_idx}", padding="15")
        cluster_frame.grid(row=2 + row_offset, column=0, columnspan=2, 
                         padx=15, pady=10, sticky="ew")
        
        comp_text = f"Composition: [{cluster_avg[0]:.3f}, {cluster_avg[1]:.3f}, {cluster_avg[2]:.3f}]"
        comp_label = ttk.Label(cluster_frame, text=comp_text, font=("Arial", 11))
        comp_label.grid(row=0, column=0, columnspan=2, pady=(0, 10))
        
        phase_frame = ttk.Frame(cluster_frame)
        phase_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        for i, (phase_name, dist) in enumerate(closest):
            btn_text = f"{phase_name}\n({dist:.3f})"
            
            btn = ttk.Button(phase_frame, text=btn_text, width=22,
                           command=lambda cn=cluster_idx, pn=phase_name: _on_phase_select(cn, pn))
            btn.grid(row=i // 2, column=i % 2, padx=8, pady=8)
        
        na_btn = ttk.Button(phase_frame, text="NA (Skip)", 
                          command=lambda cn=cluster_idx: _on_na_select(cn))
        na_btn.grid(row=2, column=0, columnspan=2, pady=(10, 5))
        
        selection_frame = ttk.Frame(cluster_frame)
        selection_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Label(selection_frame, text="Selected: ", font=("Arial", 10, "bold")).grid(
            row=0, column=0, padx=5)
        
        selection_labels[cluster_idx] = ttk.Label(selection_frame, text="None", 
                                                   font=("Arial", 10, "bold"), foreground="blue")
        selection_labels[cluster_idx].grid(row=0, column=1, padx=5)
    
    def _on_phase_select(cluster_idx, phase_name):
        selections[cluster_idx] = phase_name
        selection_labels[cluster_idx].config(text=phase_name, foreground="green")
        log_info(f"Cluster {cluster_idx}: Selected phase {phase_name}")
    
    def _on_na_select(cluster_idx):
        selections[cluster_idx] = "NA"
        selection_labels[cluster_idx].config(text="NA", foreground="red")
        log_info(f"Cluster {cluster_idx}: Selected NA")
    
    def _on_done():
        root.destroy()
    
    done_frame = ttk.Frame(scrollable_frame)
    done_frame.grid(row=100, column=0, columnspan=2, pady=20)
    
    done_btn = ttk.Button(done_frame, text="Done / Confirm Selection", command=_on_done, width=25)
    done_btn.grid(row=0, column=0, padx=10)
    
    root.mainloop()
    
    for i in range(3):
        if selections[i] is not None:
            cluster_phase_names[i] = selections[i]
        else:
            cluster_phase_names[i] = "NA"
            log_info(f"Cluster {i}: No selection made, using NA")
    
    return cluster_phase_names


## Checks system name with global variable ELEMENTS containing the elements shorts
def check_system_name(system: str):
    elements = re.findall(r"[A-Z][a-z]?", system)
    if not elements:
        return None
    if all(el in ELEMENTS for el in elements):
        return elements
    return None

## Checks report name and disassembles the name returning its parts, the checks are not complete
# and the leniency is quite big. It is assumed the report name is in shape El1El2El3_TEMP_Samp#measletter, where measurement
# letter a corresponds to overall composition
def check_report_name(report_name: str) -> Optional[Dict]:
    """
    Parse report filename and extract metadata.
    
    Expected format: <System>_<temp>_<sample>.docx where sample like '1a'.
    
    Args:
        report_name: Filename to parse
    
    Returns:
        Dictionary with parsed metadata or None if invalid
    """
    if not report_name.endswith(".docx"):
        return None
    parts = report_name[:-5].split("_", 2)
    if len(parts) != SAMPLE_NAME_PARTS:
        return None
    system, temp, sample = parts
    elems = check_system_name(system)
    if not elems:
        return None
    if not temp.isdigit() and temp != 'AC':
        return None
    if len(sample) < MIN_SAMPLE_IDENTIFIER_LENGTH or not sample[:-1].isdigit() or sample[-1] not in "abcdefghijklmnopqrstuvwxyz":
        return None
    try:
        temp_val = int(temp)
    except ValueError:
        temp_val = temp
    return {
        "elements": sorted(elems),
        "temp": temp_val,
        "sample_number": int(sample[:-1]),
        "sample_suffix": sample[-1]
    }


_EXPORT_ENTRY_PATTERN = re.compile(
    r'^([A-Z][a-z]?(?:[A-Z][a-z]?)*)_(\d+|AC)_(\d+)([a-z])'
)


def _read_phenom_csv(csv_path: str, elements: List[str]) -> List[List[float]]:
    """
    Read a PHENOM quantification CSV and extract atomic concentration for given elements.
    
    Expected CSV columns: Atomic number, Element symbol, Element name,
    Atomic concentration percentage, Weight concentration percentage, Energy level
    
    Args:
        csv_path: Path to the CSV file
        elements: List of element symbols to extract (sorted alphabetically)
    
    Returns:
        List containing one row of composition values in the same order as elements,
        or empty list on failure
    """
    try:
        df = pd.read_csv(csv_path)
        if 'Element symbol' not in df.columns or 'Atomic concentration percentage' not in df.columns:
            log_file_skipped(Path(csv_path).name, "missing required columns (Element symbol, Atomic concentration percentage)")
            return []

        filtered = df[df['Element symbol'].isin(elements)].copy()
        if filtered.empty:
            log_file_skipped(Path(csv_path).name, "no matching element symbols found")
            return []

        filtered = filtered.sort_values('Element symbol')
        found_symbols = filtered['Element symbol'].tolist()
        found_values = filtered['Atomic concentration percentage'].tolist()

        ordered = []
        for el in sorted(elements):
            if el in found_symbols:
                idx = found_symbols.index(el)
                ordered.append(found_values[idx])
            else:
                ordered.append(0.0)

        log_info(f"PHENOM CSV {Path(csv_path).name}: element order = {sorted(elements)}")
        return [ordered]

    except Exception as e:
        log_error(f"Failed to read PHENOM CSV {csv_path}: {e}")
        return []


def parse_export_folder(base_path: str) -> Dict[Tuple[str, Union[int, str], int], Dict]:
    """
    Parse the export folder for PHENOM CSV composition data.
    
    Looks for {base_path}/export/ directory. Inside it, scans for items
    (files or directories) whose names start with the pattern:
        {sys_name}_{temp}_{sample#}{site_id}
    
    For CSV files matching this pattern, reads them directly.
    For directories matching this pattern, looks for quantification.csv inside.
    
    Skips items that do not match the naming pattern (logs a skip message).
    
    Args:
        base_path: Path to the analyzed folder containing an export/ subfolder
    
    Returns:
        Dict mapping (sys_name, temp, sample_no) -> {
            'elements': sorted element list,
            'overall': list of composition vectors from site 'a' entries,
            'points': list of composition vectors from non-'a' entries,
            'site_dirs': list of (site_id, source_dir_path) for directory entries
        }
    """
    export_dir = Path(base_path) / "export"
    if not export_dir.is_dir():
        return {}

    log_info(f"Found PHENOM export folder: {export_dir}")
    export_data: Dict[Tuple[str, Union[int, str], int], Dict] = {}

    for entry in sorted(export_dir.iterdir()):
        name = entry.name
        match = _EXPORT_ENTRY_PATTERN.match(name)
        if not match:
            log_file_skipped(name, "does not match PHENOM naming pattern {sys}_{temp}_{sample#}{site}")
            continue

        sys_name, temp_str, sample_str, site = match.groups()
        temp_val: Union[int, str] = int(temp_str) if temp_str.isdigit() else temp_str
        sample_no = int(sample_str)

        system_elements = sorted(re.findall(r'[A-Z][a-z]?', sys_name))
        if not all(el in ELEMENTS for el in system_elements):
            log_file_skipped(name, f"invalid element symbols in system name '{sys_name}'")
            continue

        log_info(f"Export entry {name}: system elements order = {system_elements}")

        rows: List[List[float]] = []
        is_directory = entry.is_dir()
        if is_directory:
            csv_found = False
            for csv_file in entry.iterdir():
                if csv_file.suffix.lower() == '.csv':
                    rows = _read_phenom_csv(str(csv_file), system_elements)
                    csv_found = True
                    break
            if not csv_found:
                log_file_skipped(name, "no CSV files found in directory")
                continue
        elif entry.suffix.lower() == '.csv':
            rows = _read_phenom_csv(str(entry), system_elements)
        else:
            log_file_skipped(name, "not a directory or CSV file")
            continue

        if not rows:
            continue

        normalized = []
        for row in rows:
            total = sum(row)
            if total > 0:
                normalized.append([100.0 * v / total for v in row])

        key = (sys_name, temp_val, sample_no)
        if key not in export_data:
            export_data[key] = {'elements': system_elements, 'overall': [], 'points': [], 'site_dirs': []}

        if is_directory:
            export_data[key]['site_dirs'].append((site, str(entry)))

        if site == 'a':
            export_data[key]['overall'].extend(normalized)
        else:
            export_data[key]['points'].extend(normalized)

    log_info(f"Loaded {len(export_data)} sample groups from PHENOM export folder")
    return export_data


## takes in a report folder path and returns dict of disassembled report names used to generate the final structure
def group_reports(folder_path: str) -> Dict[Tuple[str, Union[int, str], int], List[Path]]:
    """
    Group report files by system, temperature, and sample number.
    
    Args:
        folder_path: Path to folder containing .docx reports
    
    Returns:
        Dictionary mapping (sys_name, temp, sample_no) to list of file paths
        Note: temp can be either int or str (e.g., "AC" for as-cast)
    """
    folder = Path(folder_path)
    groups = {}
    for p in folder.iterdir():
        if not p.is_file() or not p.name.endswith(".docx"):
            continue
        meta = check_report_name(p.name)
        if not meta:
            log_file_skipped(p.name, "invalid filename format")
            continue
        sys_name = "".join(meta["elements"])
        key = (sys_name, meta["temp"], meta["sample_number"])
        groups.setdefault(key, []).append(p)
    # Sort file lists by suffix letter (so 'a' goes first and also assumes 'a' contains overall measurement)
    for k, v in groups.items():
        groups[k] = sorted(v, key=lambda x: x.name[:-5].split('_', 2)[2][-1])
    return groups

def _reorder_sem_result_sheets(file_path: str):
    """
    Reorder sheets in an SEM_results workbook so numeric sample sheets
    appear in ascending order, followed by non-numeric sheets.

    Args:
        file_path: Path to the SEM_results xlsx file
    """
    try:
        wb = load_workbook(file_path)
        names = wb.sheetnames
        numeric = [(int(n), n) for n in names if n.isdigit()]
        others = [n for n in names if not n.isdigit()]
        numeric.sort(key=lambda x: x[0])
        ordered = [n for _, n in numeric] + others
        for i, name in enumerate(ordered):
            current = wb.sheetnames.index(name)
            if current != i:
                wb.move_sheet(name, offset=i - current)
        wb.save(file_path)
    except Exception as e:
        log_error(f"Failed to reorder sheets in {file_path}: {e}")


## Processes all reports according to grouping, moves them into respective system and temperature report folder and extracts data
# from an expected structure of reports and data in them, where 'a' contains overall data. Other measurements are clustered and 
# all extracted data is written into excel file, exp file is generated
def load_all_reports(folder_path: str):
    """
    Process all SEM reports in a folder, organizing them by system/temperature/sample.
    
    Args:
        folder_path: Path to folder containing .docx reports
    
    Returns:
        Tuple of (processed_list, structure_dict)
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        log_error(f"Provided path is not a folder: {folder_path}")
        return None, None

    groups = group_reports(folder_path)
    export_data = parse_export_folder(folder_path)
    structure = {}

    processed = []
    
    # Track current system/temp to generate .exp files when they change
    current_system_temp = None
    system_temp_sem_files = {}  # Track SEM files for each system/temp
    system_temp_phase_mappings = {}  # Track phase mappings per system/temp for prediction .exp
    
    sample_images_dict = {}  # Store images for each sample
    
    # Track phases and clustering history per system/temp
    system_temp_phases = {}  # Cache phases data per system
    system_temp_sorted_elements = {}  # Track sorted element order per system (for phases)
    system_temp_history = {}  # Cache clustering history per system/temp
    
    log_info(f"Processing {len(groups)} sample groups")
    
    # Sort groups by (sys_name, temp, sample_no) for consistent ordering
    # Convert temp to string for sorting to handle mixed int/str types
    sorted_groups = sorted(groups.items(), key=lambda x: (x[0][0], str(x[0][1]), x[0][2]))
    
    for (sys_name, temp, sample_no), files in sorted_groups:
        # Check if we need to create .exp file for previous system/temp
        if current_system_temp is not None and current_system_temp != (sys_name, temp):
            prev_sys, prev_temp = current_system_temp
            if (prev_sys, prev_temp) in system_temp_sem_files:
                prev_sem_file = system_temp_sem_files[(prev_sys, prev_temp)]
                prev_target_dir = Path(structure[prev_sys]["path"]) / str(prev_temp)
                prev_phases = system_temp_phases.get(prev_sys, [])
                prev_phase_mapping = system_temp_phase_mappings.get((prev_sys, prev_temp), {})
                prev_sorted_elements = system_temp_sorted_elements.get(prev_sys, [])
                prev_report_path = prev_target_dir / f"REPORT_{prev_sys}_{prev_temp}.dat"
                
                log_info(f"Creating .exp files for {prev_sys}/{prev_temp}")
                # Generate original .exp file
                c_exp(str(prev_sem_file), str(prev_target_dir), phases_data=prev_phases)
                
                # Generate prediction .exp file with phase substitutions
                from to_exp import create_exp_with_phase_prediction
                create_exp_with_phase_prediction(
                    str(prev_sem_file),
                    str(prev_target_dir),
                    phases_data=prev_phases,
                    cluster_phase_mapping=prev_phase_mapping,
                    elements_order=prev_sorted_elements,
                    report_path=str(prev_report_path)
                )
        
        # Update current system/temp tracker
        current_system_temp = (sys_name, temp)
        
        # Initialize phase mapping for this system/temp
        if current_system_temp not in system_temp_phase_mappings:
            system_temp_phase_mappings[current_system_temp] = {}
        
        # Load phases for this system (cached per system)
        if sys_name not in system_temp_phases:
            # Get system elements from the first file
            meta = check_report_name(files[0].name)
            if meta:
                system_elements = meta["elements"]  # This is sorted alphabetically
                system_temp_sorted_elements[sys_name] = system_elements
                phases_data = load_phases_for_system(sys_name, system_elements, folder_path, create_if_missing=True)
                system_temp_phases[sys_name] = phases_data
                if phases_data:
                    log_info(f"Loaded {len(phases_data)} phases for system {sys_name}")
            else:
                system_temp_phases[sys_name] = []
                system_temp_sorted_elements[sys_name] = []
        
        phases_data = system_temp_phases.get(sys_name, [])
        sorted_elements = system_temp_sorted_elements.get(sys_name, [])
        
        # Load clustering history for this system/temp (cached per system/temp)
        system_temp_key = (sys_name, temp)
        if system_temp_key not in system_temp_history:
            clustering_hist = load_clustering_history(sys_name, temp, folder_path)
            system_temp_history[system_temp_key] = clustering_hist
        else:
            clustering_hist = system_temp_history[system_temp_key]
        
        # ensure structure exists - now includes sample-specific folder
        structure = create_structure(folder_path, sys_name, temp, structure or {}, sample_number=sample_no)
        
        # Get sample-specific reports directory
        reports_dir = get_sample_reports_path(folder_path, sys_name, temp, sample_no)
        target_dir = Path(structure[sys_name]["path"]) / str(temp)
        
        # Get diagrams directory for ternary plots
        diagrams_dir = get_diagrams_path(folder_path, sys_name, temp)

        # write to SEM_results workbook sheet named with sample number
        sem_file = Path(structure[sys_name]["path"]) / str(temp) / f"SEM_results_{sys_name}_{temp}.xlsx"
        
        # Track SEM file for this system/temp
        system_temp_sem_files[(sys_name, temp)] = sem_file

        # files sorted by suffix; find 'a' file
        overall_data = None
        elements = None
        other_measurements = []
        spectrum_data = []
        sample_full_name = files[0].name[:-6] if files else f"sample_{sample_no}"
        # Display name for clustering screen (includes system and temp)
        clustering_sample_name = f"{sys_name}_{temp}_{sample_no}"
        
        # Initialize image list for this sample (accumulate from all files)
        if sample_full_name not in sample_images_dict:
            sample_images_dict[sample_full_name] = []

        # Collect all file data for processing (initialize outside try block for fallback access)
        sample_files_data = []
        for f in files:
            target = reports_dir / f.name
            
            # If already moved in previous run, use existing file
            if target.exists():
                res = extract_table(str(target))
                if not res:
                    log_file_skipped(f.name, "extraction failed")
                    continue
                comp_data, comp_data_normalized, elem, at, spectrum_info = res
                if not at:
                    log_file_skipped(f.name, "not atomic% data")
                    continue
            else:
                # Try extraction on original file first - only move if successful
                res = extract_table(str(f))
                if not res:
                    log_file_skipped(f.name, "spectra extraction failed")
                    continue
                comp_data, comp_data_normalized, elem, at, spectrum_info = res
                if not at:
                    log_file_skipped(f.name, "not atomic% data")
                    continue
                
                # Move file only after successful extraction
                shutil.move(str(f), target)
            
            # Determine table type for image extraction
            from tables import table_type
            t_type = table_type(str(target))

            elements = elem  # assume same across group

            suffix = f.name[:-5].split('_',2)[2][-1]
            
            # Choose data based on config
            use_normalized = config['normalization']['enabled']
            data_to_process = comp_data_normalized if use_normalized else comp_data
            
            if suffix == 'a':
                # treat as overall: average rows into single overall vector
                arr = np.array(data_to_process)
                if arr.size:
                    over = one_cluster(arr, 1) 
                    cluster_data = over['cluster']
                    if cluster_data:
                        # Keep cluster data for Excel sheet
                        overall_data = cluster_data
                    else:
                        overall_data = None
                else:
                    overall_data = None
                    over = None
            else:
                # extend other_measurements with all rows from this letter
                for i, row in enumerate(data_to_process):
                    other_measurements.append(row)
                    if i < len(spectrum_info):
                        spectrum_data.append(spectrum_info[i])
                    else:
                        spectrum_data.append("Spectrum Unknown")

        # Merge PHENOM export data if available for this sample
        export_match = export_data.pop((sys_name, temp, sample_no), None)
        export_tiff_images = []
        if export_match:
            export_elements = export_match['elements']
            export_overall = export_match['overall']
            export_points = export_match['points']
            export_site_dirs = export_match.get('site_dirs', [])

            if elements is not None:
                log_info(f"{sample_full_name}: Export elements = {export_elements}, docx elements = {elements}, match = {set(export_elements) == set(elements)}")
            else:
                log_info(f"{sample_full_name}: Export elements = {export_elements}, docx elements = None")

            if elements is None:
                elements = export_elements
                log_info(f"{sample_full_name}: Using elements from PHENOM export: {elements}")
            elif set(export_elements) != set(elements):
                log_warning(f"{sample_full_name}: PHENOM elements {export_elements} differ from docx elements {elements}, "
                           f"using docx elements. Export data will be reordered accordingly.")
                docx_order = {el: i for i, el in enumerate(elements)}
                reordered_export_overall = []
                for row in export_overall:
                    new_row = [0.0] * len(elements)
                    for el, val in zip(export_elements, row):
                        if el in docx_order:
                            new_row[docx_order[el]] = val
                    reordered_export_overall.append(new_row)
                export_overall = reordered_export_overall

                reordered_export_points = []
                for row in export_points:
                    new_row = [0.0] * len(elements)
                    for el, val in zip(export_elements, row):
                        if el in docx_order:
                            new_row[docx_order[el]] = val
                    reordered_export_points.append(new_row)
                export_points = reordered_export_points

            if export_overall:
                if overall_data is None:
                    overall_data = []
                overall_data.extend(export_overall)
                log_info(f"{sample_full_name}: Added {len(export_overall)} overall row(s) from PHENOM export")

            if export_points:
                start_idx = len(other_measurements) + 1
                for i, row in enumerate(export_points):
                    other_measurements.append(row)
                    spectrum_data.append(f"PHENOM-{start_idx + i}")
                log_info(f"{sample_full_name}: Added {len(export_points)} point row(s) from PHENOM export")

            # Move export site directories to sample reports folder
            if export_site_dirs:
                for site_id, src_path in export_site_dirs:
                    src = Path(src_path)
                    if not src.exists():
                        continue
                    dest = reports_dir / src.name
                    if not dest.exists():
                        shutil.move(str(src), str(dest))
                        log_info(f"Moved export folder: {src.name} -> {dest}")
                    else:
                        log_info(f"Export folder already exists at destination: {dest}")

                # Extract TIFF images directly from the export folder
                export_dir = Path(folder_path) / "export"
                for site_id, src_path in export_site_dirs:
                    tiff_name = f"{sys_name}_{temp}_{sample_no}{site_id}.tiff"
                    tiff_path = export_dir / tiff_name
                    if tiff_path.exists():
                        try:
                            with PILImage.open(str(tiff_path)) as img:
                                if img.mode != 'RGB':
                                    img = img.convert('RGB')
                                buf = io.BytesIO()
                                img.save(buf, format='PNG')
                                export_tiff_images.append((tiff_path.name, buf.getvalue()))
                                log_info(f"Added TIFF image from export: {tiff_path.name}")
                        except Exception as e:
                            log_error(f"Failed to process TIFF {tiff_path}: {e}")
        else:
            # If no docx data at all but export data exists (handled in post-loop)
            pass

        # Process images per report using matplotlib selection interface
        if config['images']['embed_images']:
            try:
                # Collect image data from all AZTEC files
                reports_with_images = []
                total_extracted = 0
                total_matching = 0
                for f in files:
                    target = reports_dir / f.name
                    if not target.exists():
                        continue
                        
                    t_type = table_type(str(target))
                    if t_type == 'AZTEC':
                        file_images = extract_aztec_images(str(target))
                        if file_images:
                            total_extracted += len(file_images)
                            images_data = []
                            all_images_data = []
                            
                            for img_name, img_data in file_images:
                                with PILImage.open(io.BytesIO(img_data)) as img:
                                    dimensions = f"{img.size[0]}x{img.size[1]}"
                                
                                metadata = {
                                    'source_file': f.name,
                                    'image_name': img_name,
                                    'file_type': t_type,
                                    'dimensions': dimensions,
                                    'size': len(img_data)
                                }
                                all_images_data.append((img_name, img_data, metadata))
                                
                                # Filter by acceptable sizes
                                if dimensions in ACCEPTABLE_IMAGE_SIZES:
                                    total_matching += 1
                                    images_data.append((img_name, img_data, metadata))
                            
                            # Use matching images if available, otherwise ask user to select from all
                            if images_data:
                                reports_with_images.append((f.name, images_data))
                            elif all_images_data:
                                log_info(f"No images match acceptable sizes {ACCEPTABLE_IMAGE_SIZES} in {f.name}, asking user to select from {len(all_images_data)} available image(s)")
                                reports_with_images.append((f.name, all_images_data))
                
                # Log summary of extracted images
                if total_extracted > 0:
                    log_info(f"Image extraction: {total_extracted} total extracted, {total_matching} match acceptable sizes {ACCEPTABLE_IMAGE_SIZES}")
                
                # Process images with matplotlib selection
                if reports_with_images:
                    selected_images = sequential_image_selection(reports_with_images)
                    if selected_images:
                        sample_images_dict[sample_full_name].extend(selected_images)
                        log_info(f"Selected {len(selected_images)} images for embedding")
                        
            except Exception as e:
                log_error(f"Image processing failed for {sample_full_name}: {e}", exc_info=True)

        # If we have measurements other than overall, do clustering / association
        cluster_labels = []
        if other_measurements:
            data = np.asarray(other_measurements, dtype=float)
            # if data has 3 columns use ternary clustering; otherwise cluster as-is, this is in preparation for binary systems
            if data.shape[1] == 3:
                pts_for_search = data
            else:
                print('data not in ternary shape, continuing with analysis by skipping')
                continue

            # decide min_samples range dynamically (2..min(6,n))
            n = len(data)
            min_samples_vals = tuple(range(2, min(6, n) + 1)) if n >= 2 else (2,)
            
            # Ensure elements is not None for clustering
            elements_for_clustering = elements if elements is not None else ['A', 'B', 'C']
            
            # Compute mean of overall_data for clustering GUI display
            overall_composition_mean = None
            if overall_data:
                overall_composition_mean = np.mean(overall_data, axis=0).tolist()
            
            # Elements are now always alphabetical, so use phases directly
            best_any = show_clustering_phase_selection(
                pts_for_search,
                elements=elements_for_clustering,
                sample_name=clustering_sample_name,
                clustering_history=clustering_hist,
                phases_data=phases_data,
                overall_composition=overall_composition_mean,
                eps_max=4.0,
                eps_steps=20,
                min_samples_range=min_samples_vals
            )

            labels = best_any[0]
            cluster_phase_names = best_any[1]
            
            if labels is None:
                # fallback: single cluster
                labels = np.zeros(len(data), dtype=int)
                cluster_phase_names = ["NA", "NA", "NA"]
            
            unique_clusters = set(labels) - {-1}
            if not unique_clusters:
                labels = np.zeros(len(data), dtype=int)

            cluster_labels = list(map(int, labels))
            
            # Save clustering result to history for future reference
            save_clustering_result(sys_name, temp, sample_full_name, pts_for_search, labels, folder_path)
            
            # Update cached history for next sample in this system/temp
            clustering_hist = load_clustering_history(sys_name, temp, folder_path)
            system_temp_history[system_temp_key] = clustering_hist
            
            # Store phase mapping for prediction .exp generation
            sample_id = f"{temp}_{sample_no}"
            system_temp_phase_mappings[current_system_temp][sample_id] = cluster_phase_names
        else:
            # no other measurements: no clusters -> empty
            cluster_labels = []
            cluster_phase_names = []
            
            # Store empty phase mapping
            sample_id = f"{temp}_{sample_no}"
            system_temp_phase_mappings[current_system_temp][sample_id] = []


        # sample label as number
        sample_label = str(sample_no)
        # Write sample sheet of .xlsx file
        # Use the first file name for sample_full_name (include system for clustering display)
        sample_full_name = files[0].name[:-6] if files else f"sample_{sample_no}"
        sample_images_to_pass = sample_images_dict.get(sample_full_name) or []
        
        # Merge TIFF images collected from export site directories
        if export_match and export_tiff_images:
            sample_images_to_pass.extend(export_tiff_images)
            log_info(f"Sample {sample_full_name}: Added {len(export_tiff_images)} TIFF image(s) from PHENOM export")
        
        # Log image summary for this sample
        if sample_images_to_pass:
            log_info(f"Sample {sample_full_name}: {len(sample_images_to_pass)} confirmed images will be embedded")
        else:
            log_info(f"Sample {sample_full_name}: No images to embed")
        
        write_sample_sheet(
            str(sem_file), 
            sample_label, 
            sample_full_name, 
            elements or [], 
            overall_data or [], 
            other_measurements, 
            cluster_labels, 
            spectrum_data, 
            sample_images_to_pass,
            cluster_phase_names
        )
        
        log_file_processed(f"{sys_name}_{temp}_sample{sample_no}", f"{len(files)} files, {len(cluster_labels)} measurements, {len(sample_images_to_pass)} images")

        processed.append(((sys_name, temp, sample_no), files))

    # Process remaining export data that had no matching docx report group
    if export_data:
        # Reset current_system_temp so the export loop does not
        # re-create .exp files for the last docx-processed group
        current_system_temp = None
        log_info(f"Processing {len(export_data)} PHENOM export-only sample(s) without matching docx reports")
        for (exp_sys, exp_temp, exp_sample), exp_info in sorted(export_data.items()):
            exp_elements = exp_info['elements']
            exp_overall = exp_info['overall']
            exp_points = exp_info['points']

            if not exp_points and not exp_overall:
                continue

            # Check if we need to create .exp file for previous system/temp
            if current_system_temp is not None and current_system_temp != (exp_sys, exp_temp):
                prev_sys, prev_temp = current_system_temp
                if (prev_sys, prev_temp) in system_temp_sem_files:
                    prev_sem_file = system_temp_sem_files[(prev_sys, prev_temp)]
                    prev_target_dir = Path(structure[prev_sys]["path"]) / str(prev_temp)
                    prev_phases = system_temp_phases.get(prev_sys, [])
                    prev_phase_mapping = system_temp_phase_mappings.get((prev_sys, prev_temp), {})
                    prev_sorted_elements = system_temp_sorted_elements.get(prev_sys, [])
                    prev_report_path = prev_target_dir / f"REPORT_{prev_sys}_{prev_temp}.dat"

                    log_info(f"Creating .exp files for {prev_sys}/{prev_temp}")
                    c_exp(str(prev_sem_file), str(prev_target_dir), phases_data=prev_phases)

                    from to_exp import create_exp_with_phase_prediction
                    create_exp_with_phase_prediction(
                        str(prev_sem_file),
                        str(prev_target_dir),
                        phases_data=prev_phases,
                        cluster_phase_mapping=prev_phase_mapping,
                        elements_order=prev_sorted_elements,
                        report_path=str(prev_report_path)
                    )

            current_system_temp = (exp_sys, exp_temp)

            if current_system_temp not in system_temp_phase_mappings:
                system_temp_phase_mappings[current_system_temp] = {}

            if exp_sys not in system_temp_phases:
                system_temp_sorted_elements[exp_sys] = exp_elements
                phases_data = load_phases_for_system(exp_sys, exp_elements, folder_path, create_if_missing=True)
                system_temp_phases[exp_sys] = phases_data
                if phases_data:
                    log_info(f"Loaded {len(phases_data)} phases for system {exp_sys} (export-only)")

            phases_data = system_temp_phases.get(exp_sys, [])
            sorted_elements = system_temp_sorted_elements.get(exp_sys, [])

            system_temp_key = (exp_sys, exp_temp)
            if system_temp_key not in system_temp_history:
                clustering_hist = load_clustering_history(exp_sys, exp_temp, folder_path)
                system_temp_history[system_temp_key] = clustering_hist
            else:
                clustering_hist = system_temp_history[system_temp_key]

            structure = create_structure(folder_path, exp_sys, exp_temp, structure or {}, sample_number=exp_sample)
            reports_dir = get_sample_reports_path(folder_path, exp_sys, exp_temp, exp_sample)

            # Move export site directories and extract TIFF images
            export_site_dirs = exp_info.get('site_dirs', [])
            sample_tiff_images = []
            if export_site_dirs:
                for site_id, src_path in export_site_dirs:
                    src = Path(src_path)
                    if not src.exists():
                        continue
                    dest = reports_dir / src.name
                    if not dest.exists():
                        shutil.move(str(src), str(dest))
                        log_info(f"Moved export folder: {src.name} -> {dest}")
                    else:
                        log_info(f"Export folder already exists at destination: {dest}")

                export_dir = Path(folder_path) / "export"
                for site_id, src_path in export_site_dirs:
                    tiff_name = f"{exp_sys}_{exp_temp}_{exp_sample}{site_id}.tiff"
                    tiff_path = export_dir / tiff_name
                    if tiff_path.exists():
                        try:
                            with PILImage.open(str(tiff_path)) as img:
                                if img.mode != 'RGB':
                                    img = img.convert('RGB')
                                buf = io.BytesIO()
                                img.save(buf, format='PNG')
                                sample_tiff_images.append((tiff_path.name, buf.getvalue()))
                                log_info(f"Added TIFF image from export: {tiff_path.name}")
                        except Exception as e:
                            log_error(f"Failed to process TIFF {tiff_path}: {e}")

            sem_file = Path(structure[exp_sys]["path"]) / str(exp_temp) / f"SEM_results_{exp_sys}_{exp_temp}.xlsx"
            system_temp_sem_files[(exp_sys, exp_temp)] = sem_file

            clustering_sample_name = f"{exp_sys}_{exp_temp}_{exp_sample}"
            elements = exp_elements
            overall_data = exp_overall if exp_overall else None
            other_measurements = exp_points
            spectrum_data = [f"PHENOM-{i+1}" for i in range(len(exp_points))]

            cluster_labels = []
            if other_measurements:
                data = np.asarray(other_measurements, dtype=float)
                if data.shape[1] == 3:
                    pts_for_search = data
                else:
                    log_info(f"Export-only {clustering_sample_name}: data not in ternary shape, skipping clustering")
                    cluster_labels = []
                    cluster_phase_names = []
                    sample_full_name_export = f"{clustering_sample_name}"
                    sample_label = str(exp_sample)
                    write_sample_sheet(
                        str(sem_file),
                        sample_label,
                        sample_full_name_export,
                        elements or [],
                        overall_data or [],
                        other_measurements,
                        cluster_labels,
                        spectrum_data,
                        sample_tiff_images,
                        []
                    )
                    log_file_processed(f"{exp_sys}_{exp_temp}_sample{exp_sample}",
                                       f"export-only, {len(other_measurements)} measurements")
                    processed.append(((exp_sys, exp_temp, exp_sample), []))
                    continue

                n = len(data)
                min_samples_vals = tuple(range(2, min(6, n) + 1)) if n >= 2 else (2,)

                overall_composition_mean = None
                if overall_data:
                    overall_composition_mean = np.mean(overall_data, axis=0).tolist()

                best_any = show_clustering_phase_selection(
                    pts_for_search,
                    elements=elements or ['A', 'B', 'C'],
                    sample_name=clustering_sample_name,
                    clustering_history=clustering_hist,
                    phases_data=phases_data,
                    overall_composition=overall_composition_mean,
                    eps_max=4.0,
                    eps_steps=20,
                    min_samples_range=min_samples_vals
                )

                labels = best_any[0]
                cluster_phase_names = best_any[1]

                if labels is None:
                    labels = np.zeros(len(data), dtype=int)
                    cluster_phase_names = ["NA", "NA", "NA"]

                unique_clusters = set(labels) - {-1}
                if not unique_clusters:
                    labels = np.zeros(len(data), dtype=int)

                cluster_labels = list(map(int, labels))

                save_clustering_result(exp_sys, exp_temp, clustering_sample_name, pts_for_search, labels, folder_path)

                clustering_hist = load_clustering_history(exp_sys, exp_temp, folder_path)
                system_temp_history[system_temp_key] = clustering_hist

                sample_id = f"{exp_temp}_{exp_sample}"
                system_temp_phase_mappings[current_system_temp][sample_id] = cluster_phase_names
            else:
                cluster_labels = []
                cluster_phase_names = []
                sample_id = f"{exp_temp}_{exp_sample}"
                system_temp_phase_mappings[current_system_temp][sample_id] = []

            sample_full_name_export = f"{clustering_sample_name}"
            sample_label = str(exp_sample)

            write_sample_sheet(
                str(sem_file),
                sample_label,
                sample_full_name_export,
                elements or [],
                overall_data or [],
                other_measurements,
                cluster_labels,
                spectrum_data,
                sample_tiff_images,
                cluster_phase_names
            )

            log_file_processed(f"{exp_sys}_{exp_temp}_sample{exp_sample}",
                               f"export-only, {len(other_measurements)} measurements")
            processed.append(((exp_sys, exp_temp, exp_sample), []))

    # Create .exp files for the last system/temp group
    if current_system_temp is not None:
        last_sys, last_temp = current_system_temp
        if (last_sys, last_temp) in system_temp_sem_files:
            last_sem_file = system_temp_sem_files[(last_sys, last_temp)]
            last_target_dir = Path(structure[last_sys]["path"]) / str(last_temp)
            last_phases = system_temp_phases.get(last_sys, [])
            last_phase_mapping = system_temp_phase_mappings.get((last_sys, last_temp), {})
            last_sorted_elements = system_temp_sorted_elements.get(last_sys, [])
            last_report_path = last_target_dir / f"REPORT_{last_sys}_{last_temp}.dat"
            
            log_info(f"Creating final .exp files for {last_sys}/{last_temp}")
            # Generate original .exp file
            c_exp(str(last_sem_file), str(last_target_dir), phases_data=last_phases)
            
            # Generate prediction .exp file with phase substitutions
            from to_exp import create_exp_with_phase_prediction
            create_exp_with_phase_prediction(
                str(last_sem_file),
                str(last_target_dir),
                phases_data=last_phases,
                cluster_phase_mapping=last_phase_mapping,
                elements_order=last_sorted_elements,
                report_path=str(last_report_path)
            )

    # Reorder sheets in all SEM_results files so numeric sample sheets appear in ascending order
    for sem_file in set(system_temp_sem_files.values()):
        if sem_file.exists():
            _reorder_sem_result_sheets(str(sem_file))

    log_info(f"Processing complete. Processed {len(processed)} samples across {len(system_temp_sem_files)} system/temperature combinations")
    return processed, structure


def update_report_dat_phases(report_path: str, sample_updates: Dict[str, List[str]]) -> bool:
    """
    Update phase assignments in existing REPORT .dat file.
    
    Format: tab-separated, columns 7, 11, 15 contain phase names
    
    Args:
        report_path: Path to REPORT .dat file
        sample_updates: Dict mapping sample_id -> [phase1, phase2, phase3]
        
    Returns:
        True if successful
    """
    try:
        if not Path(report_path).exists():
            log_warning(f"REPORT file not found: {report_path}")
            return False
        
        rows = []
        with open(report_path, 'r') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                rows.append(row)
        
        updated_count = 0
        for row in rows:
            if len(row) < 16:
                continue
            sample_id = row[0].strip()
            if not sample_id or sample_id.startswith('$'):
                continue
            
            if sample_id in sample_updates:
                phases = sample_updates[sample_id]
                if len(phases) >= 1 and phases[0]:
                    row[7] = phases[0]
                if len(phases) >= 2 and phases[1]:
                    row[11] = phases[1]
                if len(phases) >= 3 and phases[2]:
                    row[15] = phases[2]
                updated_count += 1
        
        with open(report_path, 'w', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerows(rows)
        
        log_info(f"Updated REPORT.dat with {updated_count} sample(s)")
        return True
        
    except Exception as e:
        log_error(f"Failed to update REPORT.dat: {e}")
        return False
