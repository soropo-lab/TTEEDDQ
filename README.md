# Folder Map Visualizer

The Folder Map Visualizer is a Tkinter desktop application for exploring the structure of a directory through an interactive treemap. It scans folders in the background, aggregates file metadata, and provides filtering and visual analysis tools so you can quickly discover the largest or oldest files in a project.

## Features

- Background directory scanner that keeps the UI responsive while traversing very large folder trees.
- Treemap visualisation sized by file size and coloured by age, with tooltips and click-to-open support.
- Filtering controls for minimum file size, file extensions, and maximum file age.
- Multiple sort options (size, name, modification time) and configurable rectangle limit for performance with huge folders.
- Dark mode toggle, Matplotlib navigation toolbar, and image export (PNG, SVG, PDF).
- Summary statistics showing totals for the complete scan and the filtered subset.

## Installation

1. Ensure you have Python 3.9 or newer installed. Tkinter is included with the standard Python installer on Windows and macOS; on Linux you may need to install an additional package such as `python3-tk`.
2. Install the Python dependencies:

   ```bash
   pip install matplotlib squarify
   ```

## Usage

You can launch the application either by running the module or executing the script directly:

```bash
python -m folder_map_visualizer.app
# or
python folder_map_visualizer/app.py
```

1. Click **Browse…** and select a directory to scan. The scanner runs in a background thread and reports progress in the status bar.
2. Use the filters panel to limit the data set by minimum size (in MB), file extensions (comma separated), and maximum age in days.
3. Choose how results are sorted and adjust the maximum number of rectangles rendered to balance detail with performance.
4. Toggle dark mode for a high-contrast view, click rectangles to open files in your platform explorer, and export the current treemap via **Export image**.

## Project Structure

```
folder_map_visualizer/
├── __init__.py          # Package entry point
├── app.py               # Tkinter GUI application
├── scanner.py           # Background directory scanning utilities
└── treemap.py           # Treemap preparation and rendering helpers
```

## Development Notes

- The scanner walks directories with `os.scandir` and honours a cancellation event so new scans can interrupt previous ones.
- Treemap rendering uses Matplotlib and `squarify` with a configurable limit on the number of rectangles to ensure interactivity even with >10k files.
- The application structure keeps scanning, visualisation, and UI concerns separated for easier extension.

Feel free to adapt or extend the modules for additional analyses or visualisations.
