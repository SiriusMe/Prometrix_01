from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence, QDoubleValidator, QColor, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QPushButton, QLabel, 
    QLineEdit, QWidget, QHBoxLayout, QAbstractItemView, 
    QListWidgetItem, QShortcut, QStyle, QFrame, QStyledItemDelegate, 
    QMessageBox, QFormLayout, QComboBox, QGroupBox, QGridLayout,
    QProgressBar, QTreeView, QScrollArea, QTabWidget
)
import fitz
import requests
import json
from api_endpoints import api
from typing import Optional, Dict
import os
import tempfile
from datetime import datetime


class GDTSymbolButton(QtWidgets.QPushButton):
    def __init__(self, symbol, name, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 65)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setAlignment(Qt.AlignCenter)
        
        symbol_label = QtWidgets.QLabel(symbol)
        symbol_label.setAlignment(Qt.AlignCenter)
        symbol_label.setStyleSheet("font-size: 20px; color: #495057; background: none; border: none;")
        layout.addWidget(symbol_label)
        
        name_label = QtWidgets.QLabel(name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-size: 10px; color: #495057; background: none; border: none;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

class DimensionDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dimension Details")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setMinimumHeight(380)
        
        # Define GDT symbols with their abbreviations
        self.gdt_symbols = {
            '⏥': 'Flatness',
            '↗': 'Circular Runout',
            '⏤': 'Straightness',
            '○': 'Circularity',
            '⌭': 'Cylindricity',
            '⌒': 'Line Profile',
            '⌓': 'Surface Profile',
            '⏊': 'Perpendicularity',
            '∠': 'Angularity',
            '⫽': 'Parallellism',
            '⌯': 'Symmetry',
            '⌖': 'Position',
            '◎': 'Concentricity',
            '⌰': 'Total Runout'
        }

        self.selected_gdt_symbol = None
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface"""
        # Modern styling with a more interesting color palette
        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
            }
            QLabel {
                color: #2c3e50;
                font-size: 13px;
                font-weight: 500;
                padding: 0;
                background: transparent;
                border: none;
            }
            QLineEdit, QComboBox {
                padding: 8px 12px;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                background-color: white;
                min-height: 20px;
                color: #34495e;
                selection-background-color: #3498db;
                selection-color: white;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3498db;
            }
            QLineEdit:hover, QComboBox:hover {
                border: 1px solid #95a5a6;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: right center;
                width: 20px;
                border-left: none;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#okButton {
                background-color: #3498db;
                color: white;
                border: none;
            }
            QPushButton#okButton:hover {
                background-color: #2980b9;
            }
            QPushButton#okButton:pressed {
                background-color: #1f6aa5;
            }
            QPushButton#cancelButton {
                background-color: white;
                color: #2c3e50;
                border: 1px solid #bdc3c7;
            }
            QPushButton#cancelButton:hover {
                background-color: #ecf0f1;
                border-color: #95a5a6;
            }
            QPushButton#cancelButton:pressed {
                background-color: #dde4e6;
            }
            /* Add subtle header styling */
            #headerLabel {
                color: #34495e;
                font-size: 16px;
                font-weight: bold;
                margin-bottom: 10px;
                padding-bottom: 8px;
                border-bottom: 1px solid #e9ecef;
            }
        """)
        
        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)
        
        # Add a header
        header_label = QtWidgets.QLabel("Configure Dimension Properties")
        header_label.setObjectName("headerLabel")
        main_layout.addWidget(header_label)
        
        # Create a grid layout for the form
        form_layout = QtWidgets.QGridLayout()
        form_layout.setSpacing(12)
        
        # Create input fields with validators
        self.nominal_edit = QtWidgets.QLineEdit()
        self.nominal_edit.setPlaceholderText("Enter nominal value")
        self.nominal_edit.setValidator(QtGui.QDoubleValidator())
        
        self.upper_tol_edit = QtWidgets.QLineEdit()
        self.upper_tol_edit.setPlaceholderText("Enter upper tolerance")
        self.upper_tol_edit.setValidator(QtGui.QDoubleValidator())
        
        self.lower_tol_edit = QtWidgets.QLineEdit()
        self.lower_tol_edit.setPlaceholderText("Enter lower tolerance")
        self.lower_tol_edit.setValidator(QtGui.QDoubleValidator())
        
        # Create dimension type combo box
        self.dim_type_combo = QtWidgets.QComboBox()
        
        # Add basic dimension types
        basic_types = ["Length", "Diameter", "Radius", "Angular", "Position", "Profile"]
        for type_name in basic_types:
            self.dim_type_combo.addItem(type_name)
            
        # Add separator
        self.dim_type_combo.insertSeparator(len(basic_types))
        
        # Add GDT symbols with their names
        for symbol, name in self.gdt_symbols.items():
            self.dim_type_combo.addItem(f"{symbol} {name}")
            
        # Add Other at the end
        self.dim_type_combo.insertSeparator(self.dim_type_combo.count())
        self.dim_type_combo.addItem("Other")
        
        # Create labels (not in boxes)
        nominal_label = QtWidgets.QLabel("Nominal Value:")
        upper_tol_label = QtWidgets.QLabel("Upper Tolerance:")
        lower_tol_label = QtWidgets.QLabel("Lower Tolerance:")
        dim_type_label = QtWidgets.QLabel("Dimension Type:")
        
        # Add the widgets to the grid layout
        # First column is labels, second column is inputs
        form_layout.addWidget(nominal_label, 0, 0, Qt.AlignRight)
        form_layout.addWidget(self.nominal_edit, 0, 1)
        
        form_layout.addWidget(upper_tol_label, 1, 0, Qt.AlignRight)
        form_layout.addWidget(self.upper_tol_edit, 1, 1)
        
        form_layout.addWidget(lower_tol_label, 2, 0, Qt.AlignRight)
        form_layout.addWidget(self.lower_tol_edit, 2, 1)
        
        form_layout.addWidget(dim_type_label, 3, 0, Qt.AlignRight)
        form_layout.addWidget(self.dim_type_combo, 3, 1)
        
        # Make the second column (inputs) expandable
        form_layout.setColumnStretch(1, 1)
        
        main_layout.addLayout(form_layout)
        
        # Add stretch to push buttons to bottom
        main_layout.addStretch()
        
        # Button layout
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(12)
        
        cancel_button = QtWidgets.QPushButton("Cancel")
        cancel_button.setObjectName("cancelButton")
        ok_button = QtWidgets.QPushButton("Save")
        ok_button.setObjectName("okButton")
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        main_layout.addLayout(button_layout)
        
        # Connect signals
        self.dim_type_combo.currentTextChanged.connect(self.on_dim_type_changed)

    def on_dim_type_changed(self, text):
        """Handle dimension type change"""
        # Extract symbol if it's a GDT type
        if ' ' in text:  # GDT type with symbol
            symbol = text.split(' ')[0]
            if symbol in self.gdt_symbols:
                self.selected_gdt_symbol = symbol
        else:
            self.selected_gdt_symbol = None

    def getDimensionData(self):
        """Get the entered dimension data"""
        try:
            nominal = float(self.nominal_edit.text()) if self.nominal_edit.text() else None
            upper_tol = float(self.upper_tol_edit.text()) if self.upper_tol_edit.text() else 0
            lower_tol = float(self.lower_tol_edit.text()) if self.lower_tol_edit.text() else 0
            dim_type = self.dim_type_combo.currentText()
            
            # Handle GDT types
            if ' ' in dim_type:  # GDT type with symbol
                symbol = dim_type.split(' ')[0]
                if symbol in self.gdt_symbols:
                    # Add GDT prefix and keep the symbol
                    dim_type = f"GDT: {symbol} {self.gdt_symbols[symbol]}"
                    self.selected_gdt_symbol = symbol
            
            return {
                'nominal': nominal,
                'upper_tol': upper_tol,
                'lower_tol': lower_tol,
                'dim_type': dim_type,
                'gdt_symbol': self.selected_gdt_symbol if self.selected_gdt_symbol else None
            }
        except ValueError:
            return None

