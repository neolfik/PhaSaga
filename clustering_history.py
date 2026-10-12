"""
Module for managing clustering history - saving and loading previous clustering results
to enable visualization of historical data points in subsequent clustering operations.
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from logging_config import log_info, log_warning, log_error, log_debug

# Maximum number of historical samples to display (avoid visual clutter)
MAX_HISTORICAL_SAMPLES = 10

def get_history_file_path(base_path: str, system: str, temp: int) -> Path:
    """
    Get the path to the clustering history JSON file for a system/temperature.
    
    Args:
        base_path: Base directory path
        system: System name (e.g., "InLaNi")
        temp: Temperature value
    
    Returns:
        Path to clustering_history.json file
    """
    from constants import CLUSTERING_HISTORY_FILE
    return Path(base_path) / system / str(temp) / CLUSTERING_HISTORY_FILE


def save_clustering_result(
    system: str,
    temp: int,
    sample_name: str,
    points: np.ndarray,
    labels: np.ndarray,
    base_path: str
) -> bool:
    """
    Save clustering result to history file.
    
    Args:
        system: System name
        temp: Temperature value
        sample_name: Sample identifier
        points: Nx3 array of composition points
        labels: N-length array of cluster labels
        base_path: Base directory path
    
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        history_path = get_history_file_path(base_path, system, temp)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing history if present
        if history_path.exists():
            with open(history_path, 'r') as f:
                history = json.load(f)
        else:
            history = {}
        
        # Add new entry
        history[sample_name] = {
            "points": points.tolist(),
            "labels": labels.tolist(),
            "timestamp": datetime.now().isoformat()
        }
        
        # Write back to file
        with open(history_path, 'w') as f:
            json.dump(history, f, indent=2)
        
        log_debug(f"Saved clustering result for {sample_name} to history")
        return True
        
    except Exception as e:
        log_error(f"Failed to save clustering history for {sample_name}: {e}", exc_info=True)
        return False


def load_clustering_history(
    system: str,
    temp: int,
    base_path: str,
    exclude_sample: Optional[str] = None,
    max_samples: int = MAX_HISTORICAL_SAMPLES
) -> Dict:
    """
    Load clustering history for a system/temperature combination.
    
    Args:
        system: System name
        temp: Temperature value
        base_path: Base directory path
        exclude_sample: Optional sample name to exclude (e.g., current sample)
        max_samples: Maximum number of historical samples to return (most recent)
    
    Returns:
        Dictionary mapping sample_name to {"points": [...], "labels": [...]}
        Returns empty dict if no history or error occurs
    """
    try:
        history_path = get_history_file_path(base_path, system, temp)
        
        if not history_path.exists():
            log_debug(f"No clustering history found at {history_path}")
            return {}
        
        with open(history_path, 'r') as f:
            full_history = json.load(f)
        
        # Filter out excluded sample
        if exclude_sample and exclude_sample in full_history:
            del full_history[exclude_sample]
        
        # Sort by timestamp (most recent first) and limit to max_samples
        sorted_samples = sorted(
            full_history.items(),
            key=lambda x: x[1].get('timestamp', ''),
            reverse=True
        )[:max_samples]
        
        # Convert back to dict (without timestamp for simplicity)
        history = {}
        for sample_name, data in sorted_samples:
            history[sample_name] = {
                "points": data["points"],
                "labels": data["labels"]
            }
        
        if history:
            log_info(f"Loaded {len(history)} historical samples for {system}/{temp}")
        
        return history
        
    except Exception as e:
        log_error(f"Failed to load clustering history for {system}/{temp}: {e}", exc_info=True)
        return {}


def compute_cluster_centroids(points: np.ndarray, labels: np.ndarray) -> Dict[int, np.ndarray]:
    """
    Compute centroid (mean point) for each cluster.
    
    Args:
        points: Nx3 array of composition points
        labels: N-length array of cluster labels
    
    Returns:
        Dictionary mapping cluster_id to centroid coordinates
    """
    centroids = {}
    unique_labels = np.unique(labels)
    
    for label in unique_labels:
        if label == -1:  # Skip outliers
            continue
        cluster_points = points[labels == label]
        if len(cluster_points) > 0:
            centroids[label] = np.mean(cluster_points, axis=0)
    
    return centroids


def get_historical_data_for_plotting(
    clustering_history: Dict,
    ternary_to_xy_func
) -> List[Dict]:
    """
    Process historical clustering data for visualization.
    
    Args:
        clustering_history: Dictionary from load_clustering_history()
        ternary_to_xy_func: Function to convert 3D to 2D coordinates
    
    Returns:
        List of dictionaries with processed data for each historical sample:
        [
            {
                "sample_name": str,
                "clusters": {
                    cluster_id: {
                        "points_2d": np.ndarray,  # Nx2 array
                        "centroid_2d": np.ndarray  # (x, y) tuple
                    }
                }
            },
            ...
        ]
    """
    processed_data = []
    
    for sample_name, sample_data in clustering_history.items():
        hist_points = np.array(sample_data['points'])
        hist_labels = np.array(sample_data['labels'])
        
        # Convert to 2D
        hist_points_2d = ternary_to_xy_func(hist_points)
        
        # Compute centroids in 3D then convert to 2D
        centroids_3d = compute_cluster_centroids(hist_points, hist_labels)
        
        clusters_data = {}
        for cluster_id, centroid_3d in centroids_3d.items():
            cluster_mask = hist_labels == cluster_id
            cluster_points_2d = hist_points_2d[cluster_mask]
            centroid_2d = ternary_to_xy_func(centroid_3d.reshape(1, -1))[0]
            
            clusters_data[cluster_id] = {
                "points_2d": cluster_points_2d,
                "centroid_2d": centroid_2d
            }
        
        processed_data.append({
            "sample_name": sample_name,
            "clusters": clusters_data
        })
    
    return processed_data
