from pathlib import Path
from openpyxl import Workbook
from typing import Dict, Optional
from constants import (
    REPORTS_FOLDER_NAME, 
    DIAGRAMS_FOLDER_NAME,
    SAMPLE_FOLDER_PREFIX,
    SEM_RESULTS_PATTERN,
    PHASE_TABLE_PATTERN,
    EXP_FILE_PATTERN
)
from logging_config import log_structure_created, log_debug

# Adds entry into the structure dict
def add_to_structure(structure: Dict, sys_name: str, temp, base_path: Path) -> Dict:
    """Add a system/temperature entry to the structure dictionary."""
    path = str(base_path / sys_name)
    entry = structure.setdefault(sys_name, {"temps": [], "path": path})
    if temp not in entry["temps"]:
        entry["temps"].append(temp)
    return structure

## Creates folder structure based on dict obtained by analyzing the report names in the original folder 
# where the reports were located.

## The new structure is:
# {sys_name}/
#   {temp}/
#      SEM_results_{sys_name}_{temp}.xlsx
#      phase_table_{sys_name}_{temp}.xlsx
#      {sys_name}_{temp}.exp
#      diagrams/                    <- NEW: ternary diagram images
#      reports/                     <- Reports folder
#         sample_{N}/               <- Sample-specific folders inside reports
#            {sys_name}_{temp}_{N}a.docx
#            {sys_name}_{temp}_{N}b.docx
#            ...
def create_structure(base_path: str, sys_name: str, temp: int, structure: Dict, 
                    sample_number: Optional[int] = None) -> Dict:
    """
    Create folder structure for a system/temperature combination.
    
    Args:
        base_path: Base directory path
        sys_name: System name (e.g., "InSbZn")
        temp: Temperature value
        structure: Existing structure dictionary
        sample_number: Optional sample number to create sample-specific folder
    
    Returns:
        Updated structure dictionary
    """
    base_path_p = Path(base_path)
    temp_path = base_path_p / sys_name / str(temp)
    
    # Create diagrams folder
    diagrams_path = temp_path / DIAGRAMS_FOLDER_NAME
    diagrams_path.mkdir(parents=True, exist_ok=True)
    log_structure_created(str(diagrams_path), "diagrams folder")
    
    # Create main reports folder
    reports_path = temp_path / REPORTS_FOLDER_NAME
    reports_path.mkdir(parents=True, exist_ok=True)
    
    # Create sample-specific folder inside reports/ if sample_number provided
    if sample_number is not None:
        sample_path = reports_path / f"{temp}_{sample_number}"
        sample_path.mkdir(parents=True, exist_ok=True)
        log_structure_created(str(sample_path), "sample reports folder")

    # Create valid workbooks if missing
    sem_results = SEM_RESULTS_PATTERN.format(system=sys_name, temp=temp)
    phase_table = PHASE_TABLE_PATTERN.format(system=sys_name, temp=temp)
    
    for fname in (sem_results, phase_table):
        fpath = temp_path / fname
        if not fpath.exists():
            wb = Workbook()
            ws = wb.active
            if ws is not None:
                ws.title = "Sheet1"
            wb.save(fpath)
            log_structure_created(str(fpath), "workbook")

    # .exp as text placeholder
    exp_file = EXP_FILE_PATTERN.format(system=sys_name, temp=temp)
    exp_path = temp_path / exp_file
    if not exp_path.exists():
        exp_path.write_text("# EXP placeholder\n")
        log_structure_created(str(exp_path), "exp file")

    return add_to_structure(structure or {}, sys_name, temp, base_path_p)

def get_sample_reports_path(base_path: str, sys_name: str, temp: int, sample_number: int) -> Path:
    """
    Get the reports path for a specific sample.
    
    Args:
        base_path: Base directory path
        sys_name: System name
        temp: Temperature value
        sample_number: Sample number
    
    Returns:
        Path to sample reports folder (inside main reports folder)
    """
    base_path_p = Path(base_path)
    return base_path_p / sys_name / str(temp) / REPORTS_FOLDER_NAME / f"{temp}_{sample_number}"

def get_diagrams_path(base_path: str, sys_name: str, temp: int) -> Path:
    """
    Get the diagrams path for a system/temperature.
    
    Args:
        base_path: Base directory path
        sys_name: System name
        temp: Temperature value
    
    Returns:
        Path to diagrams folder
    """
    base_path_p = Path(base_path)
    return base_path_p / sys_name / str(temp) / DIAGRAMS_FOLDER_NAME
