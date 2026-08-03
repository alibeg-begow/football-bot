import sys
import os

# Proje ana dizinini Python path'ine ekle, boylece 'shared' modulu bulunabilir.
project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
