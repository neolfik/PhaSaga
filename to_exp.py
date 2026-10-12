import os
import re
import csv
import numpy as np
import pandas as pd
from termcolor import colored
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from typing import List, Tuple, Optional, Dict
from constants import (
    MIN_REQUIRED_MEAN_ROWS,
    EXP_FIRST_ELEMENT_ROW,
    EXP_FIRST_ELEMENT_COL,
    EXP_COMPOSITION_DECIMAL_PLACES,
    REPORT_DAT_PATTERN,
    PHASE_TABLE_PATTERN,
    THREE_ELEMENT_THRESHOLD
)
from logging_config import log_info, log_warning, log_error, log_file_processed, log_file_skipped


## Write phases to the .exp file in the format from phases.py
def write_phases_to_exp(exp_file, phases_data: Optional[List], elements_order: List[str]):
    """
    Write theoretical phases to the .exp file.
    Handles both regular phases and range phases (solid solution lines).
    
    Args:
        exp_file: File object to write to
        phases_data: List of phase data tuples (can be 2 or 3 elements)
                     - 2 elements: (phase_name, composition_array) for regular phases
                     - 3 elements: (phase_name, midpoint_composition, (endpoint1, endpoint2)) for range phases
        elements_order: Element order from the Excel file (alphabetical)
    """
    if not phases_data or not elements_order or len(elements_order) != 3:
        return
    
    first_el = elements_order[0]
    second_el = elements_order[1]
    third_el = elements_order[2]
    
    binary_groups = {}  # key: (elA, elB) -> list of (C1, C2, phase_name, is_range, endpoint2)
    ternary_list = []    # list of (C1, C2, phase_name, is_range, endpoint2)
    
    seen_phases = set()
    
    for phase_data in phases_data:
        if len(phase_data) == 2:
            phase_name, composition = phase_data
            is_range = False
            endpoint2 = None
        elif len(phase_data) >= 3:
            phase_name, composition, endpoints = phase_data
            is_range = True
            endpoint2 = endpoints[1] if isinstance(endpoints, tuple) else None
        else:
            continue
        
        if phase_name in seen_phases:
            continue
        seen_phases.add(phase_name)
        
        C1 = composition[0]
        C2 = composition[1]
        
        nonzero_indices = [i for i, c in enumerate(composition) if c > 0]
        num_elements = len(nonzero_indices)
        
        if num_elements == 1:
            continue
        elif num_elements == 2:
            nonzero_elements = [elements_order[i] for i in nonzero_indices]
            a, b = nonzero_elements
            key = (a, b) if a < b else (b, a)
            if key not in binary_groups:
                binary_groups[key] = []
            binary_groups[key].append((C1, C2, phase_name, is_range, endpoint2))
        elif num_elements == 3:
            ternary_list.append((C1, C2, phase_name, is_range, endpoint2))
    
    exp_file.write("\n$Phases generated from phase list\n")
    exp_file.write("$binary phases\n")
    
    for key in sorted(binary_groups.keys()):
        elA, elB = key
        exp_file.write(f"${elA} {elB}\n")
        for C1, C2, ph, is_range, ep2 in binary_groups[key]:
            exp_file.write(f"{C1:.4f} {C2:.4f} N'{ph}\n")
            if is_range and ep2 is not None:
                ep2_C1 = ep2[0]
                ep2_C2 = ep2[1]
                exp_file.write(f"{ep2_C1:.4f} {ep2_C2:.4f} s7\n")
            else:
                exp_file.write(f"{C1:.4f} {C2:.4f} s7\n")
        exp_file.write("\n")
    
    exp_file.write("\n$ternary phases\n")
    exp_file.write(f"$ {first_el} {second_el} {third_el}\n")
    for C1, C2, ph, is_range, ep2 in ternary_list:
        exp_file.write(f"{C1:.4f} {C2:.4f} N'{ph}\n")
        if is_range and ep2 is not None:
            ep2_C1 = ep2[0]
            ep2_C2 = ep2[1]
            exp_file.write(f"{ep2_C1:.4f} {ep2_C2:.4f} s7\n")
        else:
            exp_file.write(f"{C1:.4f} {C2:.4f} s7\n")
    
    exp_file.write("\n")


