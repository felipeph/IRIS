import pytest
import time
from datetime import datetime
from src.core.ui import ProgressTracker, PipelineUI

def test_progress_tracker_bytes():
    # Simulate a tracker with 100 MB total
    tracker = ProgressTracker(100 * 1024 * 1024, mode="bytes")
    
    # Simulate update with 10 MB
    tracker.update(10 * 1024 * 1024)
    assert tracker.completed_units == 10 * 1024 * 1024
    
    # Override time and force speed calculation
    tracker.last_update_time = time.time() - 1.0 # 1 sec ago
    tracker.update(20 * 1024 * 1024) # 20MB added in 1 sec
    
    assert tracker.speed > 0
    speed_str = tracker.get_speed_str()
    assert "MB/s" in speed_str or "KB/s" in speed_str
    
    eta_str = tracker.get_eta_str()
    # It shouldn't be --:--:-- because speed > 0
    assert eta_str != "--:--:--"

def test_progress_tracker_items():
    # Simulate a tracker with 1000 items
    tracker = ProgressTracker(1000, mode="items")
    
    tracker.last_update_time = time.time() - 2.0
    tracker.update(50) # 50 items added in 2 secs
    
    assert tracker.speed > 0
    speed_str = tracker.get_speed_str()
    assert "itens/s" in speed_str
    
    eta_str = tracker.get_eta_str()
    assert eta_str != "--:--:--"

def test_pipeline_ui_renderable():
    tracker = ProgressTracker(100, mode="items")
    renderable = PipelineUI.generate_renderable(
        tracker=tracker,
        stage_title="TEST",
        start_str="12:00:00",
        total_files=10,
        total_gb=1.5,
        current_item_name="test.jpg",
        status_msg="In progress"
    )
    
    # Should be a Rich Group
    assert renderable is not None
    # Just asserting it doesn't crash during generation
