"""
XRD Assignment Module for phase association analysis.

Handles:
- XRD sample marking with bold formatting in phase_table
- XRD coverage analysis
- Phase association re-run with preselected phases
"""

import os
import json
import re
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set
from openpyxl import load_workbook
from openpyxl.styles import Font
import pandas as pd

from constants import PHASE_TABLE_PATTERN
from logging_config import log_info, log_warning, log_error


def extract_sample_number(sample_name: str) -> int:
    """Extract numeric part from sample name for sorting."""
    match = re.search(r'(\d+)$', sample_name)
    if match:
        return int(match.group(1))
    return 0
from logging_config import log_info, log_warning, log_error


def get_all_analyzed_systems(base_path: str) -> List[Tuple[str, str, Path]]:
    """
    Find all analyzed systems by scanning for phase_table files.
    
    Args:
        base_path: Base directory to search
        
    Returns:
        List of (system, temp, phase_table_path) tuples sorted by system then temp
    """
    base = Path(base_path)
    results = []
    
    for system_dir in base.iterdir():
        if not system_dir.is_dir():
            continue
        
        system_name = system_dir.name
        
        for temp_dir in system_dir.iterdir():
            if not temp_dir.is_dir():
                continue
            
            temp = temp_dir.name
            phase_table_name = PHASE_TABLE_PATTERN.format(system=system_name, temp=temp)
            phase_table_path = temp_dir / phase_table_name
            
            if phase_table_path.exists():
                results.append((system_name, temp, phase_table_path))
    
    results.sort(key=lambda x: (x[0], x[1]))
    return results


def get_xrd_info_path(phase_table_path: Path) -> Path:
    """
    Get the path to the XRD info JSON file associated with a phase_table.
    
    Args:
        phase_table_path: Path to phase_table.xlsx
        
    Returns:
        Path to the XRD info JSON file
    """
    return phase_table_path.with_suffix('.xrd_info.json')


