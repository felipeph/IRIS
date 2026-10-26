import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.project import Project, create_project
from src.core.config import config
from src.modules.youtube.cleaner import (
    verify_youtube_upload_status,
    delete_local_rendered_video,
    clean_empty_parent_dirs,
    execute_post_upload_cleanup
)
from src.modules.youtube.stage import YouTubeUploadStage
from src.core.project import init_central_db

def test_verify_youtube_upload_status_success():
    mock_yt = MagicMock()
    # Teste para uploaded
    mock_yt.videos().list().execute.return_value = {
        "items": [{"id": "abc1234", "status": {"uploadStatus": "uploaded"}}]
    }
    ok, msg = verify_youtube_upload_status(mock_yt, "abc1234")
    assert ok is True
    assert "uploaded" in msg

    # Teste para processed
    mock_yt.videos().list().execute.return_value = {
        "items": [{"id": "abc1234", "status": {"uploadStatus": "processed"}}]
    }
    ok, msg = verify_youtube_upload_status(mock_yt, "abc1234")
    assert ok is True
    assert "processed" in msg

    # Teste para processing
    mock_yt.videos().list().execute.return_value = {
        "items": [{"id": "abc1234", "status": {"uploadStatus": "processing"}}]
    }
    ok, msg = verify_youtube_upload_status(mock_yt, "abc1234")
    assert ok is True
    assert "processamento" in msg.lower()

def test_verify_youtube_upload_status_failed_or_rejected():
    mock_yt = MagicMock()
    # Rejeitado
    mock_yt.videos().list().execute.return_value = {
        "items": [{"id": "abc1234", "status": {"uploadStatus": "rejected", "rejectionReason": "copyright"}}]
    }
    ok, msg = verify_youtube_upload_status(mock_yt, "abc1234")
    assert ok is False
    assert "rejeitado" in msg.lower() or "copyright" in msg.lower()

    # Falha
    mock_yt.videos().list().execute.return_value = {
        "items": [{"id": "abc1234", "status": {"uploadStatus": "failed", "rejectionReason": "invalidFormat"}}]
    }
    ok, msg = verify_youtube_upload_status(mock_yt, "abc1234")
    assert ok is False
    assert "falha" in msg.lower() or "invalidFormat" in msg.lower()

def test_verify_youtube_upload_status_not_found():
    mock_yt = MagicMock()
    mock_yt.videos().list().execute.return_value = {"items": []}
    ok, msg = verify_youtube_upload_status(mock_yt, "inexistente")
    assert ok is False
    assert "não foi localizado" in msg

def test_verify_youtube_upload_status_api_exception():
    mock_yt = MagicMock()
    mock_yt.videos().list().execute.side_effect = ConnectionResetError("Connection lost")
    ok, msg = verify_youtube_upload_status(mock_yt, "abc1234")
    assert ok is False
    assert "Falha na comunicação" in msg

def test_verify_youtube_upload_status_missing_args():
    ok, msg = verify_youtube_upload_status(None, "abc1234")
    assert ok is False
    ok, msg = verify_youtube_upload_status(MagicMock(), "")
    assert ok is False

def test_delete_local_rendered_video_trash(tmp_path):
    video_file = tmp_path / "sample_tl.mp4"
    video_file.write_bytes(b"0" * 2048)

    with patch("src.modules.youtube.cleaner.send2trash") as mock_trash:
        ok, freed, err = delete_local_rendered_video(video_file, to_trash=True)
        assert ok is True
        assert freed == 2048
        assert err == ""
        mock_trash.assert_called_once_with(str(video_file.resolve()))

def test_delete_local_rendered_video_unlink(tmp_path):
    video_file = tmp_path / "sample_ve.mp4"
    video_file.write_bytes(b"1" * 4096)
    assert video_file.exists()

    ok, freed, err = delete_local_rendered_video(video_file, to_trash=False)
    assert ok is True
    assert freed == 4096
    assert err == ""
    assert not video_file.exists()