def load_phase_names_from_report(report_path: str) -> dict:
    """
    Read phase names from existing REPORT .dat file.
    
    Args:
        report_path: Path to the REPORT .dat file
    
    Returns:
        Dict mapping sample_id -> [phase_1_name, phase_2_name, phase_3_name]
    """
    phase_names_map = {}
    if not os.path.exists(report_path):
        log_warning(f"REPORT file not found: {report_path}")
        return phase_names_map
    
    try:
        with open(report_path, 'r') as f:
            reader = csv.reader(f, delimiter='\t')
            for row in reader:
                if len(row) < 16:
                    continue
                sample_id = row[0].strip()
                if not sample_id or sample_id.startswith('$'):
                    continue
                phase_1 = row[7].strip() if len(row) > 7 else ""
                phase_2 = row[11].strip() if len(row) > 11 else ""
                phase_3 = row[15].strip() if len(row) > 15 else ""
                phase_names_map[sample_id] = [phase_1, phase_2, phase_3]
    except Exception as e:
        log_warning(f"Failed to read REPORT file {report_path}: {e}")
    
    return phase_names_map


## manipulates the composition format to have sum of 1 instead of 100
def divide_round(num: float) -> float:
    """
    Convert composition percentage to fraction and round to 4 decimal places.
    
    Args:
        num: Composition value as percentage (0-100)
    
    Returns:
        Composition as fraction (0-1), rounded to 4 decimal places
    """
    try:
        fl = float(num)
        fl = fl / 100
        return round(fl, EXP_COMPOSITION_DECIMAL_PLACES)
    except (ValueError, TypeError):
        log_warning(f"Invalid composition value: {num}, using 0.0")
        return 0.0