def load_xrd_info(phase_table_path: Path) -> Dict:
    """
    Load XRD info from JSON sidecar file.
    
    Args:
        phase_table_path: Path to phase_table.xlsx
        
    Returns:
        Dict with xrd_samples list and optionally phase_notes
    """
    xrd_info_path = get_xrd_info_path(phase_table_path)
    
    if not xrd_info_path.exists():
        return {"xrd_samples": [], "phase_notes": []}
    
    try:
        with open(xrd_info_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {
                "xrd_samples": data.get("xrd_samples", []),
                "phase_notes": data.get("phase_notes", [])
            }
    except Exception as e:
        log_warning(f"Failed to load XRD info from {xrd_info_path}: {e}")
        return {"xrd_samples": [], "phase_notes": []}


def save_xrd_info(phase_table_path: Path, xrd_info: Dict):
    """
    Save XRD info to JSON sidecar file.
    
    Args:
        phase_table_path: Path to phase_table.xlsx
        xrd_info: Dict with xrd_samples list and optionally phase_notes
    """
    xrd_info_path = get_xrd_info_path(phase_table_path)
    
    output_data = {
        "xrd_samples": xrd_info.get("xrd_samples", []),
        "phase_notes": xrd_info.get("phase_notes", [])
    }
    
    try:
        with open(xrd_info_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, sort_keys=True)
        log_info(f"Saved XRD info: {len(xrd_info.get('xrd_samples', []))} XRD samples, {len(xrd_info.get('phase_notes', []))} notes")
    except Exception as e:
        log_error(f"Failed to save XRD info to {xrd_info_path}: {e}")


def load_phase_table_data(phase_table_path: Path) -> Tuple[List[Dict], Set[str], List[str]]:
    """
    Load phase table data with XRD bold information and phase notes.
    
    Args:
        phase_table_path: Path to phase_table.xlsx
        
    Returns:
        Tuple of (data_rows, bold_samples_set, phase_notes)
        data_rows: List of dicts with sample, phase, overall_comp, phase_comp
        bold_samples_set: Set of sample IDs that are bold (XRD-done)
        phase_notes: List of notes in format "temp_number-phase-note"
    """
    xrd_info = load_xrd_info(phase_table_path)
    xrd_samples = set(xrd_info.get('xrd_samples', []))
    phase_notes = xrd_info.get('phase_notes', [])
    
    data = []
    
    try:
        wb = load_workbook(phase_table_path)
        ws = wb.active
        
        for row_idx in range(3, ws.max_row + 1):
            sample_cell = ws.cell(row=row_idx, column=1)
            sample_val = sample_cell.value
            
            if sample_val is None or str(sample_val).strip() == "":
                continue
            
            sample_str = str(sample_val).strip()
            
            overall = [
                ws.cell(row=row_idx, column=2).value,
                ws.cell(row=row_idx, column=3).value,
                ws.cell(row=row_idx, column=4).value
            ]
            
            phase = ws.cell(row=row_idx, column=5).value
            if phase is None:
                phase = "NA"
            
            phase_comp = [
                ws.cell(row=row_idx, column=6).value,
                ws.cell(row=row_idx, column=7).value,
                ws.cell(row=row_idx, column=8).value
            ]
            
            data.append({
                'sample': sample_str,
                'overall': overall,
                'phase': phase,
                'phase_comp': phase_comp,
                'row': row_idx,
                'is_bold': sample_cell.font.bold if sample_cell.font else False
            })
        
        wb.close()
        
    except Exception as e:
        log_error(f"Failed to load phase table {phase_table_path}: {e}")
    
    return data, xrd_samples, phase_notes


def save_phase_table_with_bold(
    phase_table_path: Path,
    data: List[Dict],
    xrd_samples: Set[str],
    phase_notes: List[str] = None
):
    """
    Save phase table data with bold formatting preserved for XRD samples.
    
    Args:
        phase_table_path: Path to phase_table.xlsx
        data: List of dicts with sample, phase, overall_comp, phase_comp
        xrd_samples: Set of sample IDs that are bold (XRD-done)
        phase_notes: List of notes in format "temp_number-phase-note"
    """
    if phase_notes is None:
        phase_notes = []
    
    try:
        wb = load_workbook(phase_table_path)
        ws = wb.active
        
        bold_font = Font(bold=True)
        normal_font = Font(bold=False)
        
        for row_idx in range(3, ws.max_row + 1):
            sample_cell = ws.cell(row=row_idx, column=1)
            sample_val = sample_cell.value
            
            if sample_val is None or str(sample_val).strip() == "":
                continue
            
            sample_str = str(sample_val).strip()
            
            if sample_str in xrd_samples:
                sample_cell.font = bold_font
            else:
                sample_cell.font = normal_font
        
        wb.save(phase_table_path)
        wb.close()
        
        save_xrd_info(phase_table_path, {
            "xrd_samples": sorted(list(xrd_samples)),
            "phase_notes": sorted(phase_notes)
        })
        
        log_info(f"Saved phase table with {len(xrd_samples)} XRD-marked samples, {len(phase_notes)} notes")
        
    except Exception as e:
        log_error(f"Failed to save phase table {phase_table_path}: {e}")


def select_system_gui(base_path: str, title: str = "Select System", multi_select: bool = True) -> Optional[List[Tuple[str, str, Path]]]:
    """
    Show GUI to select system/temperature combination(s) using checkboxes.
    
    Args:
        base_path: Base directory to search
        title: Window title
        multi_select: If True, allow multiple selections
        
    Returns:
        List of (system, temp, phase_table_path) tuples or None if cancelled
    """
    systems = get_all_analyzed_systems(base_path)
    
    if not systems:
        return None
    
    root = tk.Tk()
    root.title(title)
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.5)
    window_height = int(screen_height * 0.6)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    selected = {"value": None}
    system_vars = {}
    
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text=title, font=("Arial", 16, "bold")).pack(pady=(0, 15))
    
    if multi_select:
        ttk.Label(main_frame, text="Select one or more system/temperature combinations", 
                  font=("Arial", 10)).pack(pady=(0, 10))
    
    canvas_frame = ttk.Frame(main_frame)
    canvas_frame.pack(fill=tk.BOTH, expand=True, pady=10)
    
    canvas = tk.Canvas(canvas_frame)
    scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas, padding=5)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    for system, temp, path in systems:
        display = f"{system} / {temp}"
        var = tk.BooleanVar(value=False)
        system_vars[(system, temp, path)] = var
        cb = ttk.Checkbutton(scrollable_frame, text=display, variable=var)
        cb.pack(anchor="w", pady=2)
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=15)
    
    def on_select():
        selected_systems = [key for key, var in system_vars.items() if var.get()]
        if selected_systems:
            selected["value"] = selected_systems
            root.destroy()
    
    def on_cancel():
        selected["value"] = None
        root.destroy()
    
    ttk.Button(button_frame, text="Select", command=on_select, width=15).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Cancel", command=on_cancel, width=15).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    return selected["value"]


