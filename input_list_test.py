import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional, List, Any


def get_validated_list(initial_list=None, validation_func: Optional[Callable[[str], tuple]] = None, 
                       system_name: Optional[str] = None, remove_from_master_callback: Optional[Callable[[str], None]] = None):
    items = list(initial_list or [])

    if validation_func is None:
        def validation_func(v: str) -> tuple:
            if len(v.strip()) < 3:
                return False, "At least 3 characters"
            if v in items:
                return False, "Already exists"
            return True, ""

    root = tk.Tk()
    if system_name:
        root.title(f"Phase List Builder - {system_name}")
    else:
        root.title("Phase List Builder")
    
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = int(screen_width * 0.9)
    window_height = int(screen_height * 0.9)
    root.geometry(f"{window_width}x{window_height}")
    
    root.bind('<Escape>', lambda e: root.destroy())

    main_frame = ttk.Frame(root, padding="10")
    main_frame.grid(row=0, column=0, sticky="nesw")
    
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    title_text = "Phase List Builder"
    if system_name:
        title_text += f" - {system_name}"
    title_label = ttk.Label(main_frame, text=title_text, font=("Arial", 14, "bold"))
    title_label.grid(row=0, column=0, columnspan=2, pady=(0, 10))

    if system_name:
        system_label = ttk.Label(main_frame, text=f"System elements: {system_name}", font=("Arial", 11))
        system_label.grid(row=1, column=0, columnspan=2, pady=(0, 5))
        input_frame_row = 2
        list_frame_row = 3
        status_row = 4
    else:
        input_frame_row = 1
        list_frame_row = 2
        status_row = 3

    input_frame = ttk.LabelFrame(main_frame, text="Add Phases", padding="10")
    input_frame.grid(row=input_frame_row, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

    ttk.Label(input_frame, text="Enter values (comma or newline separated):", font=("Arial", 10)).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

    text = tk.Text(input_frame, height=5, width=50)
    text.grid(row=1, column=0, columnspan=2, pady=8)

    add_btn = ttk.Button(input_frame, text="Add", width=15)
    add_btn.grid(row=2, column=0, columnspan=2, pady=8)

    list_frame = ttk.LabelFrame(main_frame, text="Current Phases", padding="10")
    list_frame.grid(row=list_frame_row, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

    main_frame.rowconfigure(list_frame_row, weight=1)
    main_frame.columnconfigure(0, weight=1)
    main_frame.columnconfigure(1, weight=1)

    listbox = tk.Listbox(list_frame, height=14, font=("Arial", 10))
    listbox.grid(row=0, column=0, columnspan=2, pady=8)

    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
    scrollbar.grid(row=0, column=2, sticky="ns")
    listbox.configure(yscrollcommand=scrollbar.set)

    button_frame = ttk.Frame(list_frame)
    button_frame.grid(row=1, column=0, columnspan=2, pady=8)

    remove_btn = ttk.Button(button_frame, text="Remove selected", width=18)
    remove_btn.grid(row=0, column=0, padx=8)

    finish_btn = ttk.Button(button_frame, text="Finish", width=18)
    finish_btn.grid(row=0, column=1, padx=8)

    status_var = tk.StringVar()
    status_label = ttk.Label(main_frame, textvariable=status_var, font=("Arial", 10))
    status_label.grid(row=status_row, column=0, columnspan=2, pady=10)

    def refresh():
        listbox.delete(0, tk.END)
        for v in items:
            listbox.insert(tk.END, v)
        status_var.set(f"{len(items)} items")

    def add_items():
        raw = text.get("1.0", tk.END).strip()
        if not raw:
            return

        values = [v.strip() for v in raw.replace("\n", ",").split(",") if v.strip()]
        errors = []

        for v in values:
            ok, msg = validation_func(v)
            if ok:
                items.append(v)
            else:
                errors.append(f"{v}: {msg}")

        text.delete("1.0", tk.END)
        refresh()

        if errors:
            messagebox.showwarning("Invalid entries", "\n".join(errors[:6]))

    def remove_selected():
        selection = listbox.curselection()
        if selection:
            phase_name = items[selection[0]]
            
            if remove_from_master_callback is not None:
                response = messagebox.askyesnocancel(
                    "Remove from Master List",
                    f"Remove '{phase_name}' from all locations in the master list?"
                )
                
                if response is None:
                    return
                elif response:
                    remove_from_master_callback(phase_name)
            
            items.pop(selection[0])
            refresh()

    def finish():
        root.destroy()

    add_btn.config(command=add_items)
    remove_btn.config(command=remove_selected)
    finish_btn.config(command=finish)

    refresh()
    root.mainloop()

    return items


# ---------------- example ----------------
if __name__ == "__main__":

    def validator(v):
        if not v.isalpha():
            return False, "Letters only"
        return True, ""

    result = get_validated_list(
        initial_list=["apple", "banana"],
        validation_func=validator
    )

    print("Final list:", result)
