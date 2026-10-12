import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics import silhouette_score
from typing import Tuple, List, Dict, Optional
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, LassoSelector
from matplotlib.path import Path as MplPath
from pathlib import Path
from constants import (
    DEFAULT_EPS_MAX,
    DEFAULT_EPS_MIN,
    DEFAULT_EPS_STEPS,
    FALLBACK_EPS_MULTIPLIER,
    FALLBACK_STEPS_MULTIPLIER,
    MIN_ACCEPTABLE_SILHOUETTE,
    POOR_CLUSTERING_THRESHOLD,
    MAX_CUSTOM_SELECTIONS,
    PLOT_FIGSIZE,
    PLOT_DPI,
    PLOT_POINT_SIZE,
    TERNARY_SQRT3_HALF,
    ONE_CLUSTER_THRESHOLD,
    HISTORICAL_POINT_ALPHA,
    HISTORICAL_POINT_COLOR,
    HISTORICAL_LINE_ALPHA,
    HISTORICAL_LINE_WIDTH,
    HISTORICAL_LINE_COLOR,
    PHASE_POINT_ALPHA,
    PHASE_MARKER_ALPHA,
    PHASE_POINT_COLOR,
    PHASE_POINT_SIZE_MULTIPLIER,
    PHASE_LABEL_OFFSET_X,
    PHASE_LABEL_OFFSET_Y,
    PHASE_LABEL_FONTSIZE
)
from logging_config import log_warning, log_info, log_error, log_clustering_result

## Using DBSCAN algorithm to assosiate points
# the method does not require smallest distance between points just minimum amount of points per group
def compute_labels(points: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    db = DBSCAN(eps=eps, min_samples=min_samples)
    return db.fit_predict(points)

## Evaluates the probability of good assosiation, the workings of this method was not understood while coding
# but the resulting score is generally right. While evaluation it also outputs number of found clusters, this number
# is used when the user confirmation of the assosiation is needed
def evaluate(points: np.ndarray, labels: np.ndarray) -> Tuple[float, int]:
    unique = set(labels)
    n_clusters = len(unique - {-1})
    if n_clusters > 1:  # Silhouette score requires at least 2 clusters
        try:
            score = silhouette_score(points, labels, metric="euclidean")
        except Exception:
            score = -1
        return score, n_clusters
    return -1, n_clusters

## Transforms the datapoints from 3D of compositions of three elements to 2D projection onto a plane A+B+C = 1 
def ternary_to_xy(points: np.ndarray) -> np.ndarray:
    """
    Convert ternary composition coordinates to 2D xy coordinates.
    
    Args:
        points: Nx3 array of composition values
    
    Returns:
        Nx2 array of xy coordinates
    """
    total = np.sum(points, axis=1)
    total[total == 0] = 1
    B, C = points[:, 1] / total, points[:, 2] / total
    x = 0.5 * (2 * B + C)
    y = TERNARY_SQRT3_HALF * C
    return np.vstack((x, y)).T

## Make the base triangle and name the corners of the triangular graph and plot the systems known phases
def draw_ternary_axes(ax,el,phases = None):
    triangle = np.array([[0, 0], [1, 0], [0.5, np.sqrt(3)/2], [0, 0]])
    ax.plot(triangle[:, 0], triangle[:, 1], "k-", lw=1.2)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, np.sqrt(3)/2 + 0.05)
    ax.set_aspect("equal")
    ax.axis("off")

    ## Adds offset names of labels
    ax.text(-0.05, -0.05, el[0], ha="right", va="top", fontsize=11)
    ax.text(1.05, -0.05, el[1], ha="left", va="top", fontsize=11)
    ax.text(0.5, np.sqrt(3)/2 + 0.05, el[2], ha="center", va="bottom", fontsize=11)

    ## Adds underlaying phases, the phases are generated in this program so no need tocheck the format
    # It is plottted with half transparency
    if phases != None:
        for phase in phases:
            ax.plot(phase[1],phase[2],'*',alpha = 0.5)
            ax.text(phase[1]-0.025,phase[2]-0.025,phase[0],ha = "center",va = "center",alpha = 0.5,fontsize = 9)