def select_samples_for_xrd_gui(
    data: List[Dict],
    xrd_samples: Set[str]
) -> Set[str]:
    """
    Show GUI to select samples for XRD assignment using checkboxes.
    
    Args:
        data: Phase table data
        xrd_samples: Set of already XRD-marked samples
        
    Returns:
        Set of selected sample IDs for XRD marking
    """
    unique_samples = list(dict.fromkeys(d['sample'] for d in data))
    
    root = tk.Tk()
    root.title("XRD Sample Assignment")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.5)
    window_height = int(screen_height * 0.6)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    sample_vars = {}
    
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text="Select Samples with XRD Data", font=("Arial", 14, "bold")).pack(pady=(0, 10))
    ttk.Label(main_frame, text="Samples marked as XRD-done will appear in bold in phase_table", 
              font=("Arial", 10)).pack(pady=(0, 15))
    
    canvas_frame = ttk.Frame(main_frame)
    canvas_frame.pack(fill=tk.BOTH, expand=True, pady=10)
    
    canvas = tk.Canvas(canvas_frame)
    scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas, padding=5)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    for sample in sorted(unique_samples, key=extract_sample_number):
        var = tk.BooleanVar(value=(sample in xrd_samples))
        sample_vars[sample] = var
        cb = ttk.Checkbutton(scrollable_frame, text=sample, variable=var)
        cb.pack(anchor="w", pady=2)
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=15)
    
    def on_confirm():
        selected = {s for s, var in sample_vars.items() if var.get()}
        root.quit()
        root.destroy()
        return selected
    
    def on_cancel():
        root.quit()
        root.destroy()
    
    ttk.Button(button_frame, text="Confirm Selection", command=on_confirm, width=15).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Cancel", command=on_cancel, width=15).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    return {s for s, var in sample_vars.items() if var.get()}


def get_ternary_phases_for_system(system_name: str, base_path: str) -> List[str]:
    """
    Get all ternary (3-element) phases for a system from the phases file.
    
    Args:
        system_name: System name (e.g., "InLaNi")
        base_path: Base directory path
        
    Returns:
        List of ternary phase names
    """
    from phases import parse_phase_formula, is_range_formula
    
    phase_file = Path(base_path) / system_name / f"phases_{system_name}.txt"
    
    if not phase_file.exists():
        log_warning(f"Phase file not found: {phase_file}")
        return []
    
    try:
        with open(phase_file, 'r', encoding='utf-8') as f:
            phases = [line.strip() for line in f if line.strip()]
        
        ternary_phases = []
        for phase in phases:
            try:
                if is_range_formula(phase):
                    parsed, _ = parse_phase_formula(phase)
                    elements = set(parsed["endpoint1"].keys())
                else:
                    parsed, _ = parse_phase_formula(phase)
                    elements = set(parsed.keys())
                
                if len(elements) == 3:
                    ternary_phases.append(phase)
            except Exception:
                continue
        
        return ternary_phases
        
    except Exception as e:
        log_error(f"Failed to read phases file {phase_file}: {e}")
        return []


