"""
Module for managing phase files - creating, validating, and loading phase data
for visualization in clustering diagrams.
"""

import re
import json
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set
from logging_config import log_info, log_warning, log_error
from phases import parse_formula, normalize, parse_phase_formula, is_range_formula, normalize_range_compositions
from input_list_test import get_validated_list
from constants import PHASE_LIST_GUI_ENABLED, PHASE_LIST_VERIFY_EXISTING, MASTER_PHASES_FILE


def validate_phase_name(phase_name: str, system_elements: List[str]) -> Tuple[bool, str]:
    """
    Validate that a phase name contains only the system elements with optional numbers.
    Supports both regular phases (e.g., "In2La3Ni") and range phases (e.g., "In1.5-1.75LaNi0.5-0.25").
    
    Args:
        phase_name: Phase formula (e.g., "In2La3Ni", "InLa", "In", "In1.5-1.75LaNi0.5-0.25")
        system_elements: List of allowed elements (e.g., ["In", "La", "Ni"])
    
    Returns:
        Tuple of (is_valid, error_message)
        - (True, "") if valid
        - (False, error_message) if invalid
    
    Examples:
        >>> validate_phase_name("In2La3Ni", ["In", "La", "Ni"])
        (True, "")
        >>> validate_phase_name("CuZn", ["In", "La", "Ni"])
        (False, "Contains elements not in system: Cu, Zn")
        >>> validate_phase_name("In1.5-1.75LaNi0.5-0.25", ["In", "La", "Ni"])
        (True, "")
    """
    # Strip whitespace
    phase_name = phase_name.strip()
    
    if not phase_name:
        return False, "Phase name is empty"
    
    # Try to parse the formula (handles both regular and range)
    try:
        parsed_data, is_range = parse_phase_formula(phase_name)
    except Exception as e:
        return False, f"Invalid format: {str(e)}"
    
    if is_range:
        composition_dict = parsed_data["endpoint1"]
        # For range phases, also check endpoint2 elements
        endpoint2_elements = set(parsed_data["endpoint2"].keys())
    else:
        composition_dict = parsed_data
        endpoint2_elements = set()
    
    if not composition_dict:
        return False, "Could not parse phase formula"
    
    # Check if all elements in the phase are in the system
    phase_elements = set(composition_dict.keys())
    allowed_elements = set(system_elements)
    
    invalid_elements = phase_elements - allowed_elements
    if invalid_elements:
        return False, f"Contains elements not in system: {', '.join(sorted(invalid_elements))}"
    
    # Also check endpoint2 elements if it's a range
    invalid_elements2 = endpoint2_elements - allowed_elements
    if invalid_elements2:
        return False, f"Contains elements not in system: {', '.join(sorted(invalid_elements2))}"
    
    return True, ""


def compute_phase_composition(
    phase_name: str,
    system_elements: List[str]
) -> Optional[np.ndarray]:
    """
    Compute normalized composition for a phase.
    
    Args:
        phase_name: Phase formula (e.g., "In2La2Ni")
        system_elements: Ordered list of system elements (e.g., ["In", "La", "Ni"])
    
    Returns:
        Numpy array of normalized compositions in the order of system_elements,
        or None if parsing fails.
        For range phases, returns the midpoint of the range.
    """
    try:
        # Parse and check if range
        parsed_data, is_range = parse_phase_formula(phase_name)
        
        if is_range:
            # For range phases, compute midpoint composition
            ep1, ep2 = normalize_range_compositions(parsed_data, system_elements)
            midpoint = (ep1 + ep2) / 2.0
            return midpoint
        else:
            normalized = normalize(parsed_data)
            composition_array = np.array([
                normalized.get(elem, 0.0) for elem in system_elements
            ])
            return composition_array
        
    except Exception as e:
        log_error(f"Failed to compute composition for {phase_name}: {e}")
        return None


