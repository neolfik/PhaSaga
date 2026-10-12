#!/usr/bin/env python3
"""
Tkinter-based combined clustering and phase selection interface.
Shows clustering options with ternary plots and phase selection side-by-side.
"""

import tkinter as tk
from tkinter import ttk
import numpy as np
from typing import List, Tuple, Dict, Optional
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
try:
    from matplotlib.backends._backend_tk import NavigationToolbar2Tk
except ImportError:
    from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import Button as MplButton, LassoSelector
from matplotlib.path import Path as MplPath
import io

from clustering import (
    compute_labels, evaluate, ternary_to_xy, draw_ternary_axes,
    plot_historical_data, plot_phases, MAX_CUSTOM_SELECTIONS
)
from constants import PHASE_DISTANCE_THRESHOLD
from logging_config import log_info, log_error, log_warning


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
                        elements: List[str] = None) -> List[Tuple[int, List[Tuple[str, float]]]]:
    """
    Find closest phases for each cluster average.
    Handles both regular phases and range phases (solid solution lines).
    
    Args:
        cluster_averages: List of cluster average positions
        phases_data: List of phase data tuples (can be 2 or 3 elements)
                     - 2 elements: (phase_name, composition_array) for regular phases
                     - 3 elements: (phase_name, composition_array, (endpoint1, endpoint2)) for range phases
        threshold: Maximum distance for phase selection
        elements: List of element names
    
    Returns:
        List of (cluster_idx, [(phase_name, distance), ...]) tuples
    """
    results = []
    
    for cluster_idx, cluster_avg in enumerate(cluster_averages):
        if cluster_avg is None:
            results.append((cluster_idx, []))
            continue
        
        distances = []
        for phase_data in phases_data:
            if len(phase_data) >= 2:
                phase_name, composition = phase_data[:2]
                
                if len(phase_data) >= 3 and isinstance(phase_data[2], tuple):
                    endpoints = phase_data[2]
                    if len(endpoints) == 2:
                        endpoint1, endpoint2 = endpoints
                        dist = point_to_line_segment_distance(cluster_avg, endpoint1, endpoint2)
                    else:
                        dist = np.linalg.norm(cluster_avg - composition)
                else:
                    dist = np.linalg.norm(cluster_avg - composition)
                
                if dist <= threshold:
                    distances.append((phase_name, dist))
        
        distances.sort(key=lambda x: x[1])
        results.append((cluster_idx, distances))
    
    return results