def test_delete_local_rendered_video_non_existent(tmp_path):
    video_file = tmp_path / "ghost.mp4"
    ok, freed, err = delete_local_rendered_video(video_file)
    assert ok is True
    assert freed == 0

def test_clean_empty_parent_dirs(tmp_path):
    root_prod = tmp_path / "6_Produzidos"
    day_dir = root_prod / "2026" / "08" / "17"
    day_dir.mkdir(parents=True)
    video_file = day_dir / "test.mp4"
    video_file.write_bytes(b"content")

    # Arquivo ainda existe -> não deve remover nada
    removed = clean_empty_parent_dirs(video_file, root_prod)
    assert removed == 0
    assert day_dir.exists()

    # Apaga arquivo e executa limpeza
    video_file.unlink()
    removed = clean_empty_parent_dirs(video_file, root_prod)
    assert removed == 3  # 17, 08 e 2026 removidos
    assert not day_dir.exists()
    assert not (root_prod / "2026").exists()
    assert root_prod.exists()  # Raiz delimitadora 6_Produzidos PRESERVADA

def test_clean_empty_parent_dirs_stops_at_non_empty(tmp_path):
    root_prod = tmp_path / "7_Video_Editado_4K"
    day_dir = root_prod / "2026" / "08" / "17"
    other_day = root_prod / "2026" / "08" / "18"
    day_dir.mkdir(parents=True)
    other_day.mkdir(parents=True)
    (other_day / "keep.mp4").write_bytes(b"keep me")

    video_file = day_dir / "del.mp4"
    video_file.write_bytes(b"delete me")
    video_file.unlink()

    removed = clean_empty_parent_dirs(video_file, root_prod)
    assert removed == 1  # Apenas a pasta '17' removida
    assert not day_dir.exists()
    assert (root_prod / "2026" / "08").exists()  # '08' contém '18' com arquivo, preservada