def get_range_phase_endpoints(
    phase_name: str,
    system_elements: List[str]
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Get the two endpoint compositions for a range phase.
    
    Args:
        phase_name: Range phase formula (e.g., "In1.5-1.75LaNi0.5-0.25")
        system_elements: Ordered list of system elements
    
    Returns:
        Tuple of (endpoint1_array, endpoint2_array) as numpy arrays,
        or None if not a range phase or parsing fails.
    """
    try:
        if not is_range_formula(phase_name):
            return None
        
        parsed_data, is_range = parse_phase_formula(phase_name)
        if not is_range:
            return None
        
        ep1, ep2 = normalize_range_compositions(parsed_data, system_elements)
        return (ep1, ep2)
        
    except Exception as e:
        log_error(f"Failed to get range endpoints for {phase_name}: {e}")
        return None


def is_phase_range(phase_name: str) -> bool:
    """
    Check if a phase name represents a range phase.
    
    Args:
        phase_name: Phase formula string
    
    Returns:
        True if the phase is a range phase
    """
    return is_range_formula(phase_name)


def get_phase_file_path(system_name: str, base_path: str) -> Path:
    """
    Get the path to the phases file for a system.
    
    Args:
        system_name: System name (e.g., "InLaNi")
        base_path: Base directory path
    
    Returns:
        Path to phases_{system}.txt file in system folder
    """
    from constants import PHASE_FILE_PATTERN
    filename = PHASE_FILE_PATTERN.format(system=system_name)
    return Path(base_path) / system_name / filename


def create_phase_file_interactive(
    system_name: str,
    system_elements: List[str],
    output_path: Path
) -> bool:
    """
    Launch interactive GUI to create a phase file with validation.
    
    Args:
        system_name: System name for display
        system_elements: List of allowed elements
        output_path: Path where to save the phase file
    
    Returns:
        True if file was created, False if user cancelled
    """
    log_info(f"Launching interactive phase list builder for system {system_name}")
    log_info(f"Allowed elements: {', '.join(system_elements)}")
    
    system_display = f"{system_name} ({', '.join(system_elements)})"
    
    # Custom validation function for phases
    def phase_validator(phase_name: str) -> tuple:
        is_valid, error_msg = validate_phase_name(phase_name, system_elements)
        return is_valid, error_msg
    
    # Launch GUI
    try:
        phase_list = get_validated_list(
            initial_list=[],
            validation_func=phase_validator,
            system_name=system_display
        )
        
        if not phase_list:
            log_warning("No phases entered. Phase file not created.")
            return False
        
        # Save to file (one phase per line)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            for phase in phase_list:
                f.write(f"{phase}\n")
        
        log_info(f"Created phase file with {len(phase_list)} phases: {output_path}")
        return True
        
    except Exception as e:
        log_error(f"Failed to create phase file interactively: {e}", exc_info=True)
        return False


def get_master_phases_path(base_path: str) -> Path:
    """
    Get the path to the master phases file in the project folder.
    
    Args:
        base_path: Base directory path (not used, kept for compatibility)
    
    Returns:
        Path to master_phases.json file in the project folder
    """
    # Store master_phases.json in the project folder (where the script is)
    # instead of the data folder
    return Path(__file__).parent / MASTER_PHASES_FILE


def load_master_phases(base_path: str) -> Dict[str, List[str]]:
    """
    Load master phases dictionary from JSON file.
    
    Args:
        base_path: Base directory path
    
    Returns:
        Dictionary mapping element -> list of phases containing that element
        Returns empty dict if file doesn't exist
    """
    master_file = get_master_phases_path(base_path)
    
    if not master_file.exists():
        log_info("Master phases file not found, creating empty")
        return {}
    
    try:
        with open(master_file, 'r', encoding='utf-8') as f:
            master_dict = json.load(f)
        log_info(f"Loaded master phases with {len(master_dict)} elements")
        return master_dict
    except Exception as e:
        log_error(f"Failed to load master phases file: {e}")
        return {}


def save_master_phases(master_dict: Dict[str, List[str]], base_path: str):
    """
    Save master phases dictionary to JSON file.
    
    Args:
        master_dict: Dictionary mapping element -> list of phases
        base_path: Base directory path
    """
    master_file = get_master_phases_path(base_path)
    
    try:
        with open(master_file, 'w', encoding='utf-8') as f:
            json.dump(master_dict, f, indent=2, sort_keys=True)
        log_info(f"Saved master phases with {len(master_dict)} elements")
    except Exception as e:
        log_error(f"Failed to save master phases file: {e}")


def update_master_phases(phase_list: List[str], master_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Add new phases to master dictionary and deduplicate.
    
    Args:
        phase_list: List of phase names to add
        master_dict: Existing master dictionary
    
    Returns:
        Updated master dictionary (deduplicated)
    """
    for phase_name in phase_list:
        try:
            # Parse the formula to extract elements
            parsed_data, is_range = parse_phase_formula(phase_name)
            
            if is_range:
                elements_in_phase = list(parsed_data["endpoint1"].keys())
            else:
                elements_in_phase = list(parsed_data.keys())
            
            # Add this phase to the list for each element it contains
            for elem in elements_in_phase:
                if elem not in master_dict:
                    master_dict[elem] = []
                if phase_name not in master_dict[elem]:
                    master_dict[elem].append(phase_name)
        
        except Exception as e:
            log_warning(f"Failed to parse phase '{phase_name}' for master dict: {e}")
    
    # Deduplicate each element's list
    for elem in master_dict:
        master_dict[elem] = list(dict.fromkeys(master_dict[elem]))
    
    return master_dict


def remove_from_master_phases(phase_name: str, master_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Remove a phase from the master dictionary across all elements.
    
    Args:
        phase_name: Name of the phase to remove
        master_dict: Existing master dictionary
    
    Returns:
        Updated master dictionary with phase removed from all element lists
    """
    try:
        # Parse to find which elements this phase contains
        parsed_data, is_range = parse_phase_formula(phase_name)
        
        if is_range:
            elements_in_phase = list(parsed_data["endpoint1"].keys())
        else:
            elements_in_phase = list(parsed_data.keys())
        
        # Remove from each element's list
        for elem in elements_in_phase:
            if elem in master_dict and phase_name in master_dict[elem]:
                master_dict[elem].remove(phase_name)
                log_info(f"Removed '{phase_name}' from master list for element '{elem}'")
        
        # Clean up empty element lists
        empty_elements = [elem for elem, phases in master_dict.items() if not phases]
        for elem in empty_elements:
            del master_dict[elem]
        
    except Exception as e:
        log_warning(f"Failed to remove phase '{phase_name}' from master dict: {e}")
    
    return master_dict


def initialize_master_phases_from_systems(base_path: str) -> Dict[str, List[str]]:
    """
    Initialize master phases file by scanning all system phase files.
    This should only be called once when MASTER_PHASE_FILE_INITIATED is False.
    
    Args:
        base_path: Base directory path
    
    Returns:
        Dictionary mapping element -> list of phases
    """
    log_info("Initializing master phases from existing system files...")
    
    base_path_obj = Path(base_path)
    master_dict: Dict[str, List[str]] = {}
    
    # Scan for all system directories
    if not base_path_obj.exists():
        log_warning(f"Base path does not exist: {base_path}")
        return master_dict
    
    system_count = 0
    phase_count = 0
    
    for system_dir in base_path_obj.iterdir():
        if not system_dir.is_dir():
            continue
        
        system_name = system_dir.name
        phase_file = system_dir / f"phases_{system_name}.txt"
        
        if not phase_file.exists():
            continue
        
        try:
            with open(phase_file, 'r', encoding='utf-8') as f:
                phase_lines = [line.strip() for line in f if line.strip()]
            
            if phase_lines:
                system_count += 1
                phase_count += len(phase_lines)
                master_dict = update_master_phases(phase_lines, master_dict)
                log_info(f"Loaded {len(phase_lines)} phases from {system_name}")
        
        except Exception as e:
            log_warning(f"Failed to load phases from {phase_file}: {e}")
    
    log_info(f"Master phases initialized: {system_count} systems, {phase_count} total phases")
    log_info(f"Master dict contains {len(master_dict)} unique elements")
    
    return master_dict


def get_phases_for_system_from_master(
    system_elements: List[str],
    master_dict: Dict[str, List[str]]
) -> List[str]:
    """
    Get phases from master dict that contain only the system elements.
    Filters to include phases with 1, 2, or 3 elements (pure phases, binary, and ternary).
    
    Args:
        system_elements: List of system elements (e.g., ["In", "La", "Ni"])
        master_dict: Master phases dictionary
    
    Returns:
        List of phase names that contain exclusively system elements and have 1-3 elements
    """
    # Collect all phases that contain any of the system elements
    candidate_phases: Set[str] = set()
    
    for elem in system_elements:
        if elem in master_dict:
            candidate_phases.update(master_dict[elem])
    
    # Filter to only phases that contain EXCLUSIVELY system elements
    # and have 1, 2, or 3 elements (pure, binary, or ternary)
    system_elements_set = set(system_elements)
    valid_phases = []
    
    for phase_name in candidate_phases:
        try:
            parsed_data, is_range = parse_phase_formula(phase_name)
            
            if is_range:
                phase_elements = set(parsed_data["endpoint1"].keys())
            else:
                phase_elements = set(parsed_data.keys())
            
            num_elements = len(phase_elements)
            
            # Check if all elements in the phase are in the system
            # AND the phase contains 1, 2, or 3 elements
            if phase_elements.issubset(system_elements_set) and 1 <= num_elements <= 3:
                valid_phases.append(phase_name)
        
        except Exception as e:
            log_warning(f"Failed to parse phase '{phase_name}': {e}")
    
    return valid_phases


def load_phases_for_system(
    system_name: str,
    system_elements: List[str],
    base_path: str,
    create_if_missing: bool = True
) -> List[Tuple[str, np.ndarray]]:
    """
    Load phases from file for a system. Creates file interactively if missing.
    Optionally prompts for verification via GUI based on settings.
    
    Args:
        system_name: System name (e.g., "InLaNi")
        system_elements: Ordered list of system elements
        base_path: Base directory path
        create_if_missing: If True, launch GUI to create file if it doesn't exist
    
    Returns:
        List of (phase_name, composition_array) tuples for regular phases,
        or (phase_name, composition_array, (endpoint1, endpoint2)) tuples for range phases.
        Returns empty list if file doesn't exist and creation was cancelled/failed
    
    Note:
        Uses lenient validation - warns about invalid phases but includes them anyway
        (as per requirements: "lenient approach")
    """
    phase_file = get_phase_file_path(system_name, base_path)
    
    should_launch_gui = False
    phase_list = []
    
    # Check if file exists
    if not phase_file.exists():
        if create_if_missing:
            log_info(f"Phase file not found for system {system_name}")
            if PHASE_LIST_GUI_ENABLED:
                should_launch_gui = True
            else:
                created = create_phase_file_interactive(system_name, system_elements, phase_file)
                if not created:
                    log_info("Phase file creation cancelled or failed. Proceeding without phases.")
                    return []
        else:
            log_info(f"Phase file not found for {system_name}: {phase_file}")
            return []
    else:
        # File exists - check if we should verify/modify it
        if PHASE_LIST_GUI_ENABLED and PHASE_LIST_VERIFY_EXISTING:
            log_info(f"Phase file exists for {system_name}: {phase_file}")
            should_launch_gui = True
    
    # Initialize master phases if needed (MOVED BEFORE GUI to show existing phases)
    from constants import MASTER_PHASE_FILE_INITIATED
    master_file_path = get_master_phases_path(base_path)
    
    if not MASTER_PHASE_FILE_INITIATED and not master_file_path.exists():
        log_info("Master phase file not initiated, initializing from existing systems...")
        master_dict = initialize_master_phases_from_systems(base_path)
        save_master_phases(master_dict, base_path)
        
        # Update the constant - Note: This changes the module variable but won't persist across runs
        # The file will be created and subsequent calls will skip initialization
        import constants
        constants.MASTER_PHASE_FILE_INITIATED = True
    else:
        # Load existing master phases
        master_dict = load_master_phases(base_path)
    
    # Store original phases before GUI for later comparison
    original_phases_before_gui = []
    if phase_file.exists():
        try:
            with open(phase_file, 'r', encoding='utf-8') as f:
                original_phases_before_gui = [line.strip() for line in f if line.strip()]
        except Exception:
            pass
    
    # Launch GUI if needed to create or verify phases
    if should_launch_gui:
        try:
            # Use the already loaded original phases
            existing_phases = original_phases_before_gui
            
            # Get phases from master file that are relevant to this system
            master_phases_for_system = get_phases_for_system_from_master(system_elements, master_dict)
            log_info(f"Found {len(master_phases_for_system)} phases in master file for system {system_elements}")
            
            # Merge master phases with system file phases (remove duplicates and sort)
            all_existing_phases = sorted(set(existing_phases + master_phases_for_system))
            
            if master_phases_for_system:
                log_info(f"Merging {len(existing_phases)} system phases with {len(master_phases_for_system)} master phases -> {len(all_existing_phases)} total unique phases")
            
            # Launch GUI with combined list from both sources
            system_display = f"{system_name} ({', '.join(system_elements)})"
            
            # Create callback for removing from master
            def remove_callback(phase_name: str):
                nonlocal master_dict
                master_dict = remove_from_master_phases(phase_name, master_dict)
                save_master_phases(master_dict, base_path)
            
            phase_list = get_validated_list(
                initial_list=all_existing_phases,
                validation_func=lambda p: validate_phase_name(p, system_elements),
                system_name=system_display,
                remove_from_master_callback=remove_callback
            )
            
            if phase_list is not None and len(phase_list) > 0:
                # Save the phases to file
                with open(phase_file, 'w', encoding='utf-8') as f:
                    for phase in phase_list:
                        f.write(f"{phase}\n")
                log_info(f"Saved {len(phase_list)} phases to {phase_file}")
            else:
                log_info("No phases entered. Proceeding without phases.")
                return []
                
        except Exception as e:
            log_error(f"Failed to launch phase list GUI: {e}")
            if not phase_file.exists():
                return []
    
    # Load and parse phases from file
    try:
        with open(phase_file, 'r', encoding='utf-8') as f:
            phase_lines = [line.strip() for line in f if line.strip()]
        
        if not phase_lines:
            log_warning(f"Phase file is empty: {phase_file}")
            phase_lines = []
        
        # Store original phases for comparison
        original_phases = phase_lines.copy()
        
        # Add pure elements at the beginning if not already in the list
        pure_elements = [elem for elem in system_elements[:3]]  # Support up to 3 elements for ternary
        existing_phases_set = set(phase_lines)
        phases_to_add = [p for p in pure_elements if p not in existing_phases_set]
        
        if phases_to_add:
            phase_lines = phases_to_add + phase_lines
            log_info(f"Added pure elements to phase list: {phases_to_add}")
        
        # Get phases from master dict that match this system
        master_phases_for_system = get_phases_for_system_from_master(system_elements, master_dict)
        log_info(f"Found {len(master_phases_for_system)} phases in master file for system {system_elements}")
        
        # Add phases from master that aren't in the system's list
        existing_phases_set = set(phase_lines)
        master_phases_to_add = [p for p in master_phases_for_system if p not in existing_phases_set]
        
        if master_phases_to_add:
            phase_lines.extend(master_phases_to_add)
            log_info(f"Added {len(master_phases_to_add)} phases from master file: {', '.join(master_phases_to_add)}")
        else:
            log_info("No new phases to add from master file (all already in system phase list)")
        
        # Remove duplicates and sort alphabetically
        phase_lines = sorted(set(phase_lines))
        
        # If phases were added from GUI, update master with NEW phases only
        if phase_list and len(phase_list) > 0:
            # Compare with phases that existed BEFORE the GUI was shown
            new_phases = [p for p in phase_list if p not in original_phases_before_gui]
            if new_phases:
                log_info(f"Updating master file with {len(new_phases)} new phases from GUI: {', '.join(new_phases)}")
                master_dict = update_master_phases(new_phases, master_dict)
                save_master_phases(master_dict, base_path)
        
        # Save updated system file if changes were made
        if phase_lines != original_phases:
            with open(phase_file, 'w', encoding='utf-8') as f:
                for phase in phase_lines:
                    f.write(f"{phase}\n")
            log_info(f"Updated system phase file with {len(phase_lines)} phases (was {len(original_phases)})")
        
        phases_data = []
        invalid_count = 0
        
        for phase_name in phase_lines:
            # Validate (lenient - warn but continue)
            is_valid, error_msg = validate_phase_name(phase_name, system_elements)
            if not is_valid:
                log_warning(f"Invalid phase '{phase_name}': {error_msg} (including anyway)")
                invalid_count += 1
            
            # Check if it's a range phase
            if is_phase_range(phase_name):
                endpoints = get_range_phase_endpoints(phase_name, system_elements)
                composition = compute_phase_composition(phase_name, system_elements)
                if composition is not None and endpoints is not None:
                    phases_data.append((phase_name, composition, endpoints))
                else:
                    log_warning(f"Could not compute composition/endpoints for phase '{phase_name}' (skipping)")
            else:
                # Regular phase
                composition = compute_phase_composition(phase_name, system_elements)
                if composition is not None:
                    phases_data.append((phase_name, composition))
                else:
                    log_warning(f"Could not compute composition for phase '{phase_name}' (skipping)")
        
        log_info(f"Loaded {len(phases_data)} phases for {system_name} " +
                (f"({invalid_count} with validation warnings)" if invalid_count > 0 else ""))
        
        return phases_data
        
    except Exception as e:
        log_error(f"Failed to load phase file {phase_file}: {e}", exc_info=True)
        return []


def format_phases_for_display(phases_data: List[Tuple[str, np.ndarray]]) -> str:
    """
    Format phase data for logging/display.
    
    Args:
        phases_data: List of (phase_name, composition) tuples
    
    Returns:
        Formatted string
    """
    if not phases_data:
        return "No phases"
    
    lines = []
    for phase_name, composition in phases_data:
        comp_str = ", ".join([f"{c:.3f}" for c in composition])
        lines.append(f"  {phase_name}: [{comp_str}]")
    
    return "\n".join(lines)
