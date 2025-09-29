# recorder_gui.py
import os
import sys
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, Listbox, Scrollbar
from tkinter import ttk  # Import ttk for the Progressbar widget
from datetime import datetime
from mutagen.mp3 import MP3  # Use mutagen for audio metadata

# Optional features that require extra packages:
try:
    import pyaudio
    import numpy as np
    HAVE_PYAUDIO = True
except Exception:
    HAVE_PYAUDIO = False

# -----------------------------
# Directories
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(BASE_DIR, "Recordings")
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "Transcripts")
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

# -----------------------------
# Globals
# -----------------------------
recording_process = None
is_recording = False
VU_RUNNING = False

vu_stream = None
pa = None

MIC_NAME = "Microphone Array (Realtek(R) Audio)"  # change if needed
ICON_PATH = os.path.join(BASE_DIR, "recorder_icon.ico")  # optional .ico

# -----------------------------
# Helpers
# -----------------------------
def timestamp_filename():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mp3"

def run_ffmpeg_record(output_path):
    """Start FFmpeg recording in a subprocess (detached on Windows)."""
    global recording_process
    cmd = [
        "ffmpeg", "-y",
        "-f", "dshow",
        "-i", f"audio={MIC_NAME}",
        "-codec:a", "libmp3lame",
        "-b:a", "128k",
        output_path
    ]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW
    recording_process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags
    )

def stop_ffmpeg_record():
    """Stop FFmpeg cleanly by sending 'q' to stdin."""
    global recording_process
    if not recording_process:
        return
    try:
        recording_process.stdin.write(b"q\n")
        recording_process.stdin.flush()
        recording_process.wait(timeout=5)
    except Exception:
        try:
            recording_process.terminate()
        except Exception:
            pass
    finally:
        recording_process = None

# -----------------------------
# VU meter
# -----------------------------
def start_vu():
    global vu_stream, pa, VU_RUNNING
    if not HAVE_PYAUDIO:
        return
    if vu_stream is None:
        pa = pyaudio.PyAudio()
        vu_stream = pa.open(format=pyaudio.paInt16,
                            channels=1,
                            rate=44100,
                            input=True,
                            frames_per_buffer=1024)
    VU_RUNNING = True
    update_vu()

def stop_vu():
    global vu_stream, pa, VU_RUNNING
    VU_RUNNING = False
    if vu_stream:
        vu_stream.stop_stream()
        vu_stream.close()
        vu_stream = None
    if pa:
        pa.terminate()
        pa = None
    vu_canvas.delete("all")

def update_vu():
    if not VU_RUNNING or not vu_stream:
        return
    try:
        data = vu_stream.read(1024, exception_on_overflow=False)
        arr = np.frombuffer(data, dtype=np.int16).astype(float)
        peak = float(np.abs(arr).max()) if arr.size > 0 else 0.0
        width = int((peak / 32768.0) * 300)  # Scale peak to fit the canvas width

        # Clear the canvas
        vu_canvas.delete("all")

        # Enhanced visualizer: gradient bars
        bar_height = 20
        num_bars = 10  # Number of gradient bars
        bar_width = width // num_bars if width > 0 else 0

        for i in range(num_bars):
            # Calculate the color gradient (from green to red)
            red = int(255 * (i / num_bars))
            green = int(255 * (1 - i / num_bars))
            color = f"#{red:02x}{green:02x}00"

            # Draw each bar
            vu_canvas.create_rectangle(
                i * bar_width, 0, (i + 1) * bar_width, bar_height,
                fill=color, outline=""
            )
    except Exception:
        vu_canvas.delete("all")

    if VU_RUNNING:
        root.after(50, update_vu)

# -----------------------------
# GUI actions
# -----------------------------
def start_recording():
    global is_recording
    if is_recording:
        return
    out_path = os.path.join(RECORDINGS_DIR, timestamp_filename())
    threading.Thread(target=run_ffmpeg_record, args=(out_path,), daemon=True).start()
    is_recording = True
    start_vu()
    start_btn.config(state="disabled", bg="#5db85b")
    stop_btn.config(state="normal", bg="#e94b4b")
    update_timer()

def stop_recording():
    global is_recording
    if not is_recording:
        return
    stop_vu()
    threading.Thread(target=stop_ffmpeg_record, daemon=True).start()
    is_recording = False
    start_btn.config(state="normal", bg="#4caf50")
    stop_btn.config(state="disabled", bg="#d9534f")
    timer_label.config(text="Recording stopped")

# Define the update_timer function first
def update_timer():
    if is_recording:
        elapsed = int(time.time() - update_timer.start_time)
        mins, secs = divmod(elapsed, 60)
        timer_label.config(text=f"Recording: {mins:02}:{secs:02}")
        root.after(1000, update_timer)

# Initialize the start_time attribute after the function is defined
update_timer.start_time = 0

def start_recording_wrapper():
    update_timer.start_time = time.time()
    start_recording()

