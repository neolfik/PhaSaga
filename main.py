from elements import load_elements
from reports import load_all_reports
from logging_config import setup_logging, log_info, log_error
from xrd_assignment import run_xrd_assignment
from phase_reassociation import run_phase_reassociation
import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog


def show_main_menu():
    """
    Show main menu with options for:
    1. New Analysis - Analyze new SEM report folder
    2. Phase Reassociation - Re-run phase association on existing data
    3. XRD Assignment - Mark samples as XRD-done
    """
    root = tk.Tk()
    root.title("Phase Association Analysis")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.7)
    window_height = int(screen_height * 0.6)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    selected_action = {"value": None}
    
    main_frame = ttk.Frame(root, padding="40")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text="Phase Association Analysis", 
              font=("Arial", 28, "bold")).pack(pady=(0, 30))
    
    options_frame = ttk.Frame(main_frame)
    options_frame.pack(pady=20)
    
    def on_new_analysis():
        selected_action["value"] = "new_analysis"
        root.destroy()
    
    def on_phase_reassociation():
        selected_action["value"] = "phase_reassociation"
        root.destroy()
    
    def on_xrd_assignment():
        selected_action["value"] = "xrd_assignment"
        root.destroy()
    
    option1_frame = ttk.LabelFrame(options_frame, text="New Analysis", padding="20")
    option1_frame.pack(fill=tk.X, pady=10, padx=20)
    ttk.Label(option1_frame, text="Analyze new SEM report folder", 
              font=("Arial", 11)).pack(anchor=tk.W)
    ttk.Label(option1_frame, text="Process new .docx SEM reports, run clustering, and associate phases", 
              font=("Arial", 9), foreground="gray").pack(anchor=tk.W)
    ttk.Button(option1_frame, text="Select Folder...", command=on_new_analysis, width=20).pack(anchor=tk.E, pady=(10, 0))
    
    option2_frame = ttk.LabelFrame(options_frame, text="Phase Reassociation", padding="20")
    option2_frame.pack(fill=tk.X, pady=10, padx=20)
    ttk.Label(option2_frame, text="Re-run phase association on existing data", 
              font=("Arial", 11)).pack(anchor=tk.W)
    ttk.Label(option2_frame, text="Edit phase assignments from existing phase_table.xlsx, optionally modify phases list", 
              font=("Arial", 9), foreground="gray").pack(anchor=tk.W)
    ttk.Button(option2_frame, text="Run Reassociation...", command=on_phase_reassociation, width=20).pack(anchor=tk.E, pady=(10, 0))
    
    option3_frame = ttk.LabelFrame(options_frame, text="XRD Assignment", padding="20")
    option3_frame.pack(fill=tk.X, pady=10, padx=20)
    ttk.Label(option3_frame, text="Mark samples as XRD-analyzed", 
              font=("Arial", 11)).pack(anchor=tk.W)
    ttk.Label(option3_frame, text="Select samples that have XRD data done. Sample names will appear bold in phase_table.", 
              font=("Arial", 9), foreground="gray").pack(anchor=tk.W)
    ttk.Button(option3_frame, text="Run XRD Assignment...", command=on_xrd_assignment, width=20).pack(anchor=tk.E, pady=(10, 0))
    
    ttk.Frame(main_frame, height=20).pack()
    
    def on_cancel():
        selected_action["value"] = None
        root.destroy()
    
    ttk.Button(main_frame, text="Cancel", command=on_cancel, width=15).pack(pady=10)
    
    root.mainloop()
    
    return selected_action["value"]


def select_folder_gui(default_path: str = "..") -> str:
    """
    Show GUI to select the folder containing reports.
    
    Args:
        default_path: Default folder path to start with
    
    Returns:
        Selected folder path as string
    """
    root = tk.Tk()
    root.title("Select Reports Folder")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    window_width = int(screen_width * 0.7)
    window_height = int(screen_height * 0.4)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    main_frame = ttk.Frame(root, padding="30")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text="Select Folder with SEM Reports", 
              font=("Arial", 20, "bold")).pack(pady=(0, 20))
    
    ttk.Label(main_frame, text="Select the folder containing SEM report files:", 
              font=("Arial", 12)).pack(pady=(0, 15))
    
    path_var = tk.StringVar(value=os.path.abspath(default_path))
    
    path_frame = ttk.Frame(main_frame)
    path_frame.pack(fill=tk.X, pady=15)
    
    path_entry = ttk.Entry(path_frame, textvariable=path_var, width=60, font=("Arial", 12))
    path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    def browse():
        folder = filedialog.askdirectory(initialdir=path_var.get())
        if folder:
            path_var.set(folder)
    
    ttk.Button(path_frame, text="Browse...", command=browse, width=15).pack(side=tk.LEFT, padx=(15, 0))
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=20)
    
    selected_path = {"value": ""}
    
    def on_start():
        selected_path["value"] = path_var.get()
        root.destroy()
    
    def on_cancel():
        selected_path["value"] = ""
        root.destroy()
    
    ttk.Button(button_frame, text="Start Processing", command=on_start, width=20).pack(side=tk.LEFT, padx=15)
    ttk.Button(button_frame, text="Cancel", command=on_cancel, width=15).pack(side=tk.LEFT, padx=15)
    
    root.mainloop()
    
    return selected_path["value"]


