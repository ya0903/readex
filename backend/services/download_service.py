import os
import zipfile

from sources.base import ChapterInfo, SourceAdapter


class DownloadService:
    def __init__(self, library_path: str):
        # Default fallback library path. Callers should pass library_path to
        # download_and_package() to override per content-type.
        self.library_path = library_path

    def _format_chapter_filename(
        self, chapter: ChapterInfo, content_type: str
    ) -> str:
        num = chapter.chapter_number
        if num == int(num):
            num_str = str(int(num))
        else:
            num_str = str(num)

        if content_type == "comic":
            return f"Issue {num_str.zfill(3)}.cbz"
        return f"Chapter {num_str}.cbz"

    def _get_chapter_path(self, library_path: str, folder_name: str, filename: str) -> str:
        return os.path.join(library_path, folder_name, filename)

    @staticmethod
    def _ext_for_image(data: bytes) -> str:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if data.startswith(b"GIF8"):
            return "gif"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "webp"
        # default to jpg (covers \xff\xd8 JPEG)
        return "jpg"

    async def download_and_package(
        self,
        source: SourceAdapter,
        folder_name: str,
        chapter: ChapterInfo,
        content_type: str,
        comicinfo_xml: str | None = None,
        progress_cb=None,  # callable(current:int, total:int)
        library_path: str | None = None,
    ) -> str | None:
        lib = library_path or self.library_path
        filename = self._format_chapter_filename(chapter, content_type)
        chapter_path = self._get_chapter_path(lib, folder_name, filename)

        if os.path.exists(chapter_path) and os.path.getsize(chapter_path) > 1024:
            return None

        # Try the new callback-aware signature first; fall back to the
        # legacy signature for sources that haven't been updated yet.
        try:
            images = await source.download_chapter(chapter, progress_cb=progress_cb)
        except TypeError:
            images = await source.download_chapter(chapter)
        if not images:
            raise RuntimeError(
                f"Source returned no images for chapter {chapter.chapter_number}"
            )

        series_dir = os.path.join(lib, folder_name)
        os.makedirs(series_dir, exist_ok=True)

        if os.path.exists(chapter_path):
            try:
                os.remove(chapter_path)
            except OSError:
                pass

        tmp_path = chapter_path + ".tmp"
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_STORED) as zf:
                for i, img_data in enumerate(images):
                    if not img_data:
                        continue
                    ext = self._ext_for_image(img_data)
                    zf.writestr(f"{i + 1:03d}.{ext}", img_data)
                if comicinfo_xml:
                    zf.writestr("ComicInfo.xml", comicinfo_xml)
            os.rename(tmp_path, chapter_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

        return chapter_path