def analyze_xrd_coverage(
    phase_table_path: Path,
    xrd_samples: Set[str],
    system_name: str,
    base_path: str
) -> Tuple[List[str], List[Tuple[str, List[str]]]]:
    """
    Analyze XRD coverage and recommend samples for completing ternary phase analysis.
    
    Args:
        phase_table_path: Path to phase_table.xlsx
        xrd_samples: Set of sample IDs marked as XRD-done
        system_name: System name
        base_path: Base directory path
        
    Returns:
        Tuple of:
        - List of ternary phases NOT assessed by XRD
        - List of recommended (sample_id, missing_phases) tuples sorted by priority
    """
    ternary_phases = set(get_ternary_phases_for_system(system_name, base_path))
    
    if not ternary_phases:
        log_info(f"No ternary phases found for system {system_name}")
        return [], []
    
    data, _, _ = load_phase_table_data(phase_table_path)
    
    xrd_phases = set()
    for row in data:
        if row['sample'] in xrd_samples:
            phase = row.get('phase', 'NA')
            if phase and phase != 'NA':
                xrd_phases.add(phase)
    
    not_assessed = sorted(ternary_phases - xrd_phases)
    
    sample_phase_map = {}
    for row in data:
        sample = row['sample']
        phase = row.get('phase', 'NA')
        if phase and phase != 'NA':
            if sample not in sample_phase_map:
                sample_phase_map[sample] = set()
            sample_phase_map[sample].add(phase)
    
    recommendations = []
    for sample, phases in sample_phase_map.items():
        if sample not in xrd_samples:
            missing_in_sample = ternary_phases - phases
            if missing_in_sample:
                recommendations.append((sample, sorted(missing_in_sample)))
    
    recommendations.sort(key=lambda x: (-len(x[1]), x[0]))
    
    return not_assessed, recommendations


def run_xrd_assignment(base_path: str) -> bool:
    """
    Main function to run XRD assignment workflow.
    
    Args:
        base_path: Base directory path
        
    Returns:
        True if completed successfully, False if cancelled or error
    """
    selection = select_system_gui(base_path, "XRD Assignment - Select System", multi_select=True)
    
    if selection is None:
        return False
    
    all_data = {}
    all_xrd_samples = {}
    
    for system, temp, phase_table_path in selection:
        data, current_xrd, phase_notes = load_phase_table_data(phase_table_path)
        
        if not data:
            log_warning(f"No data found in phase table: {phase_table_path}")
            continue
        
        new_xrd_samples = select_samples_for_xrd_gui(data, current_xrd)
        
        if new_xrd_samples != current_xrd or phase_notes:
            save_phase_table_with_bold(phase_table_path, data, new_xrd_samples, phase_notes)
        
        key = f"{system}/{temp}"
        all_data[key] = (data, phase_table_path)
        all_xrd_samples[key] = new_xrd_samples
    
    if not all_data:
        log_warning("No valid data loaded")
        return False
    
    combined_not_assessed = set()
    all_ternary_phases = set()
    all_sample_phases = {}
    all_na_samples = {}
    all_xrd_samples_combined = set()
    analyzed_phase_samples = {}
    all_phases_in_system = {}
    all_phases_samples = {}
    
    for key, (data, phase_table_path) in all_data.items():
        system, temp = key.split("/")
        
        ternary_phases = get_ternary_phases_for_system(system, base_path)
        all_ternary_phases.update(ternary_phases)
        
        xrd_samples = all_xrd_samples[key]
        all_xrd_samples_combined.update(xrd_samples)
        
        xrd_phases = set()
        for row in data:
            if row['sample'] in xrd_samples:
                phase = row.get('phase', 'NA')
                if phase and phase != 'NA':
                    xrd_phases.add(phase)
                    if phase not in analyzed_phase_samples:
                        analyzed_phase_samples[phase] = set()
                    analyzed_phase_samples[phase].add(row['sample'])
        
        combined_not_assessed.update(set(ternary_phases) - xrd_phases)
        
        for row in data:
            sample = row['sample']
            phase = row.get('phase', 'NA')
            
            if phase not in all_phases_samples:
                all_phases_samples[phase] = set()
            all_phases_samples[phase].add(sample)
            
            if phase not in all_phases_in_system:
                all_phases_in_system[phase] = set()
            all_phases_in_system[phase].add(phase)
            
            if phase == 'NA':
                if sample not in all_na_samples:
                    all_na_samples[sample] = set()
                all_na_samples[sample].add('NA')
            else:
                if sample not in all_sample_phases:
                    all_sample_phases[sample] = set()
                all_sample_phases[sample].add(phase)
    
    analyzed_phases = all_ternary_phases - combined_not_assessed
    
    recommendations_priority, recommendations_min = compute_recommendations(
        all_sample_phases, all_na_samples, all_xrd_samples_combined, combined_not_assessed
    )
    
    show_results_popup(
        analyzed_phases, analyzed_phase_samples, 
        all_ternary_phases, combined_not_assessed, 
        all_sample_phases, all_phases_samples,
        recommendations_priority, recommendations_min
    )
    
    log_info("=" * 60)
    log_info(f"XRD Assignment Complete for {len(all_data)} system(s)")
    log_info("=" * 60)
    
    if combined_not_assessed:
        log_info(f"Phases NOT assessed by XRD ({len(combined_not_assessed)}):")
        for phase in sorted(combined_not_assessed):
            log_info(f"  • {phase}")
    else:
        log_info("All ternary phases have been assessed by XRD!")
    
    log_info("=" * 60)
    
    return True