## Creates .exp file containting sample data from .xlsx file, the generation will go through if the program can find sheets
# corresponding to samples (aka one sheet one sample) and then cells containing the word 'mean', it will then go from left to right 
# in each of the detected sheets and the first mean found will be considered as the mean of overall composition
def create_exp_from_xlsx(xlsx_path: str, output_dir: str, 
                         phases_data: Optional[List[Tuple[str, np.ndarray]]] = None,
                         elements_order: Optional[List[str]] = None):
    """
    Create .exp, .dat report files and phase table from SEM results Excel file.
    
    Args:
        xlsx_path: Path to Excel file with SEM results
        output_dir: Directory to write output files
    """
    try:
        # Use ExcelFile for on-demand sheet parsing (lower memory usage)
        excel_file = pd.ExcelFile(xlsx_path)
        sheets = excel_file.sheet_names
    except Exception as e:
        log_error(f"Failed to read Excel file {xlsx_path}: {e}", exc_info=True)
        return
    pure_filename = os.path.splitext(os.path.basename(os.path.normpath(xlsx_path)))[0][12:]
    
    # Extract system and temperature from filename
    # pure_filename format: {system}_{temp}
    filename_parts = pure_filename.rsplit('_', 1)
    system_name = filename_parts[0] if len(filename_parts) > 0 else ""
    temp = filename_parts[1] if len(filename_parts) > 1 else ""
    
    # Create report and exp file paths using pattern
    report_filename = REPORT_DAT_PATTERN.format(name=pure_filename)
    report_path = os.path.join(output_dir, report_filename)
    exp_path = os.path.join(output_dir, f"{pure_filename}.exp")
    
    # Phase table data collection
    phase_table_data = []
    elements_list = []
    
    # Remove any duplicate report
    try:
        os.remove(report_path)
        log_warning(f"Removed duplicate report file {report_path}")
    except FileNotFoundError:
        log_info("Creating new report file")

    is_headers = False
    headers = None  # Initialize headers to avoid unbound error

    # Same CSV writer logic, just .dat extension
    with open(report_path, "w", newline="") as report, open(exp_path, "w") as exp:
        writer = csv.writer(report, delimiter='\t')  # tab-separated for .dat readability

        exp.write(f"ROLOG 1 {pure_filename}\n\n")
        exp.write("DIAGRAM_TYPE TRIULAR YES YES\n\n")
        exp.write(f"DATASET 1 {pure_filename}\n\n")
        exp.write("$ triangles - SEM measurement\n")
        is_written = False
        captured_elements = None  # Will hold [first_el, second_el, third_el]

        for sheet_name in sheets:
            # Read sheet on-demand (memory efficient)
            df = excel_file.parse(sheet_name)
            csvfile = df.astype(str).fillna("").values.tolist()

            mean_rows = []
            for i, row in enumerate(csvfile):
                for j, cell in enumerate(row):
                    if str(cell).strip().lower() == "mean" and j < 19:  # Using hardcoded 19 as per original
                        mean_rows.append((i, j))

            # Extract the three element names dynamically with validation
            try:
                first_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL]
                second_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL + 1]
                third_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL + 2]
                if not elements_list:
                    elements_list = [first_el, second_el, third_el]
                    captured_elements = elements_list  # Capture for phase writing
            except IndexError:
                log_error(f"Sheet {sheet_name}: Cannot extract element names from expected positions")
                writer.writerow([sheet_name, "IGNORED - INVALID FORMAT"])
                continue

            if not is_headers:
                headers = [
                    "sample", "status", "phases", "overall",
                    first_el, second_el, third_el, "phase_1_name",
                    first_el, second_el, third_el, "phase_2_name",
                    first_el, second_el, third_el, "phase_3_name",
                    first_el, second_el, third_el
                ]
                writer.writerow(headers)
                is_headers = True

            if len(mean_rows) < MIN_REQUIRED_MEAN_ROWS:
                log_file_skipped(sheet_name, f"not enough 'mean' rows (found {len(mean_rows)}, need {MIN_REQUIRED_MEAN_ROWS})")
                writer.writerow([sheet_name, "IGNORED"])
                continue

            mean_rows.sort(key=lambda x: x[1])
            mean_values = []
            for idx, (i, j) in enumerate(mean_rows):
                try:
                    vals = [
                        float(csvfile[i][j + 1]),
                        float(csvfile[i][j + 2]),
                        float(csvfile[i][j + 3])
                    ]
                    mean_values.append(vals)
                except (ValueError, IndexError) as e:
                    log_warning(f"Sheet {sheet_name}, mean row {idx}: Failed to parse values: {e}")
                    pass

            # Extract phase names from cluster blocks
            # Row 3, columns H(8), M(13), R(18) contain phase names or NA
            phase_names = ["NA", "NA", "NA"]  # Default for 3 clusters
            phase_col_indices = [7, 12, 17]  # 0-based indices for H, M, R
            
            # Check row 3 (index 2) for phase names
            if len(csvfile) > 2:
                row_3 = csvfile[1]
                for idx, col_idx in enumerate(phase_col_indices):
                    if col_idx < len(row_3):
                        cell_val = str(row_3[col_idx]).strip() if row_3[col_idx] else ""
                        if cell_val and cell_val != "NA":
                            phase_names[idx] = cell_val

            if len(mean_values) < MIN_REQUIRED_MEAN_ROWS:
                log_file_skipped(sheet_name, f"invalid or incomplete mean data (got {len(mean_values)} valid rows)")
                writer.writerow([sheet_name, "IGNORED"])
                continue

            overall = mean_values[0]
            phases = mean_values[1:]
            
            # Collect data for phase table - T_No format: {temp}_{sample_number}
            sample_t_no = f"{temp}_{sheet_name}"
            overall_comp = [round(overall[0], 2), round(overall[1], 2), round(overall[2], 2)]
            
            # Add row for each phase
            for phase_idx, phase_comp in enumerate(phases):
                if phase_idx < len(phase_names):
                    phase_table_data.append({
                        'sample': sample_t_no,
                        'overall': overall_comp,
                        'phase_name': phase_names[phase_idx],
                        'phase_comp': [round(phase_comp[0], 2), round(phase_comp[1], 2), round(phase_comp[2], 2)]
                    })
                    # Only write overall on first row
                    overall_comp = ["", "", ""]
                    sample_t_no = ""

            if not is_written:
                exp.write(f"$ PLOTTED COLUMNS ARE : x%({first_el}), x%({second_el})\n\n")
                exp.write("BLOCK X=C1; Y=C2; GOC=C3,WAMB;\n\n")
                exp.write("ATTRIBUTE CENTER\nCLIP OFF\nFONT 2\nCHARSIZE 0.4\nLINETYPE 1\n")
                exp.write(f"$unary\n${first_el}\t{second_el}\n")
                exp.write(f"1.0000\t0.0000\tN'{first_el}\n1.0000\t0.0000\ts7\n")
                exp.write(f"0.0000\t1.0000\tN'{second_el}\n0.0000\t1.0000\ts7\n")
                exp.write(f"0.0000\t0.0000\tN'{third_el}\n0.0000\t0.0000\ts7\n\n")
                
                # Write phases before samples if phases_data is provided
                write_phases_to_exp(exp, phases_data, captured_elements)
                
                exp.write("$samples\n")
                is_written = True

            exp.write(f"COLOR\t6\n")
            t_no = f"{temp}_{sheet_name}"
            exp.write(f"$ {pure_filename}_{t_no} overall composition:\n")
            exp.write(f"${first_el}\t{second_el}\n")
            exp.write(f"{divide_round(overall[0])}\t{divide_round(overall[1])}\tN'{t_no}\n")
            exp.write(f"{divide_round(overall[0])}\t{divide_round(overall[1])}\ts7\n\n")

            exp.write("$phase composition:\n")
            exp.write(f"${first_el}\t{second_el}\n")
            for k, phase in enumerate(phases, start=1):
                x = divide_round(phase[0])
                y = divide_round(phase[1])
                label = "S100" if k == 1 else "DS100"
                exp.write(f"{x}\t{y}\t{label}\n")
            exp.write(f"{divide_round(phases[0][0])}\t{divide_round(phases[0][1])}\tDS100\n$\n$\n")

            row = [
                f"{temp}_{sheet_name}", "OK",
                len(phases), "",
                round(overall[0], 2), round(overall[1], 2), round(overall[2], 2)
            ]
            for idx, phase in enumerate(phases):
                phase_name = phase_names[idx] if idx < len(phase_names) else "NA"
                row.extend([
                    phase_name, round(phase[0], 2), round(phase[1], 2), round(phase[2], 2)
                ])
            # Ensure headers is defined before using it
            if headers is not None:
                while len(row) < len(headers):
                    row.append("")
            writer.writerow(row)

            log_file_processed(sheet_name, f"{len(phases)} phases")

        exp.write("\n\nBLOCKEND\n\nTOP_LAYER_ITEM")

    log_info(f".exp file successfully created at {exp_path}")
    log_info(f"Report saved at {report_path}")
    
    # Create phase table
    if phase_table_data and elements_list:
        create_phase_table_xlsx(phase_table_data, elements_list, output_dir, pure_filename)