# -----------------------------
# Transcribe window
# -----------------------------
def open_transcribe_window():
    trans_win = tk.Toplevel(root)
    trans_win.overrideredirect(True)
    trans_win.geometry("800x700")  # Increased size for better visibility
    trans_win.configure(bg="#1e1e2f")
    trans_win.title("Transcribe")

    # Title bar
    title_bar = tk.Frame(trans_win, bg="#2b2b3f", height=32)
    title_bar.pack(fill="x")
    title_label = tk.Label(title_bar, text="Transcribe", bg="#2b2b3f", fg="white",
                           font=("Helvetica", 12, "bold"))
    title_label.pack(side="left", padx=10)

    # Drag functionality for the transcription window
    def trans_title_press(event):
        trans_win._drag_x = event.x_root - trans_win.winfo_x()
        trans_win._drag_y = event.y_root - trans_win.winfo_y()

    def trans_title_drag(event):
        x = event.x_root - trans_win._drag_x
        y = event.y_root - trans_win._drag_y
        trans_win.geometry(f"+{x}+{y}")

    # Bind drag events to the title bar and label
    for w in (title_bar, title_label):
        w.bind("<ButtonPress-1>", trans_title_press)
        w.bind("<B1-Motion>", trans_title_drag)

    close_btn = tk.Button(title_bar, text="X", command=trans_win.destroy,
                          bg="#e04343", fg="white", bd=0, font=("Helvetica", 11),
                          relief="flat", padx=8)
    close_btn.pack(side="right", padx=4)

    # Main content
    lbl = tk.Label(trans_win, text="MP3 files in Recordings:", bg="#1e2b3f",
                   fg="white", font=("Helvetica", 12))
    lbl.pack(padx=8, pady=8, anchor="w")

    frame = tk.Frame(trans_win, bg="#1e2b3f")
    frame.pack(fill="both", expand=True, padx=10, pady=5)

    scrollbar = Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")

    listbox = Listbox(frame, bg="#2b2b3f", fg="white", font=("Helvetica", 11),
                      yscrollcommand=scrollbar.set)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=listbox.yview)

    model_var = tk.StringVar(value="small")
    model_frame = tk.Frame(trans_win, bg="#1e2b3f")
    model_frame.pack(pady=6)
    tk.Label(model_frame, text="Model:", bg="#1e2b3f", fg="white").pack(side="left", padx=4)
    model_menu = tk.OptionMenu(model_frame, model_var, "tiny", "base", "small", "medium", "large")
    model_menu.config(bg="#2b2b3f", fg="white", relief="flat")
    model_menu.pack(side="left")

    def refresh_list():
        listbox.delete(0, tk.END)
        files = sorted([f for f in os.listdir(RECORDINGS_DIR) if f.lower().endswith(".mp3")])
        for f in files:
            file_path = os.path.join(RECORDINGS_DIR, f)
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # Convert size to MB
            try:
                # Use mutagen to get the duration of the audio file
                audio = MP3(file_path)
                duration = audio.info.length  # Duration in seconds
            except Exception:
                duration = 0  # If duration cannot be determined, set it to 0

            # Display metadata in the listbox, but store only the file name
            display_text = f"{f} - {file_size:.2f} MB - {int(duration)} sec"
            listbox.insert(tk.END, (f, display_text))  # Store tuple (file_name, display_text)

    def transcribe_selected():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("No selection", "Please select an MP3 file to transcribe.")
            return

        # Extract the actual file name from the selected item
        file_name, _ = listbox.get(sel[0])
        input_path = os.path.join(RECORDINGS_DIR, file_name)

        model_choice = model_var.get()
        cmd = [
            sys.executable.replace("python.exe", "pythonw.exe"), "-m", "whisper", input_path,
            "--model", model_choice,
            "--output_dir", TRANSCRIPTS_DIR,
            "--output_format", "txt"
        ]

        def run_whisper_with_output():
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                output_text.delete(1.0, tk.END)  # Clear the text box
                for line in process.stdout:
                    output_text.insert(tk.END, line)  # Append each line of output
                    output_text.see(tk.END)  # Auto-scroll to the end
                    trans_win.update_idletasks()
                process.wait()
                if process.returncode == 0:
                    messagebox.showinfo("Done", f"Transcription finished for:\n{file_name}")
                else:
                    messagebox.showerror("Error", f"Transcription failed with code {process.returncode}.")
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred:\n{e}")

        threading.Thread(target=run_whisper_with_output, daemon=True).start()

    # New Transcript button (placed above the progress console)
    new_transcript_btn = tk.Button(trans_win, text="New Transcript", command=transcribe_selected,
                                   bg="#4caf50", fg="white", relief="flat")
    new_transcript_btn.pack(pady=6)

    # Output text box for Whisper progress
    output_label = tk.Label(trans_win, text="Transcription Progress:", bg="#1e2b3f", fg="white", font=("Helvetica", 12))
    output_label.pack(pady=(10, 0))
    output_text = tk.Text(trans_win, bg="#2b2b3f", fg="white", font=("Courier", 10), height=15, wrap="word")
    output_text.pack(fill="both", expand=True, padx=10, pady=10)

    # Refresh the list after packing all widgets
    refresh_list()