def compute_recommendations(
    sample_phases: Dict[str, Set[str]],
    na_samples: Dict[str, Set[str]],
    xrd_samples: Set[str],
    not_assessed: Set[str]
) -> Tuple[List[Tuple[str, List[str], List[str]]], List[Tuple[str, List[str], List[str]]]]:
    """
    Compute sample recommendations for covering not-assessed ternary phases.
    Also includes NA samples as they may need XRD to identify the phase.
    
    Returns:
        Two lists:
        - Priority list: prioritizes 2-phase samples first, then uses 3-phase to finish, then NA samples
        - Minimum list: minimizes number of samples
        Each tuple: (sample, phases_for_not_assessed, all_phases_in_sample)
    """
    if not not_assessed:
        return [], []
    
    all_samples = set(sample_phases.keys()) | set(na_samples.keys())
    non_xrd_samples = all_samples - xrd_samples
    
    sample_coverage = {}
    for sample in non_xrd_samples:
        phases = sample_phases.get(sample, set())
        na_flag = sample in na_samples
        
        covered = phases & not_assessed
        if covered or na_flag:
            sample_coverage[sample] = {
                'covered': covered,
                'total_phases': len(phases),
                'is_two_phase': len(phases) == 2,
                'is_na': na_flag
            }
    
    priority_list = []
    remaining_phases = set(not_assessed)
    
    two_phase_samples = sorted(
        [(s, d) for s, d in sample_coverage.items() if d['is_two_phase'] and not d['is_na']],
        key=lambda x: (-len(x[1]['covered']), x[0])
    )
    
    for sample, data in two_phase_samples:
        if not remaining_phases:
            break
        covered = remaining_phases & data['covered']
        if covered:
            all_phases = list(sample_phases.get(sample, set()))
            priority_list.append((sample, sorted(covered), all_phases))
            remaining_phases -= covered
    
    three_phase_samples = sorted(
        [(s, d) for s, d in sample_coverage.items() if not d['is_two_phase'] and not d['is_na']],
        key=lambda x: (-len(x[1]['covered']), x[0])
    )
    
    for sample, data in three_phase_samples:
        if not remaining_phases:
            break
        covered = remaining_phases & data['covered']
        if covered:
            all_phases = list(sample_phases.get(sample, set()))
            priority_list.append((sample, sorted(covered), all_phases))
            remaining_phases -= covered
    
    na_samples_list = sorted(
        [(s, d) for s, d in sample_coverage.items() if d['is_na']],
        key=lambda x: x[0]
    )
    
    for sample, data in na_samples_list:
        if not remaining_phases:
            break
        all_phases = ['NA']
        priority_list.append((sample, [], all_phases))
    
    min_samples = []
    min_remaining = set(not_assessed)
    
    sorted_by_coverage = sorted(
        sample_coverage.items(),
        key=lambda x: (-len(x[1]['covered']), x[0])
    )
    
    for sample, data in sorted_by_coverage:
        if not min_remaining:
            break
        covered = min_remaining & data['covered']
        if covered:
            all_phases = list(sample_phases.get(sample, set()))
            min_samples.append((sample, sorted(covered), all_phases))
            min_remaining -= covered
    
    return priority_list, min_samples