def plot_historical_data(ax, clustering_history: Optional[Dict], ternary_to_xy_func):
    """
    Plot historical clustering data showing only cluster averages connected by lines/triangles.
    
    Args:
        ax: Matplotlib axis to plot on
        clustering_history: Dictionary from load_clustering_history() or None
        ternary_to_xy_func: Function to convert 3D to 2D coordinates (ternary_to_xy)
    """
    if not clustering_history:
        return
    
    from clustering_history import get_historical_data_for_plotting
    
    # Process historical data
    historical_samples = get_historical_data_for_plotting(clustering_history, ternary_to_xy_func)
    
    for sample_data in historical_samples:
        clusters = sample_data["clusters"]
        
        # Get centroids sorted by cluster_id
        sorted_cluster_ids = sorted(clusters.keys())
        centroids = [clusters[cid]["centroid_2d"] for cid in sorted_cluster_ids]
        
        # Plot only cluster centroids (averages)
        for centroid in centroids:
            ax.scatter(
                centroid[0], 
                centroid[1],
                color=HISTORICAL_POINT_COLOR,
                alpha=HISTORICAL_POINT_ALPHA,
                s=PLOT_POINT_SIZE,
                marker='o',
                edgecolors='none',
                zorder=1  # Behind current sample
            )
        
        # Connect centroids with lines/triangles based on number of clusters
        num_clusters = len(centroids)
        if num_clusters >= 2:
            # Create closed loop: connect each centroid to the next, last to first
            for i in range(num_clusters):
                next_i = (i + 1) % num_clusters  # Wrap around for triangle
                ax.plot(
                    [centroids[i][0], centroids[next_i][0]],
                    [centroids[i][1], centroids[next_i][1]],
                    color=HISTORICAL_LINE_COLOR,
                    alpha=HISTORICAL_LINE_ALPHA,
                    linewidth=HISTORICAL_LINE_WIDTH,
                    zorder=0  # Behind everything
                )


def plot_range_phases(ax, phases_data: Optional[List], ternary_to_xy_func):
    """
    Plot range phases as black lines connecting two endpoint compositions.
    
    Args:
        ax: Matplotlib axis to plot on
        phases_data: List of phase data tuples (can be 2 or 3 elements)
                     - 2 elements: (phase_name, composition) for regular phases
                     - 3 elements: (phase_name, composition, endpoints) for range phases
                       where endpoints is (endpoint1_array, endpoint2_array)
        ternary_to_xy_func: Function to convert 3D to 2D coordinates (ternary_to_xy)
    """
    if not phases_data:
        return
    
    for phase_data in phases_data:
        if len(phase_data) < 3:
            continue
        
        phase_name, composition, endpoints = phase_data
        if not isinstance(endpoints, tuple) or len(endpoints) != 2:
            continue
        
        endpoint1, endpoint2 = endpoints
        
        ep1_2d = ternary_to_xy_func(endpoint1.reshape(1, -1))[0]
        ep2_2d = ternary_to_xy_func(endpoint2.reshape(1, -1))[0]
        
        ax.plot(
            [ep1_2d[0], ep2_2d[0]],
            [ep1_2d[1], ep2_2d[1]],
            color='black',
            linewidth=2,
            alpha=0.8,
            zorder=9
        )
        
        ax.scatter(
            [ep1_2d[0], ep2_2d[0]],
            [ep1_2d[1], ep2_2d[1]],
            color='black',
            s=30,
            marker='o',
            zorder=10
        )
        
        mid_x = (ep1_2d[0] + ep2_2d[0]) / 2
        mid_y = (ep1_2d[1] + ep2_2d[1]) / 2
        ax.text(
            mid_x + PHASE_LABEL_OFFSET_X,
            mid_y + PHASE_LABEL_OFFSET_Y,
            phase_name,
            fontsize=PHASE_LABEL_FONTSIZE,
            alpha=PHASE_POINT_ALPHA,
            zorder=10,
            ha='left',
            va='bottom',
            color='black',
            fontweight='bold'
        )


