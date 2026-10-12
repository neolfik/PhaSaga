import re
from collections import OrderedDict
from typing import Tuple, List, Dict
import numpy as np

## From formula in shape La2Ni3Sn gets the elements and numbers
def parse_formula(formula):
    parts = re.findall(r"([A-Z][a-z]?)(\d*\.?\d*)", formula)
    d = {}
    for el, num in parts:
        # If num == '' → default = 1.0
        val = float(num) if num else 1.0
        d[el] = d.get(el, 0.0) + val
    return d


def is_range_formula(formula: str) -> bool:
    """
    Check if a formula represents a range phase (e.g., 'In1.5-1.75LaNi0.5-0.25').
    
    A range formula has the pattern where after an element and number, there is
    a dash followed by another number before the next element.
    
    Args:
        formula: Phase formula string
        
    Returns:
        True if the formula represents a range phase
    """
    pattern = r"[A-Z][a-z]?\d*\.?\d*-\d*\.?\d*"
    return bool(re.search(pattern, formula))


def parse_range_formula(formula: str) -> dict:
    """
    Parse a range phase formula like 'In1.5-1.75LaNi0.5-0.25' into two composition dictionaries.
    
    The format is: ElementValue1-Value2 followed by next ElementValue1-Value2, etc.
    Example: In1.5-1.75LaNi0.5-0.25
      - In: 1.5 to 1.75
      - La: Ni (not present) → use 0.5-0.25... wait, let me check: In1.5-1.75LaNi0.5-0.25
      
    Actually looking at the format more carefully:
    - In1.5-1.75 means In goes from 1.5 to 1.75
    - LaNi0.5-0.25 means La goes from Ni (typo?) or...
    
    Let me reconsider. The format seems to be:
    In1.5-1.75LaNi0.5-0.25
    Could mean:
    - In: 1.5-1.75 (range)
    - LaNi: 0.5-0.25 (range for each?)
    
    Actually looking at it again: In1.5-1.75LaNi0.5-0.25
    - The '-' is a separator between two composition points
    - Point 1: In=1.5, La=0.5, Ni=1.0 (if we assume total atoms)
    - Point 2: In=1.75, La=0.25, Ni=0.5
    
    Or more likely with fractions:
    - In1.5-1.75 means In ranges from 1.5 to 1.75 (in atomic fraction units)
    - LaNi0.5-0.25 means... hmm, this is confusing.
    
    Let me try a different interpretation:
    The formula `In1.5-1.75LaNi0.5-0.25` could be parsed as:
    - In: min=1.5, max=1.75
    - LaNi0.5-0.25 → La: 0.5, Ni: 0.25? Or LaNi: 0.5-0.25 range?
    
    Actually I think the format is:
    ElementMin-Max for each element
    In1.5-1.75 (In from 1.5 to 1.75)
    LaNi0.5-0.25 (La from 0.5, Ni from 0.25... but wait, where's the separator?)
    
    Let me parse it character by character:
    I n 1 . 5 - 1 . 7 5 L a N i 0 . 5 - 0 . 2 5
    
    After In1.5-1.75 we have LaNi0.5-0.25
    - La Ni0.5-0.25 → La with no number = 1.0, Ni from 0.5 to 0.25?
    
    OR the format could be:
    Element1Min-MaxElement2Min-Max...
    In1.5-1.75 (In: 1.5 to 1.75)
    LaNi0.5-0.25 (LaNi: 0.5 to 0.25, meaning La and Ni both range from 0.5 to 0.25?)
    
    Hmm, let me try yet another interpretation:
    In1.5-1.75LaNi0.5-0.25 could be:
    - In: 1.5-1.75
    - La: Ni0.5-0.25 → this doesn't make sense unless La and Ni are grouped
    
    Let me assume the format is:
    ElementMin-Max means that element has composition ranging from Min to Max
    When multiple elements are present, they represent a solid solution line
    
    Example: In1.5-1.75LaNi0.5-0.25
    - In1.5 → In has value 1.5
    - -1.75 → separator to next value 1.75
    - LaNi0.5 → La has value 0.5
    - -0.25 → separator to next value 0.25
    
    So the full interpretation:
    Point 1: In=1.5, La=0.5, Ni (missing, assume 0?)
    Point 2: In=1.75, La=0.25, Ni (missing, assume 0?)
    
    Wait, but Ni is mentioned... In1.5-1.75LaNi0.5-0.25
    After La there's Ni0.5-0.25
    
    So:
    - In1.5-1.75 → In: 1.5 to 1.75
    - LaNi0.5-0.25 → This could mean La and Ni together have 0.5 to 0.25
    
    Actually I think the format might be:
    Each Element is followed by its value or range
    Then the dash separates values for the SAME element across two points
    
    Let me try:
    In1.5-1.75LaNi0.5-0.25
    - Parse: Element, Number-Number, next Element, Number-Number
    - In: 1.5-1.75 (two values for In at two points)
    - LaNi0.5-0.25 → This is confusing...
    
    Actually I think the format is:
    E1V1-V2E2V3-V4 where V1-V2 are values for point 1 and point 2 of E1
    
    So for In1.5-1.75LaNi0.5-0.25:
    - In: point1=1.5, point2=1.75
    - LaNi0.5-0.25: This is LaNi followed by 0.5-0.25, so...
      - Maybe La has value 0.5 and Ni has value 0.25 as fixed values?
      - Or LaNi is treated as a combined symbol?
    
    Let me try a simpler approach: parse each element-number or element-number-number pair
    Pattern: Element Symbol followed by optional digits and decimal point
    In1.5-1.75LaNi0.5-0.25
    
    Matches:
    1. In1.5-1.75 → Element In with values 1.5 to 1.75
    2. LaNi0.5-0.25 → Element La with values 0.5 to 0.25... but wait, Ni is in between
    
    Actually I think the pattern might be:
    ElementValue1-Value2
    For In1.5-1.75LaNi0.5-0.25:
    - In: 1.5 to 1.75
    - LaNi0.5-0.25: La and Ni both have range 0.5-0.25?
    
    OR:
    - In1.5-1.75: In from 1.5 to 1.75
    - LaNi0.5-0.25: This should be parsed as La with 0.5 and Ni with 0.25 as the fixed point,
      but then -0.25 applies to who?
    
    Let me try yet another interpretation. Maybe the format is:
    ElementMinMax-ElementMinMax...
    Like In1.5-1.75LaNi0.5-0.25 means:
    - In: 1.5 (start), then 1.75 (end of range)
    - La: Ni0.5 (La=Ni value which is 0.5?) No...
    
    Let me look at it differently:
    In1.5-1.75LaNi0.5-0.25
    
    If I use regex to find all Element-Number patterns:
    - In1.5
    - 1.75 (not an element)
    - LaNi0.5
    - 0.25
    
    I think the safest interpretation is:
    - In1.5-1.75: In has a range from 1.5 to 1.75
    - LaNi0.5-0.25: LaNi is not a valid element, so maybe:
      - La with 0.5, and Ni with 0.25?
    
    Let me try: LaNi0.5-0.25 means:
    - La: Ni0.5 (no, doesn't work)
    - Or: La and Ni both have ranges: La from 0.5 to something, Ni from 0.25 to something
    
    Actually I think I finally understand:
    In1.5-1.75LaNi0.5-0.25 could be:
    - In1.5-1.75: In range 1.5-1.75
    - LaNi0.5: La and Ni both have value 0.5 (no range for them)
    - -0.25: This applies to...?
    
    Let me try a new approach. What if:
    In1.5-1.75LaNi0.5-0.25
    Is actually two separate formulas concatenated:
    Formula 1: In1.5LaNi0.5
    Formula 2: In1.75Ni0.25
    
    But that doesn't make sense with the structure...
    
    OK let me try one more interpretation:
    The dash `-` separates the two endpoint compositions
    Formula: In1.5-1.75LaNi0.5-0.25
    Split by dash position:
    - Before first dash: In1.5
    - After first dash, before second element: 1.75LaNi0.5
    - After second dash: 0.25
    
    So:
    Endpoint 1: In1.5, LaNi0.5 (La=0.5, Ni=0.5? No, Ni0.5 means Ni=0.5)
    But 1.75LaNi0.5 means In=1.75, La=Ni (?), Ni=0.5
    
    Actually I think the format might be simpler:
    In1.5-1.75LaNi0.5-0.25
    Means: (In: 1.5, La: 0.5) to (In: 1.75, Ni: 0.25)
    Where La and Ni are the second and third elements respectively
    
    So the parsing is:
    - In1.5-1.75: In goes from 1.5 to 1.75
    - LaNi0.5-0.25: La goes from 0.5 to 0 (implied?), Ni goes from 0 to 0.25?
    
    Actually, looking at the string again: In1.5-1.75LaNi0.5-0.25
    If I split by capital letters:
    - '' (empty)
    - 'In1.5-1.75'
    - 'LaNi0.5-0.25'
    
    So the formula has two main parts:
    1. In1.5-1.75 → In with range 1.5 to 1.75
    2. LaNi0.5-0.25 → La and Ni with range 0.5 to 0.25?
    
    If LaNi0.5-0.25 means La and Ni both have range 0.5 to 0.25:
    Point 1: In=1.5, La=0.5, Ni=0.5
    Point 2: In=1.75, La=0.25, Ni=0.25
    
    But that would mean La and Ni always have the same value, which seems unlikely.
    
    What if LaNi0.5-0.25 is parsed as:
    - La with value 0.5 (no range)
    - Ni with range 0.5 to 0.25
    
    Then:
    Point 1: In=1.5, La=0.5, Ni=0.5
    Point 2: In=1.75, La=0.5, Ni=0.25
    
    This makes more sense! It's a solid solution where In and Ni vary, but La is fixed.
    
    Let me implement this interpretation:
    - For each element-number pair, check if the number has a - in it
    - If yes, it's a range; if no, it's a fixed value
    - The dash separates the two endpoint values for that element
    """
    endpoint1 = {}
    endpoint2 = {}
    
    parts = re.findall(r"([A-Z][a-z]?)(\d*\.?\d*)(?:-(\d*\.?\d*))?", formula)
    
    for el, num1, num2 in parts:
        val1 = float(num1) if num1 else 1.0
        
        if num2:
            val2 = float(num2)
            endpoint1[el] = endpoint1.get(el, 0.0) + val1
            endpoint2[el] = endpoint2.get(el, 0.0) + val2
        else:
            endpoint1[el] = endpoint1.get(el, 0.0) + val1
            endpoint2[el] = endpoint2.get(el, 0.0) + val1
    
    return {
        "endpoint1": endpoint1,
        "endpoint2": endpoint2,
        "is_range": True
    }