# -----------------------------
# Title-bar drag helpers
# -----------------------------
def title_press(event):
    root._drag_x = event.x_root - root.winfo_x()
    root._drag_y = event.y_root - root.winfo_y()

def title_drag(event):
    x = event.x_root - root._drag_x
    y = event.y_root - root._drag_y
    root.geometry(f"+{x}+{y}")

# -----------------------------
# Minimize
# -----------------------------
def minimize_window():
    root.overrideredirect(False)
    root.iconify()
    def restore(ev=None):
        root.overrideredirect(True)
    root.bind("<Map>", restore)

# -----------------------------
# Build GUI
# -----------------------------
root = tk.Tk()
root.overrideredirect(True)
root.geometry("520x360")
root.configure(bg="#1e1e2f")
root.title("Audio Recorder")

if os.path.exists(ICON_PATH):
    try:
        root.iconbitmap(ICON_PATH)
    except Exception:
        pass
root.update_idletasks()
root.deiconify()

# Title bar
title_bar = tk.Frame(root, bg="#2b2b3f", height=32)
title_bar.pack(fill="x")

# Title label
title_label = tk.Label(title_bar, text="Audio Recorder", bg="#2b2b3f", fg="white",
                       font=("Helvetica", 12, "bold"))
title_label.pack(side="left", padx=10)

# Button frame for right alignment
button_frame = tk.Frame(title_bar, bg="#2b2b3f")
button_frame.pack(side="right")

# Transcribe button
trans_btn = tk.Button(button_frame, text="Transcribe", command=open_transcribe_window,
                      bg="#2196F3", fg="white", bd=0, font=("Helvetica", 11),
                      relief="flat", padx=8)
trans_btn.pack(side="left", padx=6)

# Minimize button
min_btn = tk.Button(button_frame, text="-", command=minimize_window,
                    bg="#bbbbbb", fg="black", bd=0, font=("Helvetica", 11),
                    relief="flat", padx=8)
min_btn.pack(side="left", padx=6)

# Exit button
close_btn = tk.Button(button_frame, text="X", command=root.destroy,
                      bg="#e04343", fg="white", bd=0, font=("Helvetica", 11),
                      relief="flat", padx=8)
close_btn.pack(side="left", padx=6)

# Bind drag events for the title bar
for w in (title_bar, title_label):
    w.bind("<ButtonPress-1>", title_press)
    w.bind("<B1-Motion>", title_drag)

# Function to get available audio input devices
def get_audio_input_devices():
    if not HAVE_PYAUDIO:
        return []
    pa = pyaudio.PyAudio()
    devices = []
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        # Only include devices with input channels and filter out irrelevant ones
        if info["maxInputChannels"] > 0 and "Microphone" in info["name"]:
            devices.append(info["name"])
    pa.terminate()
    return devices

# Function to update the selected microphone
def update_selected_mic(choice):
    global MIC_NAME
    MIC_NAME = choice
    mic_label.config(text=f"Selected Microphone: {MIC_NAME}")

# Main content
content = tk.Frame(root, bg="#1e1e2f")
content.pack(expand=True, fill="both", padx=16, pady=12)

timer_label = tk.Label(content, text="Not recording", bg="#1e2b2f",
                       fg="white", font=("Helvetica", 16))
timer_label.pack(pady=(8, 12))

vu_canvas = tk.Canvas(content, width=340, height=20,
                      bg="#2b2b3f", highlightthickness=0)
vu_canvas.pack(pady=(0, 14))

btn_frame = tk.Frame(content, bg="#1e2b2f")
btn_frame.pack(pady=6)

start_btn = tk.Button(btn_frame, text="Start Recording",
                      command=lambda: threading.Thread(target=start_recording_wrapper, daemon=True).start(),
                      bg="#4caf50", fg="white", font=("Helvetica", 13), bd=0,
                      relief="flat", padx=12, pady=8)
start_btn.pack(side="left", padx=10)

stop_btn = tk.Button(btn_frame, text="Stop Recording",
                     command=lambda: threading.Thread(target=stop_recording, daemon=True).start(),
                     bg="#d9534f", fg="white", font=("Helvetica", 13), bd=0,
                     relief="flat", padx=12, pady=8, state="disabled")
stop_btn.pack(side="left", padx=10)

# Microphone selection section
mic_frame = tk.Frame(content, bg="#1e2b2f")
mic_frame.pack(pady=(20, 10))

mic_label = tk.Label(mic_frame, text=f"Selected Microphone: {MIC_NAME}", bg="#1e2b3f", fg="white", font=("Helvetica", 12))
mic_label.pack()

devices = get_audio_input_devices()
if devices:
    mic_var = tk.StringVar(value=MIC_NAME)
    mic_menu = tk.OptionMenu(mic_frame, mic_var, *devices, command=update_selected_mic)
    mic_menu.config(bg="#2b2b3f", fg="white", relief="flat")
    mic_menu.pack()
else:
    mic_label.config(text="No audio input devices found")

root.mainloop()
