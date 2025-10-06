# Folder Map Visualizer – Requirements

## Functional Requirements
- **Folder Selection**
  - Provide a GUI dialog to let the user choose a target directory (Windows-focused, extensible to other OSes).
- **Folder Scanning Engine**
  - Recursively traverse all subdirectories and files of the selected folder.
  - Collect metadata for each file: name, absolute path, size (bytes), and last modified timestamp.
  - Store the metadata in a structured in-memory model (e.g., list of dictionaries or pandas DataFrame) ready for filtering and visualisation.
- **Visualisation (Treemap)**
  - Render a treemap where each rectangle represents a file sized by total bytes.
  - Colour rectangles according to file age (e.g., gradient from recent to old).
  - Provide hover tooltips with file details (name, size, modified date) and a legend explaining size/colour encoding.
  - Enable zooming or focus/defocus interactions to inspect dense regions.
- **Interactive GUI**
  - Build a clean desktop interface using Tkinter or PySimpleGUI with an embedded Matplotlib or Plotly canvas.
  - Display scanning progress, allow cancelling/restarting scans, and keep the UI responsive via background threads.
  - Support clicking a rectangle to reveal the file in the system file explorer (Explorer on Windows).
- **Sorting & Filtering**
  - Offer controls for sorting (e.g., largest size, oldest modification date, alphabetical).
  - Allow filtering by file type/extension, minimum size thresholds, and modified date ranges.
  - Include a summary of total folder size and file count, plus optional “Top N largest files” view.
- **Export & Sharing**
  - Provide an option to export the treemap as an image (PNG at minimum, optionally SVG/PDF).

## Non-Functional Requirements
- **Performance**
  - Handle directories containing 10,000+ files efficiently, using threading or asynchronous workers to keep the UI responsive.
  - Avoid blocking the main thread during scans and visualisation updates.
- **Usability**
  - Present a modern, uncluttered layout with intuitive controls and clear feedback.
  - Support light/dark mode or theme switching.
- **Maintainability**
  - Separate concerns across modules (scanning, visualisation, UI) to simplify future enhancements.
  - Document major components and provide usage instructions in the README.

## Optional Enhancements
- Dark mode toggle with persistence across sessions.
- Quick filters for common file types (e.g., media, archives, executables).
- Ability to bookmark frequently scanned directories.
- Keyboard shortcuts for refreshing scans, toggling filters, and exporting images.
- Integration hooks for reporting (e.g., exporting aggregated data to CSV/JSON).