## normalizes the data so that the sum is equal to one inpreparation for .exp data format
def normalize(comp_dict):
    total = sum(comp_dict.values())
    if total == 0:
        return {k: 0.0 for k in comp_dict}
    return {el: val / total for el, val in comp_dict.items()}


def parse_phase_formula(formula: str) -> Tuple[dict, bool]:
    """
    Parse a phase formula, detecting whether it's a range phase or regular phase.
    
    Args:
        formula: Phase formula string (e.g., 'In2LaNi', 'In1.5-1.75LaNi0.5-0.25')
    
    Returns:
        Tuple of (parsed_data, is_range)
        - For regular phases: ({'In': 2.0, 'La': 1.0, 'Ni': 1.0}, False)
        - For range phases: ({'endpoint1': {...}, 'endpoint2': {...}, 'is_range': True}, True)
    """
    if is_range_formula(formula):
        return parse_range_formula(formula), True
    else:
        return parse_formula(formula), False


def normalize_range_compositions(range_data: dict, system_elements: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Normalize range phase compositions for a given system.
    
    Args:
        range_data: Dict with 'endpoint1' and 'endpoint2' composition dicts
        system_elements: List of elements in the system order
    
    Returns:
        Tuple of (normalized_endpoint1, normalized_endpoint2) as numpy arrays
    """
    ep1 = range_data["endpoint1"]
    ep2 = range_data["endpoint2"]
    
    norm1 = normalize(ep1)
    norm2 = normalize(ep2)
    
    arr1 = np.array([norm1.get(el, 0.0) for el in system_elements])
    arr2 = np.array([norm2.get(el, 0.0) for el in system_elements])
    
    return arr1, arr2

## Reads phases.txt format to get the phases, This needs to be changed for the final integration.
def read_phase_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if len(lines) < 3:
        raise ValueError("phases.txt must contain at least 3 non-empty lines for the pure elements.")
    pure = lines[:3]
    phases = lines[3:]
    return pure, phases



## Generaes the .exp template with theoretical phases
def generate_template(pure, phases):
    # Headers
    system = "".join(pure)
    out_lines = []
    out_lines.append(f"ROLOG 1 {system}_literature")
    out_lines.append("")
    out_lines.append("DIAGRAM_TYPE TRIANGULAR YES YES")
    out_lines.append("")
    out_lines.append(f"DATASET 1 {system}_literature")
    out_lines.append("")
    out_lines.append("$ triangles - SEM measurement")
    out_lines.append(f"$ PLOTTED COLUMNS ARE : x%({pure[0]}), x%({pure[1]})")
    out_lines.append("")
    out_lines.append("BLOCK X=C1; Y=C2;       GOC=C3,WAMB;")
    out_lines.append("")
    out_lines.append("ATTRIBUTE CENTER")
    out_lines.append("CLIP OFF")
    out_lines.append("FONT 2")
    out_lines.append("CHARSIZE 0.4")
    out_lines.append("LINETYPE 1")
    out_lines.append("")
    # Unary block: coordinates in 2D barycentric projection: (1,0), (0,1), (0,0)
    out_lines.append("$unary")
    out_lines.append("$" + " ".join(pure))
    coords = [(1.0000, 0.0000), (0.0000, 1.0000), (0.0000, 0.0000)]
    for (x, y), el in zip(coords, pure):
        out_lines.append(f"{x:.4f}\t{y:.4f}\tN'{el}")
        out_lines.append(f"{x:.4f}\t{y:.4f}\ts7")
    out_lines.append("")  # blank line

    out_lines.append("$Phases generated from phase list")
    out_lines.append("$binary phases")

    # Collect binary + ternary phases.
    # Use OrderedDict to keep pair order stable (in order of first appearance).
    binary_groups = OrderedDict()  # key: (elA, elB) ordered by pure order -> list of (C1,C2,phase)
    ternary_list = []  # list of (C1, C2, phase)

    seen_phases = set()
    pure_elements_set = set(pure)

    for ph in phases:
        ph = ph.strip()
        if not ph:
            continue
        # Avoid duplicates
        if ph in seen_phases:
            continue
        seen_phases.add(ph)

        comp = parse_formula(ph)
        elements_in_phase = set(comp.keys())

        # Skip phases containing elements outside the pure-element set
        if not elements_in_phase.issubset(pure_elements_set):
            # skip silently
            continue

        norm = normalize(comp)
        # projection coordinates in our template: C1 = fraction of pure[0], C2 = fraction of pure[1]
        C1 = norm.get(pure[0], 0.0)
        C2 = norm.get(pure[1], 0.0)

        if len(elements_in_phase) == 1:
            # unary phase - already listed in unary section; optionally could be listed here, but skip
            continue
        elif len(elements_in_phase) == 2:
            a, b = list(elements_in_phase)
            # Order pair by position in pure elements list
            idx_a, idx_b = pure.index(a), pure.index(b)
            key = (a, b) if idx_a < idx_b else (b, a)
            if key not in binary_groups:
                binary_groups[key] = []
            binary_groups[key].append((C1, C2, ph))
        elif len(elements_in_phase) == 3:
            ternary_list.append((C1, C2, ph))
        else:
            # unusual case (more than 3 elements) - skip
            continue

    # Write binary groups in order of pure-elements appearance (sort keys accordingly)
    # Ensure ordering of keys consistent with pure order: produce keys sorted by index of first element
    def key_sorter(k):
        # return tuple indices for ordering pairs consistently
        return (pure.index(k[0]), pure.index(k[1]))
    sorted_binary_keys = sorted(binary_groups.keys(), key=key_sorter)

    for key in sorted_binary_keys:
        elA, elB = key
        out_lines.append(f"${elA} {elB}")
        for C1, C2, ph in binary_groups[key]:
            out_lines.append(f"{C1:.4f} {C2:.4f} N'{ph}")
            out_lines.append(f"{C1:.4f} {C2:.4f} s7")
        out_lines.append("")  # blank line between groups

    # Ternary phases
    out_lines.append("")
    out_lines.append("$ternary phases")
    out_lines.append("$" + " ".join(pure))
    for C1, C2, ph in ternary_list:
        out_lines.append(f"{C1:.4f} {C2:.4f} N'{ph}")
        out_lines.append(f"{C1:.4f} {C2:.4f} s7")
    out_lines.append("")
    out_lines.append("$samples")
    out_lines.append("")
    out_lines.append("BLOCKEND")
    out_lines.append("")
    out_lines.append("TOP_LAYER_ITEM")
    out_lines.append("")  # ensure trailing newline
    return "\n".join(out_lines)

# Crates a .exp file from a phase file
def create_theo_exp(phase_path, exp_path):
    pure, phases = read_phase_file(phase_path)
    exp_text = generate_template(pure, phases)
    with open(exp_path, 'w', encoding='utf-8') as f:
        f.write(exp_text)
    print(f"Generated {exp_path} from {phase_path}")