def test_execute_post_upload_cleanup_timelapse_success(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_cleanup_tl_proj", str(proj_dir))

    video_path = tmp_path / "6_Produzidos" / "2026" / "08" / "17" / "tl.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"video_bytes_123")

    project.save_timelapse({
        "output_video_path": str(video_path.resolve()),
        "status": "uploaded",
        "youtube_video_id": "yt_123"
    })

    mock_yt = MagicMock()
    with patch("src.modules.youtube.cleaner.verify_youtube_upload_status", return_value=(True, "OK")), \
         patch("src.modules.youtube.cleaner.delete_local_rendered_video", return_value=(True, len(b"video_bytes_123"), "")), \
         patch("src.modules.youtube.cleaner.clean_empty_parent_dirs"):

        success = execute_post_upload_cleanup(
            project=project,
            video_path=video_path,
            video_id="yt_123",
            job_type="timelapse",
            youtube=mock_yt,
            interactive=False
        )
        assert success is True

        tls = project.get_timelapses()
        assert len(tls) == 1
        assert tls[0]["local_file_deleted"] is True

def test_execute_post_upload_cleanup_edited_video_success(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_cleanup_ve_proj", str(proj_dir))

    video_path = tmp_path / "7_Video_Editado_4K" / "2026" / "08" / "17" / "ve.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"ve_bytes_456")

    project.save_edited_video({
        "output_video_path": str(video_path.resolve()),
        "status": "uploaded",
        "youtube_video_id": "yt_ve_456"
    })

    mock_yt = MagicMock()
    with patch("src.modules.youtube.cleaner.verify_youtube_upload_status", return_value=(True, "OK")), \
         patch("src.modules.youtube.cleaner.delete_local_rendered_video", return_value=(True, len(b"ve_bytes_456"), "")), \
         patch("src.modules.youtube.cleaner.clean_empty_parent_dirs"):

        success = execute_post_upload_cleanup(
            project=project,
            video_path=video_path,
            video_id="yt_ve_456",
            job_type="edited_video",
            youtube=mock_yt,
            interactive=False
        )
        assert success is True

        ves = project.get_edited_videos()
        assert len(ves) == 1
        assert ves[0]["local_file_deleted"] is True

def test_execute_post_upload_cleanup_aborts_on_failed_verification(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_cleanup_abort_proj", str(proj_dir))

    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"important_video")

    with patch("src.modules.youtube.cleaner.verify_youtube_upload_status", return_value=(False, "Upload rejected")), \
         patch("src.modules.youtube.cleaner.delete_local_rendered_video") as mock_del:

        success = execute_post_upload_cleanup(
            project=project,
            video_path=video_path,
            video_id="bad_id",
            job_type="timelapse",
            youtube=MagicMock(),
            interactive=False
        )
        assert success is False
        mock_del.assert_not_called()
        assert video_path.exists()

def test_execute_post_upload_cleanup_user_cancels(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_cleanup_cancel_proj", str(proj_dir))

    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"content")

    with patch("src.modules.youtube.cleaner.config.get", return_value={"cleanup_local_videos": True, "auto_cleanup_videos": False, "cleanup_to_trash": True}), \
         patch("src.modules.youtube.cleaner.verify_youtube_upload_status", return_value=(True, "OK")), \
         patch("src.modules.youtube.cleaner.Confirm.ask", return_value=False), \
         patch("src.modules.youtube.cleaner.delete_local_rendered_video", return_value=(True, 100, "")) as mock_del:

        success = execute_post_upload_cleanup(
            project=project,
            video_path=video_path,
            video_id="vid_123",
            job_type="timelapse",
            youtube=MagicMock(),
            interactive=True
        )
        assert success is True
        mock_del.assert_not_called()

def test_execute_post_upload_cleanup_disabled_config(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_cleanup_disabled_proj", str(proj_dir))
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"content")

    with patch("src.modules.youtube.cleaner.config.get", return_value={"cleanup_local_videos": False}), \
         patch("src.modules.youtube.cleaner.verify_youtube_upload_status") as mock_verify:

        success = execute_post_upload_cleanup(
            project=project,
            video_path=video_path,
            video_id="vid_123",
            job_type="timelapse",
            youtube=MagicMock(),
            interactive=False
        )
        assert success is True
        mock_verify.assert_not_called()

def test_youtube_upload_stage_calls_cleanup_after_insert(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_stage_upload_clean", str(proj_dir))

    video_path = tmp_path / "tl_test.mp4"
    video_path.write_bytes(b"sample video bytes")

    project.save_timelapse({
        "output_video_path": str(video_path.resolve()),
        "status": "rendered"
    })

    stage = YouTubeUploadStage("youtube", "Publicação no YouTube")

    mock_youtube = MagicMock()
    mock_insert_req = MagicMock()
    mock_insert_req.next_chunk.return_value = (None, {"id": "uploaded_vid_999"})
    mock_youtube.videos().insert.return_value = mock_insert_req

    with patch("src.modules.youtube.stage.get_authenticated_service", return_value=mock_youtube), \
         patch("src.modules.youtube.stage.MediaFileUpload"), \
         patch("src.modules.youtube.stage.add_video_to_playlist"), \
         patch("src.modules.youtube.stage.send_windows_toast"), \
         patch("src.modules.youtube.stage.send_ntfy_notification"), \
         patch("src.modules.youtube.stage.time.sleep"), \
         patch("src.modules.youtube.stage.execute_post_upload_cleanup") as mock_cleanup:

        ok = stage.run(project, interactive=False)
        assert ok is True
        mock_cleanup.assert_called_once()
        call_kwargs = mock_cleanup.call_args.kwargs
        assert call_kwargs["video_id"] == "uploaded_vid_999"
        assert call_kwargs["job_type"] == "timelapse"
        assert str(call_kwargs["video_path"].resolve()) == str(video_path.resolve())

def test_youtube_upload_stage_scans_already_uploaded_videos_for_cleanup(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_stage_already_uploaded", str(proj_dir))

    video_path = tmp_path / "already_up.mp4"
    video_path.write_bytes(b"already uploaded bytes")

    project.save_timelapse({
        "output_video_path": str(video_path.resolve()),
        "status": "uploaded",
        "youtube_video_id": "yt_already_123"
    })

    stage = YouTubeUploadStage("youtube", "Publicação no YouTube")
    mock_youtube = MagicMock()

    with patch("src.modules.youtube.stage.get_authenticated_service", return_value=mock_youtube), \
         patch("src.modules.youtube.stage.execute_post_upload_cleanup") as mock_cleanup:

        ok = stage.run(project, interactive=False, clean_already_uploaded=True)
        assert ok is True
        mock_cleanup.assert_called_once()
        call_kwargs = mock_cleanup.call_args.kwargs
        assert call_kwargs["video_id"] == "yt_already_123"

def test_delete_local_rendered_video_retry_on_permission_error(tmp_path):
    video_file = tmp_path / "locked_video.mp4"
    video_file.write_bytes(b"locked" * 100)

    # 1. Simular falha transitória (PermissionError na 1ª tentativa, sucesso na 2ª)
    calls = []
    def fake_send2trash(path):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError("[WinError 32] Arquivo sendo usado por outro processo")
        return None

    with patch("src.modules.youtube.cleaner.send2trash", side_effect=fake_send2trash), \
         patch("src.modules.youtube.cleaner.time.sleep") as mock_sleep, \
         patch("src.modules.youtube.cleaner.gc.collect") as mock_gc:
        ok, freed, err = delete_local_rendered_video(video_file, to_trash=True, max_retries=3, retry_delay=0.1)
        assert ok is True
        assert freed == len(b"locked" * 100)
        assert err == ""
        assert len(calls) == 2
        mock_sleep.assert_called_once_with(0.1)
        assert mock_gc.call_count >= 2

    # 2. Simular falha permanente após 3 tentativas
    with patch("src.modules.youtube.cleaner.send2trash", side_effect=PermissionError("[WinError 32] Bloqueado")), \
         patch("src.modules.youtube.cleaner.time.sleep"), \
         patch("src.modules.youtube.cleaner.gc.collect"):
        ok, freed, err = delete_local_rendered_video(video_file, to_trash=True, max_retries=3, retry_delay=0.1)
        assert ok is False
        assert freed == 0
        assert "Permissão negada após 3 tentativas" in err

def test_youtube_upload_stage_releases_media_file_descriptor(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_stage_release_fd", str(proj_dir))

    video_path = tmp_path / "tl_release_fd.mp4"
    video_path.write_bytes(b"dummy video")

    project.save_timelapse({
        "output_video_path": str(video_path.resolve()),
        "status": "rendered"
    })

    stage = YouTubeUploadStage("youtube", "Publicação no YouTube")
    mock_youtube = MagicMock()
    mock_insert_req = MagicMock()
    mock_insert_req.next_chunk.return_value = (None, {"id": "uploaded_vid_fd"})
    mock_youtube.videos().insert.return_value = mock_insert_req

    mock_media = MagicMock()
    mock_media._fd = MagicMock()

    with patch("src.modules.youtube.stage.get_authenticated_service", return_value=mock_youtube), \
         patch("src.modules.youtube.stage.MediaFileUpload", return_value=mock_media), \
         patch("src.modules.youtube.stage.add_video_to_playlist"), \
         patch("src.modules.youtube.stage.send_windows_toast"), \
         patch("src.modules.youtube.stage.send_ntfy_notification"), \
         patch("src.modules.youtube.stage.time.sleep"), \
         patch("src.modules.youtube.stage.execute_post_upload_cleanup"):

        ok = stage.run(project, interactive=False)
        assert ok is True
        mock_media._fd.close.assert_called_once()

def test_youtube_upload_stage_uses_default_64mb_chunk_size(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_stage_chunk_64mb", str(proj_dir))

    video_path = tmp_path / "tl_chunk.mp4"
    video_path.write_bytes(b"dummy video content")

    project.save_timelapse({
        "output_video_path": str(video_path.resolve()),
        "status": "rendered"
    })

    stage = YouTubeUploadStage("youtube", "Publicação no YouTube")
    mock_youtube = MagicMock()
    mock_insert_req = MagicMock()
    mock_insert_req.next_chunk.return_value = (None, {"id": "uploaded_vid_chunk"})
    mock_youtube.videos().insert.return_value = mock_insert_req

    with patch("src.modules.youtube.stage.get_authenticated_service", return_value=mock_youtube), \
         patch("src.modules.youtube.stage.MediaFileUpload") as mock_media_cls, \
         patch("src.modules.youtube.stage.add_video_to_playlist"), \
         patch("src.modules.youtube.stage.send_windows_toast"), \
         patch("src.modules.youtube.stage.send_ntfy_notification"), \
         patch("src.modules.youtube.stage.time.sleep"), \
         patch("src.modules.youtube.stage.execute_post_upload_cleanup"):

        mock_media_inst = MagicMock()
        mock_media_inst._fd = None
        mock_media_cls.return_value = mock_media_inst

        ok = stage.run(project, interactive=False)
        assert ok is True

        mock_media_cls.assert_called_once()
        _, kwargs = mock_media_cls.call_args
        # 64MB = 64 * 1024 * 1024 = 67.108.864 bytes
        assert kwargs.get("chunksize") == 64 * 1024 * 1024
        assert kwargs.get("resumable") is True

def test_youtube_upload_stage_uses_custom_chunk_size(tmp_path):
    proj_dir = tmp_path / "project_root"
    proj_dir.mkdir()
    project = create_project("test_stage_custom_chunk", str(proj_dir))

    video_path = tmp_path / "tl_custom_chunk.mp4"
    video_path.write_bytes(b"dummy video content 2")

    project.save_timelapse({
        "output_video_path": str(video_path.resolve()),
        "status": "rendered"
    })

    stage = YouTubeUploadStage("youtube", "Publicação no YouTube")
    mock_youtube = MagicMock()
    mock_insert_req = MagicMock()
    mock_insert_req.next_chunk.return_value = (None, {"id": "uploaded_vid_custom"})
    mock_youtube.videos().insert.return_value = mock_insert_req

    orig_chunk = config.get("modules.youtube.chunk_size_mb", 64)
    try:
        config.set("modules.youtube.chunk_size_mb", 32)
        with patch("src.modules.youtube.stage.get_authenticated_service", return_value=mock_youtube), \
             patch("src.modules.youtube.stage.MediaFileUpload") as mock_media_cls, \
             patch("src.modules.youtube.stage.add_video_to_playlist"), \
             patch("src.modules.youtube.stage.send_windows_toast"), \
             patch("src.modules.youtube.stage.send_ntfy_notification"), \
             patch("src.modules.youtube.stage.time.sleep"), \
             patch("src.modules.youtube.stage.execute_post_upload_cleanup"):

            mock_media_inst = MagicMock()
            mock_media_inst._fd = None
            mock_media_cls.return_value = mock_media_inst

            ok = stage.run(project, interactive=False)
            assert ok is True

            mock_media_cls.assert_called_once()
            _, kwargs = mock_media_cls.call_args
            # 32MB = 32 * 1024 * 1024 = 33.554.432 bytes
            assert kwargs.get("chunksize") == 32 * 1024 * 1024
    finally:
        config.set("modules.youtube.chunk_size_mb", orig_chunk)