class ClusteringPhaseSelector:
    def __init__(self, points: np.ndarray, 
                 labels_2: np.ndarray, labels_3: np.ndarray,
                 best_any: Dict,
                 elements: List[str],
                 sample_name: str,
                 clustering_history: Optional[Dict] = None,
                 phases_data: Optional[List[Tuple[str, np.ndarray]]] = None,
                 overall_composition: Optional[np.ndarray] = None):
        
        self.points = points
        self.labels_2 = labels_2
        self.labels_3 = labels_3
        self.best_any = best_any
        self.elements = elements
        self.sample_name = sample_name
        self.clustering_history = clustering_history
        self.phases_data = phases_data
        self.overall_composition = overall_composition
        
        self.points2d = ternary_to_xy(points)
        
        self.selected_labels = None
        self.selected_n_clusters = None
        self.phase_selections = ["NA", "NA", "NA"]
        self.custom_lasso_active = False
        self.custom_labels = None
        self.custom_selected = False
        
        self.root = tk.Tk()
        self.root.title(f"Clustering & Phase Selection: {sample_name}")
        
        # Fit window to screen without being fullscreen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = int(screen_width * 0.95)
        window_height = int(screen_height * 0.95)
        self.root.geometry(f"{window_width}x{window_height}")
        
        self.root.bind('<Escape>', lambda e: self._on_cancel())
        
        self._create_widgets()
        self._update_phase_selection(2)
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.root.mainloop()
    
    def _create_widgets(self):
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)
        
        left_frame = ttk.Frame(main_paned, width=400)
        main_paned.add(left_frame, weight=1)
        
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=3)
        
        self._create_left_panel(left_frame)
        self._create_right_panel(right_frame)
        
        # Add sample name at the bottom
        bottom_frame = ttk.Frame(self.root, relief=tk.SUNKEN, borderwidth=2)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        sample_label = ttk.Label(bottom_frame, 
                               text=f"Sample: {self.sample_name}",
                               font=("Arial", 14, "bold"),
                               background="#e0e0e0",
                               padding=10)
        sample_label.pack(fill=tk.X)
    
    def _create_left_panel(self, parent):
        title_label = ttk.Label(parent, text="Phase Selection", font=("Arial", 16, "bold"))
        title_label.pack(pady=(20, 10))
        
        instruction_label = ttk.Label(parent, 
            text="Select clustering option from right panel,\nthen select phases for each cluster below",
            font=("Arial", 10), wraplength=350)
        instruction_label.pack(pady=(0, 20))
        
        self.clustering_type_label = ttk.Label(parent, 
            text="Current: 2 Clusters", 
            font=("Arial", 11, "bold"), foreground="blue")
        self.clustering_type_label.pack(pady=(0, 10))
        
        self.phase_container = ttk.Frame(parent)
        self.phase_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=20)
        
        self.done_btn = ttk.Button(button_frame, text="Done / Confirm Selection", 
                                   command=self._on_done, width=25)
        self.done_btn.pack()
        
        cancel_btn = ttk.Button(button_frame, text="Cancel (Escape)", 
                               command=self._on_cancel, width=25)
        cancel_btn.pack(pady=10)
    
    def _create_right_panel(self, parent):
        title_label = ttk.Label(parent, text="Clustering Selection", font=("Arial", 16, "bold"))
        title_label.pack(pady=(20, 10))
        
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=10)
        
        self.btn_2 = ttk.Button(button_frame, text="Use 2 Clusters", command=self._on_use_2, width=18)
        self.btn_2.grid(row=0, column=0, padx=10)
        
        self.btn_3 = ttk.Button(button_frame, text="Use 3 Clusters", command=self._on_use_3, width=18)
        self.btn_3.grid(row=0, column=1, padx=10)
        
        self.btn_custom = ttk.Button(button_frame, text="Custom Select", command=self._on_custom_select, width=18)
        self.btn_custom.grid(row=0, column=2, padx=10)
        
        plots_frame = ttk.Frame(parent)
        plots_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.figure = Figure(figsize=(16, 8), dpi=100)
        self.figure.patch.set_facecolor('#f0f0f0')
        
        self.ax1 = self.figure.add_subplot(121)
        self.ax2 = self.figure.add_subplot(122)
        
        self._plot_2_clusters()
        self._plot_3_clusters()
        
        self.figure.tight_layout()
        
        self.canvas = FigureCanvasTkAgg(self.figure, master=plots_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        toolbar = NavigationToolbar2Tk(self.canvas, plots_frame)
        toolbar.update()
    
    def _plot_2_clusters(self):
        self.ax1.clear()
        draw_ternary_axes(self.ax1, self.elements)
        
        if self.clustering_history:
            plot_historical_data(self.ax1, self.clustering_history, ternary_to_xy)
        if self.phases_data:
            plot_phases(self.ax1, self.phases_data, ternary_to_xy)
        
        # Plot overall composition as red cross (same size as phase markers)
        if self.overall_composition is not None:
            try:
                # Ensure it's a numpy array with proper shape
                overall_arr = np.array(self.overall_composition, dtype=float)
                # Flatten if needed and ensure it's 1D with 3 elements
                if overall_arr.ndim == 0:
                    # Single float - can't plot
                    pass
                elif overall_arr.ndim == 1:
                    if len(overall_arr) == 3:
                        overall_arr = overall_arr.reshape(1, 3)
                    else:
                        # Wrong number of elements
                        pass
                elif overall_arr.ndim == 2:
                    if overall_arr.shape[1] != 3:
                        pass
                else:
                    pass
                
                if overall_arr.ndim == 2 and overall_arr.shape[0] >= 1 and overall_arr.shape[1] == 3:
                    overall_2d = ternary_to_xy(overall_arr)
                    if len(overall_2d) > 0:
                        # Use same size as phase markers (PLOT_POINT_SIZE * PHASE_POINT_SIZE_MULTIPLIER = 25 * 1.5 = 37.5)
                        self.ax1.plot(overall_2d[0, 0], overall_2d[0, 1], 'r+', 
                                      markersize=10, markeredgewidth=3, label='Overall', zorder=10)
            except Exception as e:
                print(f"Error plotting overall composition: {e}")
                import traceback
                traceback.print_exc()
        
        for lab in np.unique(self.labels_2):
            self.ax1.scatter(self.points2d[self.labels_2 == lab, 0], 
                          self.points2d[self.labels_2 == lab, 1], 
                          label=f"C{lab}", s=25)
        self.ax1.legend()
        self.ax1.set_title("2 Clusters", fontsize=12)
    
    def _plot_3_clusters(self):
        self.ax2.clear()
        draw_ternary_axes(self.ax2, self.elements)
        
        if self.clustering_history:
            plot_historical_data(self.ax2, self.clustering_history, ternary_to_xy)
        if self.phases_data:
            plot_phases(self.ax2, self.phases_data, ternary_to_xy)
        
        # Plot overall composition as red cross (same size as phase markers)
        if self.overall_composition is not None:
            try:
                # Ensure it's a numpy array with proper shape
                overall_arr = np.array(self.overall_composition, dtype=float)
                # Flatten if needed and ensure it's 1D with 3 elements
                if overall_arr.ndim == 0:
                    # Single float - can't plot
                    pass
                elif overall_arr.ndim == 1:
                    if len(overall_arr) == 3:
                        overall_arr = overall_arr.reshape(1, 3)
                    else:
                        # Wrong number of elements
                        pass
                elif overall_arr.ndim == 2:
                    if overall_arr.shape[1] != 3:
                        pass
                else:
                    pass
                
                if overall_arr.ndim == 2 and overall_arr.shape[0] >= 1 and overall_arr.shape[1] == 3:
                    overall_2d = ternary_to_xy(overall_arr)
                    if len(overall_2d) > 0:
                        # Use same size as phase markers (PLOT_POINT_SIZE * PHASE_POINT_SIZE_MULTIPLIER = 25 * 1.5 = 37.5)
                        self.ax2.plot(overall_2d[0, 0], overall_2d[0, 1], 'r+', 
                                      markersize=10, markeredgewidth=3, label='Overall', zorder=10)
            except Exception as e:
                print(f"Error plotting overall composition: {e}")
                import traceback
                traceback.print_exc()
        
        for lab in np.unique(self.labels_3):
            self.ax2.scatter(self.points2d[self.labels_3 == lab, 0], 
                          self.points2d[self.labels_3 == lab, 1], 
                          label=f"C{lab}", s=25)
        self.ax2.legend()
        self.ax2.set_title("3 Clusters", fontsize=12)
        
        self.figure.tight_layout()
    
    def _update_phase_selection(self, n_clusters: int):
        for widget in self.phase_container.winfo_children():
            widget.destroy()
        
        if self.custom_selected and self.custom_labels is not None:
            labels = self.custom_labels
        else:
            labels = self.labels_2 if n_clusters == 2 else self.labels_3
        
        # Calculate averages only for actual clusters (excluding outliers with label -1)
        unique_labels = np.unique(labels)
        unique_labels = unique_labels[unique_labels >= 0]  # Exclude outliers (-1)
        n_clusters_actual = len(unique_labels)
        
        self.cluster_averages = []
        for cluster_id in range(n_clusters_actual):
            cluster_points = [self.points[i] for i, lbl in enumerate(labels) if lbl == cluster_id]
            if cluster_points:
                avg = np.mean(cluster_points, axis=0)
                avg_sum = np.sum(avg)
                if avg_sum > 0:
                    avg = avg / avg_sum
                self.cluster_averages.append(avg)
            else:
                self.cluster_averages.append(None)
        
        # Pad with None to always have 3 entries for UI consistency
        while len(self.cluster_averages) < 3:
            self.cluster_averages.append(None)
        
        self.closest_phases = find_closest_phases(self.cluster_averages, self.phases_data or [], 
                                                  elements=self.elements)
        
        self.selection_labels = [None, None, None]
        self.selection_vars = [tk.StringVar(value="None") for _ in range(3)]
        
        # Always show 3 cluster selectors, but disable unused ones
        for cluster_idx in range(3):
            is_active = cluster_idx < n_clusters
            frame_text = f"Cluster {cluster_idx}" if is_active else f"Cluster {cluster_idx} (Not Used)"
            
            cluster_frame = ttk.LabelFrame(self.phase_container, 
                                         text=frame_text, padding="10")
            cluster_frame.pack(fill=tk.X, pady=5)
            
            # Disable the frame if not active
            if not is_active:
                # Create a disabled label to indicate unused
                disabled_label = ttk.Label(cluster_frame, 
                                          text="This cluster is not used in current selection",
                                          font=("Arial", 9, "italic"),
                                          foreground="gray")
                disabled_label.pack(pady=10)
                self.phase_selections[cluster_idx] = "NA"
                self.selection_vars[cluster_idx].set("NA")
                continue
            
            cluster_avg = self.cluster_averages[cluster_idx]
            if cluster_avg is not None:
                comp_text = f"Composition: [{cluster_avg[0]:.3f}, {cluster_avg[1]:.3f}, {cluster_avg[2]:.3f}]"
                comp_label = ttk.Label(cluster_frame, text=comp_text, font=("Arial", 9))
                comp_label.pack(pady=(0, 8))
            
            closest = next((cps for idx, cps in self.closest_phases if idx == cluster_idx), [])
            
            phase_frame = ttk.Frame(cluster_frame)
            phase_frame.pack()
            
            for i, (phase_name, dist) in enumerate(closest):
                btn_text = f"{phase_name} ({dist:.3f})"
                
                btn = ttk.Button(phase_frame, text=btn_text, width=20,
                               command=lambda cn=cluster_idx, pn=phase_name: self._on_phase_select(cn, pn))
                btn.grid(row=i//2, column=i%2, padx=3, pady=3)
            
            na_btn = ttk.Button(phase_frame, text="NA (Skip)",
                              command=lambda cn=cluster_idx: self._on_na_select(cn))
            if closest:
                na_btn.grid(row=2, column=0, columnspan=2, pady=(8, 0))
            else:
                na_btn.pack(pady=5)
            
            sel_frame = ttk.Frame(cluster_frame)
            sel_frame.pack(pady=(8, 0))
            
            ttk.Label(sel_frame, text="Selected: ", font=("Arial", 9, "bold")).grid(row=0, column=0)
            
            sel_label = ttk.Label(sel_frame, textvariable=self.selection_vars[cluster_idx],
                                  font=("Arial", 9, "bold"), foreground="blue")
            sel_label.grid(row=0, column=1)
            
            self.selection_labels[cluster_idx] = sel_label
    
    def _on_phase_select(self, cluster_idx: int, phase_name: str):
        self.phase_selections[cluster_idx] = phase_name
        self.selection_vars[cluster_idx].set(phase_name)
        self.selection_labels[cluster_idx].config(foreground="green")
        log_info(f"Cluster {cluster_idx}: Selected phase {phase_name}")
    
    def _on_na_select(self, cluster_idx: int):
        self.phase_selections[cluster_idx] = "NA"
        self.selection_vars[cluster_idx].set("NA")
        self.selection_labels[cluster_idx].config(foreground="red")
        log_info(f"Cluster {cluster_idx}: Selected NA")
    
    def _on_use_2(self):
        self.selected_labels = self.labels_2
        self.selected_n_clusters = 2
        self.custom_selected = False
        self.clustering_type_label.config(text="Current: 2 Clusters")
        self._update_phase_selection(2)
        self.btn_2.config(state="disabled")
        self.btn_3.config(state="normal")
        log_info("Selected 2 clusters")
    
    def _on_use_3(self):
        self.selected_labels = self.labels_3
        self.selected_n_clusters = 3
        self.custom_selected = False
        self.clustering_type_label.config(text="Current: 3 Clusters")
        self._update_phase_selection(3)
        self.btn_2.config(state="normal")
        self.btn_3.config(state="disabled")
        log_info("Selected 3 clusters")
    
    def _on_custom_select(self):
        log_info("Custom selection activated - opening lasso selector")
        self.root.withdraw()
        
        # Initialize all points as outliers (-1); user will assign clusters via lasso
        self.custom_labels = np.full(len(self.points), -1, dtype=int)
        selection_count = {"n": 0}
        
        fig, ax = plt.subplots(figsize=(12, 8))
        plt.subplots_adjust(bottom=0.2)
        plt.suptitle(f"{self.sample_name} - Custom Selection (Lasso: up to 3 regions)")
        
        draw_ternary_axes(ax, self.elements)
        
        if self.clustering_history:
            plot_historical_data(ax, self.clustering_history, ternary_to_xy)
        if self.phases_data:
            plot_phases(ax, self.phases_data, ternary_to_xy)
        
        sc = ax.scatter(self.points2d[:, 0], self.points2d[:, 1], c="gray", s=25)
        fig.canvas.draw_idle()
        
        ax_btn_2 = plt.axes([0.2, 0.05, 0.15, 0.075])
        ax_btn_3 = plt.axes([0.4, 0.05, 0.15, 0.075])
        ax_btn_done = plt.axes([0.6, 0.05, 0.15, 0.075])
        
        btn_2 = MplButton(ax_btn_2, "Use 2 Clusters")
        btn_3 = MplButton(ax_btn_3, "Use 3 Clusters")
        btn_done = MplButton(ax_btn_done, "Done")
        
        def on_select(verts):
            try:
                if selection_count["n"] >= MAX_CUSTOM_SELECTIONS:
                    log_info(f"Maximum of {MAX_CUSTOM_SELECTIONS} clusters selected")
                    return
                
                path = MplPath(verts)
                inside = path.contains_points(self.points2d)
                current_label = selection_count["n"]
                
                self.custom_labels[inside] = current_label
                selection_count["n"] += 1
                
                ax.clear()
                draw_ternary_axes(ax, self.elements)
                
                if self.clustering_history:
                    plot_historical_data(ax, self.clustering_history, ternary_to_xy)
                if self.phases_data:
                    plot_phases(ax, self.phases_data, ternary_to_xy)
                
                sc = ax.scatter(self.points2d[:, 0], self.points2d[:, 1],
                              c=self.custom_labels, cmap="tab10", s=25)
                ax.set_title(f"Custom Selection: {selection_count['n']} cluster(s) selected", y=1.08)
                fig.canvas.draw_idle()
                
                if selection_count["n"] == MAX_CUSTOM_SELECTIONS:
                    log_info(f"{MAX_CUSTOM_SELECTIONS} clusters selected")
            
            except Exception as e:
                log_error(f"Lasso selection error: {e}", exc_info=True)
        
        lasso = LassoSelector(ax, on_select, useblit=True, button=[1])
        
        def use_2_custom(event):
            self.custom_labels = self.labels_2
            self.selected_n_clusters = 2
            plt.close(fig)
        
        def use_3_custom(event):
            self.custom_labels = self.labels_3
            self.selected_n_clusters = 3
            plt.close(fig)
        
        def done_custom(event):
            self.selected_labels = self.custom_labels if selection_count["n"] > 0 else self.labels_3
            if self.selected_labels is None:
                self.selected_labels = self.labels_3
            plt.close(fig)
        
        btn_2.on_clicked(use_2_custom)
        btn_3.on_clicked(use_3_custom)
        btn_done.on_clicked(done_custom)
        
        plt.show()
        
        self.root.deiconify()
        
        if self.selected_labels is not None:
            n_clusters = len(np.unique(self.selected_labels))
            self.selected_n_clusters = n_clusters
            self.custom_selected = True
            self.clustering_type_label.config(text=f"Current: Custom ({n_clusters} Clusters)")
            self._update_phase_selection(n_clusters)
            
            if n_clusters == 2:
                self.btn_2.config(state="disabled")
                self.btn_3.config(state="normal")
            else:
                self.btn_2.config(state="normal")
                self.btn_3.config(state="disabled")
    
    def _on_done(self):
        if self.selected_labels is None:
            self.selected_labels = self.labels_2
            self.selected_n_clusters = 2
        
        self.root.destroy()
    
    def _on_cancel(self):
        self.selected_labels = None
        self.selected_n_clusters = None
        self.root.destroy()
    
    def get_result(self) -> Tuple[Optional[np.ndarray], List[str]]:
        if self.selected_labels is None:
            return None, ["NA", "NA", "NA"]
        return self.selected_labels, self.phase_selections


def show_clustering_phase_selection(
    points: np.ndarray,
    elements: List[str],
    sample_name: str,
    clustering_history: Optional[Dict] = None,
    phases_data: Optional[List[Tuple[str, np.ndarray]]] = None,
    overall_composition: Optional[np.ndarray] = None,
    eps_max: float = 4.0,
    eps_steps: int = 20,
    min_samples_range: Tuple[int, ...] = (3, 4, 5)
) -> Tuple[Optional[np.ndarray], List[str]]:
    """
    Show combined clustering and phase selection UI.
    
    Args:
        points: Data points to cluster (Nx3 array)
        elements: Element names
        sample_name: Sample name for display
        clustering_history: Historical clustering data
        phases_data: Phase composition data
        overall_composition: Overall/bulk composition to display on plots
        eps_max: Maximum epsilon for DBSCAN
        eps_steps: Number of epsilon steps
        min_samples_range: Range of min_samples values
    
    Returns:
        Tuple of (labels, phase_selections)
    """
    if len(points) == 0:
        log_warning(f"{sample_name}: No points to cluster")
        return np.array([]), ["NA", "NA", "NA"]
    
    if len(points) == 1:
        log_info(f"{sample_name}: Single point, assigning to cluster 0")
        return np.zeros(1, dtype=int), ["NA", "NA", "NA"]
    
    from constants import DEFAULT_EPS_MIN, MIN_ACCEPTABLE_SILHOUETTE, FALLBACK_EPS_MULTIPLIER, FALLBACK_STEPS_MULTIPLIER
    
    best_any = {"score": -1, "labels": None, "params": None}
    best_2 = {"score": -1, "labels": None, "params": None}
    best_3 = {"score": -1, "labels": None, "params": None}
    
    eps_range = np.linspace(DEFAULT_EPS_MIN, eps_max, eps_steps)
    tested_params = set()
    
    for eps in eps_range:
        for ms in min_samples_range:
            param_key = (round(eps, 6), ms)
            tested_params.add(param_key)
            
            labels = compute_labels(points, eps, ms)
            score, n_clusters = evaluate(points, labels)
            
            if score > best_any["score"]:
                best_any.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
            if n_clusters == 2 and score > best_2["score"]:
                best_2.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
            if n_clusters == 3 and score > best_3["score"]:
                best_3.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
    
    if best_any["score"] < MIN_ACCEPTABLE_SILHOUETTE:
        log_info(f"{sample_name}: Low clustering score, trying extended search")
        eps_range = np.linspace(DEFAULT_EPS_MIN, FALLBACK_EPS_MULTIPLIER * eps_max, 
                               FALLBACK_STEPS_MULTIPLIER * eps_steps)
        
        for eps in eps_range:
            for ms in min_samples_range:
                param_key = (round(eps, 6), ms)
                if param_key in tested_params:
                    continue
                
                labels = compute_labels(points, eps, ms)
                score, n_clusters = evaluate(points, labels)
                
                if score > best_any["score"]:
                    best_any.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
                if n_clusters == 2 and score > best_2["score"]:
                    best_2.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
                if n_clusters == 3 and score > best_3["score"]:
                    best_3.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
    
    labels_2 = best_2["labels"]
    labels_3 = best_3["labels"]
    
    if labels_2 is None:
        labels_2 = np.zeros(len(points), dtype=int)
    if labels_3 is None:
        labels_3 = np.zeros(len(points), dtype=int)
    
    selector = ClusteringPhaseSelector(
        points=points,
        labels_2=labels_2,
        labels_3=labels_3,
        best_any=best_any,
        elements=elements,
        sample_name=sample_name,
        clustering_history=clustering_history,
        phases_data=phases_data,
        overall_composition=overall_composition
    )
    
    return selector.get_result()
