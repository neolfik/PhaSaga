"""
Constants used throughout the phase association analysis.
Centralized location for magic numbers and configuration values.
"""

# ===== tables.py constants =====
# Mean detection in Excel sheets
MEAN_DETECTION_MAX_COL = 19  # Maximum column index to search for 'mean' keyword
MEAN_DETECTION_MIN_COL = 0   # Minimum column index for mean detection

# Normalization constants
MIN_NORMALIZATION_TOTAL = 0.1  # Minimum sum to consider valid for normalization
NORMALIZATION_WARNING_LOW = 90.0   # Warn if total composition < 90%
NORMALIZATION_WARNING_HIGH = 110.0  # Warn if total composition > 110%
HANDLE_NEGATIVE_VALUES = False  # If True, set negative values to 0 before normalization

# Image embedding constants (defaults, can be overridden by config.json)
DEFAULT_IMAGE_MIN_WIDTH_COLS = 4
DEFAULT_IMAGE_MAX_WIDTH_COLS = 8
DEFAULT_IMAGE_MAX_SIDE_BY_SIDE = 6

# Student coefficient file
STUDENT_COEFF_FILE = "student.csv"
STUDENT_COEFF_MAX_INDEX = 12  # Maximum index for t-value lookup

# ===== clustering.py constants =====
# DBSCAN clustering parameters
DEFAULT_EPS_MAX = 4.0          # Maximum epsilon for DBSCAN search
DEFAULT_EPS_MIN = 1.0          # Minimum epsilon for DBSCAN search
DEFAULT_EPS_STEPS = 20         # Number of epsilon values to test
FALLBACK_EPS_MULTIPLIER = 2.0  # Multiply eps_max by this for fallback search
FALLBACK_STEPS_MULTIPLIER = 4  # Multiply eps_steps by this for fallback search

# Clustering quality thresholds
MIN_ACCEPTABLE_SILHOUETTE = 0.45  # Minimum score before triggering fallback
POOR_CLUSTERING_THRESHOLD = 0.30  # Warn user if score below this

# Interactive plot parameters
MAX_CUSTOM_SELECTIONS = 3      # Maximum number of custom cluster selections
PLOT_FIGSIZE = (12, 7)     # Figure size for clustering plots
PLOT_DPI = 300                 # DPI for saved figures
PLOT_POINT_SIZE = 25           # Size of scatter plot points

# Ternary diagram constants
TERNARY_SQRT3_HALF = 0.8660254037844387  # sqrt(3)/2 for ternary projection

# ===== to_exp.py constants =====
# .exp file generation
MIN_REQUIRED_MEAN_ROWS = 3     # Minimum number of mean rows required
EXP_FIRST_ELEMENT_ROW = 2      # Row index for first element name
EXP_FIRST_ELEMENT_COL = 2      # Column index for first element (0-based)
EXP_COMPOSITION_DECIMAL_PLACES = 4  # Decimal places for composition values
THREE_ELEMENT_THRESHOLD = 0.001  # Minimum fraction for all three elements to be considered a three-element phase

# ===== reports.py constants =====
# Sample name parsing
SAMPLE_NAME_PARTS = 3          # Expected parts in report filename (system_temp_sample)
MIN_SAMPLE_IDENTIFIER_LENGTH = 2  # Minimum length for sample identifier (e.g., "1a")

# ===== one_cluster.py constants =====
ONE_CLUSTER_THRESHOLD = 1      # Z-score threshold for outlier detection in one_cluster

# ===== File/Folder naming =====
# Folder structure
REPORTS_FOLDER_NAME = "reports"
DIAGRAMS_FOLDER_NAME = "diagrams"
SAMPLE_FOLDER_PREFIX = ""  # Empty to use only sample number (1, 2, etc.)

# ===== Image handling =====
# Image extraction constants
MAX_IMAGES_PER_SAMPLE = 10  # Prevent memory issues with too many images
TEMP_IMAGE_PREFIX = "sem_img_"  # Prefix for temporary image files
SUPPORTED_IMAGE_FORMATS = ['.png', '.jpg', '.jpeg']  # Supported image formats
AZTEC_IMAGE_PATH = 'media/image2.png'  # Path to first image in AZTEC .docx files (updated to media/)
ACCEPTABLE_IMAGE_SIZES = [
    "570x484",
    "863x587",
]
TARGET_IMAGE_SIZE = ACCEPTABLE_IMAGE_SIZES[0]  # Default/primary target size (for backwards compatibility)

# File naming patterns
SEM_RESULTS_PATTERN = "SEM_results_{system}_{temp}.xlsx"
PHASE_TABLE_PATTERN = "phase_table_{system}_{temp}.xlsx"
EXP_FILE_PATTERN = "{system}_{temp}.exp"
EXP_FILE_PATTERN_PREDICTION = "{system}_{temp}_phase_predic.exp"
REPORT_DAT_PATTERN = "REPORT_{name}.dat"
TERNARY_DIAGRAM_PATTERN = "{sample_name}_ternary_final.png"

# Phase table header constants
PHASE_TABLE_COL_SAMPLE = 0
PHASE_TABLE_COL_OVERALL_START = 1
PHASE_TABLE_COL_PHASE = 4
PHASE_TABLE_COL_PHASE_COMP_START = 5
PHASE_TABLE_COL_NOTE = 8

# ===== Phase Management =====
# Phase file naming
PHASE_FILE_PATTERN = "phases_{system}.txt"
PHASE_DISTANCE_THRESHOLD = 0.15  # Maximum distance for phase selection
PHASE_LIST_GUI_ENABLED = True    # Enable interactive phase list GUI on each system analysis
PHASE_LIST_VERIFY_EXISTING = True # Ask to verify/modify phases even if phases.txt exists

# Master phase file
MASTER_PHASES_FILE = "master_phases.json"
MASTER_PHASE_FILE_INITIATED = False  # Set to True after first initialization

# ===== Clustering History =====
# History file naming
CLUSTERING_HISTORY_FILE = "clustering_history.json"

# Maximum historical samples to display (avoid clutter)
MAX_HISTORICAL_SAMPLES = 45

# ===== Visualization - Historical Data & Phases =====
# Historical data visualization settings
HISTORICAL_POINT_ALPHA = 0.5        # Transparency for historical points
HISTORICAL_POINT_COLOR = 'gray'     # Color for historical points
HISTORICAL_LINE_ALPHA = 0.5         # Transparency for connecting lines
HISTORICAL_LINE_WIDTH = 0.5         # Width of connecting lines
HISTORICAL_LINE_COLOR = 'grey'      # Color for connecting lines

# Phase visualization settings
PHASE_POINT_ALPHA = 0.8             # Transparency for phase points (label text)
PHASE_MARKER_ALPHA = 0.8            # Transparency for phase markers
PHASE_POINT_COLOR = 'black'         # Color for phase points
PHASE_POINT_SIZE_MULTIPLIER = 1.5   # Size multiplier for phase points
PHASE_LABEL_OFFSET_X = 0.02         # X offset for phase labels
PHASE_LABEL_OFFSET_Y = 0.02         # Y offset for phase labels
PHASE_LABEL_FONTSIZE = 8            # Font size for phase labels

# ===== Logging =====
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
