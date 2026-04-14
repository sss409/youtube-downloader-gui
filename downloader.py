"""YouTube動画GUIダウンローダー (yt-dlp + tkinter)"""

import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

import yt_dlp


class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube ダウンローダー")
        self.resizable(False, False)
        self._save_dir = ""
        self._build_ui()

    # ── UI構築 ──────────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # URL入力
        tk.Label(self, text="URL:").grid(row=0, column=0, sticky="e", **pad)
        self.url_var = tk.StringVar()
        tk.Entry(self, textvariable=self.url_var, width=55).grid(row=0, column=1, columnspan=2, sticky="ew", **pad)

        # フォーマット選択
        tk.Label(self, text="フォーマット:").grid(row=1, column=0, sticky="e", **pad)
        self.fmt_var = tk.StringVar(value="動画 (最高画質)")
        formats = ["動画 (最高画質)", "動画 1080p", "動画 720p", "動画 480p", "音声のみ (MP3)"]
        ttk.Combobox(self, textvariable=self.fmt_var, values=formats, state="readonly", width=30).grid(
            row=1, column=1, sticky="w", **pad
        )

        # 保存先
        tk.Label(self, text="保存先:").grid(row=2, column=0, sticky="e", **pad)
        self.dir_var = tk.StringVar(value="（未選択）")
        tk.Label(self, textvariable=self.dir_var, width=40, anchor="w", relief="sunken").grid(
            row=2, column=1, sticky="ew", **pad
        )
        tk.Button(self, text="選択...", command=self._choose_dir).grid(row=2, column=2, **pad)

        # ダウンロードボタン
        self.dl_btn = tk.Button(self, text="ダウンロード", width=20, bg="#0078d4", fg="white", command=self._start_download)
        self.dl_btn.grid(row=3, column=0, columnspan=3, pady=8)

        # 進捗バー
        self.progress = ttk.Progressbar(self, length=480, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=3, padx=10, pady=(0, 4))

        # ログ
        self.log = scrolledtext.ScrolledText(self, width=65, height=12, state="disabled", font=("Consolas", 9))
        self.log.grid(row=5, column=0, columnspan=3, padx=10, pady=(0, 10))

    # ── イベントハンドラ ─────────────────────────────────────

    def _choose_dir(self):
        d = filedialog.askdirectory()
        if d:
            self._save_dir = d
            self.dir_var.set(d)

    def _start_download(self):
        url = self.url_var.get().strip()
        if not url:
            self._log("⚠ URLを入力してください")
            return
        if not self._save_dir:
            self._log("⚠ 保存先フォルダを選択してください")
            return

        self.dl_btn.config(state="disabled")
        self.progress["value"] = 0
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    # ── ダウンロード処理 ──────────────────────────────────────

    def _download(self, url: str):
        opts = self._build_opts()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self._log("✅ ダウンロード完了")
        except Exception as e:
            self._log(f"❌ エラー: {e}")
        finally:
            self.dl_btn.config(state="normal")

    def _build_opts(self) -> dict:
        fmt = self.fmt_var.get()
        fmt_map = {
            # mergeフォーマット: ffmpegマージを前提に最良ストリームを選択
            "動画 (最高画質)": "bestvideo+bestaudio/best",
            "動画 1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "動画 720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "動画 480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "音声のみ (MP3)": "bestaudio/best",
        }
        opts = {
            "outtmpl": f"{self._save_dir}/%(title)s.%(ext)s",
            "format": fmt_map[fmt],
            "merge_output_format": "mp4",          # マージ後の出力形式を統一
            "concurrent_fragment_downloads": 4,    # フラグメントを4並列でDL
            "throttledratelimit": 100_000,          # 100KB/s以下でスロットリング検出・再試行
            "progress_hooks": [self._progress_hook],
            "logger": _QtLogger(self._log),
            "noplaylist": True,
        }
        if fmt == "音声のみ (MP3)":
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        return opts

    # GUI更新を0.5秒に間引くための最終更新時刻
    _last_progress_update: float = 0.0

    def _progress_hook(self, d: dict):
        import time
        if d["status"] == "downloading":
            now = time.monotonic()
            if now - self._last_progress_update < 1.0:
                return  # 0.5秒未満の更新は無視してGUI負荷を軽減
            self._last_progress_update = now
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = downloaded / total * 100
                self.progress["value"] = pct
            speed = d.get("_speed_str", "")
            eta = d.get("_eta_str", "")
            self._log(f"  {d.get('_percent_str', '').strip():>7}  速度: {speed}  残り: {eta}", replace_last=True)
        elif d["status"] == "finished":
            self._last_progress_update = 0.0
            self.progress["value"] = 100
            self._log(f"  処理中: {d['filename']}")

    # ── ユーティリティ ────────────────────────────────────────

    def _log(self, msg: str, replace_last: bool = False):
        """スレッドセーフなログ追記"""
        self.after(0, self._write_log, msg, replace_last)

    def _write_log(self, msg: str, replace_last: bool):
        self.log.config(state="normal")
        if replace_last:
            self.log.delete("end-2l", "end-1c")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")


class _QtLogger:
    """yt-dlp のログを GUI ログに転送するアダプター"""

    def __init__(self, log_fn):
        self._log = log_fn

    def debug(self, msg):
        if msg.startswith("[debug]"):
            return
        self._log(msg)

    def info(self, msg):
        self._log(msg)

    def warning(self, msg):
        self._log(f"⚠ {msg}")

    def error(self, msg):
        self._log(f"❌ {msg}")


if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()
