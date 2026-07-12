import asyncio
from pathlib import Path

import numpy as np

from app.services import plate_tracker
from app.services.plate_tracker import TrackedPlate, VideoStreamProcessor
from app.services.plate_recognition import PlateRecognizer
from app.services.session_manager import SessionStatus, SessionType, TrackingSession
from app.services import video_processor


def _detection(plate_no: str, confidence: float) -> dict:
    return {
        "plateNo": plate_no,
        "color": "blue",
        "vehicleType": "car",
        "confidence": confidence,
        "bbox": {"x": 10, "y": 10, "width": 30, "height": 12},
    }


def test_default_plate_confidence_threshold_is_060(monkeypatch):
    monkeypatch.delenv("CARMATE_PLATE_CONFIDENCE", raising=False)
    recognizer = PlateRecognizer.__new__(PlateRecognizer)
    recognizer.catcher = lambda _image: [
        ("川A59000", 0.59, 0, [0, 0, 10, 5]),
        ("川A60000", 0.60, 0, [10, 0, 20, 5]),
    ]

    results = recognizer.detect_on_full_image(
        np.zeros((20, 30, 3), dtype=np.uint8)
    )

    assert [result["plate_no"] for result in results] == ["川A60000"]


def test_tracked_plate_keeps_highest_confidence_plate_number():
    track = TrackedPlate(1, _detection("川A11111", 0.80), 0, 0.0)

    track.update(_detection("川A22222", 0.70), 1, 0.1)
    assert track.plate_no == "川A11111"
    assert track.best_confidence == 0.80

    track.update(_detection("川A33333", 0.95), 2, 0.2)
    assert track.plate_no == "川A33333"
    assert track.best_confidence == 0.95
    assert track.confidence == 0.8167


def test_video_stream_processor_does_not_skip_frames_by_default(monkeypatch):
    calls = []

    def fake_recognize(_frame):
        calls.append(1)
        return []

    monkeypatch.setattr(plate_tracker, "recognize_plates", fake_recognize)
    processor = VideoStreamProcessor()
    frame = np.zeros((2, 2, 3), dtype=np.uint8)

    processor.process_frame(frame, 25.0)
    processor.process_frame(frame, 25.0)

    assert len(calls) == 2


def test_stream_worker_processes_first_and_latest_frame(monkeypatch):
    async def scenario():
        session = TrackingSession("stream-test", SessionType.STREAM, "rtsp://test")
        queue = asyncio.Queue(maxsize=1)
        started = asyncio.Event()
        release = asyncio.Event()
        processed = []

        async def fake_run_detection(_session, _processor, _frame, _fps, frame_idx):
            processed.append(frame_idx)
            if frame_idx == 1:
                started.set()
                await release.wait()

        monkeypatch.setattr(video_processor, "_run_detection", fake_run_detection)
        worker = asyncio.create_task(
            video_processor._stream_detection_worker(session, object(), queue)
        )

        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        video_processor._replace_queued_frame(queue, (frame, 25.0, 1))
        await started.wait()
        video_processor._replace_queued_frame(queue, (frame, 25.0, 2))
        video_processor._replace_queued_frame(queue, (frame, 25.0, 3))
        release.set()

        await asyncio.wait_for(queue.join(), timeout=1)
        await video_processor._stop_stream_detection_worker(queue, worker)
        assert processed == [1, 3]

    asyncio.run(scenario())


def test_seek_resets_processor_before_processing_target_frame():
    class FakeCapture:
        def __init__(self):
            self.position = None

        def set(self, _key, value):
            self.position = value

        def read(self):
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

    class FakeProcessor:
        def __init__(self):
            self.reset_count = 0
            self.calls = 0

        def reset(self):
            self.reset_count += 1

        def process_frame(self, _frame, _fps):
            self.calls += 1
            return [], np.zeros((2, 2, 3), dtype=np.uint8)

    async def scenario():
        session = TrackingSession("video-test", SessionType.VIDEO, "video.mp4")
        session.update_status(SessionStatus.PROCESSING)
        session.put_client_message({"type": "seek", "currentTime": 2.5})
        processor = FakeProcessor()
        cap = FakeCapture()

        async def stop_after_result(message):
            if message.get("type") == "detection":
                session.update_status(SessionStatus.STOPPED)

        session.broadcast = stop_after_result
        await video_processor._run_event_loop(session, cap, processor, 100, 10.0)

        assert processor.reset_count == 1
        assert processor.calls == 1
        assert cap.position == 25

    asyncio.run(scenario())


def test_cleanup_deletes_only_owned_temporary_source(tmp_path: Path):
    owned = tmp_path / "owned.mp4"
    owned.write_bytes(b"video")
    owned_session = TrackingSession(
        "owned",
        SessionType.VIDEO,
        str(owned),
        delete_source_on_cleanup=True,
    )
    video_processor._cleanup_session_source(owned_session)
    assert not owned.exists()

    retained = tmp_path / "retained.mp4"
    retained.write_bytes(b"video")
    retained_session = TrackingSession("retained", SessionType.VIDEO, str(retained))
    video_processor._cleanup_session_source(retained_session)
    assert retained.exists()