def create_exp_with_phase_prediction(xlsx_path: str, output_dir: str,
                                     phases_data: Optional[List[Tuple[str, np.ndarray]]] = None,
                                     cluster_phase_mapping: Optional[dict] = None,
                                     elements_order: Optional[List[str]] = None,
                                     report_path: Optional[str] = None):
    """
    Create second .exp file with phase prediction/substitution.
    
    Uses theoretical phase compositions for identified phases, keeps measured
    compositions for NA (unidentified) phases.
    
    Args:
        xlsx_path: Path to Excel file with SEM results
        output_dir: Directory to write output file
        phases_data: List of (phase_name, composition_array) tuples
        cluster_phase_mapping: Dict mapping sample_id -> [phase_name_1, phase_name_2, phase_name_3]
        elements_order: Element order [first_el, second_el, third_el] (sorted/alphabetical)
        report_path: Path to existing REPORT .dat file for phase name fallback
    """
    if not phases_data or not cluster_phase_mapping:
        log_info("Skipping phase prediction .exp file (no phases or mappings)")
        return
    
    report_phase_names = load_phase_names_from_report(report_path) if report_path else {}
    
    # Reuse most of the logic from create_exp_from_xlsx, but substitute phase compositions
    try:
        excel_file = pd.ExcelFile(xlsx_path)
        sheets = excel_file.sheet_names
    except Exception as e:
        log_error(f"Failed to read Excel file for prediction {xlsx_path}: {e}", exc_info=True)
        return
    
    pure_filename = os.path.splitext(os.path.basename(os.path.normpath(xlsx_path)))[0][12:]
    filename_parts = pure_filename.rsplit('_', 1)
    system_name = filename_parts[0] if len(filename_parts) > 0 else ""
    temp = filename_parts[1] if len(filename_parts) > 1 else ""
    
    from constants import EXP_FILE_PATTERN_PREDICTION
    exp_path = os.path.join(output_dir, EXP_FILE_PATTERN_PREDICTION.format(system=system_name, temp=temp))
    
    captured_elements = None
    
    # First pass: get element order from Excel file
    for sheet_name in sheets:
        df = excel_file.parse(sheet_name)
        csvfile = df.astype(str).fillna("").values.tolist()
        
        try:
            first_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL]
            second_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL + 1]
            third_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL + 2]
            captured_elements = [first_el, second_el, third_el]
            break  # Get elements from first sheet only
        except IndexError:
            continue
    
    if not captured_elements:
        log_error("Could not extract element order from Excel file")
        return
    
    # Elements are now always alphabetical, so phases are already in correct order
    
    # Create phase name -> composition lookup (now in Excel element order)
    # Handle both regular phases and range phases
    phase_composition_map = {}
    for phase_data in phases_data:
        if len(phase_data) >= 2:
            phase_name, composition = phase_data[:2]
            phase_composition_map[phase_name] = composition
    
    with open(exp_path, "w") as exp:
        exp.write(f"ROLOG 1 {pure_filename}_phase_predic\n\n")
        exp.write("DIAGRAM_TYPE TRIULAR YES YES\n\n")
        exp.write(f"DATASET 1 {pure_filename}_phase_predic\n\n")
        exp.write("$ triangles - SEM measurement with phase predictions\n")
        is_written = False
        
        for sheet_name in sheets:
            df = excel_file.parse(sheet_name)
            csvfile = df.astype(str).fillna("").values.tolist()
            
            mean_rows = []
            for i, row in enumerate(csvfile):
                for j, cell in enumerate(row):
                    if str(cell).strip().lower() == "mean" and j < 19:
                        mean_rows.append((i, j))
            
            # Extract elements
            try:
                first_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL]
                second_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL + 1]
                third_el = csvfile[EXP_FIRST_ELEMENT_ROW][EXP_FIRST_ELEMENT_COL + 2]
                if not captured_elements:
                    captured_elements = [first_el, second_el, third_el]
            except IndexError:
                continue
            
            if len(mean_rows) < MIN_REQUIRED_MEAN_ROWS:
                continue
            
            mean_rows.sort(key=lambda x: x[1])
            mean_values = []
            for idx, (i, j) in enumerate(mean_rows):
                try:
                    vals = [
                        float(csvfile[i][j + 1]),
                        float(csvfile[i][j + 2]),
                        float(csvfile[i][j + 3])
                    ]
                    mean_values.append(vals)
                except (ValueError, IndexError):
                    pass
            
            if len(mean_values) < MIN_REQUIRED_MEAN_ROWS:
                continue
            
            overall = mean_values[0]
            phases = mean_values[1:]
            
            # Get phase names for this sample
            sample_id = f"{temp}_{sheet_name}"
            phase_names = cluster_phase_mapping.get(sample_id, ["NA", "NA", "NA"])
            
            # Check REPORT file for NA phases (as fallback)
            report_phases = report_phase_names.get(sample_id, [])
            for i in range(min(3, len(phase_names))):
                if phase_names[i] == "NA" and i < len(report_phases):
                    report_phase = report_phases[i]
                    if report_phase and report_phase != "NA":
                        phase_names[i] = report_phase
                        log_info(f"{sample_id} cluster {i+1}: Using phase name from REPORT: {report_phase}")
            
            if not is_written:
                exp.write(f"$ PLOTTED COLUMNS ARE : x%({first_el}), x%({second_el})\n\n")
                exp.write("BLOCK X=C1; Y=C2; GOC=C3,WAMB;\n\n")
                exp.write("ATTRIBUTE CENTER\nCLIP OFF\nFONT 2\nCHARSIZE 0.4\nLINETYPE 1\n")
                exp.write(f"$unary\n${first_el}\t{second_el}\n")
                exp.write(f"1.0000\t0.0000\tN'{first_el}\n1.0000\t0.0000\ts7\n")
                exp.write(f"0.0000\t1.0000\tN'{second_el}\n0.0000\t1.0000\ts7\n")
                exp.write(f"0.0000\t0.0000\tN'{third_el}\n0.0000\t0.0000\ts7\n\n")
                
                # Write phases (same as original)
                write_phases_to_exp(exp, phases_data, captured_elements)
                
                exp.write("$samples\n")
                is_written = True
            
            exp.write(f"COLOR\t6\n")
            t_no = f"{temp}_{sheet_name}"
            exp.write(f"$ {pure_filename}_{t_no} overall composition:\n")
            exp.write(f"${first_el}\t{second_el}\n")
            exp.write(f"{divide_round(overall[0])}\t{divide_round(overall[1])}\tN'{t_no}\n")
            exp.write(f"{divide_round(overall[0])}\t{divide_round(overall[1])}\ts7\n\n")
            
            exp.write("$phase composition (with predictions):\n")
            exp.write(f"${first_el}\t{second_el}\n")
            
            # PHASE SUBSTITUTION LOGIC - use theoretical composition for three-element phases
            for k, (measured_phase, phase_name) in enumerate(zip(phases, phase_names), start=1):
                is_three_element = all(c > THREE_ELEMENT_THRESHOLD for c in measured_phase)
                if phase_name != "NA" and phase_name in phase_composition_map and is_three_element:
                    theoretical_comp = phase_composition_map[phase_name]
                    x = divide_round(theoretical_comp[0] * 100)
                    y = divide_round(theoretical_comp[1] * 100)
                    log_info(f"{sample_id} cluster {k}: Using theoretical composition for {phase_name} (3 elements)")
                else:
                    x = divide_round(measured_phase[0])
                    y = divide_round(measured_phase[1])
                    if phase_name == "NA":
                        log_info(f"{sample_id} cluster {k}: Using measured composition for {phase_name}")
                    elif not is_three_element:
                        log_info(f"{sample_id} cluster {k}: Using measured composition for {phase_name} (2 or fewer elements)")
                
                label = "S100" if k == 1 else "DS100"
                exp.write(f"{x}\t{y}\t{label}\n")
            
            # Triangle closing line
            if phases:
                first_phase_is_three = all(c > THREE_ELEMENT_THRESHOLD for c in phases[0])
                if phase_names[0] != "NA" and phase_names[0] in phase_composition_map and first_phase_is_three:
                    theoretical_comp = phase_composition_map[phase_names[0]]
                    x = divide_round(theoretical_comp[0] * 100)
                    y = divide_round(theoretical_comp[1] * 100)
                else:
                    x = divide_round(phases[0][0])
                    y = divide_round(phases[0][1])
                exp.write(f"{x}\t{y}\tDS100\n$\n$\n")
        
        exp.write("\n\nBLOCKEND\n\nTOP_LAYER_ITEM")
    
    log_info(f"Phase prediction .exp file created at {exp_path}")


