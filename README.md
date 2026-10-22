# MP4 to MP3 Batch Converter

A small Windows desktop app for converting folders of MP4 videos into MP3 audio files. Choose an input folder and a destination folder; conversion runs locally. The Windows executable bundles FFmpeg, so users do not need to install it separately.

## Download and use

1. Open the repository's **Releases** page and download `MP4-to-MP3-Converter.exe`.
2. Run the EXE. On first launch, Windows may show a SmartScreen warning because the app is not code-signed; only run it if you trust this project.
3. Browse to the folder containing MP4 files and choose the destination folder.
4. Optionally include subfolders or replace existing MP3s, then click **Convert MP4 files to MP3**.

The converter also recognizes the appended fragmented-DASH MP4 payload found in the supplied PLAYit Smart Muxer sample and extracts its audio instead of converting the short silent preview. Other proprietary variants may differ. By default, subfolders are not scanned, existing MP3s are kept, and output is encoded at 192 kbps. Recursive mode preserves the input folder structure. Files are processed locally; they are not uploaded to a server.

## Build on Windows

Python 3.11 is recommended.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name MP4-to-MP3-Converter --collect-all imageio_ffmpeg app.py
```

The executable is created at `dist\MP4-to-MP3-Converter.exe`.

## License

MIT. FFmpeg is provided by the `imageio-ffmpeg` package; see its license and the FFmpeg licensing notices distributed with the build.
