import os
import subprocess

def compile_resources():
    """Compile the Qt resource file into a Python module."""
    try:
        # Run pyrcc5 to compile the resource file
        subprocess.run(['pyrcc5', 'resources.qrc', '-o', 'resources_rc.py'], check=True)
        print("Resource file compiled successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error compiling resource file: {e}")
    except FileNotFoundError:
        print("Error: pyrcc5 not found. Make sure PyQt5 is installed correctly.")

if __name__ == '__main__':
    compile_resources() 