def plot_phases(ax, phases_data: Optional[List[Tuple[str, np.ndarray]]], ternary_to_xy_func):
    """
    Plot theoretical phases as black points with labels.
    Separates range phases (plotted as lines) from regular phases (plotted as points).
    
    Args:
        ax: Matplotlib axis to plot on
        phases_data: List of phase data tuples (can be 2 or 3 elements)
                     - 2 elements: (phase_name, composition) for regular phases
                     - 3 elements: (phase_name, composition, endpoints) for range phases
        ternary_to_xy_func: Function to convert 3D to 2D coordinates (ternary_to_xy)
    """
    if not phases_data:
        return
    
    regular_phases = []
    range_phases = []
    
    for phase_data in phases_data:
        if len(phase_data) == 2:
            regular_phases.append(phase_data)
        elif len(phase_data) >= 3:
            range_phases.append(phase_data)
    
    plot_range_phases(ax, range_phases, ternary_to_xy_func)
    
    for phase_name, composition in regular_phases:
        phase_2d = ternary_to_xy_func(composition.reshape(1, -1))[0]
        
        ax.scatter(
            phase_2d[0], 
            phase_2d[1],
            color=PHASE_POINT_COLOR,
            alpha=PHASE_MARKER_ALPHA,
            s=PLOT_POINT_SIZE * PHASE_POINT_SIZE_MULTIPLIER,
            marker='x',
            zorder=10,
            linewidths=2
        )
        
        ax.text(
            phase_2d[0] + PHASE_LABEL_OFFSET_X,
            phase_2d[1] + PHASE_LABEL_OFFSET_Y,
            phase_name,
            fontsize=PHASE_LABEL_FONTSIZE,
            alpha=PHASE_POINT_ALPHA,
            zorder=10,
            ha='left',
            va='bottom'
        )


