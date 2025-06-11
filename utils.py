import os
import sys

def resource_path(relative_path):
    """Get the absolute path to a resource, works for dev and for PyInstaller"""
    try:
        # If it's already an absolute path, return it
        if os.path.isabs(relative_path) and os.path.exists(relative_path):
            return relative_path

        # First try PyInstaller's _MEIPASS
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path:
            path = os.path.join(base_path, relative_path)
            if os.path.exists(path):
                return os.path.abspath(path)

        # Try current directory
        current_dir = os.path.abspath(".")
        path = os.path.join(current_dir, relative_path)
        if os.path.exists(path):
            return os.path.abspath(path)

        # Try parent directory of current directory
        parent_dir = os.path.dirname(current_dir)
        path = os.path.join(parent_dir, relative_path)
        if os.path.exists(path):
            return os.path.abspath(path)

        # If we're in a PyInstaller bundle, try the _internal directory
        if base_path:
            internal_path = os.path.join(base_path, '_internal', relative_path)
            if os.path.exists(internal_path):
                return os.path.abspath(internal_path)

        # If all else fails, return absolute path to current directory path
        # (this will let the error be handled by the calling code)
        return os.path.abspath(os.path.join(current_dir, relative_path))

    except Exception as e:
        print(f"Error in resource_path: {str(e)}")
        return os.path.abspath(relative_path)