def show_results_popup(
    analyzed_phases: Set[str],
    analyzed_phase_samples: Dict[str, Set[str]],
    all_ternary_phases: Set[str],
    not_assessed: Set[str],
    sample_phases: Dict[str, Set[str]],
    phase_samples: Dict[str, Set[str]],
    priority_recommendations: List[Tuple[str, List[str], List[str]]],
    min_recommendations: List[Tuple[str, List[str], List[str]]]
):
    """Show popup window with analysis results and recommendations."""
    root = tk.Tk()
    root.title("XRD Assignment Results")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.95)
    window_height = int(screen_height * 0.9)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text="XRD Assignment Complete", font=("Arial", 16, "bold")).pack(pady=(0, 15))
    
    notebook = ttk.Notebook(main_frame)
    notebook.pack(fill=tk.BOTH, expand=True, pady=10)
    
    analyzed_frame = ttk.Frame(notebook, padding="10")
    notebook.add(analyzed_frame, text="All Phases")
    
    create_all_phases_list(
        analyzed_frame, analyzed_phases, analyzed_phase_samples,
        all_ternary_phases, not_assessed, sample_phases, phase_samples
    )
    
    priority_frame = ttk.Frame(notebook, padding="10")
    notebook.add(priority_frame, text="Two-Phase Priority")
    
    create_recommendation_list(priority_frame, priority_recommendations, not_assessed, "Prioritizes 2-phase samples first, then 3-phase, then NA samples")
    
    min_frame = ttk.Frame(notebook, padding="10")
    notebook.add(min_frame, text="Minimum Samples")
    
    create_recommendation_list(min_frame, min_recommendations, not_assessed, "Minimizes number of samples")
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=15)
    
    ttk.Button(button_frame, text="Close", command=root.destroy, width=15).pack()
    
    root.mainloop()


def create_all_phases_list(
    parent, analyzed_phases: Set[str], analyzed_phase_samples: Dict[str, Set[str]],
    all_ternary_phases: Set[str], not_assessed: Set[str],
    sample_phases: Dict[str, Set[str]], phase_samples: Dict[str, Set[str]]
):
    """Create list of all phases with analyzed/not analyzed status and candidate samples."""
    list_frame = ttk.Frame(parent)
    list_frame.pack(fill=tk.BOTH, expand=True)
    
    scrollbar = ttk.Scrollbar(list_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    text_widget = tk.Text(list_frame, font=("Arial", 10), yscrollcommand=scrollbar.set, wrap=tk.WORD)
    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=text_widget.yview)
    
    text_widget.tag_config("bold", font=("Arial", 10, "bold"))
    text_widget.tag_config("normal", font=("Arial", 10))
    text_widget.tag_config("na", font=("Arial", 10, "italic"))
    
    ternary_not_analyzed = sorted(all_ternary_phases & not_assessed)
    ternary_analyzed = sorted(all_ternary_phases & analyzed_phases)
    
    text_widget.insert(tk.END, "TERNARY PHASES - NOT ANALYZED BY XRD\n", "bold")
    text_widget.insert(tk.END, "=" * 50 + "\n", "normal")
    
    for phase in ternary_not_analyzed:
        samples = phase_samples.get(phase, set())
        if samples:
            sorted_samples = sorted(samples, key=extract_sample_number)
            sample_strs = []
            for s in sorted_samples:
                num_phases = len(sample_phases.get(s, set()))
                sample_strs.append(f"{s}({num_phases})")
            text_widget.insert(tk.END, f"{phase} → {', '.join(sample_strs)}\n", "normal")
        else:
            text_widget.insert(tk.END, f"{phase} → no samples\n", "normal")
    
    na_samples = phase_samples.get('NA', set())
    if na_samples:
        sorted_na = sorted(na_samples, key=extract_sample_number)
        sample_strs = []
        for s in sorted_na:
            num_phases = len(sample_phases.get(s, set()))
            sample_strs.append(f"{s}({num_phases})")
        text_widget.insert(tk.END, f"\nNA (unidentified phase) → {', '.join(sample_strs)}\n", "na")
    
    text_widget.insert(tk.END, "\nTERNARY PHASES - ANALYZED BY XRD\n", "bold")
    text_widget.insert(tk.END, "=" * 50 + "\n", "normal")
    
    for phase in ternary_analyzed:
        samples = analyzed_phase_samples.get(phase, set())
        if samples:
            sorted_samples = sorted(samples, key=extract_sample_number)
            text_widget.insert(tk.END, f"{phase} ({', '.join(sorted_samples)})\n", "bold")
    
    text_widget.config(state=tk.DISABLED)