def create_phase_table_xlsx(phase_data: List[dict], elements: List[str], output_dir: str, pure_filename: str):
    """
    Create phase table xlsx file from collected data.
    
    Args:
        phase_data: List of dicts with sample, overall, phase_name, phase_comp
        elements: List of element names
        output_dir: Output directory
        pure_filename: System/temp filename base
    """
    try:
        # Determine system name and temp from filename
        # pure_filename format: {system}_{temp}
        parts = pure_filename.rsplit('_', 1)
        system_name = parts[0] if len(parts) > 0 else ""
        temp = parts[1] if len(parts) > 1 else ""
        
        phase_table_filename = PHASE_TABLE_PATTERN.format(system=system_name, temp=temp)
        phase_table_path = os.path.join(output_dir, phase_table_filename)
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        
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
        ws['B2'] = elements[0] if len(elements) > 0 else ""
        ws['C2'] = elements[1] if len(elements) > 1 else ""
        ws['D2'] = elements[2] if len(elements) > 2 else ""
        ws['F2'] = elements[0] if len(elements) > 0 else ""
        ws['G2'] = elements[1] if len(elements) > 1 else ""
        ws['H2'] = elements[2] if len(elements) > 2 else ""
        
        # Write data rows
        current_row = 3
        for data in phase_data:
            ws.cell(row=current_row, column=1, value=data.get('sample', ''))
            
            overall = data.get('overall', [])
            ws.cell(row=current_row, column=2, value=overall[0] if len(overall) > 0 else "")
            ws.cell(row=current_row, column=3, value=overall[1] if len(overall) > 1 else "")
            ws.cell(row=current_row, column=4, value=overall[2] if len(overall) > 2 else "")
            
            ws.cell(row=current_row, column=5, value=data.get('phase_name', 'NA'))
            
            phase_comp = data.get('phase_comp', [])
            ws.cell(row=current_row, column=6, value=phase_comp[0] if len(phase_comp) > 0 else "")
            ws.cell(row=current_row, column=7, value=phase_comp[1] if len(phase_comp) > 1 else "")
            ws.cell(row=current_row, column=8, value=phase_comp[2] if len(phase_comp) > 2 else "")
            
            current_row += 1
        
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
        
        wb.save(phase_table_path)
        log_info(f"Phase table created: {phase_table_path}")
        
    except Exception as e:
        log_error(f"Failed to create phase table: {e}", exc_info=True)