def select_base_folder_for_existing(base_path: str = "..") -> str:
    """
    Show GUI to select base folder for existing system operations.
    
    Args:
        base_path: Default folder path to start with
    
    Returns:
        Selected folder path as string
    """
    root = tk.Tk()
    root.title("Select Data Folder")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    window_width = int(screen_width * 0.6)
    window_height = int(screen_height * 0.35)
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    main_frame = ttk.Frame(root, padding="25")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    ttk.Label(main_frame, text="Select Data Folder", 
              font=("Arial", 18, "bold")).pack(pady=(0, 15))
    
    ttk.Label(main_frame, text="Select folder containing analyzed systems:", 
              font=("Arial", 11)).pack(pady=(0, 10))
    
    path_var = tk.StringVar(value=os.path.abspath(base_path))
    
    path_frame = ttk.Frame(main_frame)
    path_frame.pack(fill=tk.X, pady=15)
    
    path_entry = ttk.Entry(path_frame, textvariable=path_var, width=50, font=("Arial", 11))
    path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    def browse():
        folder = filedialog.askdirectory(initialdir=path_var.get())
        if folder:
            path_var.set(folder)
    
    ttk.Button(path_frame, text="Browse...", command=browse, width=12).pack(side=tk.LEFT, padx=(10, 0))
    
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=15)
    
    selected_path = {"value": ""}
    
    def on_confirm():
        selected_path["value"] = path_var.get()
        root.destroy()
    
    def on_cancel():
        selected_path["value"] = ""
        root.destroy()
    
    ttk.Button(button_frame, text="Confirm", command=on_confirm, width=15).pack(side=tk.LEFT, padx=10)
    ttk.Button(button_frame, text="Cancel", command=on_cancel, width=12).pack(side=tk.LEFT, padx=10)
    
    root.mainloop()
    
    return selected_path["value"]


if __name__ == "__main__":
    setup_logging()
    
    log_info("=" * 60)
    log_info("Starting Phase Association Analysis")
    log_info("=" * 60)
    
    try:
        load_elements("elements.csv")
        log_info("Elements database loaded successfully")
    except Exception as e:
        log_error(f"Failed to load elements database: {e}", exc_info=True)
        sys.exit(1)
    
    action = show_main_menu()
    
    if action is None:
        log_info("Selection cancelled by user")
        sys.exit(0)
    
    if action == "new_analysis":
        folder_path = select_folder_gui("..")
        
        if not folder_path:
            log_info("Folder selection cancelled by user")
            sys.exit(0)
        
        log_info(f"Selected folder: {folder_path}")
        
        try:
            result = load_all_reports(folder_path)
            if result is None:
                log_error("Failed to process reports")
                sys.exit(1)
            
            processed, structure = result
            
            if processed:
                log_info("=" * 60)
                log_info(f"Successfully processed {len(processed)} sample groups:")
                for group_key, files in processed:
                    sys_name, temp, sample_no = group_key
                    log_info(f"  - {sys_name}/{temp}/sample_{sample_no}: {len(files)} files")
                log_info("=" * 60)
            else:
                log_info("No samples were processed")
                
        except Exception as e:
            log_error(f"Critical error during processing: {e}", exc_info=True)
            sys.exit(1)
    
    elif action == "phase_reassociation":
        base_path = select_base_folder_for_existing("..")
        
        if not base_path:
            log_info("Folder selection cancelled by user")
            sys.exit(0)
        
        log_info(f"Selected data folder: {base_path}")
        
        try:
            run_phase_reassociation(base_path)
        except Exception as e:
            log_error(f"Critical error during phase reassociation: {e}", exc_info=True)
            sys.exit(1)
    
    elif action == "xrd_assignment":
        base_path = select_base_folder_for_existing("..")
        
        if not base_path:
            log_info("Folder selection cancelled by user")
            sys.exit(0)
        
        log_info(f"Selected data folder: {base_path}")
        
        try:
            run_xrd_assignment(base_path)
        except Exception as e:
            log_error(f"Critical error during XRD assignment: {e}", exc_info=True)
            sys.exit(1)
    
    log_info("Analysis complete")