def create_recommendation_list(parent, recommendations, not_assessed, description):
    """Create recommendation list widget with formatting."""
    ttk.Label(parent, text=description, font=("Arial", 10)).pack(anchor="w", pady=(0, 5))
    
    list_frame = ttk.Frame(parent)
    list_frame.pack(fill=tk.BOTH, expand=True)
    
    scrollbar = ttk.Scrollbar(list_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    text_widget = tk.Text(list_frame, font=("Arial", 11), yscrollcommand=scrollbar.set, height=15, wrap=tk.WORD)
    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=text_widget.yview)
    
    text_widget.tag_config("bold", font=("Arial", 11, "bold"))
    text_widget.tag_config("normal", font=("Arial", 11))
    text_widget.tag_config("na", font=("Arial", 11, "italic"))
    
    if not recommendations:
        text_widget.insert(tk.END, "No recommendations available")
        return
    
    for sample, not_assessed_in_sample, all_phases in recommendations:
        text_widget.insert(tk.END, f"{sample} (")
        
        for i, phase in enumerate(all_phases):
            if phase == 'NA':
                text_widget.insert(tk.END, "{NA}", "na")
            else:
                text_widget.insert(tk.END, phase)
            if i < len(all_phases) - 1:
                text_widget.insert(tk.END, ", ")
        
        text_widget.insert(tk.END, ") → ")
        
        if not not_assessed_in_sample:
            text_widget.insert(tk.END, "covers all remaining phases\n", "normal")
            continue
        
        for i, phase in enumerate(not_assessed_in_sample):
            if phase in not_assessed:
                text_widget.insert(tk.END, f"[{phase}]", "bold")
            else:
                text_widget.insert(tk.END, phase)
            if i < len(not_assessed_in_sample) - 1:
                text_widget.insert(tk.END, ", ")
        
        text_widget.insert(tk.END, "\n")
    
    text_widget.config(state=tk.DISABLED)


def load_phase_associations_from_table(phase_table_path: Path) -> Tuple[Dict[str, List[str]], List[str]]:
    """
    Load existing phase associations from phase_table.
    
    Args:
        phase_table_path: Path to phase_table.xlsx
        
    Returns:
        Tuple of:
        - Dict mapping sample_id -> [phase_1, phase_2, phase_3] or sample_id -> []
        - List of phase notes in format "temp_number-phase-note"
    """
    data, _, phase_notes = load_phase_table_data(phase_table_path)
    
    sample_phases = {}
    for row in data:
        sample = row['sample']
        phase = row.get('phase', 'NA')
        if phase and phase != 'NA':
            if sample not in sample_phases:
                sample_phases[sample] = []
            sample_phases[sample].append(phase)
    
    return sample_phases, phase_notes