def update_predic_exp_for_samples(
    exp_path: str,
    sample_updates: Dict[str, List[str]],
    phase_composition_map: Dict[str, np.ndarray],
    elements_order: List[str]
) -> bool:
    """
    Update specific sample entries in existing phase_predic.exp file.
    Only changes samples that were reassociated.
    
    Logic for each updated sample:
    - For each cluster with assigned phase:
      - If phase != "NA" AND phase is ternary (all 3 elements > 0.1%):
        Use theoretical composition from phase_composition_map
      - Else: Use measured/overall composition (keep existing)
    - Keep theoretical phases section unchanged
    - Only update $samples section for modified samples
    
    Args:
        exp_path: Path to existing phase_predic.exp file
        sample_updates: Dict mapping sample_id -> [phase1, phase2, phase3]
        phase_composition_map: Dict mapping phase_name -> composition_array
        elements_order: Element order [first_el, second_el, third_el]
        
    Returns:
        True if successful
    """
    THREE_ELEMENT_THRESHOLD = 0.001
    
    try:
        with open(exp_path, 'r') as f:
            lines = f.readlines()
        
        output_lines = []
        in_samples_section = False
        current_sample_id = None
        sample_buffer = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if line.strip().startswith("$samples"):
                in_samples_section = True
                output_lines.append(line)
                i += 1
                continue
            
            if in_samples_section:
                if line.startswith("$ ") and "overall composition:" in line:
                    match = re.search(r'\$(\w+)_(\w+)_(\w+)\s+overall', line)
                    if match:
                        sample_id = f"{match.group(2)}_{match.group(3)}"
                        current_sample_id = sample_id
                        sample_buffer = [line]
                        
                        if sample_id in sample_updates:
                            phases = sample_updates[sample_id]
                            phase_comp_lines = []
                            
                            j = i + 1
                            while j < len(lines) and not lines[j].startswith("$ "):
                                sample_buffer.append(lines[j])
                                if "phase composition" in lines[j].lower():
                                    j += 1
                                    while j < len(lines) and not lines[j].startswith("$ "):
                                        phase_comp_lines.append(lines[j])
                                        sample_buffer.append(lines[j])
                                        j += 1
                                    break
                                j += 1
                            
                            output_lines.extend(sample_buffer)
                            
                            if phase_comp_lines:
                                output_lines.append("$phase composition (with predictions):\n")
                                output_lines.append(f"${elements_order[0]}\t${elements_order[1]}\n")
                                
                                for k, phase_name in enumerate(phases, start=1):
                                    measured = phase_comp_lines[k] if k < len(phase_comp_lines) else "0.0000\t0.0000\tS100\n"
                                    
                                    if phase_name != "NA" and phase_name in phase_composition_map:
                                        theoretical = phase_composition_map[phase_name]
                                        x = round(theoretical[0], 4)
                                        y = round(theoretical[1], 4)
                                        label = "S100" if k == 1 else "DS100"
                                        output_lines.append(f"{x:.4f}\t{y:.4f}\t{label}\n")
                                    else:
                                        output_lines.append(measured)
                                
                                while j < len(lines) and not lines[j].startswith("$ "):
                                    j += 1
                                i = j
                                continue
                            else:
                                i += 1
                                continue
                        else:
                            output_lines.extend(sample_buffer)
                            i += 1
                            continue
                    else:
                        output_lines.append(line)
                        i += 1
                elif line.startswith("$ "):
                    output_lines.append(line)
                    i += 1
                else:
                    output_lines.append(line)
                    i += 1
            else:
                output_lines.append(line)
                i += 1
        
        with open(exp_path, 'w') as f:
            f.writelines(output_lines)
        
        log_info(f"Updated phase_predic.exp with {len(sample_updates)} sample(s)")
        return True
        
    except Exception as e:
        log_error(f"Failed to update phase_predic.exp: {e}")
        return False