class PDFPreviewDialog(QtWidgets.QDialog):
    def __init__(self, pdf_path, parent=None, open_drawing=False):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.current_page = 0
        self.rotation = 0
        self.pdf_doc = fitz.open(pdf_path)
        self.open_drawing = open_drawing  # Flag to indicate if drawing should be opened directly
        
        self.setup_ui()
        self.load_current_page()

    def setup_ui(self):
        self.setWindowTitle("PDF Preview")
        self.setMinimumSize(800, 600)
        
        # Apply modern styling
        self.setStyleSheet("""
            QDialog {
                background-color: #fafafa;
            }
            QLabel {
                color: #555555;
                font-size: 11px;
            }
            QSpinBox {
                padding: 4px;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                background-color: white;
                color: #333333;
                font-size: 11px;
                min-width: 60px;
            }
            QSpinBox:focus {
                border: 1px solid #bdbdbd;
                background-color: #fafafa;
            }
            QPushButton {
                padding: 6px 14px;
                border-radius: 3px;
                border: 1px solid #e0e0e0;
                background-color: #f5f5f5;
                color: #424242;
                font-size: 11px;
                min-width: 90px;
            }
            QPushButton:hover {
                background-color: #eeeeee;
                border: 1px solid #bdbdbd;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
            QPushButton[text="OK"] {
                background-color: #f5f5f5;
                border: 1px solid #2196f3;
                color: #2196f3;
            }
            QPushButton[text="OK"]:hover {
                background-color: #e3f2fd;
            }
            QPushButton[text="OK"]:pressed {
                background-color: #bbdefb;
            }
            QGraphicsView {
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                background-color: white;
            }
        """)

        # Main layout with margins
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Preview area with shadow effect
        preview_frame = QtWidgets.QFrame()
        preview_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        preview_layout = QtWidgets.QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scene = QtWidgets.QGraphicsScene()
        self.view = QtWidgets.QGraphicsView(self.scene)
        
        # Add shadow effect to preview
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(QtGui.QColor(0, 0, 0, 25))
        shadow.setOffset(0, 2)
        self.view.setGraphicsEffect(shadow)
        
        preview_layout.addWidget(self.view)
        layout.addWidget(preview_frame)

        # Controls layout
        controls_frame = QtWidgets.QFrame()
        controls_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
            }
        """)
        
        controls_layout = QtWidgets.QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(15, 10, 15, 10)

        # Page navigation with modern icons
        nav_layout = QtWidgets.QHBoxLayout()
        nav_layout.setSpacing(8)
        
        self.page_label = QtWidgets.QLabel("Page:")
        self.page_spin = QtWidgets.QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(len(self.pdf_doc))
        self.page_spin.setValue(1)
        self.page_spin.valueChanged.connect(self.page_changed)

        self.total_pages_label = QtWidgets.QLabel(f"of {len(self.pdf_doc)}")

        nav_layout.addWidget(self.page_label)
        nav_layout.addWidget(self.page_spin)
        nav_layout.addWidget(self.total_pages_label)

        # Rotation controls with icons
        rotation_layout = QtWidgets.QHBoxLayout()
        rotation_layout.setSpacing(12)
        
        # Create tool buttons for rotation
        self.rotate_left_btn = QtWidgets.QToolButton()
        self.rotate_right_btn = QtWidgets.QToolButton()
        
        # Set icons (replace with your icon paths)
        self.rotate_left_btn.setIcon(QIcon(r"D:\siri\calipers\prometrix\prometrix\Smart_Metrology_19082024\icons8-rotate-left-24.png"))
        self.rotate_right_btn.setIcon(QIcon(r"D:\siri\calipers\prometrix\prometrix\Smart_Metrology_19082024\icons8-rotate-right-24.png"))
        
        # Set icon size
        icon_size = QtCore.QSize(20, 20)
        self.rotate_left_btn.setIconSize(icon_size)
        self.rotate_right_btn.setIconSize(icon_size)
        
        # Style the tool buttons
        tool_button_style = """
            QToolButton {
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                padding: 4px;
                background-color: #f5f5f5;
            }
            QToolButton:hover {
                background-color: #eeeeee;
                border: 1px solid #bdbdbd;
            }
            QToolButton:pressed {
                background-color: #e0e0e0;
            }
        """
        self.rotate_left_btn.setStyleSheet(tool_button_style)
        self.rotate_right_btn.setStyleSheet(tool_button_style)
        
        # Set tooltips
        self.rotate_left_btn.setToolTip("Rotate Left")
        self.rotate_right_btn.setToolTip("Rotate Right")
        
        # Connect signals
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_page(-90))
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_page(90))
        
        rotation_layout.addWidget(self.rotate_left_btn)
        rotation_layout.addWidget(self.rotate_right_btn)

        # Add layouts to controls
        controls_layout.addLayout(nav_layout)
        controls_layout.addStretch()
        controls_layout.addLayout(rotation_layout)

        layout.addWidget(controls_frame)

        # Button layout
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        
        ok_button = QtWidgets.QPushButton("OK")
        cancel_button = QtWidgets.QPushButton("Cancel")
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)

    def load_current_page(self):
        page = self.pdf_doc[self.current_page]
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72).prerotate(self.rotation))
        
        # Convert to QImage
        img = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride, QtGui.QImage.Format_RGB888)
        
        # Create pixmap and add to scene
        self.scene.clear()
        pixmap = QtGui.QPixmap.fromImage(img)
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        
        # Fit view to page
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def page_changed(self, value):
        self.current_page = value - 1
        self.load_current_page()

    def rotate_page(self, angle):
        self.rotation = (self.rotation + angle) % 360
        self.load_current_page()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene.items():
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def get_selected_page(self):
        return self.current_page

    def get_rotation(self):
        return self.rotation
        
    def accept(self):
        # If this dialog was opened with open_drawing=True, set a flag on the parent
        # This will prevent the parent dialog from reopening when this dialog is accepted
        if self.open_drawing and self.parent() and isinstance(self.parent(), OperationsDialog):
            self.parent().drawing_accepted = True
        super().accept() 
    
# Add this new class for background loading
class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def run(self):
        try:
            data = api.get_all_orders()
            if data is not None:
                self.data_loaded.emit(data)
            else:
                self.error_occurred.emit("Failed to fetch data from API")
        except Exception as e:
            self.error_occurred.emit(f"Error loading data: {str(e)}")

class PartNumberDialog(QDialog):
    def __init__(self, parent=None):
        """Initialize dialog and load data from API"""
        super(PartNumberDialog, self).__init__(parent)
        self.setWindowTitle("Select Part Number")
        self.setFixedSize(400, 480)  # Reduced size
        
        # Main layout with smaller margins
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)  # Reduced margins
        layout.setSpacing(6)  # Reduced spacing
        
        # Header section - more compact
        title_label = QLabel("Select a Part")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        layout.addWidget(title_label)
        
        # Search box with icon - more compact
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(4)  # Reduced spacing
        
        search_icon = QLabel()
        search_icon.setPixmap(self.style().standardPixmap(QStyle.SP_FileDialogContentsView).scaled(14, 14))
        search_layout.addWidget(search_icon)
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search part numbers...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #f8f9fa;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
                background-color: white;
            }
        """)
        self.search_box.textChanged.connect(self.filter_items)
        search_layout.addWidget(self.search_box)
        layout.addWidget(search_container)
        
        # List widget with improved styling
        self.list_widget = QListWidget(self)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                outline: none;
            }
            QListWidget::item {
                padding: 2px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                border-bottom: 1px solid #bbdefb;
            }
            QListWidget::item:hover:!selected {
                background-color: #f5f9ff;
            }
        """)
        
        # Loading indicator with improved styling
        self.loading_label = QLabel("Loading data...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 13px;
                padding: 12px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.loading_label)
        
        self.list_widget.setVisible(False)
        layout.addWidget(self.list_widget)
        
        # Status bar with improved styling
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 11px;
                padding: 2px;
            }
        """)
        layout.addWidget(self.status_label)
        
        # Button container with improved styling
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        
        self.cancel_button = QPushButton("Cancel", self)
        self.ok_button = QPushButton("Select", self)
        
        button_style = """
            QPushButton {
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 12px;
                min-width: 80px;
            }
        """
        
        self.cancel_button.setStyleSheet(button_style + """
            QPushButton {
                background-color: #f8f9fa;
                color: #2c3e50;
                border: 1px solid #e0e0e0;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
        """)
        
        self.ok_button.setStyleSheet(button_style + """
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.handle_item_activation)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        layout.addWidget(button_container)
        
        # Keyboard shortcuts
        QShortcut(QKeySequence("Return"), self, self.handle_return_key)
        QShortcut(QKeySequence("Escape"), self, self.reject)
        
        # Connect double-click signal
        self.list_widget.itemDoubleClicked.connect(self.handle_item_activation)
        
        # Initialize attributes for PDF handling
        self.downloaded_file = None
        self.selected_page = 0
        self.selected_rotation = 0
        self.selected_production_order = None  # Add this line
        self.operations_dialog = None  # Initialize operations_dialog attribute
        
        # Start loading data
        self.load_data()

    def load_data(self):
        """Start loading data from API in background"""
        if not api.token:  # Check if we have a valid token
            self.on_loading_error("Please log in first")
            return
            
        self.loader_thread = DataLoaderThread()
        self.loader_thread.data_loaded.connect(self.on_data_loaded)
        self.loader_thread.error_occurred.connect(self.on_loading_error)
        self.loader_thread.start()
        
    def on_data_loaded(self, data):
        """Handle the loaded data"""
        self.loading_label.hide()
        self.list_widget.setVisible(True)
        
        for order in data:
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(8, 4, 8, 4)
            item_layout.setSpacing(12)
            
            # Part number container
            part_container = QWidget()
            part_layout = QVBoxLayout(part_container)
            part_layout.setContentsMargins(0, 0, 0, 0)
            part_layout.setSpacing(0)
            
            part_label = QLabel("Part Number")
            part_label.setStyleSheet("color: #666; font-size: 10px;")
            part_number_value = QLabel(order.get('part_number', ''))
            part_number_value.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50;")
            
            part_layout.addWidget(part_label)
            part_layout.addWidget(part_number_value)
            item_layout.addWidget(part_container)
            
            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.VLine)
            separator.setStyleSheet("color: #e0e0e0;")
            item_layout.addWidget(separator)
            
            # Production order container
            order_container = QWidget()
            order_layout = QVBoxLayout(order_container)
            order_layout.setContentsMargins(0, 0, 0, 0)
            order_layout.setSpacing(0)
            
            order_label = QLabel("Production Order")
            order_label.setStyleSheet("color: #666; font-size: 10px;")
            order_value = QLabel(order.get('production_order', ''))
            order_value.setStyleSheet("font-size: 13px; color: #2c3e50;")
            
            order_layout.addWidget(order_label)
            order_layout.addWidget(order_value)
            item_layout.addWidget(order_container)
            
            # Add to list widget
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, (order.get('part_number', ''), order.get('production_order', '')))
            
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, item_widget)
        
        self.update_status()
        
    def on_loading_error(self, error_message):
        """Handle loading errors"""
        self.loading_label.setText(f"Error: {error_message}\nPlease try again later.")
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #dc3545;
                font-size: 14px;
                padding: 20px;
            }
        """)

    def filter_items(self):
        """Filter items based on search text"""
        search_text = self.search_box.text().lower()
        visible_count = 0
        
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            part_number, production_order = item.data(Qt.UserRole)
            matches = (search_text in part_number.lower() or 
                      search_text in production_order.lower())
                
            item.setHidden(not matches)
            if matches:
                visible_count += 1
        
        if search_text:
            self.status_label.setText(f"Found {visible_count} matching items")
        else:
            self.update_status()
    
    def update_status(self):
        """Update status label"""
        total_items = self.list_widget.count()
        visible_items = sum(1 for i in range(total_items) if not self.list_widget.item(i).isHidden())
        self.status_label.setText(f"Showing {visible_items} of {total_items} items")
    
    def handle_item_activation(self, item=None):
        """Handle item selection via double-click or select button and open operations dialog"""
        if not item:
            item = self.list_widget.currentItem()
        if not item:
            return
            
        selected_data = item.data(Qt.UserRole)
        if not selected_data:
            return
            
        self.selected_part_number = selected_data[0]  # Get part number
        self.selected_production_order = selected_data[1]  # Get production order
        
        # Create a new operations dialog for the selected part number
        # This ensures we get a fresh dialog each time with the correct part number
        self.operations_dialog = OperationsDialog(
            part_number=self.selected_part_number,
            production_order=self.selected_production_order,
            parent=self
        )
        
        # Show the operations dialog
        result = self.operations_dialog.exec_()
        
        if result == QDialog.Accepted:
            # If operations dialog was accepted, accept this dialog too
            self.downloaded_file = self.operations_dialog.get_downloaded_file()
            self.selected_page = self.operations_dialog.get_selected_page()
            self.selected_rotation = self.operations_dialog.get_selected_rotation()
            self.accept()
        else:
            # If operations dialog was rejected, keep this dialog open
            # Do not call self.reject() here
            pass

    def handle_return_key(self):
        """Handle Return/Enter key press"""
        if self.list_widget.currentItem():
            self.handle_item_activation()

    def get_selected_part_number(self):
        """Get the selected part number"""
        return self.selected_part_number

    def get_selected_production_order(self):
        """Get the selected production order"""
        return self.selected_production_order

    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key_Up and self.list_widget.currentRow() == 0:
            self.search_box.setFocus()
        elif event.key() == Qt.Key_Down and self.search_box.hasFocus():
            self.list_widget.setFocus()
            self.list_widget.setCurrentRow(0)
        else:
            super().keyPressEvent(event)

    def get_downloaded_file(self):
        return self.downloaded_file

    def get_selected_page(self):
        return self.selected_page

    def get_selected_rotation(self):
        return self.selected_rotation

class DocumentVersionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Document Version")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title label
        title_label = QLabel("Select Document Version")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                padding-bottom: 10px;
            }
        """)
        layout.addWidget(title_label)
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search versions...")
        self.search_box.textChanged.connect(self.filter_versions)
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #2196f3;
                background-color: #fff;
            }
        """)
        layout.addWidget(self.search_box)
        
        # Version list
        self.version_list = QListWidget()
        self.version_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 12px;
                border-bottom: 1px solid #f0f0f0;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
                border: none;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(self.version_list)
        
        # Selection info label
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        cancel_button = QPushButton("Cancel")
        ok_button = QPushButton("Select")
        
        for button in [cancel_button, ok_button]:
            button.setMinimumWidth(100)
            button.setMinimumHeight(36)
        
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
            QPushButton:pressed {
                background-color: #1976d2;
            }
        """)
        
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)

    def filter_versions(self, text):
        """Filter versions based on search text"""
        for i in range(self.version_list.count()):
            item = self.version_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def load_versions(self, production_order: str):
        """Load document versions for the production order"""
        try:
            versions = api.get_document_versions(production_order)
            self.loading_label.hide()
            
            if versions:
                for version in versions:
                    item = QListWidgetItem()
                    
                    # Extract version information
                    version_num = version.get('version_number', 'N/A')
                    created_at = version.get('created_at', '').split('T')[0]
                    status = version.get('status', '').title()
                    doc_id = version.get('document_id')
                    version_id = version.get('id')
                    
                    # Debug print
                    print(f"Version data: doc_id={doc_id}, version_id={version_id}")
                    
                    # Build version text
                    version_text = f"Version {version_num}"
                    if created_at:
                        version_text += f" - {created_at}"
                    if status:
                        version_text += f" ({status})"
                    
                    item.setText(version_text)
                    # Store full version data including IDs
                    item.setData(Qt.UserRole, version)
                    self.version_list.addItem(item)
                
                # Sort versions by version number (newest first)
                self.version_list.sortItems(Qt.DescendingOrder)
                
                # Select the latest version by default
                self.version_list.setCurrentRow(0)
                
                # Enable buttons
                self.ok_button.setEnabled(True)
            else:
                self.loading_label.setText("No versions found")
                self.loading_label.show()
                self.ok_button.setEnabled(False)
                
        except Exception as e:
            print(f"Error loading versions: {str(e)}")
            self.loading_label.setText(f"Error loading versions: {str(e)}")
            self.loading_label.show()
            self.ok_button.setEnabled(False)
    
    def select_latest_version(self):
        """Download and open the latest version"""
        try:
            # Create temporary directory if it doesn't exist
            temp_dir = os.path.join(os.path.expanduser("~"), ".smartmetrology", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate temp file path
            temp_file = os.path.join(temp_dir, f"drawing_{self.production_order}.pdf")
            
            # Show download progress
            self.loading_label.setText("Downloading latest version...")
            self.loading_label.show()
            self.ok_button.setEnabled(False)
            QtWidgets.QApplication.processEvents()
            
            # Download the file
            if api.download_latest_document(self.production_order, temp_file):
                self.loading_label.hide()
                self.ok_button.setEnabled(True)
                
                # Store the file path
                self.downloaded_file = temp_file
                self.accept()
            else:
                self.loading_label.setText("Failed to download document")
                self.loading_label.show()
                
        except Exception as e:
            print(f"Error downloading latest version: {str(e)}")
            self.loading_label.setText(f"Error: {str(e)}")
            self.loading_label.show()
            self.ok_button.setEnabled(True)

    def accept(self):
        """Handle the OK button click - download selected version"""
        selected_version = self.get_selected_version()
        if not selected_version:
            return
            
        try:
            # Create temporary directory if it doesn't exist
            temp_dir = os.path.join(os.path.expanduser("~"), ".smartmetrology", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate temp file path
            temp_file = os.path.join(temp_dir, f"drawing_{self.production_order}.pdf")
            
            # Show download progress
            self.loading_label.setText("Downloading selected version...")
            self.loading_label.show()
            self.ok_button.setEnabled(False)
            QtWidgets.QApplication.processEvents()
            
            # Get document and version IDs
            doc_id = selected_version.get('document_id')
            version_id = selected_version.get('id')
            
            if not doc_id or not version_id:
                raise ValueError("Missing document or version ID")
            
            # Download the specific version
            if api.download_specific_version(doc_id, version_id, temp_file):
                self.loading_label.hide()
                
                # Show PDF Preview Dialog
                preview_dialog = PDFPreviewDialog(temp_file, self)
                if preview_dialog.exec_() == QtWidgets.QDialog.Accepted:
                    # Store the file path and preview dialog results
                    self.downloaded_file = temp_file
                    self.selected_page = preview_dialog.get_selected_page()
                    self.selected_rotation = preview_dialog.get_rotation()
                    super().accept()
                else:
                    # Clean up temp file if preview was cancelled
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                    self.reject()
            else:
                self.loading_label.setText("Failed to download document")
                self.loading_label.show()
                self.ok_button.setEnabled(True)
                
        except Exception as e:
            print(f"Error downloading version: {str(e)}")
            self.loading_label.setText(f"Error: {str(e)}")
            self.loading_label.show()
            self.ok_button.setEnabled(True)

    def get_selected_version(self) -> Optional[Dict]:
        """Get the selected version data"""
        current_item = self.version_list.currentItem()
        if current_item:
            return current_item.data(Qt.UserRole)
        return None

    def get_downloaded_file(self) -> Optional[str]:
        """Get the path to the downloaded file"""
        return getattr(self, 'downloaded_file', None)

    def get_selected_page(self) -> int:
        """Get the selected page number"""
        return getattr(self, 'selected_page', 0)

    def get_selected_rotation(self) -> int:
        """Get the selected rotation"""
        return getattr(self, 'selected_rotation', 0)

    def download_latest_version(self):
        """Download the latest version of the document"""
        try:
            # Create temporary file
            temp_file_path = os.path.join(tempfile.gettempdir(), f"drawing_{self.production_order}.pdf")
            
            if api.download_latest_document(self.production_order, temp_file_path):
                self.downloaded_file = temp_file_path
                self.accept()  # Just accept directly, preview will be shown by parent dialog
            else:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Download Error",
                    "Failed to download the document."
                )
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to download document: {str(e)}"
            )

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login")
        self.setFixedSize(300, 200)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Title
        title_label = QLabel("Login")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        layout.addWidget(title_label)
        
        # Username
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")
        self.username_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        layout.addWidget(self.username_edit)
        
        # Password
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setStyleSheet(self.username_edit.styleSheet())
        layout.addWidget(self.password_edit)
        
        # Error label
        self.error_label = QLabel()
        self.error_label.setStyleSheet("""
            QLabel {
                color: #e74c3c;
                font-size: 12px;
            }
        """)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        # Login button
        self.login_button = QPushButton("Login")
        self.login_button.setStyleSheet("""
            QPushButton {
                padding: 8px;
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.login_button.clicked.connect(self.try_login)
        layout.addWidget(self.login_button)
        
        # Enter key triggers login
        QShortcut(QKeySequence("Return"), self, self.try_login)
        
    def try_login(self):
        """Attempt to login with provided credentials"""
        username = self.username_edit.text()
        password = self.password_edit.text()
        
        if not username or not password:
            self.error_label.setText("Please enter both username and password")
            self.error_label.show()
            return
            
        self.login_button.setEnabled(False)
        self.login_button.setText("Logging in...")
        
        if api.login(username, password):
            # Get the role from the API handler
            role = getattr(api, 'user_role', None)
            if role:
                # Pass both username and role to parent
                self.parent().handle_login_success(username, role)
            self.accept()
        else:
            self.error_label.setText("Invalid username or password")
            self.error_label.show()
            self.login_button.setEnabled(True)
            self.login_button.setText("Login")

    def handle_login_response(self, response):
        if response.status_code == 200:
            # Get user role
            username = self.username_edit.text()
            role_response = requests.get(
                f"{api.base_url}/auth/users/{username}/role",
                headers={"Authorization": f"Bearer {api.token}"}
            )
            
            if role_response.status_code == 200:
                role = role_response.json().get('role', '')
                self.parent().handle_login_success(username, role)
                self.accept()
            else:
                print(f"Error getting user role: {role_response.text}")
                self.show_error("Failed to get user role")
        else:
            self.show_error("Invalid credentials")

class OperationsDialog(QtWidgets.QDialog):
    def __init__(self, part_number, production_order, parent=None):
        super().__init__(parent)
        self.part_number = part_number
        self.production_order = production_order
        self.downloaded_file = None
        self.selected_operation = None
        self.selected_page = 0
        self.selected_rotation = 0
        self.ipid = None
        self.drawing_accepted = False  # Flag to track if drawing was accepted in PDFPreviewDialog
        self.setup_ui()
        
        # Load operations
        self.load_operations()
        
    def setup_ui(self):
        self.setWindowTitle("Select Operation")
        self.setMinimumSize(800, 600)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title section
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("Operations List")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
        """)
        
        part_number_label = QLabel(f"Part Number: {self.part_number}")
        part_number_label.setStyleSheet("""
            color: #0066cc;
            font-size: 14px;
        """)
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(part_number_label)
        layout.addWidget(title_widget)
        
        # Operations list
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
            }
            QListWidget::item {
                padding: 15px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)
        layout.addWidget(self.list_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Add Final Inspection Drawing button
        self.final_inspection_button = QPushButton("Final Inspection Drawing")
        self.final_inspection_button.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                background-color: #27ae60;  /* Green color */
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:disabled {
                background-color: #a5d6a7;
            }
        """)
        self.final_inspection_button.clicked.connect(self.open_final_inspection)
        button_layout.addWidget(self.final_inspection_button)
        
        self.view_drawing_button = QPushButton("View Drawing")
        self.view_drawing_button.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
            QPushButton:disabled {
                background-color: #90caf9;
            }
        """)
        self.view_drawing_button.clicked.connect(self.view_drawing)
        self.view_drawing_button.setEnabled(False)  # Initially disabled
        
        button_layout.addWidget(self.view_drawing_button)
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                background-color: #f5f5f5;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        # Connect selection changed signal
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        
        self.selected_operation = None
        self.downloaded_file = None
        
        # Load operations data
        self.load_operations()

    def load_operations(self):
        try:
            operations = api.get_operations(self.part_number)
            
            for operation in operations:
                item = QListWidgetItem()
                widget = QWidget()
                layout = QVBoxLayout(widget)
                layout.setContentsMargins(15, 15, 15, 15)
                layout.setSpacing(10)
                
                # Operation header
                header_widget = QWidget()
                header_layout = QHBoxLayout(header_widget)
                header_layout.setContentsMargins(0, 0, 0, 0)
                header_layout.setSpacing(10)
                
                op_number = QLabel(f"Operation {operation['operation_number']}")
                op_number.setStyleSheet("""
                    QLabel {
                        font-weight: bold;
                        color: #2c3e50;
                        font-size: 14px;
                        padding: 2px 0;
                        min-height: 20px;
                    }
                """)
                
                work_center = QLabel(f"Work Center: {operation['work_center']}")
                work_center.setStyleSheet("""
                    QLabel {
                        color: #666;
                        font-size: 13px;
                        padding: 2px 0;
                        min-height: 20px;
                    }
                """)
                
                header_layout.addWidget(op_number)
                header_layout.addStretch()
                header_layout.addWidget(work_center)
                
                desc = QLabel(operation['operation_description'])
                desc.setStyleSheet("""
                    QLabel {
                        color: #333;
                        font-size: 13px;
                        padding: 5px 0;
                        min-height: 20px;
                        background: transparent;
                    }
                """)
                desc.setWordWrap(True)
                
                layout.addWidget(header_widget)
                layout.addWidget(desc)
                
                widget.setMinimumHeight(80)
                
                item.setSizeHint(widget.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, widget)
                
                # Store operation data
                item.setData(Qt.UserRole, operation)
                
        except Exception as e:
            print(f"Error loading operations: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load operations: {str(e)}")

    def on_selection_changed(self):
        self.view_drawing_button.setEnabled(self.list_widget.currentItem() is not None)

    def view_drawing(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            return
            
        operation_data = current_item.data(Qt.UserRole)
        operation_number = operation_data['operation_number']
        
        # Add detailed debug prints
        print(f"\nView Drawing Details:")
        print(f"Part Number: {self.part_number}")
        print(f"Production Order: {self.production_order}")
        print(f"Operation Number: {operation_number}")
        print(f"Operation Data: {operation_data}")
        
        # Store the operation number
        self.op_no = operation_number
        
        try:
            print(f"\nMaking API request:")
            print(f"URL will be: {api.base_url}/document-management/documents/download-latest_new/{self.production_order}/ENGINEERING_DRAWING")
            
            # Get order data first
            order_data = api._make_request("/planning/all_orders")
            
            pdf_content = api.get_ipid_drawing(
                self.production_order,
                operation_number
            )
            
            if pdf_content:
                # Save to temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                temp_file.write(pdf_content)
                temp_file.close()
                
                # Show PDF Preview Dialog with open_drawing flag set to True
                preview_dialog = PDFPreviewDialog(temp_file.name, self, open_drawing=True)
                if preview_dialog.exec_() == QDialog.Accepted:
                    # Store the file path and metadata
                    self.downloaded_file = temp_file.name
                    operation_data['order_data'] = order_data  # Store order data
                    self.selected_operation = operation_data
                    self.selected_page = preview_dialog.get_selected_page()
                    self.selected_rotation = preview_dialog.get_rotation()
                    # Generate IPID string using part number for the identifier
                    self.ipid = f"IPID-{self.part_number}-{operation_number}"
                    
                    # Accept the dialog to return to the main application
                    # The main application will handle opening the drawing
                    self.accept()
                else:
                    # Clean up temp file if preview was cancelled
                    try:
                        os.remove(temp_file.name)
                    except:
                        pass
            else:
                QMessageBox.warning(
                    self, 
                    "Error", 
                    f"Failed to download drawing for Operation {operation_number}"
                )
                
        except Exception as e:
            print(f"Error downloading drawing: {e}")
            QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to download drawing for Operation {operation_number}: {str(e)}"
            )

    def open_final_inspection(self):
        """Open final inspection drawing"""
        try:
            # Set operation number for final inspection
            self.op_no = "999"
            
            # Use the new endpoint format with part number
            endpoint = f"/document-management/documents/download-latest_new/{self.part_number}/ENGINEERING_DRAWING"
            print(f"Downloading final inspection drawing from: {endpoint}")
            
            # Make the request with stream=True
            pdf_content = api._make_request(endpoint, stream=True)
            
            if pdf_content:
                # Save to temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                temp_file.write(pdf_content)
                temp_file.close()
                
                # Show PDF Preview Dialog
                preview_dialog = PDFPreviewDialog(temp_file.name, self)
                if preview_dialog.exec_() == QDialog.Accepted:
                    self.downloaded_file = temp_file.name
                    self.selected_page = preview_dialog.get_selected_page()
                    self.selected_rotation = preview_dialog.get_rotation()  # Fixed method name
                    
                    # Create a dummy operation for final inspection
                    self.selected_operation = {
                        "operation_number": "999",
                        "operation_description": "Final Inspection",
                        "work_center": "QC",
                        "order_data": api._make_request("/planning/all_orders")  # Store order data
                    }
                    
                    self.accept()
                else:
                    # Clean up temp file if preview was cancelled
                    try:
                        os.remove(temp_file.name)
                    except:
                        pass
            else:
                QMessageBox.warning(
                    self, 
                    "Error", 
                    "Failed to download final inspection drawing"
                )
                
        except Exception as e:
            print(f"Error opening final inspection: {e}")
            QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to open final inspection drawing: {str(e)}"
            )

    def handle_item_activation(self, item=None):
        """Handle double-click or Enter key on list item by viewing the drawing"""
        if not item:
            item = self.list_widget.currentItem()
        if not item:
            return
            
        # View the drawing for the selected operation
        self.view_drawing()

    def get_operation_number(self):
        return self.op_no

    def get_measurement_instrument(self):
        """Get the measurement instrument"""
        return ["Not Specified"]  # Always return default value

    def get_selected_operation(self):
        """Get the selected operation data"""
        return self.selected_operation

    def get_downloaded_file(self):
        """Get the path to the downloaded file"""
        return self.downloaded_file

    def get_selected_page(self):
        """Get the selected page number"""
        return getattr(self, 'selected_page', 0)

    def get_selected_rotation(self):
        """Get the selected rotation"""
        return getattr(self, 'selected_rotation', 0)

    def get_order_id(self):
        """Get the order ID from the operation data"""
        try:
            if self.selected_operation:
                return self.selected_operation.get('order_id') or self.production_order
            return self.production_order
        except Exception as e:
            print(f"Error getting order ID: {e}")
            return self.production_order

    def get_document_id(self):
        """Get document ID - using production order as fallback"""
        try:
            if self.selected_operation:
                return self.selected_operation.get('document_id') or self.production_order
            return self.production_order
        except Exception as e:
            print(f"Error getting document ID: {e}")
            return self.production_order

    def download_drawing(self):
        """Download the engineering drawing"""
        try:
            # Use the new endpoint format with part number
            endpoint = f"/document-management/documents/download-latest_new/{self.part_number}/ENGINEERING_DRAWING"
            print(f"Downloading drawing from: {endpoint}")
            
            # Make the request
            response = api._make_request(endpoint, stream=True)
            
            if response:
                # Create temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                temp_file.write(response)
                temp_file.close()
                
                self.downloaded_file = temp_file.name
                print(f"Drawing downloaded to: {self.downloaded_file}")
                
                # Load PDF preview
                self.load_pdf_preview()
            else:
                raise Exception("Failed to download drawing")
                
        except Exception as e:
            print(f"Error downloading drawing: {e}")
            QMessageBox.critical(self, "Error", f"Failed to download drawing: {str(e)}")

class MeasurementInstrumentDialog(QDialog):
    def __init__(self, parent=None, allow_multiple=False, is_admin=False):
        super().__init__(parent)
        self.setWindowTitle("Select Measurement Instrument")
        self.setMinimumWidth(500)
        self.allow_multiple = allow_multiple
        self.is_admin = is_admin  # Store if admin view
        
        self.setup_ui()
        self.load_instruments()

    def setup_ui(self):
        """Setup the UI elements"""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header layout for title and count
        header_layout = QHBoxLayout()
        
        # Title label
        title_label = QLabel("Available Instruments")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        header_layout.addWidget(title_label)
        
        # Count label
        self.count_label = QLabel()
        self.count_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 14px;
                padding: 2px 8px;
                background-color: #f8f9fa;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
            }
        """)
        header_layout.addWidget(self.count_label, alignment=Qt.AlignRight)
        
        layout.addLayout(header_layout)
        
        # Loading label
        self.loading_label = QLabel("Loading instruments...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 13px;
                padding: 12px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.loading_label)
        
        # Search box with icon
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(4)
        
        search_icon = QLabel()
        search_icon.setPixmap(self.style().standardPixmap(QStyle.SP_FileDialogContentsView).scaled(14, 14))
        search_layout.addWidget(search_icon)
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search instruments...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #f8f9fa;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
                background-color: white;
            }
        """)
        self.search_box.textChanged.connect(self.filter_instruments)
        search_layout.addWidget(self.search_box)
        layout.addWidget(search_container)
        
        # Instruments list
        self.instrument_list = QListWidget()
        self.instrument_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.instrument_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.instrument_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.instrument_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                outline: none;
            }
            QListWidget::item {
                padding: 1px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        self.instrument_list.setVisible(False)
        layout.addWidget(self.instrument_list)
        
        # Status bar with improved styling
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 11px;
                padding: 2px;
            }
        """)
        layout.addWidget(self.status_label)
        
        # Button container with improved styling
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        
        self.cancel_button = QPushButton("Cancel", self)
        self.ok_button = QPushButton("Select", self)
        
        button_style = """
            QPushButton {
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 12px;
                min-width: 80px;
            }
        """
        
        self.cancel_button.setStyleSheet(button_style + """
            QPushButton {
                background-color: #f8f9fa;
                color: #2c3e50;
                border: 1px solid #e0e0e0;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
        """)
        
        self.ok_button.setStyleSheet(button_style + """
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.handle_item_activation)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        layout.addWidget(button_container)
        
        # Keyboard shortcuts
        QShortcut(QKeySequence("Return"), self, self.handle_return_key)
        QShortcut(QKeySequence("Escape"), self, self.reject)
        
        # Connect double-click signal
        self.instrument_list.itemDoubleClicked.connect(self.handle_item_activation)
        
        # Load instruments
        self.load_instruments()

    def create_instrument_widget(self, instrument_data):
        """Create a custom widget for instrument list item"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Instrument info
        info_layout = QVBoxLayout()
        
        # For all users, show only the category name (no code, no format with dashes)
        category_name = instrument_data['name']
        if " - " in category_name:
            category_name = category_name.split(" - ")[0]  # Only take the category part
            
        name_label = QLabel(category_name)
        name_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        
        info_layout.addWidget(name_label)
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # Store the data in the widget
        widget.setProperty("instrument_data", instrument_data)
        
        return widget

    def filter_by_subcategory(self, index):
        """Filter instruments by selected subcategory"""
        if not hasattr(self, 'instrument_list') or not self.instrument_list.isVisible():
            return
            
        selected_text = self.subcategory_combo.currentText().strip()
        search_text = self.search_box.text().strip().lower()
        
        visible_count = 0
        total_count = self.instrument_list.count()
        
        for i in range(self.instrument_list.count()):
            item = self.instrument_list.item(i)
            widget = self.instrument_list.itemWidget(item)
            if widget:
                instrument_data = widget.property("instrument_data")
                if instrument_data:
                    # Get category name properly for matching
                    category_name = instrument_data['name']
                    if " - " in category_name:
                        category_name = category_name.split(" - ")[0]
                    
                    # Match by category name only
                    category_match = (selected_text == "All Categories" or 
                                   selected_text.lower() in category_name.lower())
                    search_match = (not search_text or 
                                  search_text in category_name.lower())
                    
                    # Show/hide based on matches
                    item.setHidden(not (category_match and search_match))
                    if not item.isHidden():
                        visible_count += 1
        
        # Update count label based on selection and filter state
        if selected_text == "All Categories" and not search_text:
            self.count_label.setText(f"Total: {total_count}")
        else:
            self.count_label.setText(f"Showing {visible_count} of {total_count}")

    def filter_instruments(self, text):
        """Filter instruments based on search text"""
        search_text = self.search_box.text().strip().lower()
        visible_count = 0
        total_count = self.instrument_list.count()
        
        for i in range(self.instrument_list.count()):
            item = self.instrument_list.item(i)
            widget = self.instrument_list.itemWidget(item)
            if widget:
                instrument_data = widget.property("instrument_data")
                if instrument_data:
                    # Get category name properly for matching
                    category_name = instrument_data['name']
                    if " - " in category_name:
                        category_name = category_name.split(" - ")[0]
                    
                    # Match by category name only
                    search_match = (not search_text or 
                                  search_text in category_name.lower())
                    
                    # Show/hide based on matches
                    item.setHidden(not search_match)
                    if not item.isHidden():
                        visible_count += 1
        
        # Update count label based on filter state
        if not search_text:
            self.count_label.setText(f"Total: {total_count}")
        else:
            self.count_label.setText(f"Showing {visible_count} of {total_count}")

    def handle_return_key(self):
        """Handle Return key press"""
        if self.instrument_list.selectedItems():
            self.accept()

    def showEvent(self, event):
        """Handle dialog show event"""
        super().showEvent(event)
        # Refresh instrument data when dialog is shown
        self.refresh_data()

    def refresh_data(self):
        """Refresh instrument data"""
        self.load_instruments()

    def load_instruments(self):
        """Load instruments from the API"""
        try:
            # Show loading indicator
            self.loading_label.setText("Loading instruments...")
            self.loading_label.show()
            self.instrument_list.setVisible(False)

            # Use fixed category ID for Instruments
            instruments_category_id = 2  # Changed back to 3 from 5

            # Get subcategories for Instruments category
            subcategories = api.get_inventory_subcategories(instruments_category_id)
            if not subcategories:
                raise Exception("Failed to fetch subcategories")

            # Store subcategories for filtering
            self.subcategories = subcategories

            # Clear list
            self.instrument_list.clear()

            # Track unique categories to avoid duplicates
            added_categories = set()
            
            # Add each unique category once
            for subcategory in subcategories:
                if subcategory.get('category_id') == instruments_category_id:
                    category_name = subcategory['name']
                    if category_name not in added_categories:
                        added_categories.add(category_name)
                        
                        # Create item with just the category name
                        item = QListWidgetItem()
                        widget = self.create_instrument_widget({
                            'name': category_name,  # Just the category name
                            'id': subcategory['id'],
                            'subcategory_id': subcategory['id'],
                            'instrument_code': category_name  # For consistent data structure
                        })
                        item.setSizeHint(widget.sizeHint())
                        self.instrument_list.addItem(item)
                        self.instrument_list.setItemWidget(item, widget)

            # Show list and hide loading
            self.loading_label.hide()
            self.instrument_list.setVisible(True)

            # Update count label
            total_count = len(added_categories)
            self.count_label.setText(f"Total: {total_count}")

        except Exception as e:
            error_msg = f"Error loading instruments: {str(e)}"
            self.loading_label.setText(error_msg)
            print(error_msg)

    def get_selected_instrument(self):
        """Get the selected instrument(s)"""
        selected = self.instrument_list.selectedItems()
        if not selected:
            return None
            
        if not self.allow_multiple:
            # Return just the category name for single selection
            item = selected[0]
            widget = self.instrument_list.itemWidget(item)
            if widget:
                instrument_data = widget.property("instrument_data")
                if instrument_data:
                    category_name = instrument_data['name']
                    if " - " in category_name:
                        category_name = category_name.split(" - ")[0]
                    return category_name
            return None
            
        # Return list of category names for multiple selection
        result = []
        for item in selected:
            widget = self.instrument_list.itemWidget(item)
            if widget:
                instrument_data = widget.property("instrument_data")
                if instrument_data:
                    category_name = instrument_data['name']
                    if " - " in category_name:
                        category_name = category_name.split(" - ")[0]
                    result.append(category_name)
        return result

    def accept(self):
        """Override accept to validate selection"""
        if not self.instrument_list.selectedItems():
            QtWidgets.QMessageBox.warning(
                self,
                "No Selection",
                "Please select at least one instrument."
            )
            return
        
        super().accept()

    def handle_item_activation(self):
        """Handle item selection via double-click or select button"""
        if not self.instrument_list.selectedItems():
            return
        self.accept()

    async def discover_devices(self):
        """Discover Bluetooth devices using Bleak"""
        try:
            import asyncio
            import nest_asyncio
            from bleak import BleakScanner
            
            nest_asyncio.apply()
            
            async with BleakScanner() as scanner:
                devices = await scanner.discover()
                return devices
                
        except Exception as e:
            print(f"Error discovering Bluetooth devices: {str(e)}")
            raise e

class DeviceDetailsDialog(QDialog):
    def __init__(self, device, instrument_data, parent=None):
        super().__init__(parent)
        self.device = device
        self.instrument_data = instrument_data
        self.all_instruments = []
        # Get calibration data when initializing
        self.calibration_data = self.get_calibration_data()
        self.setup_ui()

    def get_calibration_data(self):
        """Get calibration data for all instruments"""
        try:
            # Get fresh calibration data from API
            calibrations = api.get_calibrations()
            if not calibrations:
                print("Warning: No calibration data found")
                return {}
            
            # Process calibration data
            calibration_map = {}
            for cal in calibrations:
                item_id = cal.get('inventory_item_id')
                if item_id:
                    # Format dates
                    last_cal = cal.get('last_calibration')
                    next_cal = cal.get('next_calibration')
                    if last_cal:
                        last_cal = last_cal.split('T')[0] if 'T' in last_cal else last_cal
                    if next_cal:
                        next_cal = next_cal.split('T')[0] if 'T' in next_cal else next_cal
                    
                    # Calculate status using frequency_days from API
                    status = 'unknown'
                    try:
                        if next_cal:
                            from datetime import datetime
                            next_cal_date = datetime.strptime(next_cal, '%Y-%m-%d')
                            days_remaining = (next_cal_date - datetime.now()).days
                            frequency = cal.get('frequency_days', 365)  # Default to 365 if not specified
                            
                            if days_remaining < 0:
                                status = 'overdue'
                            elif days_remaining <= frequency * 0.1:  # Due within 10% of frequency
                                status = 'due'
                            else:
                                status = 'valid'
                    except Exception as e:
                        print(f"Error calculating calibration status: {e}")
                    
                    calibration_map[item_id] = {
                        'status': status,
                        'last_calibration': last_cal,
                        'next_calibration': next_cal,
                        'certificate_number': cal.get('certificate_number'),
                        'days_remaining': days_remaining if 'days_remaining' in locals() else None,
                        'calibration_type': cal.get('calibration_type'),
                        'frequency_days': cal.get('frequency_days'),
                        'remarks': cal.get('remarks'),
                        'created_at': cal.get('created_at'),
                        'updated_at': cal.get('updated_at'),
                        'created_by': cal.get('created_by')
                    }
            
            return calibration_map
            
        except Exception as e:
            print(f"Error getting calibration data: {str(e)}")
            return {}

    def setup_ui(self):
        self.setWindowTitle("Instrument Details")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        # Create header section with a more subtle design
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 16)
        
        title_label = QLabel("Measurement Instruments")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: 500;
            color: #2c3e50;
            margin-bottom: 4px;
        """)
        
        subtitle_label = QLabel("Select an instrument to continue")
        subtitle_label.setStyleSheet("""
            font-size: 13px;
            color: #7f8c8d;
        """)
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        layout.addWidget(header_widget)
        
        # Search section with subtle styling
        search_widget = QWidget()
        search_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 6px;
            }
        """)
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(12, 10, 12, 10)
        
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("color: #95a5a6; font-size: 14px;")
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search instruments...")
        self.search_input.textChanged.connect(self.filter_instruments)
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: none;
                background: transparent;
                font-size: 13px;
                padding: 4px;
                color: #2c3e50;
            }
            QLineEdit:focus {
                outline: none;
            }
            QLineEdit::placeholder {
                color: #95a5a6;
            }
        """)
        
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_input)
        layout.addWidget(search_widget)
        
        # Table header with subtle styling
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 6px;
            }
        """)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(24)
        
        header_style = """
            QLabel {
                color: #7f8c8d;
                font-size: 12px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        """
        
        category_header = QLabel("Category")
        code_header = QLabel("Code")
        status_header = QLabel("Status")
        calibration_header = QLabel("Calibration")
        
        category_header.setStyleSheet(header_style)
        code_header.setStyleSheet(header_style)
        status_header.setStyleSheet(header_style)
        calibration_header.setStyleSheet(header_style)
        
        category_header.setFixedWidth(200)
        code_header.setFixedWidth(120)
        status_header.setFixedWidth(120)
        
        header_layout.addWidget(category_header)
        header_layout.addWidget(code_header)
        header_layout.addWidget(status_header)
        header_layout.addWidget(calibration_header)
        header_layout.addStretch()
        
        layout.addWidget(header_widget)
        
        # Instruments list with subtle styling
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameStyle(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #e0e0e0;
                background-color: white;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                border: none;
                background: #f8f9fa;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #bdc3c7;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #95a5a6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self.instrument_container = QWidget()
        self.instrument_layout = QVBoxLayout(self.instrument_container)
        self.instrument_layout.setSpacing(0)
        self.instrument_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container for instrument widgets with table-like styling
        self.instruments_widget = QWidget()
        self.instruments_widget.setStyleSheet("""
            QWidget {
                background-color: white;
            }
        """)
        self.instruments_grid = QVBoxLayout(self.instruments_widget)
        self.instruments_grid.setContentsMargins(0, 0, 0, 0)
        self.instruments_grid.setSpacing(0)
        
        self.instrument_widgets = []  # Initialize the list to store widgets
        
        self.instrument_layout.addWidget(self.instruments_widget)
        self.instrument_layout.addStretch()
        
        
        self.scroll_area.setWidget(self.instrument_container)
        layout.addWidget(self.scroll_area)
        
        # Button section with subtle styling
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 16, 0, 0)
        button_layout.setSpacing(12)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #f8f9fa;
                color: #2c3e50;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #f1f3f4;
                border-color: #cbd1d4;
            }
            QPushButton:pressed {
                background-color: #e9ecef;
            }
        """)
        self.cancel_button.clicked.connect(self.reject)
        
        self.ok_button = QPushButton("Select")
        self.ok_button.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #2472a4;
            }
        """)
        self.ok_button.clicked.connect(self.save_selection)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        
        layout.addWidget(button_widget)
        
        # Populate the instruments
        self.populate_instruments()
    
    def populate_instruments(self):
        """Populate the list of instruments with their categories, codes and calibration data"""
        try:
            # Use provided instruments if available
            instruments = self.all_instruments
            
            # If no instruments provided, try to load them
            if not instruments:
                # Try to load instruments if none were passed
                instruments_category_id = 2
                subcategories = api.get_inventory_subcategories(instruments_category_id)
                
                if subcategories:
                    instruments = []
                    for subcategory in subcategories:
                        if subcategory.get('category_id') == instruments_category_id:
                            items = api.get_inventory_items(subcategory['id'])
                            if items:
                                for item in items:
                                    # Get instrument code
                                    dynamic_data = item.get('dynamic_data', {})
                                    instrument_code = dynamic_data.get('Instrument code')
                                    
                                    if not instrument_code:
                                        continue
                                        
                                    instruments.append({
                                        'name': f"{subcategory['name']} - {instrument_code}",
                                        'id': item.get('id'),
                                        'subcategory_id': subcategory['id'],
                                        'subcategory_name': subcategory['name'],
                                        'instrument_code': instrument_code,
                                        'dynamic_data': dynamic_data
                                    })
            
            # Clear existing widgets
            for widget in self.instrument_widgets:
                if widget.isWidgetType():
                    widget.setParent(None)
            self.instrument_widgets = []
            
            row = 0
            for instrument in instruments:
                # Get calibration info from stored data
                cal_info = self.calibration_data.get(instrument.get('id'), {})
                
                # Create widget for this instrument
                instrument_widget = QWidget()
                instrument_widget.setProperty('instrument_data', instrument)
                instrument_widget.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        border-bottom: 1px solid #e0e0e0;
                        margin: 0;
                    }
                    QWidget:hover {
                        background-color: #f5f9ff;
                    }
                    QWidget[selected="true"] {
                        background-color: #e3f2fd;
                    }
                """)
                
                # Single row layout
                row_layout = QHBoxLayout(instrument_widget)
                row_layout.setContentsMargins(16, 12, 16, 12)
                row_layout.setSpacing(24)  # Increased spacing between columns for better readability
                
                # Category with icon
                category_text = f"📐 {instrument.get('subcategory_name', 'Unknown')}"
                category_label = QLabel(category_text)
                category_label.setStyleSheet("""
                    color: #2c2c2c;
                    font-size: 13px;
                """)
                category_label.setMinimumWidth(160)  # Slightly reduced width
                
                # Code
                code_text = instrument.get('instrument_code', 'N/A')
                code_label = QLabel(code_text)
                code_label.setStyleSheet("""
                    color: #2c2c2c;
                    font-size: 13px;
                """)
                code_label.setMinimumWidth(100)  # Slightly reduced width
                
                # Get calibration info
                last_cal = cal_info.get('last_calibration', 'N/A')
                next_cal = cal_info.get('next_calibration', 'N/A')
                days_remaining = cal_info.get('days_remaining')
                
                # Format dates
                if last_cal != 'N/A':
                    last_cal = last_cal.split('T')[0] if 'T' in last_cal else last_cal
                if next_cal != 'N/A':
                    next_cal = next_cal.split('T')[0] if 'T' in next_cal else next_cal
                
                # Status indicator
                status_text = "Not Calibrated"
                status_color = "#757575"
                status_bg_color = "#f5f5f5"
                icon = "⚠️"
                
                if days_remaining is not None:
                    if days_remaining < 0:
                        status_text = "Overdue"
                        status_color = "#d32f2f"
                        status_bg_color = "#ffebee"
                        icon = "⚠️"
                    elif days_remaining <= 30:
                        status_text = "Due Soon"
                        status_color = "#ed6c02"
                        status_bg_color = "#fff4e5"
                        icon = "⚠️"
                    else:
                        status_text = "Valid"
                        status_color = "#2e7d32"
                        status_bg_color = "#e8f5e9"
                        icon = "✓"
                
                # Status label with background
                status_label = QLabel(f"{icon} {status_text}")
                status_label.setStyleSheet(f"""
                    QLabel {{
                        background-color: {status_bg_color};
                        color: {status_color};
                        font-size: 13px;
                        padding: 4px 8px;
                        border-radius: 4px;
                    }}
                """)
                status_label.setMinimumWidth(120)
                
                # Calibration dates
                dates_text = []
                if last_cal != 'N/A':
                    dates_text.append(f"Last: {last_cal}")
                if next_cal != 'N/A':
                    dates_text.append(f"Next: {next_cal}")
                
                dates_label = QLabel(" | ".join(dates_text) if dates_text else "")
                dates_label.setStyleSheet("""
                    color: #666666;
                    font-size: 13px;
                """)
                
                # Add widgets to row layout with fixed widths for alignment
                category_label.setFixedWidth(200)
                code_label.setFixedWidth(120)
                status_label.setFixedWidth(120)
                
                row_layout.addWidget(category_label)
                row_layout.addWidget(code_label)
                row_layout.addWidget(status_label)
                if dates_text:
                    row_layout.addWidget(dates_label, 1)
                row_layout.addStretch()
                
                # Add to instruments grid with no spacing
                self.instruments_grid.addWidget(instrument_widget)
                self.instruments_grid.setSpacing(0)  # Remove spacing between rows
                self.instrument_widgets.append(instrument_widget)
                
                # Connect click event
                instrument_widget.mousePressEvent = lambda e, w=instrument_widget: self.select_instrument(w)
                
                row += 1
            
            # Pre-select current instrument if it exists and is valid
            if self.instrument_data:
                for widget in self.instrument_widgets:
                    instrument = widget.property('instrument_data')
                    if instrument and instrument.get('id') == self.instrument_data.get('id'):
                        self.select_instrument(widget)
                        break
            
        except Exception as e:
            print(f"Error populating instruments: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def select_instrument(self, widget):
        """Handle selection of an instrument"""
        # Get instrument data and check calibration status
        instrument_data = widget.property('instrument_data')
        if instrument_data:
            cal_info = self.calibration_data.get(instrument_data.get('id'), {})
            days_remaining = cal_info.get('days_remaining')
            
            if days_remaining is not None and days_remaining < 0:
                # Show warning dialog for overdue instruments
                reply = QMessageBox.warning(
                    self,
                    "Overdue Calibration",
                    "This instrument is overdue for calibration. Are you sure you want to select it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.No:
                    return
        
        # Proceed with selection if user confirms or instrument is not overdue
        # Deselect all widgets
        for w in self.instrument_widgets:
            w.setProperty('selected', False)
            w.setStyleSheet(w.styleSheet())  # Refresh styling
        
        # Select this widget
        widget.setProperty('selected', True)
        widget.setStyleSheet(widget.styleSheet())  # Refresh styling
        
        # Update current instrument data
        self.instrument_data = widget.property('instrument_data')
    
    def filter_instruments(self, text):
        """Filter instruments based on search text"""
        text = text.lower()
        for widget in self.instrument_widgets:
            instrument = widget.property('instrument_data')
            category = instrument.get('subcategory_name', '').lower()
            code = instrument.get('instrument_code', '').lower()
            
            visible = text in category or text in code
            widget.setVisible(visible)
            
    def save_selection(self):
        """Save the selected instrument and close dialog"""
        # Check if an instrument is selected
        selected_found = False
        for widget in self.instrument_widgets:
            if widget.property('selected'):
                selected_found = True
                break
                
        if not selected_found:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select an instrument before proceeding."
            )
            return
            
        # If we have a selection, accept the dialog
        self.accept()
        
    def get_selected_data(self):
        """Get the selected instrument data"""
        for widget in self.instrument_widgets:
            if widget.property('selected'):
                instrument_data = widget.property('instrument_data')
                if instrument_data:
                    # Get calibration info for this instrument
                    cal_info = self.calibration_data.get(instrument_data.get('id'), {})
                    next_cal = cal_info.get('next_calibration', 'N/A')
                    
                    # Format the instrument code with calibration date
                    instrument_code = instrument_data.get('instrument_code', 'N/A')
                    if next_cal and next_cal != 'N/A':
                        instrument_data['display_name'] = f"{instrument_code} ({next_cal})"
                    else:
                        instrument_data['display_name'] = instrument_code
                        
                    return instrument_data
        return None

    def save_selection(self):
        """Save the selected instrument"""
        if not self.instrument_data:
            QtWidgets.QMessageBox.warning(self, "Error", "Please select an instrument")
            return
        self.accept()

class ReportFolderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Report")
        self.setMinimumWidth(550)
        self.setMinimumHeight(650)
        
        self.folder_structure = None
        self.selected_folder = None
        self.new_folder_name = ""
        self.is_saving = False
        self.save_successful = False  # Add flag to track save success
        
        # Set window style
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QGroupBox {
                font-weight: 500;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 12px;
                color: #424242;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background-color: white;
            }
            QPushButton {
                background-color: #f5f5f5;
                color: #424242;
                border: 1px solid #e0e0e0;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #eeeeee;
                border-color: #bdbdbd;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #9e9e9e;
                border-color: #e0e0e0;
            }
            QPushButton#okButton {
                background-color: #1976d2;
                color: white;
                border: none;
            }
            QPushButton#okButton:hover {
                background-color: #1565c0;
            }
            QPushButton#okButton:pressed {
                background-color: #0d47a1;
            }
            QPushButton#okButton:disabled {
                background-color: #90caf9;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                color: #424242;
            }
            QLineEdit:focus {
                border-color: #1976d2;
            }
            QTreeView {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
            }
            QTreeView::item {
                padding: 6px;
                color: #424242;
            }
            QTreeView::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QLabel {
                color: #424242;
            }
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                text-align: center;
                height: 4px;
            }
            QProgressBar::chunk {
                background-color: #1976d2;
            }
        """)
        
        self.setup_ui()
        self.load_folder_structure()
        
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 24, 24, 24)
        
        # Title and description
        title_label = QLabel("Save Report")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: 500;
            color: #424242;
        """)
        description_label = QLabel("Select an existing folder or create a new one to save your report.")
        description_label.setStyleSheet("""
            font-size: 13px;
            color: #757575;
            margin-bottom: 16px;
        """)
        main_layout.addWidget(title_label)
        main_layout.addWidget(description_label)
        
        # Tree view section
        tree_group = QGroupBox("Existing Folders")
        tree_layout = QVBoxLayout()
        tree_layout.setSpacing(8)
        
        # Search box for folders
        search_layout = QHBoxLayout()
        search_icon = QLabel("🔍")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search folders...")
        self.search_box.textChanged.connect(self.filter_folders)
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_box)
        tree_layout.addLayout(search_layout)
        
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setModel(QStandardItemModel())
        self.tree_view.clicked.connect(self.on_folder_selected)
        self.tree_view.setMinimumHeight(300)
        tree_layout.addWidget(self.tree_view)
        
        tree_group.setLayout(tree_layout)
        main_layout.addWidget(tree_group)
        
        # New folder section
        new_folder_group = QGroupBox("New Folder")
        new_folder_layout = QVBoxLayout()
        new_folder_layout.setSpacing(12)
        
        # Input field with label
        input_layout = QHBoxLayout()
        label = QLabel("Folder Name:")
        label.setStyleSheet("font-weight: 500;")
        self.folder_name_edit = QLineEdit()
        self.folder_name_edit.setPlaceholderText("Enter folder name")
        input_layout.addWidget(label)
        input_layout.addWidget(self.folder_name_edit)
        new_folder_layout.addLayout(input_layout)
        
        # Select button
        select_button = QPushButton("Select New Folder")
        select_button.setMinimumHeight(36)
        select_button.clicked.connect(self.select_new_folder)
        new_folder_layout.addWidget(select_button)
        
        new_folder_group.setLayout(new_folder_layout)
        main_layout.addWidget(new_folder_group)
        
        # Status section
        self.status_label = QLabel()
        self.status_label.setStyleSheet("""
            padding: 8px;
            border-radius: 4px;
            background-color: #f5f5f5;
            color: #424242;
        """)
        self.status_label.hide()
        main_layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.handle_cancel)
        
        self.ok_button = QPushButton("Save")
        self.ok_button.setObjectName("okButton")
        self.ok_button.clicked.connect(self.handle_save)
        
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
    def filter_folders(self, text):
        """Filter folders in tree view based on search text"""
        if not text:
            # Show all items
            self.populate_tree_view(self.folder_structure)
            return
            
        def match_folder(folder, search_text):
            if search_text.lower() in folder['name'].lower():
                return True
            if 'children' in folder:
                return any(match_folder(child, search_text) for child in folder['children'])
            return False
            
        # Filter the folder structure
        filtered_structure = [
            folder for folder in self.folder_structure
            if match_folder(folder, text)
        ]
        
        # Update tree view with filtered results
        self.populate_tree_view(filtered_structure)
        
    def show_status(self, message, is_error=False):
        """Show status message with appropriate styling"""
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"""
            padding: 8px;
            border-radius: 4px;
            background-color: {'#ffebee' if is_error else '#e8f5e9'};
            color: {'#c62828' if is_error else '#2e7d32'};
        """)
        self.status_label.show()
        
    def handle_save(self):
        """Handle the save button click"""
        if not self.selected_folder and not self.new_folder_name:
            self.show_status("Please select a folder or enter a new folder name", True)
            return
            
        try:
            self.is_saving = True
            self.ok_button.setEnabled(False)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            self.progress_bar.show()
            self.show_status("Saving report...")
            
            # Get the folder path
            folder_path = self.get_selected_folder()
            if not folder_path:
                raise ValueError("No folder selected")
                
            # Set the save_successful flag to True - this will be checked by the caller
            self.save_successful = True
            
            # Accept the dialog to return to the caller
            self.accept()
            
        except Exception as e:
            print(f"Error during save: {str(e)}")
            self.show_status(f"Error saving report: {str(e)}", True)
            self.save_successful = False
            self.is_saving = False
            self.ok_button.setEnabled(True)
            self.progress_bar.hide()
            
    def handle_cancel(self):
        """Handle the cancel button click"""
        if self.is_saving:
            reply = QMessageBox.question(
                self,
                "Cancel Save",
                "Are you sure you want to cancel saving the report?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.reject()
        else:
            self.reject()
            
    def select_new_folder(self):
        """Select a new folder name"""
        folder_name = self.folder_name_edit.text().strip()
        if not folder_name:
            self.show_status("Please enter a folder name", True)
            return
            
        self.new_folder_name = folder_name
        self.selected_folder = None
        
        # Set active status
        self.folder_name_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #1976d2;
                border-radius: 4px;
                background-color: white;
                color: #424242;
            }
        """)
        
        self.folder_name_edit.clear()
        self.show_status(f"Selected new folder: {folder_name}")
        
    def on_folder_selected(self, index):
        """Handle folder selection"""
        model = self.tree_view.model()
        item = model.itemFromIndex(index)
        
        # Get the full path of the selected item by traversing up the tree
        path_parts = []
        current_item = item
        while current_item and current_item != model.invisibleRootItem():
            path_parts.insert(0, current_item.text())
            current_item = current_item.parent()
            
        # Build the full path
        full_path = "/".join(path_parts)
        
        # If this is the root "REPORT" folder, show error and prevent selection
        if len(path_parts) == 1 and path_parts[0] == "REPORT":
            self.show_status("Cannot select the root REPORT folder. Please select a subfolder.", True)
            self.selected_folder = None
            self.ok_button.setEnabled(False)
            return
        
        # If this is a file (has extension), get its parent folder
        if "." in path_parts[-1]:  # This is a file
            path_parts.pop()  # Remove the file
            full_path = "/".join(path_parts)
            
        # If this is under REPORT, make sure we select the proper subfolder
        if path_parts and path_parts[0] == "REPORT":
            if len(path_parts) >= 2:  # If we have at least one subfolder under REPORT
                # Select the first subfolder under REPORT
                full_path = path_parts[1]  # Just use the first subfolder name
                
                # Find and select the corresponding item in the tree
                for row in range(model.rowCount()):
                    root_item = model.item(row)
                    if root_item.text() == path_parts[1]:
                        item = root_item
                        break
        
        self.selected_folder = {
            'id': item.data(Qt.UserRole),
            'path': full_path
        }
        self.new_folder_name = ""
        
        # Reset input field style
        self.folder_name_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                color: #424242;
            }
            QLineEdit:focus {
                border-color: #1976d2;
            }
        """)
        
        self.show_status(f"Selected folder: {self.selected_folder['path']}")
        
        # Enable save button
        self.ok_button.setEnabled(True)
        
        # Highlight the selected folder in the tree view
        self.tree_view.setCurrentIndex(model.indexFromItem(item))
        
    def get_selected_folder(self):
        """Get the selected folder name"""
        if self.selected_folder:
            return self.selected_folder['path']
        elif self.new_folder_name:
            return self.new_folder_name
        return None

    def load_folder_structure(self):
        """Load the folder structure from the API"""
        try:
            self.folder_structure = api.get_report_structure()
            if self.folder_structure:
                print("Received folder structure:", self.folder_structure)
                self.populate_tree_view(self.folder_structure)
            else:
                self.show_status("No folder structure received from API", True)
        except Exception as e:
            print(f"Error loading folder structure: {str(e)}")
            self.show_status(f"Failed to load folder structure: {str(e)}", True)
            
    def populate_tree_view(self, folders, parent_item=None):
        """Populate the tree view with folder structure"""
        try:
            model = self.tree_view.model()
            if parent_item is None:
                model.clear()
                parent_item = model.invisibleRootItem()
                
            for folder in folders:
                try:
                    item = QStandardItem(folder['name'])
                    item.setData(folder['id'], Qt.UserRole)
                    path = folder.get('path', folder['name'])
                    item.setData(path, Qt.UserRole + 1)
                    parent_item.appendRow(item)
                    
                    if 'children' in folder and folder['children']:
                        self.populate_tree_view(folder['children'], item)
                except KeyError as e:
                    print(f"Error processing folder: {folder}, missing key: {str(e)}")
                    continue
        except Exception as e:
            print(f"Error populating tree view: {str(e)}")
            self.show_status("Error loading folders", True)
            
    def handle_save(self):
        """Handle the save button click"""
        if not self.selected_folder and not self.new_folder_name:
            self.show_status("Please select a folder or enter a new folder name", True)
            return
            
        try:
            self.is_saving = True
            self.ok_button.setEnabled(False)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            self.progress_bar.show()
            self.show_status("Saving report...")
            
            # Get the folder path
            folder_path = self.get_selected_folder()
            if not folder_path:
                raise ValueError("No folder selected")
                
            # Set the save_successful flag to True - this will be checked by the caller
            self.save_successful = True
            
            # Accept the dialog to return to the caller
            self.accept()
            
        except Exception as e:
            print(f"Error during save: {str(e)}")
            self.show_status(f"Error saving report: {str(e)}", True)
            self.save_successful = False
            self.is_saving = False
            self.ok_button.setEnabled(True)
            self.progress_bar.hide()
            
    def get_save_status(self):
        """Return whether the save was successful"""
        return self.save_successful
        
    def get_selected_folder(self):
        """Get the selected folder name"""
        if self.selected_folder:
            return self.selected_folder['path']
        elif self.new_folder_name:
            return self.new_folder_name
        return None


