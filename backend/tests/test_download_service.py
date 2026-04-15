# readex/backend/tests/test_download_service.py
import os
import zipfile
from unittest.mock import AsyncMock
import pytest
from sources.base import ChapterInfo
from services.download_service import DownloadService


@pytest.fixture
def tmp_library(tmp_path):
    return tmp_path / "library"


@pytest.fixture
def mock_source():
    source = AsyncMock()
    source.name = "mangadex"
    source.download_chapter = AsyncMock(return_value=[
        b"fake-jpg-page-1",
        b"fake-jpg-page-2",
        b"fake-jpg-page-3",
    ])
    return source


@pytest.fixture
def service(tmp_library):
    return DownloadService(library_path=str(tmp_library))


@pytest.mark.asyncio
async def test_download_creates_cbz(service, mock_source, tmp_library):
    chapter = ChapterInfo(
        source_chapter_id="ch1", chapter_number=1.0,
        title="Chapter 1", url="https://example.com/ch1",
    )
    result_path = await service.download_and_package(
        source=mock_source, folder_name="One Piece",
        chapter=chapter, content_type="manga",
    )
    assert result_path.endswith(".cbz")
    assert os.path.exists(result_path)
    with zipfile.ZipFile(result_path) as zf:
        names = zf.namelist()
        assert len(names) == 3
        assert names[0] == "001.jpg"


@pytest.mark.asyncio
async def test_download_manga_naming(service, mock_source, tmp_library):
    chapter = ChapterInfo(
        source_chapter_id="ch50", chapter_number=50.0,
        title=None, url="",
    )
    result_path = await service.download_and_package(
        source=mock_source, folder_name="Naruto",
        chapter=chapter, content_type="manga",
    )
    assert result_path.endswith("Chapter 50.cbz")
    assert "Naruto" in result_path


@pytest.mark.asyncio
async def test_download_comic_naming(service, mock_source, tmp_library):
    chapter = ChapterInfo(
        source_chapter_id="iss1", chapter_number=1.0,
        title=None, url="",
    )
    result_path = await service.download_and_package(
        source=mock_source, folder_name="Batman (2016)",
        chapter=chapter, content_type="comic",
    )
    assert result_path.endswith("Issue 001.cbz")


@pytest.mark.asyncio
async def test_download_half_chapter(service, mock_source, tmp_library):
    chapter = ChapterInfo(
        source_chapter_id="ch10-5", chapter_number=10.5,
        title=None, url="",
    )
    result_path = await service.download_and_package(
        source=mock_source, folder_name="Test",
        chapter=chapter, content_type="manga",
    )
    assert result_path.endswith("Chapter 10.5.cbz")


@pytest.mark.asyncio
async def test_skip_if_already_exists(service, mock_source, tmp_library):
    folder = tmp_library / "Existing"
    folder.mkdir(parents=True)
    # A real CBZ from a prior download (>1KB) should be skipped
    (folder / "Chapter 1.cbz").write_bytes(b"x" * 2048)

    chapter = ChapterInfo(
        source_chapter_id="ch1", chapter_number=1.0,
        title=None, url="",
    )
    result_path = await service.download_and_package(
        source=mock_source, folder_name="Existing",
        chapter=chapter, content_type="manga",
    )
    assert result_path is None
    mock_source.download_chapter.assert_not_called()


@pytest.mark.asyncio
async def test_overwrites_stub_empty_cbz(service, mock_source, tmp_library):
    """A tiny stub CBZ from a prior failed download should be overwritten."""
    folder = tmp_library / "Stubbed"
    folder.mkdir(parents=True)
    (folder / "Chapter 1.cbz").write_bytes(b"")  # empty stub

    chapter = ChapterInfo(
        source_chapter_id="ch1", chapter_number=1.0,
        title=None, url="",
    )
    result_path = await service.download_and_package(
        source=mock_source, folder_name="Stubbed",
        chapter=chapter, content_type="manga",
    )
    assert result_path is not None
    assert os.path.getsize(result_path) > 100
    mock_source.download_chapter.assert_called_once()


@pytest.mark.asyncio
async def test_raises_on_no_images(tmp_library):
    """When source returns no images, raise (don't create empty CBZ)."""
    from unittest.mock import AsyncMock
    bad_source = AsyncMock()
    bad_source.name = "broken"
    bad_source.download_chapter = AsyncMock(return_value=[])

    service = DownloadService(library_path=str(tmp_library))
    chapter = ChapterInfo(
        source_chapter_id="ch1", chapter_number=1.0,
        title=None, url="",
    )
    with pytest.raises(RuntimeError, match="no images"):
        await service.download_and_package(
            source=bad_source, folder_name="Empty",
            chapter=chapter, content_type="manga",
        )
    # No file should be created
    assert not (tmp_library / "Empty" / "Chapter 1.cbz").exists() or \
        (tmp_library / "Empty" / "Chapter 1.cbz").stat().st_size == 0