## Makes the best possible estimate in the specified range of values when clustering provided points and then takes in user input
# to either choose automatic clustering or a custom selection using matplotlib lasso tool
def a_search(points: np.ndarray, 
             eps_max: float = DEFAULT_EPS_MAX, 
             eps_steps: int = DEFAULT_EPS_STEPS, 
             min_samples_range: Tuple[int, ...] = (3, 4, 5),
             elements: List[str] = ['A','B','C'],
             sample_name: str = 'Sample name',
             save_path: Optional[str] = None,
             clustering_history: Optional[Dict] = None,
             phases_data: Optional[List[Tuple[str, np.ndarray]]] = None) -> Dict:
    best_any = {"score": -1, "labels": None, "params": None}
    best_2 = {"score": -1, "labels": None, "params": None}
    best_3 = {"score": -1, "labels": None, "params": None}

    # Handle edge cases for very small datasets
    if len(points) == 0:
        log_warning(f"{sample_name}: No points to cluster")
        return {"score": 1.0, "labels": np.array([]), "params": (0.0, 0, 0)}
    
    if len(points) == 1:
        log_info(f"{sample_name}: Single point, assigning to cluster 0")
        labels = np.zeros(1, dtype=int)
        return {"score": 1.0, "labels": labels, "params": (0.0, 1, 1)}

    # For 2 points, still run clustering and show interactive plot as requested
    if len(points) == 2:
        log_info(f"{sample_name}: Only 2 points, clustering may not be optimal")

    eps_range = np.linspace(DEFAULT_EPS_MIN, eps_max, eps_steps)
    
    # Track tested parameters to avoid redundant computation in fallback
    tested_params = set()

    for eps in eps_range:
        for ms in min_samples_range:
            # Round eps to avoid floating point comparison issues
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

    # fallback search with broadened parameters in case of bad fit of the clustering
    if best_any["score"] < MIN_ACCEPTABLE_SILHOUETTE:
        log_info(f"{sample_name}: Initial clustering score {best_any['score']:.3f} < {MIN_ACCEPTABLE_SILHOUETTE}, trying extended search")
        eps_range = np.linspace(DEFAULT_EPS_MIN, FALLBACK_EPS_MULTIPLIER * eps_max, FALLBACK_STEPS_MULTIPLIER * eps_steps)
        skipped_count = 0
        tested_count = 0
        for eps in eps_range:
            for ms in min_samples_range:
                param_key = (round(eps, 6), ms)
                if param_key in tested_params:
                    skipped_count += 1
                    continue  # Skip already-tested parameters
                
                tested_count += 1
                labels = compute_labels(points, eps, ms)
                score, n_clusters = evaluate(points, labels)
                if score > best_any["score"]:
                    best_any.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
                if n_clusters == 2 and score > best_2["score"]:
                    best_2.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
                if n_clusters == 3 and score > best_3["score"]:
                    best_3.update({"score": score, "labels": labels, "params": (eps, ms, n_clusters)})
        
        if skipped_count > 0:
            log_info(f"{sample_name}: Fallback search - tested {tested_count} new parameters, skipped {skipped_count} already-tested")
        
        # Warn if still poor after fallback
        if best_any["score"] < POOR_CLUSTERING_THRESHOLD:
            log_warning(
                f"{sample_name}: Clustering quality poor (score: {best_any['score']:.3f}). "
                f"Consider manual selection."
            )

    # Interactive choice
    labels_2 = best_2["labels"]
    labels_3 = best_3["labels"]

    points2d = ternary_to_xy(points)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=PLOT_FIGSIZE)
    plt.subplots_adjust(bottom=0.25)
    plt.suptitle(sample_name)
    result = {"labels": None, "source_ax": None}  # Track which axis was used
    selector = {"lasso": None}
    
    # Store save_path in result for later use
    result["save_path"] = save_path

    # Plot best two clusters
    ax1.set_title("2 Clusters", y=1.08)
    draw_ternary_axes(ax1, elements)
    
    # Add historical data and phases (background)
    plot_historical_data(ax1, clustering_history, ternary_to_xy)
    plot_phases(ax1, phases_data, ternary_to_xy)
    
    # Plot current sample (foreground)
    for lab in np.unique(labels_2):
        ax1.scatter(points2d[labels_2 == lab, 0], points2d[labels_2 == lab, 1], label=f"C{lab}", s=PLOT_POINT_SIZE)
    ax1.legend()

    # Plot best three clusters
    ax2.set_title("3 Clusters", y=1.08)
    draw_ternary_axes(ax2, elements)
    
    # Add historical data and phases (background)
    plot_historical_data(ax2, clustering_history, ternary_to_xy)
    plot_phases(ax2, phases_data, ternary_to_xy)
    
    # Plot current sample (foreground)
    for lab in np.unique(labels_3):
        ax2.scatter(points2d[labels_3 == lab, 0], points2d[labels_3 == lab, 1], label=f"C{lab}", s=PLOT_POINT_SIZE)
    ax2.legend()

    # Buttons for interaction
    ax_b2 = plt.axes([0.2, 0.1, 0.15, 0.075])
    ax_b3 = plt.axes([0.4, 0.1, 0.15, 0.075])
    ax_bc = plt.axes([0.6, 0.1, 0.15, 0.075])

    b2 = Button(ax_b2, "Use 2 Clusters")
    b3 = Button(ax_b3, "Use 3 Clusters")
    bc = Button(ax_bc, "Custom Select")

    def use_2(event):
        result["labels"] = labels_2
        result["source_ax"] = ax1  # Track that ax1 was selected
        plt.close(fig)

    def use_3(event):
        result["labels"] = labels_3
        result["source_ax"] = ax2  # Track that ax2 was selected
        plt.close(fig)

    def custom_select(event):
        ax2.set_title("Custom Selection (Lasso active: up to 3 regions)")
        if selector["lasso"] is not None:
            selector["lasso"].disconnect_events()

        custom_labels = np.zeros(len(points), dtype=int)
        selection_count = {"n": 0}

        # Draw base plot
        ax2.clear()
        draw_ternary_axes(ax2, elements)
        
        # Add historical data and phases (background)
        plot_historical_data(ax2, clustering_history, ternary_to_xy)
        plot_phases(ax2, phases_data, ternary_to_xy)
        
        # Plot current sample
        sc = ax2.scatter(points2d[:, 0], points2d[:, 1], c="gray", s=PLOT_POINT_SIZE)
        fig.canvas.draw_idle()

        def on_select(verts):
            try:
                if selection_count["n"] >= MAX_CUSTOM_SELECTIONS:
                    log_info(f"Maximum of {MAX_CUSTOM_SELECTIONS} clusters selected. Ignoring further selections.")
                    return

                path = MplPath(verts)
                inside = path.contains_points(points2d)
                current_label = selection_count["n"]

                # Assign new cluster label to selected points
                custom_labels[inside] = current_label
                selection_count["n"] += 1

                # Update plot
                ax2.clear()
                draw_ternary_axes(ax2, elements)
                
                # Add historical data and phases (background)
                plot_historical_data(ax2, clustering_history, ternary_to_xy)
                plot_phases(ax2, phases_data, ternary_to_xy)
                
                # Plot current sample with custom labels
                sc = ax2.scatter(
                    points2d[:, 0],
                    points2d[:, 1],
                    c=custom_labels,
                    cmap="tab10",
                    s=PLOT_POINT_SIZE,
                )
                ax2.set_title(f"Custom Selection: {selection_count['n']} cluster(s) selected", y=1.08)
                fig.canvas.draw_idle()

                # Store result live
                result["labels"] = custom_labels
                result["source_ax"] = ax2  # Custom selection uses ax2

                # If max selections reached, finalize
                if selection_count["n"] == MAX_CUSTOM_SELECTIONS:
                    log_info(f"{MAX_CUSTOM_SELECTIONS} clusters selected. You can now close the window.")
                    if selector["lasso"] is not None:
                        selector["lasso"].disconnect_events()

            except Exception as e:
                log_error(f"Lasso selection error: {e}", exc_info=True)

        selector["lasso"] = LassoSelector(ax2, on_select, useblit=True, button=[1])
        log_info("Lasso active – draw up to 3 regions. Close window when done.")
    b2.on_clicked(use_2)
    b3.on_clicked(use_3)
    bc.on_clicked(custom_select)

    plt.show()

    # Determine final labels
    final_labels = result["labels"] if result["labels"] is not None else best_any["labels"]
    final_score = None if result["labels"] is not None else best_any["score"]
    
    # Save diagram if save_path provided
    if save_path and final_labels is not None:
        try:
            # If we have a tracked source axis, save it directly (optimized)
            if result.get("source_ax") is not None:
                source_ax = result["source_ax"]
                
                # Create new figure from the selected axis (faster than replotting)
                save_fig = plt.figure(figsize=(8, 7))
                save_ax = save_fig.add_subplot(111)
                
                # Copy the content from source_ax to save_ax
                # Get all children (artists) from source and copy to save
                for artist in source_ax.get_children():
                    if hasattr(artist, 'get_label'):
                        # Copy scatter plots, lines, patches, etc.
                        try:
                            save_ax.add_artist(artist)
                        except:
                            pass  # Some artists can't be copied easily
                
                # Copy axis properties
                save_ax.set_xlim(source_ax.get_xlim())
                save_ax.set_ylim(source_ax.get_ylim())
                save_ax.set_aspect(source_ax.get_aspect())
                save_ax.axis('off')
                save_ax.set_title(f"{sample_name} - Final Clustering", y=1.08)
                
                # Try to copy legend if it exists
                if source_ax.get_legend():
                    save_ax.legend()
            else:
                # Fallback: create clean figure (if no source tracked)
                save_fig = plt.figure(figsize=(8, 7))
                save_ax = save_fig.add_subplot(111)
                save_ax.set_title(f"{sample_name} - Final Clustering", y=1.08)
                draw_ternary_axes(save_ax, elements)
                
                # Add historical data and phases (background)
                plot_historical_data(save_ax, clustering_history, ternary_to_xy)
                plot_phases(save_ax, phases_data, ternary_to_xy)
                
                # Plot current sample (foreground)
                for lab in np.unique(final_labels):
                    mask = final_labels == lab
                    label_text = f"Cluster {lab}" if lab != -1 else "Outliers"
                    save_ax.scatter(
                        points2d[mask, 0], 
                        points2d[mask, 1], 
                        label=label_text, 
                        s=PLOT_POINT_SIZE
                    )
                save_ax.legend()
            
            # Save with high DPI
            save_fig.savefig(save_path, dpi=PLOT_DPI, bbox_inches='tight')
            plt.close(save_fig)
            log_info(f"Saved ternary diagram to: {save_path}")
        except Exception as e:
            log_error(f"Failed to save ternary diagram: {e}", exc_info=True)
    
    # Log clustering result
    n_clusters = len(set(final_labels) - {-1}) if final_labels is not None else 0
    log_clustering_result(sample_name, n_clusters, final_score)

    # Return the chosen clustering
    if result["labels"] is None:
        log_info("No selection made. Returning best cluster result by default.")
        return best_any
    return {"score": None, "labels": result["labels"], "params": None}

## clusters the data to one group and outliers used for deciding overall compositions of the sample
def one_cluster(vectors: np.ndarray, threshold: float = ONE_CLUSTER_THRESHOLD) -> Dict:
    """
    Cluster data into one group and identify outliers based on z-score threshold.
    
    Args:
        vectors: Array of composition vectors
        threshold: Z-score threshold for outlier detection (default from constants)
    
    Returns:
        Dictionary with 'cluster' and 'outliers' lists
    """
    arr = np.array(vectors)
    
    if len(arr) == 0:
        return {"cluster": [], "outliers": []}
    
    if len(arr) == 1:
        return {"cluster": arr.tolist(), "outliers": []}
    
    centroid = arr.mean(axis=0)
    dists = np.linalg.norm(arr - centroid, axis=1)
    
    # z-score distance relative to spread
    std = dists.std() if dists.std() > 0 else 1e-9
    mask = (dists - dists.mean()) / std <= threshold
    
    return {
        "cluster": arr[mask].tolist(),
        "outliers": arr[~mask].tolist()
    }