def save_phase_associations_to_table(
    phase_table_path: Path,
    sample_phases: Dict[str, List[str]],
    xrd_samples: Set[str],
    phase_notes: List[str] = None
):
    """
    Save phase associations back to phase_table.
    
    Args:
        phase_table_path: Path to phase_table.xlsx
        sample_phases: Dict mapping sample_id -> [phase_1, phase_2, phase_3]
        xrd_samples: Set of XRD-marked sample IDs
        phase_notes: List of notes in format "temp_number-phase-note"
    """
    if phase_notes is None:
        phase_notes = []
    
    try:
        wb = load_workbook(phase_table_path)
        ws = wb.active
        
        bold_font = Font(bold=True)
        normal_font = Font(bold=False)
        
        for row_idx in range(3, ws.max_row + 1):
            sample_cell = ws.cell(row=row_idx, column=1)
            sample_val = sample_cell.value
            
            if sample_val is None or str(sample_val).strip() == "":
                continue
            
            sample_str = str(sample_val).strip()
            
            phase_col = ws.cell(row=row_idx, column=5)
            
            if sample_str in sample_phases:
                phases = sample_phases[sample_str]
                if phases:
                    phase_col.value = phases[0]
            else:
                phase_col.value = "NA"
            
            if sample_str in xrd_samples:
                sample_cell.font = bold_font
            else:
                sample_cell.font = normal_font
        
        wb.save(phase_table_path)
        wb.close()
        
        save_xrd_info(phase_table_path, {
            "xrd_samples": sorted(list(xrd_samples)),
            "phase_notes": sorted(phase_notes)
        })
        
        log_info(f"Saved phase associations to {phase_table_path}")
        
    except Exception as e:
        log_error(f"Failed to save phase associations: {e}")


def add_phase_note(note: str, phase_table_path: Path, temp: str) -> bool:
    """
    Add a note for a specific phase. The note is stored in format "temp_number-phase-note".
    
    Args:
        note: The note text to add
        phase_table_path: Path to phase_table.xlsx
        temp: Temperature string (e.g., "500C")
        
    Returns:
        True if successful
    """
    if "-" not in note:
        log_warning(f"Note format should be 'phase-note', got: {note}")
        return False
    
    parts = note.split("-", 1)
    phase = parts[0]
    note_text = parts[1] if len(parts) > 1 else ""
    
    formatted_note = f"{temp}-{phase}-{note_text}"
    
    data, xrd_samples, phase_notes = load_phase_table_data(phase_table_path)
    
    if formatted_note not in phase_notes:
        phase_notes.append(formatted_note)
        save_phase_table_with_bold(phase_table_path, data, xrd_samples, phase_notes)
        log_info(f"Added phase note: {formatted_note}")
        return True
    
    log_warning(f"Note already exists: {formatted_note}")
    return False


def get_phase_notes(phase: str, phase_notes: List[str]) -> List[str]:
    """
    Get all notes for a specific phase from the phase_notes list.
    
    Args:
        phase: Phase name to filter notes for
        phase_notes: List of notes in format "temp_number-phase-note"
        
    Returns:
        List of notes matching the phase
    """
    return [n for n in phase_notes if n.endswith(f"-{phase}") or f"-{phase}-" in n]


def remove_phase_note(note: str, phase_table_path: Path, temp: str) -> bool:
    """
    Remove a note for a specific phase.
    
    Args:
        note: The note text to remove (will be matched against full format internally)
        phase_table_path: Path to phase_table.xlsx
        temp: Temperature string
        
    Returns:
        True if successful
    """
    data, xrd_samples, phase_notes = load_phase_table_data(phase_table_path)
    
    note_to_remove = None
    
    if "-" in note:
        parts = note.split("-", 1)
        phase = parts[0]
        formatted = f"{temp}-{phase}-{parts[1] if len(parts) > 1 else ''}"
        for n in phase_notes:
            if n == formatted:
                note_to_remove = n
                break
    
    if note_to_remove:
        phase_notes.remove(note_to_remove)
        save_phase_table_with_bold(phase_table_path, data, xrd_samples, phase_notes)
        log_info(f"Removed phase note: {note_to_remove}")
        return True
    
    return False
