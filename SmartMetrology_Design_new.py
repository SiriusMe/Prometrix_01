import math
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QMovie, QPolygonF, QImage, QPixmap
from PyQt5.QtWidgets import QFileDialog, QMainWindow, QGraphicsView, QMessageBox, QDialog, QTableWidgetItem, \
    QGraphicsPolygonItem, QMenu, QWidget, QHBoxLayout, QLabel, QSpinBox
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPen, QColor
from PyQt5.QtWidgets import QGraphicsRectItem
import fitz  # PyMuPDF
import cv2
import os
import sys
from utils import resource_path  # Add import for resource_path

# Set up model path before importing YOLO
model_path = os.path.abspath(resource_path('best.pt'))
model_dir = os.path.dirname(model_path)
os.environ['YOLO_MODEL_PATH'] = model_path
os.environ['YOLO_MODEL_DIR'] = model_dir

from ultralytics import YOLO
from ui_smart_metrology import Ui_MainWindow
from dialogs import DimensionDialog, PDFPreviewDialog, PartNumberDialog, LoginDialog, OperationsDialog, MeasurementInstrumentDialog, ReportFolderDialog , DeviceDetailsDialog
from events import EventHandler, ViewEvents, TableEvents, VisualizationEvents
from graphics import CustomGraphicsView
from algorithms import DimensionParser, ImageProcessor, BoundingBoxUtils, ClusterDetector,ZoneDetector
import requests
from PyQt5.QtWidgets import QGraphicsPolygonItem, QGraphicsPathItem, QGraphicsTextItem, QGraphicsEllipseItem
from api_endpoints import APIEndpoints, api
import json
import asyncio
from bleak import BleakClient
import tempfile
import uuid
from PyQt5 import QtPrintSupport
from collections import namedtuple
import sys
import time
import nest_asyncio
from PyQt5.QtCore import QThread, pyqtSignal

# Apply nest_asyncio to allow running asyncio in a non-async context
nest_asyncio.apply()

class PDFProcessStatus:
    PREPARING = "Preparing document..."
    OPENING = "Opening document..."
    LOADING = "Loading page..."
    PROCESSING = "Processing page..."
    FINALIZING = "Finalizing..."

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.ocr_results = []
        self.worker = None
        self.loaded_page = None
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.user_role = None  # Store user role

        # Add header widget for order details
        self.setup_header_widget()

        # Create a new scene for the graphics view
        self.scene = QtWidgets.QGraphicsScene()
        
        # Create and set the CustomGraphicsView with the new scene
        self.ui.pdf_view = CustomGraphicsView(self.scene, self)
        self.ui.drawing_layout.addWidget(self.ui.pdf_view)

        # Connect stamp tool action
        self.ui.actionStamp.triggered.connect(self.toggleStampMode)

        # # Connect Bluetooth action
        # if 'Bluetooth Connectivity' in self.ui.actions:
        #     self.ui.actions['Bluetooth Connectivity'].triggered.connect(self.show_bluetooth_dialog)

        # Initialize loading timer
        self.loading_timer = QtCore.QTimer(self)
        self.loading_timer.timeout.connect(self.update_loading_animation)

        # Create progress bar in the drawing widget
        self.progress_bar = QtWidgets.QProgressBar(self.ui.drawing)
        self.progress_bar.setFixedSize(self.ui.drawing.width(), 2)  # Make it thin
        self.progress_bar.move(0, 0)  # Position at top

        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #F0F0F0;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0078D4;  /* Windows blue */
                width: 20px;
            }
        """)

        # Set up loading animation properties
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)

        # Initialize resize mode variables
        self.resize_mode = False
        self.resize_handles = []
        self.original_bbox = None
        self.original_bbox_item = None
        self.editing_row = None
        self.finish_button = None

        # Initialize animation position
        self.animation_position = 0
        self.animation_direction = 1
        self.loading_timer.setInterval(20)  # Faster animation

        # Add method to center progress bar when drawing widget is resized
        self.ui.drawing.resizeEvent = self.on_drawing_resize

        # Initialize variables
        self.current_pdf = None
        self.current_page = None
        self.zoom_factor = 1.0
        self.zoom_step = 1.15
        self.rotation = 0
        self.current_file = None
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.masked_image = None
        #self.reader = None
        self.pdf_results = None
        self.bbox_data = {'ocr': [], 'yolo': []}  # Dictionary to store bbox data

        # Initialize YOLO model
        try:
            # Use the environment variable we set earlier
            model_path = os.environ['YOLO_MODEL_PATH']
            print(f"Attempting to load YOLO model from: {model_path}")
            print(f"File exists: {os.path.exists(model_path)}")
            print(f"Current working directory: {os.getcwd()}")
            print(f"Model directory: {os.environ['YOLO_MODEL_DIR']}")
            
            # List directory contents for debugging
            print("Directory contents:")
            model_dir = os.environ['YOLO_MODEL_DIR']
            for root, dirs, files in os.walk(model_dir):
                for file in files:
                    if file.endswith('.pt'):
                        print(f"Found model file: {os.path.join(root, file)}")
            
            # Initialize YOLO with absolute path
            self.yolo_model = YOLO(model_path)
            print("Successfully loaded YOLO model")
            
        except Exception as e:
            print(f"Error loading YOLO model: {str(e)}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            self.yolo_model = None

        # Set the main window reference
        self.ui.pdf_view.main_window = self

        # Connect signals
        self.ui.actionNewProject.triggered.connect(self.open_pdf)
        self.ui.actionZoomIn.triggered.connect(lambda: self.zoom_in(use_mouse_position=False))
        self.ui.actionZoomOut.triggered.connect(lambda: self.zoom_out(use_mouse_position=False))
        self.ui.actionDisplayWholeDrawing.triggered.connect(self.fit_to_view)
        self.ui.actionSelectionTool.triggered.connect(self.toggleSelectionMode)
        self.ui.actionOpen.triggered.connect(self.open_part_number)

        # Setup graphics view
        self.setup_view()

        # Add new dictionaries for storing detections
        self.all_detections = {
            'ocr': {
                0: [],  # Original orientation
                90: [],  # 90 degree rotation
            },
            'yolo': []  # YOLO detections
        }

        # Connect view control actions
        self.ui.actionMoveView.triggered.connect(self.toggleMoveMode)
        self.ui.actionZoomIn.triggered.connect(lambda: self.zoom_in(use_mouse_position=False))
        self.ui.actionZoomOut.triggered.connect(lambda: self.zoom_out(use_mouse_position=False))
        self.ui.actionZoomDynamic.triggered.connect(self.toggleDynamicZoom)
        self.ui.actionZoomArea.triggered.connect(self.toggleZoomArea)
        self.ui.actionDisplayWholeDrawing.triggered.connect(self.fit_to_view)

        self.ui.actionNewProject.setEnabled(False)

        # Connect the Properties action
        self.ui.actionCharacteristicsProperties.triggered.connect(self.toggleCharacteristicsProperties)
        self.properties_mode_active = False
        self.properties_cursor = QtGui.QCursor(QtCore.Qt.PointingHandCursor)


        # Connect the HideStamp action
        self.ui.actionHideStamp.triggered.connect(self.toggleBalloonVisibility)
        self.balloons_hidden = False  # Track balloon visibility state

         # Connect the FieldDivision action
        self.ui.actionFieldDivision.triggered.connect(self.toggleFieldDivision)
        self.grid_visible = False  # Track grid visibility state

        self.ui.actionCharacteristicsOverview.triggered.connect(self.toggleCharacteristicsOverview)
        self.overview_mode_active = False  # Track grid visibility state

        self.ui.actionProjectOverview.triggered.connect(self.show_project_overview)

        # Update the table context menu connection
        self.ui.dimtable.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.dimtable.customContextMenuRequested.connect(self.show_table_context_menu)

        # Ensure window opens maximized
        self.showMaximized()

        # Connect save action
        self.ui.actionSave.triggered.connect(self.save_to_database)

        # Connect logout action
        self.ui.actions['Logout'].triggered.connect(self.logout)

        # Initialize attributes
        self.current_order_details = {}

        # Add these attributes to store the current image
        self.current_image = None
        self.vertical_lines = None
        self.horizontal_lines = None

        # Connect cell changed signal to enable manual measurement entry
        self.ui.dimtable.cellChanged.connect(self.handle_cell_change)

        # Set table style to ensure proper display
        self.ui.dimtable.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #d0d0d0;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:selected {
                color: black;
                background-color: transparent;
            }
        """)

        # Setup custom table delegate to ensure background colors work
        self.setup_custom_table_delegate()

    def setup_header_widget(self):
        """Setup header widget to display order details"""
        # Create header widget
        self.header_widget = QtWidgets.QWidget()
        self.header_widget.setStyleSheet("""
            QWidget {
                background-color: transparent;
                border: none;
            }
            QLabel {
                background-color: transparent;
                border: none;
            }
            QLabel[class="label"] {
                color: #666666;
                font-size: 13px;
                padding-right: 5px;
                background: none;
            }
            QLabel[class="value"] {
                color: #1976d2;
                font-weight: bold;
                font-size: 13px;
                background: none;
            }
            QFrame#separator {
                color: #e0e0e0;
                background: none;
            }
        """)

        # Create layout with no margins
        header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 5, 0, 5)  # Reduced left/right margins to 0
        header_layout.setSpacing(15)

        # Create info sections with label: value format
        sections = [
            ('Part Number', 'part_number'),
            ('Production Order', 'production_order'),
            ('Required Qty', 'required_quantity')
        ]

        self.header_labels = {}

        for i, (label_text, key) in enumerate(sections):
            # Create horizontal layout for each section
            section_layout = QtWidgets.QHBoxLayout()
            section_layout.setSpacing(5)
            section_layout.setContentsMargins(0, 0, 0, 0)  # No margins

            # Add label
            label = QtWidgets.QLabel(f"{label_text}:")
            label.setProperty('class', 'label')
            section_layout.addWidget(label)

            # Add value
            value = QtWidgets.QLabel("-")
            value.setProperty('class', 'value')
            section_layout.addWidget(value)

            # Store reference to value label
            self.header_labels[key] = value

            # Add to main layout
            header_layout.addLayout(section_layout)

            # Add separator after each section except the last
            if i < len(sections) - 1:
                separator = QtWidgets.QFrame()
                separator.setFrameShape(QtWidgets.QFrame.VLine)
                separator.setObjectName("separator")
                separator.setStyleSheet("QFrame { color: #e0e0e0; background: none; }")
                header_layout.addWidget(separator)

        header_layout.addStretch()

        # Add header widget to table frame
        if hasattr(self.ui, 'header_placeholder'):
            self.ui.header_placeholder.setParent(None)
            table_layout = self.ui.table_frame.layout()
            table_layout.insertWidget(0, self.header_widget)

    def update_order_details(self, part_number: str):
        """Update header with order details"""
        try:
            # Get order details from API
            details = api.get_order_details(part_number)

            if details:
                # Update labels
                self.header_labels['part_number'].setText(details['part_number'])
                self.header_labels['production_order'].setText(details['production_order'])
                self.header_labels['required_quantity'].setText(str(details['required_quantity']))

                # Store order details
                self.current_order_details = details
            else:
                # Clear labels if no details found
                for label in self.header_labels.values():
                    label.setText("-")

        except Exception as e:
            print(f"Error updating order details: {str(e)}")
            # Clear labels on error
            for label in self.header_labels.values():
                label.setText("-")

    def center_progress_bar(self):
        """Center the progress bar in the drawing widget"""
        if self.progress_bar and self.ui.drawing:
            # Calculate center position
            drawing_center_x = self.ui.drawing.width() // 2
            drawing_center_y = self.ui.drawing.height() // 2
            progress_bar_x = drawing_center_x - (self.progress_bar.width() // 2)
            progress_bar_y = drawing_center_y - (self.progress_bar.height() // 2)

            # Move progress bar to center
            self.progress_bar.move(progress_bar_x, progress_bar_y)

    def on_drawing_resize(self, event):
        """Handle drawing widget resize events"""
        # Center the progress bar when the drawing widget is resized
        self.center_progress_bar()
        # Call the original resize event if it exists
        if hasattr(self.ui.drawing, 'original_resize_event'):
            self.ui.drawing.original_resize_event(event)

    def setup_view(self):
        """Setup the graphics view with optimal settings"""
        self.ui.pdf_view.setRenderHints(
            QtGui.QPainter.Antialiasing |
            QtGui.QPainter.SmoothPixmapTransform |
            QtGui.QPainter.TextAntialiasing |
            QtGui.QPainter.HighQualityAntialiasing
        )
        self.ui.pdf_view.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.ui.pdf_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ui.pdf_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ui.pdf_view.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.ui.pdf_view.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.ui.dimtable.cellClicked.connect(self.highlight_bbox)

    def find_innermost_boundary(self, image):
        """
        Find the innermost boundary rectangle that contains the main technical drawing
        """
        return ImageProcessor.find_innermost_boundary(image)

    def process_pdf_page(self, page):
        """Process PDF page with text extraction and YOLO detection"""
        try:
            # Create rotation matrix based on selected rotation
            rotation_matrix = fitz.Matrix(300 / 72, 300 / 72).prerotate(self.rotation)

            # Get pixmap with selected rotation
            pix = page.get_pixmap(matrix=rotation_matrix)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

            # Store the original rotated image
            processed_img = img.copy()

            # Get text using PyMuPDF
            fitz_dict = page.get_text("dict")['blocks']
            pdf_results = []

            # Process text blocks
            for block in fitz_dict:
                if 'lines' in block:
                    for line in block['lines']:
                        for span in line['spans']:
                            dimension = span['text'].strip()
                            if not dimension:  # Skip empty text
                                continue
                            bound_box = span['bbox']
                            # Scale coordinates
                            bound_box = [i * 2 for i in bound_box]
                            # Convert to our standard format
                            scene_box = [
                                [bound_box[0], bound_box[1]],  # top-left
                                [bound_box[2], bound_box[1]],  # top-right
                                [bound_box[2], bound_box[3]],  # bottom-right
                                [bound_box[0], bound_box[3]]  # bottom-left
                            ]
                            pdf_results.append({
                                'text': dimension,
                                'box': scene_box,
                                'confidence': 1.0,  # PyMuPDF doesn't provide confidence
                                'rotation': 0
                            })

            # Store results
            self.all_detections['ocr'][0] = pdf_results
            self.ocr_results = pdf_results

            # Process YOLO if model exists
            if self.yolo_model:
                marked_image = img.copy()
                mask, _ = self.find_innermost_boundary(img)
                if mask is not None:
                    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(marked_image, contours, -1, (0, 255, 0), 2)

                    detections = self.yolo_model(marked_image)[0]
                    yolo_results = [
                        {
                            'box': [int(x1), int(y1), int(x2), int(y2)],
                            'confidence': float(conf),
                            'class': int(cls),
                            'class_name': detections.names[int(cls)]
                        }
                        for x1, y1, x2, y2, conf, cls in detections.boxes.data
                        if conf >= 0.75
                    ]

                    self.all_detections['yolo'] = yolo_results
                    self.yolo_detections = yolo_results
                    processed_img = marked_image

            return self.convert_to_pixmap(processed_img)

        except Exception as e:
            print(f"Error in process_pdf_page: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def is_valid_detection(self, result):
        """Check if the detection is valid based on box dimensions and position"""
        try:
            box = result['box']
            # Get box dimensions
            x_coords = [p[0] for p in box]
            y_coords = [p[1] for p in box]
            width = max(x_coords) - min(x_coords)
            height = max(y_coords) - min(y_coords)

            # Skip if box dimensions are invalid
            if width <= 0 or height <= 0:
                return False

            # Skip if box is too small
            if width < 5 or height < 5:
                return False

            # Skip if box is outside image bounds
            if min(x_coords) < 0 or min(y_coords) < 0:
                return False

            return True
        except:
            return False

    def convert_to_pixmap(self, img):
        """Convert numpy image to QPixmap"""
        if img is None:
            return None

        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if len(img.shape) == 3 else img
        height, width = rgb_img.shape[:2]
        bytes_per_line = 3 * width

        qimage = QtGui.QImage(
            rgb_img.tobytes(),
            width,
            height,
            bytes_per_line,
            QtGui.QImage.Format_RGB888
        )
        return QtGui.QPixmap.fromImage(qimage)

    def get_best_ocr_results(self):
        """Get the OCR results with the highest confidence across all rotations"""
        all_results = []
        for rotation, results in self.all_detections['ocr'].items():
            for result in results:
                result['rotation'] = rotation
                all_results.append(result)

        # Sort by confidence
        all_results.sort(key=lambda x: x['confidence'], reverse=True)

        # Remove duplicates (keep highest confidence)
        seen_texts = set()
        best_results = []
        for result in all_results:
            text = result['text'].strip().lower()
            if text not in seen_texts:
                seen_texts.add(text)
                best_results.append(result)

        return best_results

    def add_to_table_and_scene(self, text, bbox, scene_box=None, is_selection=False):
        """Add detected text and bbox to table and scene"""
        return VisualizationEvents.add_to_table_and_scene(self, text, bbox, scene_box, is_selection)

    def highlight_bbox(self, row, column):
        """Highlight the selected bounding box and create a balloon with row number"""
        try:
            # Get the bbox data from the table
            item = self.ui.dimtable.item(row, 2)  # Nominal column
            if not item:
                return

            bbox = item.data(Qt.UserRole)
            if not bbox:
                return

            # Use the CustomGraphicsView's highlight_bbox method
            self.ui.pdf_view.highlight_bbox(bbox, row + 1)

        except Exception as e:
            print(f"Error highlighting bbox: {str(e)}")

    def is_dimensional_value(self, text):
        return DimensionParser.is_dimensional_value(text)

    def determine_dimension_type(self, text, nominal_value):
        """Determine the dimension type based on the text and nominal value"""
        return DimensionParser.determine_dimension_type(text, nominal_value)

    def parse_dimension(self, text):
        return DimensionParser.parse_dimension(text)

    def enhance_image(self, image):
        return ImageProcessor.enhance_image(image)

    def open_pdf(self, file_path=None):
        """Open and process PDF file"""
        try:
            # Show file dialog if no file path provided
            if file_path is None:
                file_path, _ = QFileDialog.getOpenFileName(
                    self, "Open PDF", "", "PDF files (*.pdf)"
                )

            if file_path:
                # Always show preview dialog to select page and rotation
                preview_dialog = PDFPreviewDialog(file_path, self)
                if preview_dialog.exec_() == QDialog.Accepted:
                    page_number = preview_dialog.get_selected_page()
                    rotation = preview_dialog.get_rotation()
                    self.process_pdf(file_path, page_number, rotation)

        except Exception as e:
            print(f"Error opening PDF: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to open PDF: {str(e)}")

    def fetch_existing_bboxes(self):
        """Fetch existing bounding boxes from database for current order and operation"""
        try:
            # Get order_id from stored data
            order_id = None
            if hasattr(self.operations_dialog, 'selected_operation'):
                stored_orders = self.operations_dialog.selected_operation.get('order_data', [])
                if stored_orders and isinstance(stored_orders, list):
                    for order in stored_orders:
                        if str(order.get('production_order')) == str(self.operations_dialog.production_order):
                            order_id = order.get('id')
                            break

            # If not found in stored data, fetch from API
            if not order_id:
                response = api._make_request("/planning/all_orders")
                if response and isinstance(response, list):
                    for order in response:
                        if str(order.get('production_order')) == str(self.operations_dialog.production_order):
                            order_id = order.get('id')
                            break

            if not order_id:
                print("Could not find order_id")
                return []

            # Get operation number
            operation_number = self.operations_dialog.get_operation_number()

            # Fetch bounding box data from API
            endpoint = f"/quality/master-boc/order/{order_id}?op_no={operation_number}"
            response = api._make_request(endpoint)

            if response:
                print(f"Loaded {len(response)} bounding boxes from database")
                return response
            else:
                print("No bounding box data found")
                return []

        except Exception as e:
            print(f"Error fetching bounding boxes: {str(e)}")
            return []

    def process_pdf(self, file_path, page_number, rotation):
        """Process PDF file with given parameters"""
        try:
            
            print("\n=== VIEW DRAWING DETAILS ===")
            print(f"Current order details: {self.current_order_details}")
            print(f"User: {getattr(self, 'user_role', 'unknown')}")
            print(f"File: {file_path}")
            print(f"Page: {page_number}")
            print(f"Rotation: {rotation}")
            
            print("\n=== PROCESSING PDF ===")
            print(f"File: {file_path}")
            print(f"Page: {page_number}")
            print(f"Rotation: {rotation}")
            # Make sure to close any existing PDF document first
            if hasattr(self, 'current_pdf') and self.current_pdf is not None:
                try:
                    print("Closing existing PDF document")
                    self.current_pdf.close()
                except Exception as e:
                    print(f"Error closing current PDF: {str(e)}")
            
            # Reset the dimension table to clear any existing data
            print("Resetting dimension table")
            self.reset_dimension_table()
            
            # Completely reset the graphics view
            print("Resetting graphics view")
            self.ui.pdf_view.reset_view()
            
            # Create a new scene
            print("Creating new scene")
            self.scene = QtWidgets.QGraphicsScene()
            self.ui.pdf_view.setScene(self.scene)
            
            print(f"New scene created: {self.scene}")
            
            # Force a scene update and process events to ensure UI updates
            print("Forcing scene update")
            QtWidgets.QApplication.processEvents()
            
            # Open the PDF document
            print("Opening PDF document")
            self.current_pdf = fitz.open(file_path)
            
            # Load the specified page
            self.current_page = self.current_pdf[page_number]
            self.rotation = rotation
            self.loaded_page = self.current_page 

            # Create rotation matrix based on selected rotation
            rotation_matrix = fitz.Matrix(2, 2).prerotate(rotation)

            # Get the page pixmap with rotation
            pix = self.current_page.get_pixmap(matrix=rotation_matrix)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img)

            # Add new pixmap to the scene
            print("Getting page pixmap and adding it to scene")
            pixmap_item = self.scene.addPixmap(pixmap)
            self.scene.setSceneRect(QRectF(pixmap.rect()))
            
            # Ensure the pixmap is visible
            print(f"Scene items after adding pixmap: {len(self.scene.items())}")
            pixmap_item.setZValue(0)
            self.ui.pdf_view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            self.ui.pdf_view.centerOn(pixmap_item)
            
            # Set the current file path
            self.current_file = file_path

            # For admin/supervisor users, process the page with OCR/YOLO
            if self.is_admin_or_supervisor():
                # Disable selection tool until OCR is complete
                self.ui.actionSelectionTool.setEnabled(False)
                
                # Fetch and draw existing bounding boxes
                existing_bboxes = self.fetch_existing_bboxes()
                if existing_bboxes:
                    # Clear existing table data
                    self.ui.dimtable.setRowCount(0)
                    
                    # Process each dimension and its bbox
                    for dimension in existing_bboxes:
                        row = self.ui.dimtable.rowCount()
                        self.ui.dimtable.insertRow(row)

                        # Set data in table
                        self.ui.dimtable.setItem(row, 0, QTableWidgetItem(str(row + 1)))  # Serial number
                        self.ui.dimtable.setItem(row, 1, QTableWidgetItem(dimension.get('zone', 'N/A')))
                        self.ui.dimtable.setItem(row, 2, QTableWidgetItem(str(dimension.get('nominal', ''))))
                        self.ui.dimtable.setItem(row, 3, QTableWidgetItem(str(dimension.get('uppertol', 0))))
                        self.ui.dimtable.setItem(row, 4, QTableWidgetItem(str(dimension.get('lowertol', 0))))
                        self.ui.dimtable.setItem(row, 5, QTableWidgetItem(dimension.get('dimension_type', 'Unknown')))
                        self.ui.dimtable.setItem(row, 6, QTableWidgetItem(dimension.get('measured_instrument', 'Not Specified')))

                        # Draw bounding box if bbox data exists
                        bbox = dimension.get('bbox', [])
                        if bbox:
                            try:
                                # Convert bbox to list if it's not already
                                if not isinstance(bbox, list):
                                    bbox = list(bbox)

                                # Ensure we have valid coordinates
                                if len(bbox) >= 8:
                                    # Create points for polygon
                                    points = []
                                    for i in range(0, len(bbox), 2):
                                        x = float(bbox[i])
                                        y = float(bbox[i+1])
                                        points.append([x, y])

                                    # Create and style the polygon
                                    polygon = QGraphicsPolygonItem(QPolygonF([QPointF(p[0], p[1]) for p in points]))
                                    pen = QPen(QColor(0, 255, 0))  # Green color
                                    pen.setWidth(2)
                                    pen.setCosmetic(True)
                                    polygon.setPen(pen)
                                    polygon.setZValue(1)

                                    # Add polygon to scene
                                    self.scene.addItem(polygon)

                                    # Store points data in table
                                    nominal_item = self.ui.dimtable.item(row, 2)
                                    if nominal_item:
                                        nominal_item.setData(Qt.UserRole, points)

                            except Exception as bbox_error:
                                print(f"Error processing bbox for row {row}: {bbox_error}")
                                print(f"Original bbox data: {bbox}")

                # Process the page with OCR/YOLO
                self.process_page()

            # Fit view to content - do this for both admin/supervisor and operator
            self.ui.pdf_view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            self.zoom_factor = 1.0  # Reset zoom factor after fitting

            # Force a final update
            self.ui.pdf_view.viewport().update()
            QtWidgets.QApplication.processEvents()

        except Exception as e:
            print(f"Error processing PDF: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to process PDF: {str(e)}")

    def is_admin_or_supervisor(self):
        """Helper method to check if user has admin or supervisor privileges"""
        return self.user_role in ['admin', 'supervisor']

    def start_loading_process(self):
        """Handle the PDF loading process with loading animation in a separate thread"""
        try:
            # Initialize loading UI with infinite progress
            self.start_loading()

            # Create and start worker thread
            self.worker = self.PDFWorker(self, self.loading_params)
            self.worker.finished.connect(self._on_pdf_processing_finished)
            self.worker.error.connect(self._on_pdf_processing_error)
            self.worker.progress_update.connect(self._on_progress_update)
            self.worker.start()

        except Exception as e:
            self.stop_loading()
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to start PDF processing: {str(e)}"
            )

    def _on_pdf_processing_finished(self):
        """Handle completion of PDF processing"""
        self.stop_loading()
        self.worker.deleteLater()

    def _on_pdf_processing_error(self, error_message):
        """Handle errors in PDF processing"""
        self.stop_loading()
        self.worker.deleteLater()
        QtWidgets.QMessageBox.critical(
            self,
            "Error",
            f"Failed to load PDF: {error_message}"
        )

    def _on_progress_update(self, message):
        """Update progress message from worker thread"""
        if hasattr(self, 'loading_label'):
            self.loading_label.setText(message)

    def prepare_document(self):
        """Step 1: Prepare for document loading"""
        try:
            self.reset_dimension_table()
            self.ui.pdf_view.clearYOLODetections()
            return True
        except Exception as e:
            print(f"Error in prepare_document: {str(e)}")
            return False

    def open_document(self):
        """Step 2: Open the PDF document"""
        try:
            self.current_pdf = fitz.open(self.loading_params['file_path'])
            self.current_file = self.loading_params['file_path']
            return True
        except Exception as e:
            print(f"Error in open_document: {str(e)}")
            return False

    def load_page(self):
        """Step 3: Load the selected page"""
        try:
            if self.current_pdf:
                self.current_page = self.current_pdf[self.loading_params['selected_page']]
                self.rotation = self.loading_params['rotation']
                return True
            return False
        except Exception as e:
            print(f"Error in load_page: {str(e)}")
            return False

    def process_page(self):
        """Process the current page with OCR and YOLO"""
        try:
            # Get pixmap of current page
            pix = self.current_page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

            # Initialize empty results
            self.pdf_results = []
            self.all_detections = {'yolo': []}

            # Enable selection tool for admin/supervisor
            if self.is_admin_or_supervisor():
                self.ui.actionSelectionTool.setEnabled(True)

            # Fit view to content
            self.ui.pdf_view.fitInView(self.ui.pdf_view.sceneRect(), Qt.KeepAspectRatio)
            self.zoom_factor = 1.0

            return True

        except Exception as e:
            print(f"Error processing page: {str(e)}")
            return False

    def finalize_loading(self):
        """Step 5: Finalize the loading process"""
        try:
            # Clean up loading parameters
            self.loading_params = None
            return True
        except Exception as e:
            print(f"Error in finalize_loading: {str(e)}")
            return False

    def start_loading(self):
        """Start the loading animation with circular progress indicator"""
        # Center the loading indicator
        self.ui.center_loading_indicator()

        self.ui.loading_indicator.setVisible(True)
        self.ui.loading_indicator.raise_()

        # Create rotation animation
        self.loading_animation = QtCore.QPropertyAnimation(self.ui.loading_indicator, b"angle")
        # Explicitly set start and end values to fix the warning
        self.loading_animation.setStartValue(0.0)
        self.loading_animation.setEndValue(360.0)
        self.loading_animation.setDuration(1000)  # 1 second per rotation
        self.loading_animation.setLoopCount(-1)  # Infinite loop

        # Set curve shape for smooth continuous rotation
        self.loading_animation.setEasingCurve(QtCore.QEasingCurve.Linear)
        
        # Make sure the animation is properly configured before starting
        self.ui.loading_indicator._angle = 0.0  # Initialize the angle property

        # Connect finished signal to restart animation
        self.loading_animation.finished.connect(self.restart_loading_animation)

        self.loading_animation.start()

    def restart_loading_animation(self):
        """Restart the loading animation to create continuous rotation"""
        if self.ui.loading_indicator.isVisible():
            self.loading_animation.setCurrentTime(0)
            self.loading_animation.start()

    def stop_loading(self):
        """Stop the loading animation"""
        if hasattr(self, 'loading_animation'):
            self.loading_animation.stop()
        if hasattr(self.ui, 'loading_indicator'):
            self.ui.loading_indicator.setVisible(False)

    def update_loading_animation(self, angle):
        """Update the circular loading animation"""
        if hasattr(self.ui, 'loading_indicator') and self.ui.loading_indicator.isVisible():
            self.ui.loading_indicator.setAngle(angle)

    def reset_dimension_table(self):
        """Clear all rows in the dimension table and clean up graphics items."""
        # Clear table rows
        self.ui.dimtable.setRowCount(0)

        # Clear any existing highlights
        self.clear_highlighted_bbox()

        # Clear all OCR items including balloons
        self.ui.pdf_view.clearOCRItems()

        # Reset all balloon-related attributes
        self.current_highlight = None
        self.balloon_circle = None
        self.balloon_triangle = None
        self.balloon_text = None

    def render_page(self):
        """Render the current page with masking, OCR and YOLO detection overlay"""
        if not self.current_page:
            return

        try:
            # Process the page with masking and get QPixmap
            pixmap = self.process_pdf_page(self.current_page)

            # Add to scene
            self.ui.scene.clear()
            self.ui.pdf_view.clearOCRItems()  # Clear previous items
            pixmap_item = self.ui.scene.addPixmap(pixmap)

            # Skip drawing individual OCR and YOLO boxes - they'll be handled by cluster_detections

            # Call cluster_detections to create merged boxes
            self.cluster_detections()

            # Adjust view if needed
            if self.zoom_factor == 1.0:
                self.fit_to_view()

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Render Error",
                f"Failed to render PDF page: {str(e)}"
            )

    def zoom_in(self, use_mouse_position=False, mouse_pos=None):
        self.zoom_factor = ViewEvents.zoom_in(
            self.ui.pdf_view,
            self.zoom_factor,
            self.max_zoom,
            self.zoom_step,
            use_mouse_position,
            mouse_pos
        )

    def zoom_out(self, use_mouse_position=False, mouse_pos=None):
        self.zoom_factor = ViewEvents.zoom_out(
            self.ui.pdf_view,
            self.zoom_factor,
            self.min_zoom,
            self.zoom_step,
            use_mouse_position,
            mouse_pos
        )

    def fit_to_view(self):
        self.zoom_factor = ViewEvents.fit_to_view(self.ui.pdf_view, self.ui.scene)

    def resizeEvent(self, event):
        """Handle window resize events"""
        super().resizeEvent(event)
        # Update table column widths if operator is logged in
        if hasattr(self, 'user_role') and self.user_role == 'operator':
            self.setupCentralWidget()

    def toggleStampMode(self):
        """Toggle stamp tool mode"""
        if not self.is_admin_or_supervisor():
            QMessageBox.warning(self, "Access Denied",
                              "Only administrators or supervisors can use the stamp tool.")
            return

        if hasattr(self.ui, 'pdf_view'):
            self.ui.pdf_view.stamp_mode = not self.ui.pdf_view.stamp_mode
            self.ui.pdf_view.selection_mode = False
            self.ui.actionSelectionTool.setChecked(False)

    def toggleSelectionMode(self):
        """Toggle selection mode for OCR/YOLO detection"""
        if not self.is_admin_or_supervisor():
            QMessageBox.warning(self, "Access Denied",
                              "Only administrators or supervisors can use the selection tool.")
            # Uncheck the action button if it was checked
            self.ui.actionSelectionTool.setChecked(False)
            return

        if self.ui.pdf_view.selection_mode:
            self.ui.pdf_view.exitSelectionMode()
            self.ui.actionSelectionTool.setChecked(False)
        else:
            self.ui.pdf_view.enterSelectionMode()
            self.ui.actionSelectionTool.setChecked(True)
            # Disable stamp mode when entering selection mode
            self.ui.pdf_view.stamp_mode = False
            self.ui.actionStamp.setChecked(False)

    def show_table_context_menu(self, position):
        """Show context menu for table rows"""
        menu = QMenu()

        # Get selected rows
        selected_rows = set(item.row() for item in self.ui.dimtable.selectedItems())

        if self.is_admin_or_supervisor():
            # Admin/supervisor menu options
            delete_action = menu.addAction("Delete Row")
            set_instrument_action = menu.addAction("Set Measurement Instrument")

            if selected_rows:  # Valid selection
                action = menu.exec_(self.ui.dimtable.viewport().mapToGlobal(position))
                if action == delete_action:
                    for row in sorted(selected_rows, reverse=True):
                        TableEvents.delete_table_row_and_bbox(self, row)
                elif action == set_instrument_action:
                    self.set_measurement_instrument(selected_rows)
        else:
            # Operator menu options
            filter_action = menu.addAction("Filter by Instrument")
            clear_filter_action = menu.addAction("Clear Filter")
            menu.addSeparator()
            add_device_action = menu.addAction("Add Device")
            connect_device_action = menu.addAction("Connect to Device")

            action = menu.exec_(self.ui.dimtable.viewport().mapToGlobal(position))
            if action == filter_action:
                self.filter_by_instrument()
            elif action == clear_filter_action:
                self.clear_instrument_filter()
            elif action == add_device_action:
                if selected_rows:  # If there's a selected row
                    row = list(selected_rows)[0]  # Get the first selected row
                    self.connect_to_device(row)
            elif action == connect_device_action:
                if selected_rows:  # If there's a selected row
                    row = list(selected_rows)[0]  # Get the first selected row
                    self.connect_to_bluetooth_device(row)

    def filter_by_instrument(self):
        """Show dialog to filter table by instrument"""
        dialog = MeasurementInstrumentDialog(self, allow_multiple=True, is_admin=self.user_role == 'admin')  # Allow multiple selection
        if dialog.exec_() == QDialog.Accepted:
            instruments = dialog.get_selected_instrument()
            if instruments:
                # Hide rows that don't match any of the selected instruments
                for row in range(self.ui.dimtable.rowCount()):
                    instrument_item = self.ui.dimtable.item(row, 6)  # Instrument column
                    instrument_text = instrument_item.text() if instrument_item else ""
                    self.ui.dimtable.setRowHidden(row, instrument_text not in instruments)

                # Update status bar
                visible_rows = sum(1 for row in range(self.ui.dimtable.rowCount())
                                 if not self.ui.dimtable.isRowHidden(row))
                instruments_str = ", ".join(instruments)
                self.statusBar().showMessage(f"Showing {visible_rows} rows for {instruments_str}")

    def clear_instrument_filter(self):
        """Clear the instrument filter and show all rows"""
        for row in range(self.ui.dimtable.rowCount()):
            self.ui.dimtable.setRowHidden(row, False)
        
        # Update status bar
        self.ui.statusbar.showMessage(f"Showing all {self.ui.dimtable.rowCount()} dimensions")
        
    def connect_to_bluetooth_device(self, row):
        """Connect to a Bluetooth device associated with the instrument in the selected row"""
        try:
            # Get the instrument name and code from the table
            instrument_item = self.ui.dimtable.item(row, 6)  # Instrument column
            if not instrument_item or not instrument_item.text():
                QtWidgets.QMessageBox.warning(
                    self,
                    "No Instrument",
                    "No measurement instrument is associated with this row."
                )
                return
            
            # The instrument column might contain the name, but we need the code
            # Try to extract the code which typically follows a pattern like L02-8087
            instrument_text = instrument_item.text()
            print(f"Instrument text from table: {instrument_text}")
            
            # Try to extract the instrument code using a regex pattern
            import re
            # Look for patterns like L02-8087 or similar instrument codes
            code_match = re.search(r'([A-Z][0-9]{2}-[0-9]{4})', instrument_text)
            
            if code_match:
                instrument_code = code_match.group(1)
                print(f"Extracted instrument code: {instrument_code}")
            else:
                # If no code pattern is found, check if it's in the format 'Name (Code)'
                name_code_match = re.search(r'(.*?)\s*\(([^)]+)\)', instrument_text)
                if name_code_match:
                    instrument_code = name_code_match.group(2).strip()
                    print(f"Extracted instrument code from parentheses: {instrument_code}")
                else:
                    # If no code pattern is found, use the text as is
                    instrument_code = instrument_text
                    print(f"Using full text as instrument code: {instrument_code}")
            
            # Show status message
            self.ui.statusbar.showMessage(f"Connecting to device for {instrument_code}...")
            
            # Get the Bluetooth address from the API using the endpoint from api_endpoints.py
            api_url = api.base_url + APIEndpoints.INVENTORY_ITEMS
            print(f"API URL: {api_url}")
            response = requests.get(api_url)
            
            if response.status_code != 200:
                raise Exception(f"Failed to get inventory items: {response.status_code}")
                
            items = response.json()
            print(f"Found {len(items)} items from API")
            bluetooth_address = None
            
            # Find the item with matching instrument code or name
            print(f"Looking for instrument: {instrument_code}")
            
            # First try to find an exact match on instrument code
            exact_match_found = False
            
            # Check if the instrument_code is actually a subcategory name (like 'Plug Gauge Box')
            is_subcategory_name = False
            
            # Look for L02-xxxx pattern to determine if it's an instrument code or subcategory name
            import re
            if not re.search(r'([A-Z][0-9]{2}-[0-9]{4})', instrument_code):
                # If it doesn't match the pattern, it might be a subcategory name
                is_subcategory_name = True
                print(f"{instrument_code} appears to be a subcategory name rather than an instrument code")
            
            # First pass: look for exact instrument code match
            for item in items:
                dynamic_data = item.get('dynamic_data', {})
                item_code = item.get('item_code', 'Unknown')
                item_instrument_code = dynamic_data.get('Instrument code')
                item_bluetooth = dynamic_data.get('Bluetooth Address')
                print(f"Checking item {item_code} with instrument code {item_instrument_code} and bluetooth {item_bluetooth}")
                
                # Check for exact match on instrument code
                if item_instrument_code and item_instrument_code == instrument_code and item_bluetooth:
                    bluetooth_address = item_bluetooth
                    exact_match_found = True
                    print(f"EXACT MATCH FOUND for {instrument_code}: {bluetooth_address}")
                    break
                    
                # If we're looking for a subcategory name, also check the row text for the instrument code
                if is_subcategory_name and item_bluetooth:
                    # Get the full row text to check for instrument code in the row
                    row_text = ""
                    for col in range(self.ui.dimtable.columnCount()):
                        cell_item = self.ui.dimtable.item(row, col)
                        if cell_item:
                            row_text += cell_item.text() + " "
                    
                    # If the row contains the instrument code from this item, use it
                    if item_instrument_code and item_instrument_code in row_text:
                        bluetooth_address = item_bluetooth
                        exact_match_found = True
                        print(f"ROW TEXT MATCH FOUND for {item_instrument_code} in row text: {bluetooth_address}")
                        break
                    
            # If no exact match, try to find a match based on subcategory name
            if not bluetooth_address:
                print("No exact match found, trying to match by name...")
                
                # Fetch subcategories once and cache them
                subcategories = {}
                try:
                    # Get all subcategories for instruments (category_id=2)
                    all_subcategories = api.get_inventory_subcategories(2)
                    for subcategory in all_subcategories:
                        subcategories[subcategory.get('id')] = subcategory.get('name')
                    print(f"Cached {len(subcategories)} subcategories")
                except Exception as e:
                    print(f"Error fetching subcategories: {str(e)}")
                
                # Try to find a match based on the instrument name or code
                # This is a more specific search to ensure we get the right instrument
                for item in items:
                    dynamic_data = item.get('dynamic_data', {})
                    item_bluetooth = dynamic_data.get('Bluetooth Address')
                    item_instrument_code = dynamic_data.get('Instrument code')
                    item_name = item.get('name', '')
                    item_code = item.get('item_code', '')
                    
                    # Skip items without Bluetooth address
                    if not item_bluetooth:
                        continue
                        
                    # Try to match by instrument code (more specific)
                    if item_instrument_code and instrument_code:
                        # Check for partial code match (e.g., L02-81 in L02-8123)
                        if (instrument_code in item_instrument_code or 
                            item_instrument_code in instrument_code):
                            bluetooth_address = item_bluetooth
                            print(f"PARTIAL CODE MATCH FOUND for {item_instrument_code}: {bluetooth_address}")
                            break
                    
                    # Try to match by item name
                    if item_name and instrument_code:
                        if (instrument_code.lower() in item_name.lower() or 
                            item_name.lower() in instrument_code.lower()):
                            bluetooth_address = item_bluetooth
                            print(f"NAME MATCH FOUND for {item_name} ({item_instrument_code}): {bluetooth_address}")
                            break
                
                # Print the selected row's text for debugging purposes
                if not bluetooth_address:
                    print("Checking selected row text for additional context...")
                    
                    # Get the selected row's full text to use for matching
                    selected_row_text = ""
                    if row < self.ui.dimtable.rowCount():
                        for col in range(self.ui.dimtable.columnCount()):
                            item = self.ui.dimtable.item(row, col)
                            if item:
                                selected_row_text += item.text() + " "
                    
                    print(f"Selected row text: {selected_row_text}")
                        
            # Also check if the item has a Bluetooth address and the instrument code matches
            # any part of the dynamic data
            if not bluetooth_address:
                for item in items:
                    dynamic_data = item.get('dynamic_data', {})
                    item_bluetooth = dynamic_data.get('Bluetooth Address')
                    
                    if item_bluetooth:
                        match_found = False
                        for key, value in dynamic_data.items():
                            if isinstance(value, str) and instrument_code.lower() in value.lower():
                                bluetooth_address = item_bluetooth
                                print(f"DYNAMIC DATA MATCH FOUND in {key}: {bluetooth_address}")
                                match_found = True
                                break
                        
                        if match_found:
                            break
            
            # Only connect if we have an exact match for this specific instrument code
            # This prevents connecting to a device that's associated with a different instrument
            if exact_match_found:
                print(f"Using exact match Bluetooth address {bluetooth_address} for instrument {instrument_code}")
            else:
                print(f"No exact match found for instrument {instrument_code}")
            
            if not bluetooth_address or not exact_match_found:
                # Show a more helpful message with instructions
                result = QtWidgets.QMessageBox.question(
                    self,
                    "No Exact Bluetooth Match",
                    f"No exact Bluetooth address match found for instrument {instrument_code}.\n\nWould you like to open the Bluetooth Connectivity dialog to associate a device now?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                
                if result == QtWidgets.QMessageBox.Yes:
                    # Open the Bluetooth connectivity dialog
                    from bluetooth_connectivity import BluetoothConnectivityDialog
                    dialog = BluetoothConnectivityDialog(self, instrument_code)
                    dialog.exec_()
                    
                    # After dialog closes, try to get the address again
                    # Refresh the data from API
                    response = requests.get(api_url)
                    if response.status_code == 200:
                        items = response.json()
                        for item in items:
                            dynamic_data = item.get('dynamic_data', {})
                            item_instrument_code = dynamic_data.get('Instrument code')
                            if item_instrument_code == instrument_code:
                                bluetooth_address = dynamic_data.get('Bluetooth Address')
                                if bluetooth_address:
                                    print(f"Found newly associated address: {bluetooth_address}")
                                    exact_match = True
                                    break
                
                # If we still don't have an exact match, return without connecting
                if not bluetooth_address or not exact_match:
                    self.ui.statusbar.showMessage(f"No exact Bluetooth match for {instrument_code}. Please associate a device first.")
                    return
            
            # Create a progress dialog
            progress = QtWidgets.QProgressDialog("Connecting to Bluetooth device...", "Cancel", 0, 0, self)
            progress.setWindowTitle("Connecting")
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.show()
            
            # Create a thread to handle the Bluetooth connection
            self.bluetooth_thread = BluetoothMonitorThread(bluetooth_address, self)
            self.bluetooth_thread.connection_status.connect(self.on_bluetooth_connection_status)
            self.bluetooth_thread.data_received.connect(self.on_bluetooth_data_received)
            self.bluetooth_thread.finished.connect(progress.close)  # Close progress dialog when thread finishes
            self.bluetooth_thread.start()
            
            # Update status
            self.ui.statusbar.showMessage(f"Connecting to Bluetooth device {bluetooth_address}...")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Connection Error",
                f"Error connecting to Bluetooth device: {str(e)}"
            )
            self.ui.statusbar.showMessage("Bluetooth connection failed")
            print(f"Error connecting to Bluetooth device: {str(e)}")
    
    def on_bluetooth_connection_status(self, status, message):
        """Handle Bluetooth connection status updates"""
        if status:
            self.ui.statusbar.showMessage(f"Bluetooth connected: {message}")
        else:
            self.ui.statusbar.showMessage(f"Bluetooth error: {message}")
            QtWidgets.QMessageBox.warning(
                self,
                "Connection Error",
                f"Error connecting to Bluetooth device: {message}"
            )
            
    def on_bluetooth_data_received(self, data):
        """Handle data received from Bluetooth device"""
        try:
            # Parse the measurement value
            measurement = None
            if 'Measured value:' in data:
                measurement = data.split('Measured value:')[-1].strip()
            else:
                measurement = data.strip()
                
            # Try to convert to float to ensure it's a valid measurement
            measurement_value = float(measurement)
            
            # Find the currently selected row
            selected_rows = self.ui.dimtable.selectedItems()
            if not selected_rows:
                print(f"No row selected, can't populate measurement: {measurement_value}")
                self.ui.statusbar.showMessage(f"Please select a row to add measurement: {measurement_value}")
                return
                
            # Get the row of the first selected item
            row = selected_rows[0].row()
            
            # Store the current measurement value for this row
            if not hasattr(self, 'current_measurement_columns'):
                self.current_measurement_columns = {}
            
            # Initialize or get the current column index for this row
            current_col_index = self.current_measurement_columns.get(row, 8)  # Start with M1 (column 8)
            
            # Check if we've gone through all columns
            if current_col_index > 10:  # We've filled M1, M2, and M3
                # Reset to M1 to start over
                current_col_index = 8
                # Clear existing values
                for col in [8, 9, 10]:
                    self.ui.dimtable.setItem(row, col, QtWidgets.QTableWidgetItem(""))
                self.ui.statusbar.showMessage(f"Starting new measurement set for row {row+1}")
            
            # Add the measurement to the current column
            new_item = QtWidgets.QTableWidgetItem(str(measurement_value))
            self.ui.dimtable.setItem(row, current_col_index, new_item)
            
            # Update the status bar
            col_name = ['M1', 'M2', 'M3'][current_col_index-8]  # Convert column index to name
            self.ui.statusbar.showMessage(f"Measurement {measurement_value} added to {col_name} in row {row+1}")
            
            # Highlight the cell
            from PyQt5 import QtGui
            self.ui.dimtable.item(row, current_col_index).setBackground(QtGui.QColor(200, 255, 200))
            
            # Move to the next column for the next measurement
            self.current_measurement_columns[row] = current_col_index + 1
                
        except Exception as e:
            print(f"Error processing Bluetooth data: {str(e)}")
            self.ui.statusbar.showMessage(f"Error processing measurement: {str(e)}")
    
        
        # TODO: Process the data as needed for your application
        # For example, you might want to update a measurement value in the table
        
    def set_measurement_instrument(self, rows):
        """Set measurement instrument for selected rows"""
        dialog = MeasurementInstrumentDialog(self, is_admin=self.user_role == 'admin')
        if dialog.exec_() == QDialog.Accepted:
            instrument = dialog.get_selected_instrument()
            if instrument:
                # Apply the selected instrument to all selected rows
                for row in rows:
                    item = QTableWidgetItem(instrument)
                    item.setTextAlignment(Qt.AlignCenter)
                    self.ui.dimtable.setItem(row, 6, item)  # Column 6 is Measurement Instrument

    def delete_table_row_and_bbox(self, row):
        """Delete the table row and its corresponding bbox"""
        TableEvents.delete_table_row_and_bbox(self, row)

    def toggleMoveMode(self):
        ViewEvents.toggle_move_mode(self.ui.pdf_view, self.ui.actionMoveView)

    def toggleDynamicZoom(self):
        ViewEvents.toggle_dynamic_zoom(self.ui.pdf_view, self.ui.actionZoomDynamic)

    def toggleZoomArea(self):
        ViewEvents.toggle_zoom_area(self.ui.pdf_view, self.ui.actionZoomArea)

    def cluster_detections(self):
        """Cluster OCR and YOLO detections based on proximity"""
        pdf_results = self.pdf_results if hasattr(self, 'pdf_results') else []
        yolo_detections = self.all_detections.get('yolo', [])
        ClusterDetector.cluster_detections(self, pdf_results, yolo_detections, DimensionParser)
        # print(f"YEEEEEEEET\n{ocr_results}\n{yolo_detections}")

    def is_box_contained(self, inner_box, outer_box):
        return BoundingBoxUtils.is_box_contained(inner_box, outer_box)

    def calculate_iou(self, box1, box2):
        return BoundingBoxUtils.calculate_iou(box1, box2)

    def open_part_number(self):
        """Open part number dialog and handle selected file"""
        try:
            # Show login dialog first if not authenticated
            if not api.token:
                try:
                    # Try to connect to the API server
                    print("Testing API connection...")
                    base_url = APIEndpoints.BASE_URL
                    response = requests.get(base_url, timeout=10)
                    print(f"API response status: {response.status_code}")

                    # Show login dialog if server is responding
                    login_dialog = LoginDialog(self)
                    if login_dialog.exec_() != QDialog.Accepted:
                        return

                    # Verify token was obtained
                    if not api.token:
                        QMessageBox.critical(
                            self,
                            "Login Error",
                            "Failed to obtain authentication token. Please try again."
                        )
                        return

                except requests.RequestException as e:
                    print(f"API connection error: {str(e)}")
                    QMessageBox.warning(
                        self,
                        "Connection Error",
                        f"Cannot connect to the server at {APIEndpoints.BASE_URL}\n\n"
                        f"Error: {str(e)}\n\n"
                        "Opening local file browser instead..."
                    )
                    self.open_pdf()
                    return

            # Show part number dialog
            dialog = PartNumberDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                file_path = dialog.get_downloaded_file()
                selected_page = dialog.get_selected_page()
                rotation = dialog.get_selected_rotation()

                # Store the operations dialog reference
                self.operations_dialog = dialog.operations_dialog

                if file_path and os.path.exists(file_path):
                    try:
                        # Always reset the scene and graphics view before starting a new drawing load
                        if hasattr(self, 'ui') and hasattr(self.ui, 'pdf_view'):
                            print("\n=== RESETTING SCENE FROM open_part_number ===")
                            self.ui.pdf_view.reset_view()
                            if hasattr(self, 'scene'):
                                self.scene.clear()

                        # Start loading immediately
                        self.start_loading()
                        QtWidgets.QApplication.processEvents()

                        # Reset the dimension table and clear YOLO detections
                        self.reset_dimension_table()
                        self.ui.pdf_view.clearYOLODetections()

                        # Actually load and display the new drawing
                        self.process_pdf(file_path, selected_page, rotation)
                        self.finalize_loading()

                    except Exception as e:
                        QtWidgets.QMessageBox.critical(
                            self,
                            "Error",
                            f"Failed to open PDF: {str(e)}"
                        )
                    finally:
                        # Stop loading
                        self.stop_loading()
                        QtWidgets.QApplication.processEvents()

                        # Clean up temporary file
                        try:
                            os.remove(file_path)
                        except:
                            pass
                else:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Error",
                        "No file was downloaded or the file is missing."
                    )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred: {str(e)}\n\nOpening local file browser instead..."
            )
            self.open_pdf()

    def clear_highlighted_bbox(self):
        """Clear any existing highlighted bbox and balloon"""
        try:
            # Clear highlight polygon
            if hasattr(self, 'current_highlight') and self.current_highlight:
                self.ui.pdf_view.scene().removeItem(self.current_highlight)
                self.current_highlight = None

            # Clear balloon objects
            balloon_objects = ['balloon_circle', 'balloon_triangle', 'balloon_text']
            for obj_name in balloon_objects:
                if hasattr(self, obj_name):
                    obj = getattr(self, obj_name)
                    if obj and obj.scene():  # Check if object exists and is in scene
                        self.ui.pdf_view.scene().removeItem(obj)
                    setattr(self, obj_name, None)  # Set attribute to None

        except Exception as e:
            print(f"Error clearing highlight: {str(e)}")

    def is_similar_text(self, text1, text2):
        """Compare two texts to check if they are similar (ignoring spaces and case)"""
        try:
            # Remove spaces and convert to lowercase for comparison
            clean_text1 = ''.join(text1.lower().split())
            clean_text2 = ''.join(text2.lower().split())

            # Check for exact match
            if clean_text1 == clean_text2:
                return True

            # Check for numeric values (handle cases like "12.5" and "12,5")
            try:
                num1 = float(clean_text1.replace(',', '.'))
                num2 = float(clean_text2.replace(',', '.'))
                return abs(num1 - num2) < 0.001  # Small threshold for floating point comparison
            except:
                pass

            return False
        except:
            return False

    def generate_pdf_report(self, file_path):
        """Generate a PDF report with the dimension table data matching the standard inspection report format"""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch, mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.graphics.shapes import Circle, Drawing

            # Get calibration data
            calibration_data = api.get_calibrations() or {}
            calibration_map = {}
            for cal in calibration_data:
                instrument_code = cal.get('instrument_code', '')
                if instrument_code:
                    last_cal = cal.get('last_calibration', '').split('T')[0] if cal.get('last_calibration') else 'N/A'
                    next_cal = cal.get('next_calibration', '').split('T')[0] if cal.get('next_calibration') else 'N/A'
                    calibration_map[instrument_code] = {
                        'last_calibration': last_cal,
                        'next_calibration': next_cal
                    }

            # Create document
            doc = SimpleDocTemplate(file_path, pagesize=A4,
                                 leftMargin=10*mm, rightMargin=10*mm,
                                 topMargin=10*mm, bottomMargin=10*mm)
            elements = []
            styles = getSampleStyleSheet()

            # Prepare logo for title block
            logo_path = r"D:\siri\calipers\prometrix\prometrix\Smart_Metrology_19082024\belKannada.png"
            logo_img = None
            if os.path.exists(logo_path):
                logo_img = Image(logo_path, width=35*mm, height=12*mm)  # Increased width, reduced height

            # Add title section with logo
            if logo_img:
                title_data = [
                    ['FABRICATION - COMPONENTS', logo_img],
                    ['INSPECTION REPORT']
                ]
            else:
                title_data = [
                    ['FABRICATION - COMPONENTS'],
                    ['INSPECTION REPORT']
                ]

            if logo_img:
                title_table = Table(title_data, colWidths=[doc.width-40*mm, 40*mm])  # Adjusted column width for wider logo
            else:
                title_table = Table(title_data, colWidths=[doc.width])

            title_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Text column
                ('ALIGN', (-1, 0), (-1, -1), 'RIGHT' if logo_img else 'CENTER'),  # Logo column
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('SPAN', (0, 0), (0, 0)),  # First row text
                ('SPAN', (0, 1), (-1, 1)),  # Second row text spans all columns
            ]))
            elements.append(title_table)
            elements.append(Spacer(1, 5*mm))

            # Add header information
            header_data = [
                ['Nomenclature', self.current_order_details.get('part_description', 'N/A'), 'Inspection Report No.', self.operations_dialog.ipid if hasattr(self.operations_dialog, 'ipid') else 'N/A'],
                ['Part No.', self.current_order_details.get('part_number', 'N/A'), 'Purchase Order', self.current_order_details.get('production_order', 'N/A')],
                ['Stage Detail', f"Operation {self.operations_dialog.get_operation_number()}" if hasattr(self.operations_dialog, 'get_operation_number') else 'N/A', 'Qty', str(self.quantity_input.value() if hasattr(self, 'quantity_input') else '1')],
                ['Operator', api.username or 'N/A', '', '']  # Add operator row
            ]
            
            header_table = Table(header_data, colWidths=[doc.width*0.2, doc.width*0.3, doc.width*0.2, doc.width*0.3])
            header_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('PADDING', (0, 0), (-1, -1), 4),
                ('SPAN', (1, 3), (3, 3)),  # Merge the last three cells of the operator row
            ]))
            elements.append(header_table)
            elements.append(Spacer(1, 5*mm))

            # Create main measurement table
            # First create the specification header
            spec_header = [['Specification', '', '', '', '', '', '', '', 'Observation', '', '', '', '']]
            spec_subheader = [
                'Sl.\nNo.',
                'Zone',
                'Nominal',
                'Upper\nTol',
                'Lower\nTol',
                'Instrument',
                'Used\nInstrument',
                'Next\nCalibration',  # New column
                'M1',
                'M2',
                'M3',
                'Mean',
                'Go/\nNo-Go'
            ]

            # Add all headers to data
            table_data = [
                ['', 'Specification', '', '', '', '', '', '', 'Observation', '', '', '', ''],
                spec_subheader
            ]

            # Function to create a colored dot
            def create_dot(color):
                drawing = Drawing(10, 10)
                circle = Circle(5, 5, 4, fillColor=color, strokeColor=None)
                drawing.add(circle)
                return drawing

            # Get measurement data from the table
            for row in range(self.ui.dimtable.rowCount()):
                row_data = []
                # Get first 5 columns (Sl No, Nominal, Upper Tol, Lower Tol, Zone)
                for col in range(5):
                    item = self.ui.dimtable.item(row, col)
                    row_data.append(item.text() if item else '')
                
                # Add instrument columns (6 and 7)
                instrument = ''
                used_instrument = ''
                for col in range(6, 8):
                    item = self.ui.dimtable.item(row, col)
                    value = item.text() if item else ''
                    if col == 6:  # Instrument column
                        instrument = value
                        row_data.append(value)
                    elif col == 7:  # Used Instrument column
                        used_instrument = value
                        # Strip out the calibration date in parentheses for display
                        if '(' in value:
                            used_instrument_display = value.split('(')[0].strip()
                        else:
                            used_instrument_display = value
                        row_data.append(used_instrument_display)

                # Extract calibration date from Used Inst. column if it's in brackets
                next_cal = 'N/A'
                if used_instrument and '(' in used_instrument and ')' in used_instrument:
                    try:
                        next_cal = used_instrument.split('(')[1].split(')')[0]
                    except:
                        next_cal = 'N/A'
                row_data.append(next_cal)  # Add calibration date

                # Get measurement values (M1, M2, M3)
                measurements = []
                for col in range(8, 11):  # M1, M2, M3 columns
                    item = self.ui.dimtable.item(row, col)
                    value = item.text() if item else ''
                    row_data.append(value)
                    if value:
                        try:
                            measurements.append(float(value.replace(',', '.')))
                        except ValueError:
                            pass
                
                # Add mean value
                mean_item = self.ui.dimtable.item(row, 11)  # Mean column
                mean_value = mean_item.text() if mean_item else ''
                row_data.append(mean_value)

                # Determine dot color based on measurements and tolerance
                dot_color = colors.red  # Default to red
                if measurements:  # If measurements exist
                    try:
                        nominal = float(self.ui.dimtable.item(row, 2).text().replace(',', '.'))
                        upper_tol = float(self.ui.dimtable.item(row, 3).text().replace(',', '.'))
                        lower_tol = float(self.ui.dimtable.item(row, 4).text().replace(',', '.'))
                        mean = float(mean_value.replace(',', '.'))
                        
                        # Check if mean is within tolerance
                        if nominal + lower_tol <= mean <= nominal + upper_tol:
                            dot_color = colors.green
                    except (ValueError, AttributeError):
                        pass

                # Add colored dot to row data
                row_data.append(create_dot(dot_color))
                
                table_data.append(row_data)

            # Calculate column widths
            total_width = doc.width
            col_widths = [
                total_width*0.05,  # Sl. No.
                total_width*0.07,  # Zone
                total_width*0.10,  # Nominal
                total_width*0.08,  # Upper Tol
                total_width*0.08,  # Lower Tol
                total_width*0.14,  # Instrument
                total_width*0.12,  # Used Instrument
                total_width*0.10,  # Calibration
                total_width*0.07,  # M1
                total_width*0.07,  # M2
                total_width*0.07,  # M3
                total_width*0.07,  # Mean
                total_width*0.05   # Diff
            ]

            # Create the main table
            main_table = Table(table_data, colWidths=col_widths, repeatRows=2)
            
            # Add style to main table
            main_style = [
                # Grid
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                # Merge cells for specification and observation headers
                ('SPAN', (1, 0), (7, 0)),  # Specification (now includes Calibration)
                ('SPAN', (8, 0), (-1, 0)),  # Observation
                # Headers style
                ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, 1), 8),
                ('BACKGROUND', (0, 0), (-1, 1), colors.lightgrey),
                # Data style
                ('FONTNAME', (0, 2), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 2), (-1, -1), 8),
                ('ALIGN', (0, 2), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]
            
            # Add alternating row colors
            for row in range(2, len(table_data)):
                if row % 2 == 0:
                    main_style.append(('BACKGROUND', (0, row), (-1, row), colors.white))
                else:
                    main_style.append(('BACKGROUND', (0, row), (-1, row), colors.lightgrey))

            main_table.setStyle(TableStyle(main_style))
            elements.append(main_table)

            # Build document
            doc.build(elements)
            return True

        except Exception as e:
            print(f"Error generating PDF report: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def save_to_database(self):
        """Save dimension data to database and generate PDF report for operator"""
        try:
            operation_number = self.operations_dialog.get_operation_number()
            production_order = self.operations_dialog.production_order
            ipid = f"IPID-{self.operations_dialog.part_number}-{operation_number}"

            # Get order_id from stored data or fetch from API
            order_id = None
            if hasattr(self.operations_dialog.selected_operation, 'order_data'):
                stored_orders = self.operations_dialog.selected_operation['order_data']
                if stored_orders and isinstance(stored_orders, list):
                    for order in stored_orders:
                        if str(order.get('production_order')) == str(production_order):
                            order_id = order.get('id')
                            break
            
            # Only fetch from API if not found in stored data
            if not order_id:
                try:
                    response = api._make_request("/planning/all_orders")
                    if response and isinstance(response, list):
                        for order in response:
                            if str(order.get('production_order')) == str(production_order):
                                order_id = order.get('id')
                                break

                        if not order_id:
                            raise Exception(f"Could not find order_id for production order {production_order}")
                    else:
                        raise Exception("Invalid response from all_orders endpoint")
                except Exception as e:
                    print(f"Error getting order_id: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to get order ID: {str(e)}")
                    return

            # Get quantity for operator role - safely handle quantity_input access
            quantity_no = 1  # Default value
            if self.user_role == 'operator':
                try:
                    if hasattr(self, 'quantity_input') and self.quantity_input is not None:
                        quantity_no = self.quantity_input.value()
                    else:
                        print("Warning: quantity_input not found, using default value of 1")
                except Exception as e:
                    print(f"Error accessing quantity_input: {e}")
                    QMessageBox.warning(self, "Warning", "Could not access quantity value, using default value of 1")

            # Check for quantity completion before processing any rows
            if self.user_role == 'operator' and quantity_no > 1:
                # Check if previous quantity is completed
                if not api.check_quantity_completion(order_id, ipid):
                    QMessageBox.critical(self, "Quantity Error",
                        "Quantity 1 is not approved yet. Please wait for approval before proceeding with next quantity.")
                    return

            # If no quantity error, proceed with saving rows
            document_id = 2 if operation_number == "999" else 3

            # First save to report if operator role
            if self.user_role == 'operator':
                report_dialog = ReportFolderDialog(self)
                if report_dialog.exec_() == QDialog.Accepted and report_dialog.get_save_status():
                    selected_folder = report_dialog.get_selected_folder()
                    if not selected_folder:
                        QMessageBox.critical(self, "Error", "No folder selected for report")
                        return
                        
                    # Generate and save PDF report
                    try:
                        temp_pdf = os.path.join(tempfile.gettempdir(), f"report_{uuid.uuid4()}.pdf")
                        if self.generate_pdf_report(temp_pdf):  # Use new method here
                            # Upload the report
                            document_name = f"Inspection_Report_{production_order}_{operation_number}"
                            description = f"Inspection report for {production_order} - Operation {operation_number}"
                            
                            if not api.upload_inspection_report(
                                production_order=production_order,
                                operation_number=operation_number,
                                file_path=temp_pdf,
                                folder_path=selected_folder,
                                document_name=document_name,
                                description=description
                            ):
                                QMessageBox.warning(self, "Warning", "Failed to upload inspection report")
                                return
                        try:
                            os.remove(temp_pdf)
                        except:
                            pass
                    except Exception as e:
                        print(f"Error saving inspection report: {str(e)}")
                        QMessageBox.critical(self, "Error", f"Failed to save inspection report: {str(e)}")
                        return
                else:
                    # User cancelled or save failed
                    return

            success_count = 0
            failed_rows = []
            total_rows = self.ui.dimtable.rowCount()

            # Process all rows
            for row in range(total_rows):
                try:
                    if self.user_role == 'operator':
                        payload = self.prepare_stage_inspection_payload(row, operation_number, order_id, quantity_no)
                        result = api.create_stage_inspection(payload)
                    else:
                        payload = self.prepare_master_boc_payload(row, document_id, operation_number, order_id, ipid)
                        result = api.create_master_boc(payload)

                    if result is None:
                        failed_rows.append(row + 1)
                    else:
                        success_count += 1

                except Exception as e:
                    failed_rows.append(row + 1)

            # Save ballooned drawing for admin/supervisor
            if self.is_admin_or_supervisor() and success_count > 0:
                try:
                    temp_pdf = os.path.join(tempfile.gettempdir(), f"ballooned_{uuid.uuid4()}.pdf")
                    if self.save_scene_to_pdf(temp_pdf):
                        if not api.upload_ballooned_drawing(production_order, ipid, temp_pdf):
                            QMessageBox.warning(self, "Warning", "Failed to upload ballooned drawing")
                    try:
                        os.remove(temp_pdf)
                    except:
                        pass
                except Exception as e:
                    print(f"Error saving ballooned drawing: {str(e)}")
                    
            # Show results
            if failed_rows:
                QMessageBox.warning(
                    self,
                    "Warning",
                    f"Failed to save rows: {', '.join(map(str, failed_rows))}\n"
                    f"Successfully saved {success_count} out of {total_rows} rows."
                )
            else:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Successfully saved all {total_rows} rows."
                )
                
        except Exception as e:
            print(f"Error saving to database: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to save data: {str(e)}")

    def prepare_stage_inspection_payload(self, row, operation_number, order_id, quantity_no):
        """Prepare payload for stage inspection (operator role)"""
        def get_cell_text(row, col):
            item = self.ui.dimtable.item(row, col)
            return item.text() if item else ""

        measured_1 = float(get_cell_text(row, 8) or "0")  # M1 column
        measured_2 = float(get_cell_text(row, 9) or "0")  # M2 column
        measured_3 = float(get_cell_text(row, 10) or "0") # M3 column
        measured_mean = (measured_1 + measured_2 + measured_3) / 3 if any(
            [measured_1, measured_2, measured_3]) else 0

        return {
            "op_id": api.get_operator_id(),  # Use operator_id from api instance
            "nominal_value": get_cell_text(row, 2) or "0",  # Nominal column
            "uppertol": float(get_cell_text(row, 3) or "0"),  # Upper Tol column
            "lowertol": float(get_cell_text(row, 4) or "0"),  # Lower Tol column
            "zone": get_cell_text(row, 1) or "N/A",  # Zone column
            "dimension_type": get_cell_text(row, 5) or "Unknown",  # Type column
            "measured_1": measured_1,
            "measured_2": measured_2,
            "measured_3": measured_3,
            "measured_mean": measured_mean,
            "measured_instrument": get_cell_text(row, 6) or "Not Specified",  # Instrument column
            "used_inst": get_cell_text(row, 7) or "Not Specified",  # Used Inst. column
            "op_no": operation_number,
            "order_id": order_id,
            "quantity_no": quantity_no
        }

    def prepare_master_boc_payload(self, row, document_id, operation_number, order_id, ipid):
        """Prepare payload for master BOC (admin role)"""
        def get_cell_text(row, col):
            item = self.ui.dimtable.item(row, col)
            return item.text() if item else ""

        # Get nominal and convert tolerances
        nominal = get_cell_text(row, 2)
        if not nominal or nominal.strip() == '':
            raise ValueError("Missing nominal value")

        try:
            upper_tol = float(get_cell_text(row, 3) or "0")
        except ValueError:
            upper_tol = 0.0

        try:
            lower_tol = float(get_cell_text(row, 4) or "0")
            if lower_tol > 0:  # If positive, make it negative
                lower_tol = -lower_tol
        except ValueError:
            lower_tol = 0.0

        # Get bounding boxes and validate
        bboxes = self.ui.pdf_view.get_all_bboxes_for_row(row)
        if not bboxes:
            raise ValueError("No bounding boxes found")

        validated_bboxes = []
        for bbox in bboxes:
            if isinstance(bbox, list):
                if len(bbox) == 8:  # Already in [x1,y1,x2,y1,x2,y2,x1,y2] format
                    validated_bboxes.extend([float(x) for x in bbox])
                elif len(bbox) == 4:  # Convert from [x1,y1,x2,y2] to 8-point format
                    x1, y1, x2, y2 = map(float, bbox)
                    validated_bboxes.extend([
                        x1, y1,  # Top-left
                        x2, y1,  # Top-right
                        x2, y2,  # Bottom-right
                        x1, y2   # Bottom-left
                    ])

        if not validated_bboxes:
            raise ValueError("No valid bounding boxes")

        return {
            "order_id": order_id,
            "document_id": document_id,
            "nominal": nominal,
            "uppertol": upper_tol,
            "lowertol": lower_tol,
            "zone": get_cell_text(row, 1) or "N/A",
            "dimension_type": get_cell_text(row, 5) or "Unknown",
            "measured_instrument": get_cell_text(row, 6) or "Not Specified",
            "op_no": operation_number,
            "bbox": validated_bboxes,
            "ipid": ipid,
            "part_number": self.operations_dialog.part_number
        }

    def save_scene_to_pdf(self, file_path):
        """Save the current scene with balloons to PDF"""
        try:
            # Create printer
            printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.HighResolution)
            printer.setOutputFormat(QtPrintSupport.QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            printer.setPageSize(QtGui.QPageSize(self.ui.scene.sceneRect().size().toSize()))

            # Create painter
            painter = QtGui.QPainter()
            painter.begin(printer)

            # Apply rotation if needed
            if hasattr(self, 'rotation') and self.rotation != 0:
                # Translate to center of page
                painter.translate(printer.pageRect().center())
                # Rotate around center
                painter.rotate(self.rotation)
                # Translate back
                painter.translate(-printer.pageRect().center())

            # Render scene
            self.ui.scene.render(painter)
            painter.end()

            return True
        except Exception as e:
            print(f"Error saving scene to PDF: {str(e)}")
            return False

    def handle_login_success(self, username, role):
        """Handle successful login"""
        try:
            # Store the new role
            self.user_role = role.lower()
            print(f"Logged in as {username} with role: {self.user_role}")

            # Remove any existing quantity widget first
            self.remove_quantity_widget()

            # Configure UI based on role
            self.configure_ui_for_role()

            # Show operations dialog
            self.show_operations_dialog()

        except Exception as e:
            print(f"Error in handle_login_success: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to handle login: {str(e)}")

    def remove_quantity_widget(self):
        """Remove the quantity widget if it exists"""
        try:
            if hasattr(self.ui, 'dimtable'):
                table_parent_layout = self.ui.dimtable.parent().layout()
                if table_parent_layout:
                    # Find and remove any existing quantity widgets
                    for i in reversed(range(table_parent_layout.count())):
                        item = table_parent_layout.itemAt(i)
                        widget = item.widget() if item is not None else None
                        if widget and isinstance(widget, QWidget) and widget.findChild(QLabel, None) and widget.findChild(QLabel, None).text().startswith("Quantity:"):
                            table_parent_layout.removeWidget(widget)
                            widget.deleteLater()
                            print("Removed existing quantity widget")
        except Exception as e:
            print(f"Error removing quantity widget: {str(e)}")

    def configure_ui_for_role(self):
        """Configure UI elements based on user role"""
        try:
            is_privileged = self.is_admin_or_supervisor()

            # Enable/disable selection tool - initially disabled for admin/supervisor until OCR completes
            if hasattr(self.ui, 'actionSelectionTool'):
                self.ui.actionSelectionTool.setEnabled(False)  # Start disabled

            # Enable/disable stamp tool
            if hasattr(self.ui, 'actionStamp'):
                self.ui.actionStamp.setEnabled(is_privileged)

            # Update graphics view settings
            if hasattr(self.ui, 'pdf_view'):
                self.ui.pdf_view.selection_mode = False  # Start with selection mode off
                self.ui.pdf_view.stamp_mode = False  # Always start with stamp mode off

            # Update status bar with role info
            self.statusBar().showMessage(f"Logged in as: {self.user_role}")

            # Configure table with role-specific columns
            self.setupCentralWidget()

            # Remove quantity widget for non-operator roles
            if not self.user_role == 'operator':
                self.remove_quantity_widget()

        except Exception as e:
            print(f"Error configuring UI for role: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to configure UI: {str(e)}")

    def setupCentralWidget(self):
        """Setup central widget with role-specific table columns"""
        # Create base headers list
        base_headers = ["Sl No.", "Zone", "Actual", "+Tol", "-Tol", "Dimension Type", "Instrument"]
        operator_headers = ["Used Inst.", "M1", "M2", "M3", "Mean", "Quantity No."]

        # Determine total columns based on role
        if self.user_role == 'operator':
            headers = base_headers + operator_headers
            total_columns = len(headers)
            self.ui.dimtable.setColumnCount(total_columns)

            # Increase table frame width for operator view
            screen_width = QtWidgets.QApplication.desktop().screenGeometry().width()
            table_width = int(screen_width * 0.45)  # Use 45% of screen width
            self.ui.table_frame.setMinimumWidth(table_width)

            # Set fixed column widths for operator view
            column_widths = {
                0: 50,    # Sl No.
                1: 50,    # Zone
                2: 80,    # Actual
                3: 60,    # +Tol
                4: 60,    # -Tol
                5: 120,   # Dim.Type
                6: 120,   # Instrument
                7: 100,   # Used Inst.
                8: 80,    # M1
                9: 80,    # M2
                10: 80,   # M3
                11: 80,   # Mean
                12: 100,  # Quantity No.
            }

            # Apply column widths
            for col, width in column_widths.items():
                if col < total_columns:
                    self.ui.dimtable.setColumnWidth(col, width)

            # Print debug information
            print("\nOperator Table Setup:")
            print(f"Total columns: {self.ui.dimtable.columnCount()}")
            print("Headers:", headers)
            for i, header in enumerate(headers):
                print(f"Column {i}: {header}")
        else:
            headers = base_headers
            self.ui.dimtable.setColumnCount(len(headers))

            # Reset table frame width for admin/supervisor view
            self.ui.table_frame.setMinimumWidth(0)

            # Set column widths for admin/supervisor view
            self.ui.dimtable.setColumnWidth(0, 60)   # Sl No.
            self.ui.dimtable.setColumnWidth(1, 50)   # Zone
            self.ui.dimtable.setColumnWidth(2, 65)   # Actual
            self.ui.dimtable.setColumnWidth(3, 50)   # +Tol
            self.ui.dimtable.setColumnWidth(4, 50)   # -Tol
            self.ui.dimtable.setColumnWidth(5, 120)  # Dim.Type
            self.ui.dimtable.setColumnWidth(6, 100)  # Instrument

        # Set headers
        for i, header in enumerate(headers):
            item = QtWidgets.QTableWidgetItem(header)
            item.setTextAlignment(Qt.AlignCenter)
            self.ui.dimtable.setHorizontalHeaderItem(i, item)

        # Configure selection behavior based on role
        if self.is_admin_or_supervisor():
            self.ui.dimtable.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        else:
            self.ui.dimtable.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self.ui.dimtable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.ui.dimtable.setFocusPolicy(Qt.StrongFocus)

        # Connect selection change signal
        self.ui.dimtable.itemSelectionChanged.connect(self.on_table_selection_changed)

        # Set table style
        self.ui.dimtable.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #d0d0d0;
                selection-background-color: #e3f2fd;
                selection-color: black;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: black;
            }
        """)

    def on_table_selection_changed(self):
        """Handle table selection changes"""
        selected_rows = self.ui.dimtable.selectedItems()
        if selected_rows:
            row = selected_rows[0].row()
            self.highlight_bbox(row, 2)  # 2 is the nominal column

    def logout(self):
        """Handle user logout"""
        try:
            # Clear API token
            api.token = None
            api.user_role = None
            api.username = None

            # Clear current data
            self.reset_application_state()

            # Show login dialog
            login_dialog = LoginDialog(self)
            if login_dialog.exec_() == QDialog.Accepted:
                # Login successful, continue with application
                pass
            else:
                # Login cancelled, close application
                self.close()

        except Exception as e:
            print(f"Error during logout: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to logout: {str(e)}")

    def reset_application_state(self):
        """Reset application state after logout"""
        try:
            # Clear user-specific data
            self.user_role = None

            # Remove quantity widget
            self.remove_quantity_widget()

            # Clear PDF view
            if hasattr(self.ui, 'pdf_view'):
                self.ui.pdf_view.clearOCRItems(clear_all=True)
                # Clear any existing highlights and balloons
                self.clear_highlighted_bbox()
                # Clear scene
                scene = self.ui.pdf_view.scene()
                if scene:
                    scene.clear()

            # Clear balloon object references
            self.balloon_circle = None
            self.balloon_triangle = None
            self.balloon_text = None
            self.current_highlight = None

            # Clear dimension table
            if hasattr(self.ui, 'dimtable'):
                self.ui.dimtable.setRowCount(0)

            # Clear any stored measurements or data
            if hasattr(self, 'measurements'):
                self.measurements.clear()
            if hasattr(self, 'current_measurements'):
                self.current_measurements.clear()

            # Reset status bar
            self.statusBar().clearMessage()

            # Clear any stored file paths or data
            self.current_pdf = None
            self.current_page = None
            self.rotation = 0
            self.loading_params = None
            self.current_file = None
            self.current_image = None
            self.vertical_lines = None
            self.horizontal_lines = None

            # Clear any stored detection data
            if hasattr(self, 'all_detections'):
                self.all_detections = {
                    'ocr': {
                        0: [],  # Original orientation
                        90: [],  # 90 degree rotation
                    },
                    'yolo': []  # YOLO detections
                }

            # Disable tools that require login
            # self.ui.actionSelectionTool.setEnabled(False)
            # self.ui.actionStamp.setEnabled(False)
            # self.ui.actionFieldDivision.setEnabled(False)
            # self.ui.actionCharacteristicsProperties.setEnabled(False)
            # self.ui.actionCharacteristicsOverview.setEnabled(False)

            # Reset window title
            self.setWindowTitle("Quality Management Tool")

            # Clear header labels
            if hasattr(self, 'header_labels'):
                for label in self.header_labels.values():
                    label.setText("-")

            # Reset any active modes
            self.properties_mode_active = False
            self.overview_mode_active = False
            self.balloons_hidden = False
            self.grid_visible = False

            # Reset any stored order details
            self.current_order_details = {}

            # Reset any stored operations dialog reference
            if hasattr(self, 'operations_dialog'):
                self.operations_dialog = None

        except Exception as e:
            print(f"Error resetting application state: {str(e)}")
            import traceback
            traceback.print_exc()

    def show_operations_dialog(self):
        """Show the operations dialog after successful login"""
        try:
            # Show part number dialog first
            part_dialog = PartNumberDialog(self)
            if part_dialog.exec_() == QDialog.Accepted:
                # Get selected part number and production order
                part_number = part_dialog.get_selected_part_number()
                production_order = part_dialog.get_selected_production_order()
                
                # Get the downloaded file from the part number dialog
                file_path = part_dialog.get_downloaded_file()
                selected_page = part_dialog.get_selected_page()
                selected_rotation = part_dialog.get_selected_rotation()

                # Store current order details
                self.current_order_details = {
                    'part_number': part_number,
                    'production_order': production_order
                }

                # Update header with order details
                self.update_order_details(part_number)

                # Debug print current order details
                print(f"\nCurrent order details:")
                print(self.current_order_details)

                # Get the operations dialog from the part number dialog
                if hasattr(part_dialog, 'operations_dialog') and part_dialog.operations_dialog:
                    self.operations_dialog = part_dialog.operations_dialog

                if file_path:
                    # Store the current page and rotation
                    self.current_page = selected_page
                    self.rotation = selected_rotation

                    # Open the PDF directly without showing preview again
                    # The process_pdf method will handle closing the current PDF
                    # and clearing the scene
                    self.process_pdf(file_path, selected_page, selected_rotation)

                    # Store operation data
                    if hasattr(self, 'operations_dialog') and self.operations_dialog:
                        self.current_operation = self.operations_dialog.get_selected_operation()

                    # If operator, load data from API
                    if self.user_role == 'operator':
                        self.load_operator_data()

        except Exception as e:
            print(f"Error showing operations dialog: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to show operations dialog: {str(e)}")

    def load_operator_data(self):
        """Load operator data from API"""
        try:
            # Get the current part number and production order
            if not hasattr(self, 'operations_dialog') or not self.operations_dialog:
                QMessageBox.warning(self, "Warning", "Please select a part number and operation first.")
                return

            part_number = self.operations_dialog.part_number
            production_order = self.operations_dialog.production_order
            operation_number = self.operations_dialog.get_operation_number()

            # Get order_id from stored data or fetch from API
            order_id = None
            if hasattr(self.operations_dialog.selected_operation, 'order_data'):
                stored_orders = self.operations_dialog.selected_operation['order_data']
                if stored_orders and isinstance(stored_orders, list):
                    for order in stored_orders:
                        if str(order.get('production_order')) == str(production_order):
                            order_id = order.get('id')
                            break

            # If not found in stored data, fetch from API
            if not order_id:
                response = api._make_request("/planning/all_orders")
                if response and isinstance(response, list):
                    for order in response:
                        if str(order.get('production_order')) == str(production_order):
                            order_id = order.get('id')
                            break

            if not order_id:
                raise Exception(f"Could not find order_id for production order {production_order}")

            # Use the correct endpoint format
            endpoint = f"/quality/master-boc/order/{order_id}?op_no={operation_number}"
            print(f"Fetching operator data from: {endpoint}")

            response = api._make_request(endpoint)

            if response:
                print(f"Loaded operator data: {json.dumps(response, indent=2)}")

                # Clear existing data
                self.ui.dimtable.setRowCount(0)
                self.ui.pdf_view.scene().clear()

                # Add quantity input widget above table only for operator role
                if self.user_role == 'operator':
                    # Remove existing quantity widgets if any
                    table_parent_layout = self.ui.dimtable.parent().layout()
                    for i in reversed(range(table_parent_layout.count())):
                        item = table_parent_layout.itemAt(i)
                        widget = item.widget() if item is not None else None
                        if widget and isinstance(widget, QWidget) and widget.findChild(QLabel, None) and widget.findChild(QLabel, None).text().startswith("Quantity:"):
                            table_parent_layout.removeWidget(widget)
                            widget.deleteLater()
                    # Now add the new quantity widget
                    quantity_widget = QWidget()
                    quantity_layout = QHBoxLayout(quantity_widget)
                    quantity_layout.setContentsMargins(10, 5, 10, 5)

                    # Create a container widget for better alignment
                    container = QWidget()
                    container_layout = QHBoxLayout(container)
                    container_layout.setContentsMargins(0, 0, 0, 0)
                    container_layout.setSpacing(10)

                    quantity_label = QLabel("Quantity:")
                    quantity_label.setStyleSheet("""
                        QLabel {
                            font-size: 13px;
                            font-weight: bold;
                            color: #2c3e50;
                            background: transparent;
                        }
                    """)

                    self.quantity_input = QSpinBox()
                    self.quantity_input.setMinimum(1)
                    self.quantity_input.setMaximum(9999)
                    self.quantity_input.setValue(1)
                    self.quantity_input.setStyleSheet("""
                        QSpinBox {
                            padding: 5px;
                            border: none;
                            border-bottom: 1px solid #ccc;
                            min-width: 80px;
                            background: transparent;
                        }
                        QSpinBox::up-button, QSpinBox::down-button {
                            width: 16px;
                            border: none;
                            background: transparent;
                        }
                        QSpinBox:focus {
                            border-bottom: 2px solid #2196f3;
                        }
                    """)

                    container_layout.addWidget(quantity_label)
                    container_layout.addWidget(self.quantity_input)
                    container_layout.addStretch()

                    quantity_layout.addWidget(container)
                    quantity_layout.addStretch()

                    # Insert quantity widget above table
                    table_parent_layout = self.ui.dimtable.parent().layout()
                    table_index = table_parent_layout.indexOf(self.ui.dimtable)
                    table_parent_layout.insertWidget(table_index, quantity_widget)
                else:
                    # For admin users, remove any existing quantity widget
                    table_parent_layout = self.ui.dimtable.parent().layout()
                    for i in reversed(range(table_parent_layout.count())):
                        item = table_parent_layout.itemAt(i)
                        widget = item.widget() if item is not None else None
                        if widget and isinstance(widget, QWidget) and widget.findChild(QLabel, None) and widget.findChild(QLabel, None).text().startswith("Quantity:"):
                            table_parent_layout.removeWidget(widget)
                            widget.deleteLater()

                # Set correct column count for operator view
                base_headers = ["Sl No.", "Zone", "Actual", "+Tol", "-Tol", "Dimension Type", "Instrument"]
                operator_headers = ["Used Inst.", "M1", "M2", "M3", "Mean"]  # Quantity No. is handled separately
                headers = base_headers + operator_headers
                self.ui.dimtable.setColumnCount(len(headers))

                # Reload the PDF page
                if self.current_page:
                    # Create rotation matrix based on stored rotation
                    rotation_matrix = fitz.Matrix(2, 2).prerotate(self.rotation)
                    pix = self.current_page.get_pixmap(matrix=rotation_matrix)
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(img)
                    self.ui.pdf_view.scene().addPixmap(pixmap)
                    self.ui.pdf_view.setSceneRect(QRectF(pixmap.rect()))

                # Process each dimension
                for dimension in response:
                    row = self.ui.dimtable.rowCount()
                    self.ui.dimtable.insertRow(row)

                    # Set data in table (adjusted column indices)
                    self.ui.dimtable.setItem(row, 0, QTableWidgetItem(str(row + 1)))  # Serial number
                    self.ui.dimtable.setItem(row, 1, QTableWidgetItem(dimension.get('zone', 'N/A')))
                    self.ui.dimtable.setItem(row, 2, QTableWidgetItem(str(dimension.get('nominal', ''))))
                    self.ui.dimtable.setItem(row, 3, QTableWidgetItem(str(dimension.get('uppertol', 0))))
                    self.ui.dimtable.setItem(row, 4, QTableWidgetItem(str(dimension.get('lowertol', 0))))
                    self.ui.dimtable.setItem(row, 5, QTableWidgetItem(dimension.get('dimension_type', 'Unknown')))
                    self.ui.dimtable.setItem(row, 6, QTableWidgetItem(dimension.get('measured_instrument', 'Not Specified')))

                    # Add empty cells for operator columns (adjusted range)
                    for i in range(7, 12):  # Changed from 11 to 12 to include Mean column
                        item = QTableWidgetItem("")
                        item.setTextAlignment(Qt.AlignCenter)
                        self.ui.dimtable.setItem(row, i, item)

                    # Draw bounding box if bbox data exists
                    bbox = dimension.get('bbox', [])
                    print(f"\nRow {row} bbox data: {bbox}")  # Debug print

                    if bbox:
                        try:
                            # Convert bbox to list if it's not already
                            if not isinstance(bbox, list):
                                bbox = list(bbox)

                            # Ensure we have valid coordinates
                            if len(bbox) >= 8:
                                # Create points for polygon
                                points = []
                                for i in range(0, len(bbox), 2):
                                    x = float(bbox[i])
                                    y = float(bbox[i+1])
                                    points.append([x, y])

                                print(f"Converted points: {points}")  # Debug print

                                # Create and style the polygon
                                polygon = QGraphicsPolygonItem(QPolygonF([QPointF(p[0], p[1]) for p in points]))
                                pen = QPen(QColor(0, 255, 0))  # Green color
                                pen.setWidth(2)
                                pen.setCosmetic(True)
                                polygon.setPen(pen)
                                polygon.setZValue(1)

                                # Add polygon to scene
                                self.ui.pdf_view.scene().addItem(polygon)

                                # Store points data in table instead of raw bbox
                                nominal_item = self.ui.dimtable.item(row, 2)
                                if nominal_item:
                                    nominal_item.setData(Qt.UserRole, points)  # Store as points list
                                    print(f"Stored points data: {points}")  # Debug print

                        except Exception as bbox_error:
                            print(f"Error processing bbox for row {row}: {bbox_error}")
                            print(f"Original bbox data: {bbox}")

                print(f"Loaded {len(response)} dimensions from database")

                # Fit view to content
                self.ui.pdf_view.fitInView(self.ui.pdf_view.sceneRect(), Qt.KeepAspectRatio)

            else:
                print("No data returned from API")
                QMessageBox.warning(self, "Warning", "No dimension data found")

        except Exception as e:
            print(f"Error loading operator data: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load data: {str(e)}")

    def update_table_zones(self):
        """Update zones for all items in the table"""
        try:
            if self.current_image is None:
                return

            for row in range(self.ui.dimtable.rowCount()):
                # Get the bbox from the nominal column
                nominal_item = self.ui.dimtable.item(row, 2)
                if nominal_item and nominal_item.data(Qt.UserRole):
                    bbox = nominal_item.data(Qt.UserRole)

                    # Calculate midpoint and get zone
                    midpoint = ClusterDetector.calculate_merged_box_midpoint(bbox)
                    if midpoint:
                        zone = ZoneDetector.get_zone_for_midpoint(self.current_image, midpoint)
                        self.ui.dimtable.setItem(row, 1, QTableWidgetItem(zone))

        except Exception as e:
            print(f"Error updating table zones: {str(e)}")

    def update_highlight_box(self):
        """Update all bboxes and balloons based on current table rows"""
        try:
            # First clear any existing highlight
            self.clear_highlighted_bbox()

            # Remove all existing balloons
            balloon_items = []
            for item in self.ui.pdf_view.scene().items():
                if hasattr(item, 'balloon_data'):
                    balloon_items.append(item)

            for item in balloon_items:
                self.ui.pdf_view.scene().removeItem(item)

            # Clear balloon references
            self.balloon_circle = None
            self.balloon_triangle = None
            self.balloon_text = None
            self.current_highlight = None

            # Update serial numbers for all rows
            for row_idx in range(self.ui.dimtable.rowCount()):
                sl_no_item = QTableWidgetItem(str(row_idx + 1))
                sl_no_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row_idx, 0, sl_no_item)

            # Re-apply balloons for all rows using VisualizationEvents.highlight_bbox
            from events import VisualizationEvents
            for row_idx in range(self.ui.dimtable.rowCount()):
                VisualizationEvents.highlight_bbox(self, row_idx, 2)  # 2 is nominal column

            # Clear the final highlight
            self.clear_highlighted_bbox()

        except Exception as e:
            print(f"Error updating highlight boxes: {str(e)}")
            import traceback
            traceback.print_exc()






    def toggleBalloonVisibility(self):
        """Toggle the visibility of balloons and annotation circles in the scene"""
        try:
            # Toggle the state
            self.balloons_hidden = not self.balloons_hidden

            # Update the icon/action to show the current state
            if self.balloons_hidden:
                self.ui.actionHideStamp.setText("Show Annotations")
                self.ui.actionHideStamp.setToolTip("Show Annotation Circles")
            else:
                self.ui.actionHideStamp.setText("Hide Annotations")
                self.ui.actionHideStamp.setToolTip("Hide Annotation Circles")

            # Find all balloon items using the same logic as in HighlightManager.delete_balloons
            balloon_items = []

            # Look for all types of items that could be part of a balloon
            for item in self.ui.pdf_view.scene().items():
                # Check for balloon_data attribute
                if hasattr(item, 'balloon_data'):
                    balloon_items.append(item)
                    continue

                # Check for circle, triangle, and text items that might be balloons
                if isinstance(item, QtWidgets.QGraphicsEllipseItem):
                    # Circle part of balloon
                    balloon_items.append(item)
                elif isinstance(item, QtWidgets.QGraphicsPathItem):
                    # Path items used for balloon circles and triangles
                    balloon_items.append(item)
                elif isinstance(item, QtWidgets.QGraphicsPolygonItem):
                    # Check if it's a small triangle (likely part of a balloon)
                    polygon = item.polygon()
                    if len(polygon) == 3:  # Triangle has 3 points
                        # Calculate area of polygon
                        points = [(p.x(), p.y()) for p in polygon]
                        area = 0.5 * abs(sum(x0*y1 - x1*y0
                                            for ((x0, y0), (x1, y1)) in zip(points, points[1:] + [points[0]])))
                        if area < 500:  # Small triangle is likely a balloon pointer
                            balloon_items.append(item)
                elif isinstance(item, QtWidgets.QGraphicsTextItem):
                    # Check if it's a single digit or small number (likely a balloon number)
                    text = item.toPlainText()
                    if text.isdigit() and len(text) <= 3:
                        balloon_items.append(item)

            # Toggle visibility of all balloon items
            for item in balloon_items:
                item.setVisible(not self.balloons_hidden)

            # Show status message
            status_msg = f"{'Hidden' if self.balloons_hidden else 'Shown'} {len(balloon_items)} annotation items"
            self.ui.statusbar.showMessage(status_msg, 3000)  # Show for 3 seconds

        except Exception as e:
            print(f"Error toggling annotation visibility: {str(e)}")
            import traceback
            traceback.print_exc()


    def toggleFieldDivision(self):
        """Toggle the visibility of field division grid lines"""
        try:
            # Check if grid is currently visible
            grid_visible = hasattr(self, 'grid_visible') and self.grid_visible

            # Toggle the state
            self.grid_visible = not grid_visible

            # Update the icon/action to show the current state
            if self.grid_visible:
                self.ui.actionFieldDivision.setText("Hide Field Division")
                self.ui.actionFieldDivision.setToolTip("Hide Field Division Grid")
                self.ui.actionDisplayWholeDrawing.trigger()


                # Disable selection and stamping features
                self.ui.actionSelectionTool.setEnabled(False)
                self.ui.actionStamp.setEnabled(False)
                self.ui.actionCharacteristicsProperties.setEnabled(False)

                # Store current tool and switch to pan tool
                self.previous_tool = self.current_tool if hasattr(self, 'current_tool') else None
                self.ui.pdf_view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
                self.current_tool = 'pan'

            else:
                self.ui.actionFieldDivision.setText("Show Field Division")
                self.ui.actionFieldDivision.setToolTip("Show Field Division Grid")

                # Re-enable selection and stamping features
                self.ui.actionSelectionTool.setEnabled(True)
                self.ui.actionStamp.setEnabled(True)
                self.ui.actionCharacteristicsProperties.setEnabled(True)

                # Restore previous tool if available
                if hasattr(self, 'previous_tool') and self.previous_tool:
                    if self.previous_tool == 'selection':
                        self.ui.pdf_view.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
                        self.current_tool = 'selection'
                    else:
                        self.ui.pdf_view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
                        self.current_tool = self.previous_tool

            # Call the draw_field_division method
            from algorithms import ZoneDetector
            success = ZoneDetector.draw_field_division(self, self.grid_visible)


            # Make sure grid items are protected
            if self.grid_visible:
                for item in self.ui.pdf_view.scene().items():
                    if hasattr(item, 'is_grid_item') and item.is_grid_item:
                        # Make grid items not selectable and not movable
                        item.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                        item.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
                        # Set a high Z value to ensure grid stays on top
                        item.setZValue(100)

            # Show status message
            if success:
                status_msg = f"{'Shown' if self.grid_visible else 'Hidden'} field division grid"
            else:
                status_msg = "Failed to update field division grid"

            self.ui.statusbar.showMessage(status_msg, 3000)  # Show for 3 seconds

        except Exception as e:
            print(f"Error toggling field division: {str(e)}")
            import traceback
            traceback.print_exc()

    def toggleCharacteristicsProperties(self):
        """Toggle the properties editing mode for balloons"""
        try:
            # Toggle the properties mode state
            self.properties_mode_active = not getattr(self, 'properties_mode_active', False)

            if self.properties_mode_active:
                # Update UI to show active state
                self.ui.actionCharacteristicsProperties.setText("Exit Properties Mode")
                self.ui.actionCharacteristicsProperties.setToolTip("Exit Properties Mode")

                # Disable other tools
                self.ui.actionSelectionTool.setEnabled(False)
                self.ui.actionStamp.setEnabled(False)
                self.ui.actionFieldDivision.setEnabled(False)

                # Change cursor to indicate clickable items
                self.ui.pdf_view.viewport().setCursor(self.properties_cursor)

                # Store original event handler
                self.original_mouse_press = self.ui.pdf_view.mousePressEvent

                # Set custom event handler
                self.ui.pdf_view.mousePressEvent = self.propertiesMousePressEvent

                # Show status message
                self.ui.statusbar.showMessage("Properties Mode: Click on a balloon to edit its number", 5000)

            else:
                # Restore normal state
                self.ui.actionCharacteristicsProperties.setText("Properties")
                self.ui.actionCharacteristicsProperties.setToolTip("Edit Properties")

                # Re-enable other tools if user is admin/supervisor
                if self.is_admin_or_supervisor():
                    self.ui.actionSelectionTool.setEnabled(True)
                    self.ui.actionStamp.setEnabled(True)
                    self.ui.actionFieldDivision.setEnabled(True)

                # Restore cursor
                self.ui.pdf_view.viewport().setCursor(QtCore.Qt.ArrowCursor)

                # Restore original event handler
                if hasattr(self, 'original_mouse_press'):
                    self.ui.pdf_view.mousePressEvent = self.original_mouse_press

                # Show status message
                self.ui.statusbar.showMessage("Properties Mode: Disabled", 3000)

        except Exception as e:
            print(f"Error toggling properties mode: {str(e)}")
            import traceback
            traceback.print_exc()

    def propertiesMousePressEvent(self, event):
        """Handle mouse press events in properties mode"""
        try:
            if getattr(self, 'properties_mode_active', False):
                # Convert mouse position to scene coordinates
                scene_pos = self.ui.pdf_view.mapToScene(event.pos())

                # Get items at the clicked position
                items = self.ui.pdf_view.scene().items(scene_pos)

                # Find balloon items
                balloon_item = None
                balloon_data = None

                for item in items:
                    # Check if item has balloon_data attribute
                    if hasattr(item, 'balloon_data'):
                        balloon_item = item
                        balloon_data = item.balloon_data
                        break

                    # Check for various balloon item types
                    if (isinstance(item, QtWidgets.QGraphicsEllipseItem) or
                        isinstance(item, QtWidgets.QGraphicsPathItem) or
                        isinstance(item, QtWidgets.QGraphicsPolygonItem) or
                        (isinstance(item, QtWidgets.QGraphicsTextItem) and
                        item.toPlainText().isdigit() and len(item.toPlainText()) <= 3)):
                        balloon_item = item
                        # Try to find related items to get balloon_data
                        for related_item in self.ui.pdf_view.scene().items():
                            if (hasattr(related_item, 'balloon_data') and
                                related_item.balloon_data.get('group_id') == getattr(item, 'group_id', None)):
                                balloon_data = related_item.balloon_data
                                break
                        break

                if balloon_item:
                    # Get current row number from balloon data
                    current_row = None
                    if balloon_data and 'row' in balloon_data:
                        current_row = balloon_data['row']
                    else:
                        # Try to get row from text item
                        for item in items:
                            if isinstance(item, QtWidgets.QGraphicsTextItem):
                                try:
                                    current_row = int(item.toPlainText()) - 1  # Convert to 0-based index
                                    break
                                except ValueError:
                                    pass

                    if current_row is not None:
                        # Show input dialog for new balloon number
                        current_text = str(current_row + 1)  # Convert to 1-based for display

                        dialog = QtWidgets.QInputDialog(self)
                        dialog.resize(400, 200)  # Set wider and taller size
                        font = dialog.font()
                        font.setPointSize(12)
                        dialog.setFont(font)

                        new_text, ok = QtWidgets.QInputDialog.getText(
                            dialog,  # Use our pre-sized dialog
                            "Change Balloon Number",
                            "Enter new number (1-" + str(self.ui.dimtable.rowCount()) + "):",
                            QtWidgets.QLineEdit.Normal,
                            current_text
                        )


                        if ok and new_text:
                            try:
                                new_row = int(new_text) - 1  # Convert to 0-based index

                                # Validate row number
                                if 0 <= new_row < self.ui.dimtable.rowCount():
                                    # Use HighlightManager to change the balloon number
                                    from highlight_manager import HighlightManager
                                    success = self.change_balloon_number(current_row, new_row)

                                    if success:
                                        self.ui.statusbar.showMessage(f"Balloon number updated from {current_row+1} to {new_row+1}", 3000)
                                    else:
                                        self.ui.statusbar.showMessage("Failed to update balloon number", 3000)
                                else:
                                    self.ui.statusbar.showMessage(f"Invalid row number. Must be between 1 and {self.ui.dimtable.rowCount()}", 3000)
                            except ValueError:
                                self.ui.statusbar.showMessage("Invalid input. Please enter a number.", 3000)

                        # Don't propagate the event further
                        return
                    else:
                        self.ui.statusbar.showMessage("Could not determine balloon row number", 3000)

            # Call original handler for other cases
            if hasattr(self, 'original_mouse_press'):
                self.original_mouse_press(event)

        except Exception as e:
            print(f"Error handling properties mouse press: {str(e)}")
            import traceback
            traceback.print_exc()

            # Don't call original handler in exception handler to prevent recursion
            # Instead, just log the error and return
            self.ui.statusbar.showMessage(f"Error in properties mode: {str(e)}", 3000)


    def change_balloon_number(self, old_row, new_row):
        """ Change a balloon's number by swapping table data and updating visualizations """
        try:
            # Validate inputs
            if old_row == new_row:
                return True  # No change needed

            if old_row < 0 or new_row < 0 or old_row >= self.ui.dimtable.rowCount() or new_row >= self.ui.dimtable.rowCount():
                return False

            # Get the data from both rows
            def get_row_data(row_idx):
                data = {}
                for col in range(self.ui.dimtable.columnCount()):
                    item = self.ui.dimtable.item(row_idx, col)
                    if item:
                        data[col] = {
                            'text': item.text(),
                            'data': item.data(Qt.UserRole)
                        }
                return data

            old_row_data = get_row_data(old_row)
            new_row_data = get_row_data(new_row)

            # Swap data in the table
            for col in range(self.ui.dimtable.columnCount()):
                # Skip the serial number column (0)
                if col == 0:
                    continue

                # Update old row with new row data
                if col in new_row_data:
                    old_item = QTableWidgetItem(new_row_data[col]['text'])
                    if new_row_data[col]['data'] is not None:
                        old_item.setData(Qt.UserRole, new_row_data[col]['data'])
                    self.ui.dimtable.setItem(old_row, col, old_item)

                # Update new row with old row data
                if col in old_row_data:
                    new_item = QTableWidgetItem(old_row_data[col]['text'])
                    if old_row_data[col]['data'] is not None:
                        new_item.setData(Qt.UserRole, old_row_data[col]['data'])
                    self.ui.dimtable.setItem(new_row, col, new_item)

            # Update serial numbers for all rows
            for row_idx in range(self.ui.dimtable.rowCount()):
                sl_no_item = QTableWidgetItem(str(row_idx + 1))
                sl_no_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row_idx, 0, sl_no_item)

            # Find and remove all balloon items
            from highlight_manager import HighlightManager

            # Remove all existing balloons
            balloon_items = []
            for item in self.ui.pdf_view.scene().items():
                if hasattr(item, 'balloon_data'):
                    balloon_items.append(item)
                elif isinstance(item, QtWidgets.QGraphicsEllipseItem) or \
                    isinstance(item, QtWidgets.QGraphicsPathItem) or \
                    isinstance(item, QtWidgets.QGraphicsTextItem) and \
                    item.toPlainText().isdigit() and len(item.toPlainText()) <= 3:
                    balloon_items.append(item)

            for item in balloon_items:
                self.ui.pdf_view.scene().removeItem(item)

            # Recreate balloons for each row using the bounding box data from the table
            for row_idx in range(self.ui.dimtable.rowCount()):
                # Get the bbox data from the nominal column (column 2)
                item = self.ui.dimtable.item(row_idx, 2)
                if item and item.data(Qt.UserRole):
                    bbox = item.data(Qt.UserRole)

                    # Create new balloon with correct row number
                    balloon_items = HighlightManager.create_balloon(
                        self.ui.pdf_view,
                        bbox,
                        row_idx + 1  # Convert to 1-based for display
                    )

                    # Add balloon items to the scene
                    for balloon_item in balloon_items:
                        # Store row information in balloon_data
                        balloon_item.balloon_data = {'row': row_idx}
                        self.ui.pdf_view.scene().addItem(balloon_item)

            # Force scene update
            self.ui.pdf_view.scene().update()

            return True

        except Exception as e:
            print(f"Error changing balloon number: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def toggleCharacteristicsOverview(self):
        """Toggle the properties editing mode for balloons"""
        try:
            # Toggle the properties mode state
            self.properties_mode_active = not getattr(self, 'properties_mode_active', False)

            if self.properties_mode_active:
                # Update UI to show active state
                self.ui.actionCharacteristicsProperties.setText("Exit Overview Mode")
                self.ui.actionCharacteristicsProperties.setToolTip("Exit Overview Mode")

                # Disable other tools
                self.ui.actionSelectionTool.setEnabled(False)
                self.ui.actionStamp.setEnabled(False)
                self.ui.actionFieldDivision.setEnabled(False)
                self.ui.actionCharacteristicsProperties.setEnabled(False)

                # Set custom cursor for properties mode
                if not hasattr(self, 'properties_cursor'):
                    self.properties_cursor = QtCore.Qt.PointingHandCursor

                # Apply the cursor
                self.ui.pdf_view.viewport().setCursor(self.properties_cursor)

                # Store original event handler
                self.original_mouse_move = self.ui.pdf_view.mouseMoveEvent

                # Set custom event handlers
                self.ui.pdf_view.mouseMoveEvent = self.propertiesMouseMoveEvent

                # Show status message
                self.ui.statusbar.showMessage("Overview Mode: Hover on a balloon to overview it", 5000)

            else:
                # Restore normal state
                self.ui.actionCharacteristicsOverview.setText("Overview")
                self.ui.actionCharacteristicsOverview.setToolTip("Overview Properties")

                # Re-enable other tools if user is admin/supervisor
                if self.is_admin_or_supervisor():
                    self.ui.actionSelectionTool.setEnabled(True)
                    self.ui.actionStamp.setEnabled(True)
                    self.ui.actionFieldDivision.setEnabled(True)
                    self.ui.actionCharacteristicsProperties.setEnabled(True)

                # Restore cursor
                self.ui.pdf_view.viewport().setCursor(QtCore.Qt.ArrowCursor)

                if hasattr(self, 'original_mouse_move'):
                    self.ui.pdf_view.mouseMoveEvent = self.original_mouse_move

                # Hide any active tooltip
                if hasattr(self, 'balloon_tooltip') and self.balloon_tooltip:
                    self.balloon_tooltip.hide()
                    self.balloon_tooltip = None

                # Show status message
                self.ui.statusbar.showMessage("Properties Mode: Disabled", 3000)

        except Exception as e:
            print(f"Error toggling properties mode: {str(e)}")
            import traceback
            traceback.print_exc()

    def propertiesMouseMoveEvent(self, event):
        """Handle mouse move events in properties mode to show tooltips"""
        try:
            if getattr(self, 'properties_mode_active', False):
                # Convert mouse position to scene coordinates
                scene_pos = self.ui.pdf_view.mapToScene(event.pos())

                # Get items at the cursor position
                items = self.ui.pdf_view.scene().items(scene_pos)

                # Find balloon items
                balloon_item = None
                balloon_data = None
                balloon_row = None

                for item in items:
                    # Check if item has balloon_data attribute
                    if hasattr(item, 'balloon_data'):
                        balloon_item = item
                        balloon_data = item.balloon_data
                        # Get row from balloon_data - handle both formats
                        if 'row' in balloon_data:
                            balloon_row = balloon_data.get('row')
                        elif 'table_row' in balloon_data:
                            balloon_row = balloon_data.get('table_row') - 1  # Convert from 1-based to 0-based
                        break

                    # Check for text items that might be balloon numbers
                    if isinstance(item, QtWidgets.QGraphicsTextItem):
                        try:
                            number = int(item.toPlainText())
                            balloon_row = number - 1  # Convert from 1-based to 0-based
                            balloon_item = item
                            break
                        except ValueError:
                            pass

                    # Check for balloon components by type
                    if (isinstance(item, QtWidgets.QGraphicsEllipseItem) or
                        isinstance(item, QtWidgets.QGraphicsPathItem) or
                        isinstance(item, QtWidgets.QGraphicsPolygonItem)):
                        # Try to find related text item to get the row number
                        for related_item in self.ui.pdf_view.scene().items():
                            if isinstance(related_item, QtWidgets.QGraphicsTextItem):
                                try:
                                    if related_item.pos().x() >= item.boundingRect().left() and \
                                    related_item.pos().x() <= item.boundingRect().right() and \
                                    related_item.pos().y() >= item.boundingRect().top() and \
                                    related_item.pos().y() <= item.boundingRect().bottom():
                                        number = int(related_item.toPlainText())
                                        balloon_row = number - 1  # Convert from 1-based to 0-based
                                        balloon_item = item
                                        break
                                except (ValueError, AttributeError):
                                    pass

                # If we found a balloon, show tooltip with table data
                if balloon_item and balloon_row is not None:
                    # Validate row number is within range
                    if 0 <= balloon_row < self.ui.dimtable.rowCount():
                        # Create tooltip if it doesn't exist
                        if not hasattr(self, 'balloon_tooltip') or not self.balloon_tooltip:
                            self.balloon_tooltip = QtWidgets.QDialog(self)
                            self.balloon_tooltip.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
                            self.balloon_tooltip.setAttribute(Qt.WA_TranslucentBackground)
                            self.balloon_tooltip.setStyleSheet("""
                                QDialog {
                                    background-color: rgba(255, 255, 255, 240);
                                    border: 1px solid #aaa;
                                    border-radius: 5px;
                                }
                                QLabel {
                                    color: #333;
                                    font-size: 12px;
                                    padding: 2px;
                                }
                                QLabel.header {
                                    font-weight: bold;
                                    background-color: #f0f0f0;
                                    border-bottom: 1px solid #ddd;
                                }
                            """)

                            # Create layout
                            tooltip_layout = QtWidgets.QVBoxLayout(self.balloon_tooltip)
                            tooltip_layout.setContentsMargins(10, 10, 10, 10)
                            tooltip_layout.setSpacing(5)

                            # Create content widget
                            self.tooltip_content = QtWidgets.QWidget()
                            content_layout = QtWidgets.QVBoxLayout(self.tooltip_content)
                            content_layout.setContentsMargins(0, 0, 0, 0)
                            content_layout.setSpacing(5)

                            tooltip_layout.addWidget(self.tooltip_content)

                        # Update tooltip content
                        self.display_tooltip_content(balloon_row)

                        # Position tooltip near cursor but not under it
                        global_pos = self.ui.pdf_view.viewport().mapToGlobal(event.pos())
                        self.balloon_tooltip.move(global_pos + QtCore.QPoint(15, 15))

                        # Show tooltip
                        self.balloon_tooltip.show()

                        # Return without calling original handler
                        return
                    else:
                        print(f"Invalid balloon row: {balloon_row}, max rows: {self.ui.dimtable.rowCount()}")
                else:
                    # Hide tooltip if no balloon is under cursor
                    if hasattr(self, 'balloon_tooltip') and self.balloon_tooltip:
                        self.balloon_tooltip.hide()

            # Call original handler for other cases
            if hasattr(self, 'original_mouse_move'):
                self.original_mouse_move(event)

        except Exception as e:
            print(f"Error handling properties mouse move: {str(e)}")
            import traceback
            traceback.print_exc()

            # Call original handler if there's an error
            if hasattr(self, 'original_mouse_move'):
                self.original_mouse_move(event)

    def display_tooltip_content(self, row):
        """Update the tooltip content with table data for the given row"""
        try:
            # Clear existing content
            if hasattr(self, 'tooltip_content'):
                # Remove all widgets from layout
                layout = self.tooltip_content.layout()
                while layout.count():
                    item = layout.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.deleteLater()

            # Add title
            title = QtWidgets.QLabel(f"Balloon {row + 1} Details")
            title.setAlignment(Qt.AlignCenter)
            title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
            self.tooltip_content.layout().addWidget(title)

            # Create table for data
            data_table = QtWidgets.QTableWidget()
            data_table.setColumnCount(2)
            data_table.setHorizontalHeaderLabels(["Field", "Value"])
            data_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            data_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            data_table.verticalHeader().setVisible(False)
            data_table.setStyleSheet("""
                QTableWidget {
                    border: 1px solid;
                    background-color: #add8e6;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    padding: 5px;
                    border: 1px solid #ddd;
                    font-weight: bold;
                }
            """)

            # Get column headers from main table
            headers = []
            for col in range(1, self.ui.dimtable.columnCount()):  # Skip serial number column
                header = self.ui.dimtable.horizontalHeaderItem(col)
                if header:
                    headers.append(header.text())
                else:
                    headers.append(f"Column {col}")

            # Add data rows
            data_rows = []
            for col in range(1, self.ui.dimtable.columnCount()):  # Skip serial number column
                item = self.ui.dimtable.item(row, col)
                if item:
                    field = headers[col-1]
                    value = item.text()
                    data_rows.append((field, value))

            # Set row count and populate table
            data_table.setRowCount(len(data_rows))
            for i, (field, value) in enumerate(data_rows):
                data_table.setItem(i, 0, QTableWidgetItem(field))
                data_table.setItem(i, 1, QTableWidgetItem(value))

            # Add table to tooltip
            self.tooltip_content.layout().addWidget(data_table)

            # Resize tooltip to fit content
            self.balloon_tooltip.adjustSize()

        except Exception as e:
            print(f"Error updating tooltip content: {str(e)}")
            import traceback
            traceback.print_exc()


    def show_project_overview(self):
        """Display project overview information in a styled message box"""
        try:
            if not self.current_order_details:
                QMessageBox.warning(self, "No Data", "No order details available")
                return

            # Create styled HTML message
            message = f"""
            <html>
            <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 20px;
                    padding: 10px
                }}
                .login-info {{
                    display: inline-block;
                }}
                .welcome-text {{
                    font-size: 24px;
                    margin-bottom: 8px;
                }}
                .username {{
                    color: #0078D4;
                    font-weight: bold;
                    font-size: 26px;
                }}
                .role {{
                    color: #666;
                    margin-top: 5px;
                    font-size: 16px;
                }}
                .section-title {{
                    color: #333;
                    font-weight: bold;
                    margin: 15px 0;
                    padding-bottom: 5px;
                    border-bottom: 2px solid #0078D4;
                }}
                .details-table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin-top: 10px;
                    border: 2px solid #0078D4;
                }}
                .details-table td {{
                    padding: 8px;
                    border: 1px solid #ccc;
                }}
                .label {{
                    color: #666;
                    font-weight: bold;
                    width: 30%;
                    background-color: #f5f5f5;
                    border-right: 2px solid #0078D4;
                }}
                .value {{
                    color: #333;
                }}
            </style>
            </head>
            <body>
                <div class="header">
                    <div class="login-info">
                        <div class="welcome-text">Welcome <span class="username">{api.username}</span></div>
                        <div class="role">Logged in as: {api.user_role}</div>
                    </div>
                </div>
                <div class="section-title">Order Details</div>
                <table class="details-table">
            """

            # Get operation data if available
            operation_data = None
            operation_number = "N/A"
            operation_description = "N/A"
            work_center = "N/A"
            setup_time = "N/A"
            ideal_cycle_time = "N/A"

            if hasattr(self, 'operations_dialog'):
                if hasattr(self.operations_dialog, 'get_operation_number'):
                    operation_number = str(self.operations_dialog.get_operation_number() or 'N/A')

                if hasattr(self.operations_dialog, 'get_selected_operation'):
                    operation_data = self.operations_dialog.get_selected_operation()
                    if operation_data:
                        operation_description = operation_data.get('operation_description', 'N/A')
                        work_center = operation_data.get('work_center', 'N/A')
                        setup_time = str(operation_data.get('setup_time', 'N/A'))
                        ideal_cycle_time = str(operation_data.get('ideal_cycle_time', 'N/A'))

            # Add order details in table format
            details = [
                ("Part Number:", self.current_order_details.get('part_number', 'N/A')),
                ("Production Order:", self.current_order_details.get('production_order', 'N/A')),
                ("Required Quantity:", str(self.current_order_details.get('required_quantity', 'N/A'))),
                ("Part Description:", self.current_order_details.get('part_description', 'N/A')),
                ("Sale Order:", self.current_order_details.get('sale_order', 'N/A')),
                ("Total Operations:", str(self.current_order_details.get('total_operations', 'N/A')))
            ]

            # Add project details if available
            if 'project' in self.current_order_details:
                project = self.current_order_details['project']
                details.extend([
                    ("Project Name:", project.get('name', 'N/A')),
                    ("Priority:", str(project.get('priority', 'N/A'))),
                    ("Start Date:", project.get('start_date', 'N/A')),
                    ("End Date:", project.get('end_date', 'N/A'))
                ])

            # Add rows to table
            for label, value in details:
                message += f"""
                    <tr>
                        <td class="label">{label}</td>
                        <td class="value">{value}</td>
                    </tr>
                """

            # Add operation details section
            message += """
                </table>
                <div class="section-title">Operation Details</div>
                <table class="details-table">
            """

            # Add operation details
            operation_details = [
                ("Operation Number:", operation_number),
                ("Operation Description:", operation_description),
                ("Work Center:", work_center),
                ("Setup Time:", setup_time),
                ("Ideal Cycle Time:", ideal_cycle_time)
            ]

            # Add operation details rows
            for label, value in operation_details:
                message += f"""
                    <tr>
                        <td class="label">{label}</td>
                        <td class="value">{value}</td>
                    </tr>
                """

            # Close HTML
            message += """
                </table>
            </body>
            </html>
            """

            # Create custom dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Project Overview")
            dialog.setMinimumWidth(500)

            # Create layout
            layout = QtWidgets.QVBoxLayout(dialog)

            # Create QLabel with HTML content
            label = QtWidgets.QLabel()
            label.setTextFormat(Qt.RichText)
            label.setOpenExternalLinks(False)
            label.setText(message)
            label.setWordWrap(True)

            # Add label to layout
            layout.addWidget(label)

            # Add OK button
            button_box = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok
            )
            button_box.accepted.connect(dialog.accept)
            layout.addWidget(button_box)

            # Style the dialog
            dialog.setStyleSheet("""
                QDialog {
                    background-color: white;
                }
                QDialogButtonBox {
                    margin-top: 15px;
                }
                QPushButton {
                    background-color: #D1FFBD;
                    color: black;
                    border: none;
                    padding: 6px 20px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #106EBE;
                }
            """)

            # Show dialog
            dialog.exec_()

        except Exception as e:
            print(f"Error showing project overview: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to display project overview: {str(e)}")

    def show_bluetooth_dialog(self):
        """Show the Bluetooth connectivity dialog"""
        dialog = BluetoothDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            # Handle successful connection if needed
            pass

    def connect_to_device(self, row):
        """Connect to measurement device"""
        try:
            # Show device details dialog
            details_dialog = DeviceDetailsDialog(None, None, self)
            if details_dialog.exec_() == QtWidgets.QDialog.Accepted:
                # Get the selected instrument data
                instrument_data = details_dialog.get_selected_data()
                if instrument_data:
                    # Update the instrument name in the Instrument column
                    instrument_name = instrument_data['subcategory_name']
                    instrument_item = QTableWidgetItem(instrument_name)
                    instrument_item.setTextAlignment(Qt.AlignCenter)
                    self.ui.dimtable.setItem(row, 6, instrument_item)  # Instrument column
                    
                    # Add the instrument code with calibration date to the Used Inst. column
                    display_name = instrument_data.get('display_name', instrument_data['instrument_code'])
                    used_inst_item = QTableWidgetItem(display_name)
                    used_inst_item.setTextAlignment(Qt.AlignCenter)
                    self.ui.dimtable.setItem(row, 7, used_inst_item)  # Used Inst. column
                    
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to connect to device: {str(e)}")

    def handle_connection_status(self, status):
        """Handle connection status updates"""
        self.statusBar().showMessage(status)
        if status == "Connected to device":
            if hasattr(self, 'connecting_dialog'):
                self.connecting_dialog.close()
            self.statusBar().showMessage("Connected. Receiving measurements...")

    def set_row_color(self, row, is_valid):
        """Set row background color based on validity by applying a more direct approach"""
        try:
            # Use softer, more professional colors
            valid_color = QtGui.QColor(210, 242, 210)    # Softer green
            invalid_color = QtGui.QColor(255, 200, 200)  # Softer red
            color = valid_color if is_valid else invalid_color
            
            # Store row validation status for custom painting via data role
            for col in range(self.ui.dimtable.columnCount()):
                item = self.ui.dimtable.item(row, col)
                if not item:
                    item = QtWidgets.QTableWidgetItem()
                    self.ui.dimtable.setItem(row, col, item)
                
                # Set background color with Qt.BackgroundRole
                item.setData(Qt.BackgroundRole, color)
                
                # Set text color to ensure visibility
                text_color = QtGui.QColor(0, 0, 0)  # Black text
                item.setData(Qt.ForegroundRole, text_color)
                
                # Ensure text alignment is center
                item.setTextAlignment(Qt.AlignCenter)
            
            # Force update at multiple levels to ensure rendering
            self.ui.dimtable.viewport().update()
            self.ui.dimtable.update()
            
            # Debug output with more visibility
            status = "VALID (GREEN)" if is_valid else "INVALID (RED)"
            print(f"!!! APPLIED {status} COLOR TO ROW {row} !!!")
            
            return True
        except Exception as e:
            print(f"ERROR SETTING ROW COLOR: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def setup_custom_table_delegate(self):
        """Set up a custom delegate for the table to ensure background colors are visible"""
        try:
            # Custom delegate class definition
            class ColorDelegate(QtWidgets.QStyledItemDelegate):
                def paint(self, painter, option, index):
                    # Create a copy of the option to prevent modifying the original
                    opt = QtWidgets.QStyleOptionViewItem(option)
                    
                    # Get the background color from the item's data
                    bg_brush = index.data(Qt.BackgroundRole)
                    
                    # Check if the item is selected
                    is_selected = option.state & QtWidgets.QStyle.State_Selected
                    
                    if is_selected:
                        # Draw selection background with light blue color
                        selection_color = QtGui.QColor(227, 242, 253)  # Light blue
                        painter.fillRect(opt.rect, selection_color)
                        
                        # Draw focus rectangle for selected item
                        if option.state & QtWidgets.QStyle.State_HasFocus:
                            focus_pen = QtGui.QPen(QtGui.QColor("#4a90e2"))
                            focus_pen.setWidth(2)
                            painter.setPen(focus_pen)
                            focus_rect = opt.rect.adjusted(1, 1, -1, -1)
                            painter.drawRect(focus_rect)
                    elif bg_brush is not None:
                        # Fill with the validation color if not selected
                        painter.fillRect(opt.rect, bg_brush)
                    
                    # Draw grid lines for better table appearance
                    grid_pen = QtGui.QPen(QtGui.QColor("#d0d0d0"))
                    grid_pen.setWidth(1)
                    painter.setPen(grid_pen)
                    
                    # Draw bottom and right borders
                    painter.drawLine(opt.rect.bottomLeft(), opt.rect.bottomRight())
                    painter.drawLine(opt.rect.topRight(), opt.rect.bottomRight())
                    
                    # Draw the text with proper alignment
                    text = index.data(Qt.DisplayRole)
                    if text:
                        # Set text alignment (center)
                        text_rect = QtCore.QRectF(opt.rect)
                        # Add a small padding for text
                        text_rect.adjust(5, 2, -5, -2)
                        
                        # Get text color - use selection text color if selected
                        if is_selected:
                            text_color = QtGui.QColor(0, 0, 0)  # Black text for selected items
                        else:
                            # Use the foreground color from the item if available
                            text_color = index.data(Qt.ForegroundRole)
                            if not text_color:
                                text_color = QtGui.QColor(0, 0, 0)  # Default to black
                                
                        painter.setPen(QtGui.QPen(text_color))
                        # Draw text with center alignment
                        painter.drawText(text_rect, Qt.AlignCenter, str(text))
            
            # Create and set the delegate
            delegate = ColorDelegate()
            self.ui.dimtable.setItemDelegate(delegate)
            print("Custom color delegate applied to table with selection support")
            
            # Apply a clean, modern style to the table
            self.ui.dimtable.setStyleSheet("""
                QTableWidget {
                    background-color: white;
                    gridline-color: #d0d0d0;
                    border: 1px solid #d0d0d0;
                    border-radius: 4px;
                }
                QHeaderView::section {
                    background-color: #f5f5f5;
                    color: #333333;
                    padding: 6px;
                    border: 1px solid #d0d0d0;
                    font-weight: bold;
                }
            """)
            
            # Enable selection features
            self.ui.dimtable.setAlternatingRowColors(False)
            self.ui.dimtable.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.ui.dimtable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            
            return True
        except Exception as e:
            print(f"Error setting up custom delegate: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def update_measurement(self, row, column, value):
        """Update measurement value and check if mean is in range"""
        try:
            # Adjust column index for measurement values (M1, M2, M3)
            # Since we added Used Inst. column, we need to shift measurement columns by 1
            adjusted_column = column + 1

            # Create new item with center alignment
            item = QtWidgets.QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            
            # Set the item in the table
            self.ui.dimtable.setItem(row, adjusted_column, item)
            
            # Calculate mean after each measurement
            measurements = []
            for col in range(8, 11):  # M1, M2, M3 columns
                item = self.ui.dimtable.item(row, col)
                if item and item.text():
                    try:
                        measurements.append(float(item.text()))
                    except ValueError:
                        continue
            
            # Update mean if we have measurements
            if measurements:
                mean = sum(measurements) / len(measurements)
                mean_item = QtWidgets.QTableWidgetItem(f"{mean:.3f}")
                mean_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row, 11, mean_item)  # Mean column
                
                # Check tolerance and highlight the row
                self.check_and_highlight_row(row)
                
        except Exception as e:
            print(f"Error updating measurement: {str(e)}")
            import traceback
            traceback.print_exc()

    def handle_measurement_error(self, error_message):
        """Handle measurement errors"""
        QMessageBox.critical(self, "Measurement Error", error_message)
        self.stop_measurements()

    def stop_measurements(self):
        """Stop ongoing measurements"""
        if hasattr(self, 'measurement_thread') and self.measurement_thread.isRunning():
            self.measurement_thread.stop()
            self.measurement_thread.wait()

    def handle_cell_change(self, row, column):
        """Handle cell value changes and calculate mean"""
        try:
            # If mean column is directly edited, update validation immediately
            if column == 11:  # Mean column
                print("Mean column directly edited - checking values")
                self.check_and_highlight_row(row)
                return
                
            # Only process measurement columns (M1, M2, M3)
            if column not in [8, 9, 10]:  # Adjusted for the correct columns
                return
    
            # Recalculate mean when measurement values change
            measurements = []
            for col in range(8, 11):  # M1, M2, M3 columns
                item = self.ui.dimtable.item(row, col)
                if item and item.text():
                    try:
                        # Use safe_float for consistent handling of decimal separators
                        measurements.append(self.safe_float(item.text()))
                    except ValueError:
                        continue
            
            # Update mean if we have measurements
            if measurements:
                mean = sum(measurements) / len(measurements)
                mean_item = QtWidgets.QTableWidgetItem(f"{mean:.3f}")
                mean_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row, 11, mean_item)  # Mean column
                
                # Check tolerance and highlight the row
                self.check_and_highlight_row(row)
            
        except Exception as e:
            print(f"Error handling cell change: {str(e)}")
            import traceback
            traceback.print_exc()

    def check_and_highlight_row(self, row):
        """Check tolerance and highlight row based on mean value"""
        try:
            # Get nominal, upper and lower tolerance values
            nominal_item = self.ui.dimtable.item(row, 2)  # Nominal column
            upper_tol_item = self.ui.dimtable.item(row, 3)  # Upper tolerance column
            lower_tol_item = self.ui.dimtable.item(row, 4)  # Lower tolerance column
            mean_item = self.ui.dimtable.item(row, 11)  # Mean column
            
            # Check if all required items exist and have values
            if not all([nominal_item, upper_tol_item, lower_tol_item]) or \
               not all([item.text() for item in [nominal_item, upper_tol_item, lower_tol_item]]):
                # Missing basic dimension data
                return
                
            if not mean_item or not mean_item.text():
                # If mean is not calculated yet, try to calculate it now
                measurements = []
                for col in range(8, 11):  # M1, M2, M3 columns
                    item = self.ui.dimtable.item(row, col)
                    if item and item.text():
                        try:
                            # Handle both decimal separators
                            measurements.append(self.safe_float(item.text()))
                        except ValueError:
                            continue
                
                # Only proceed if we have measurements
                if not measurements:
                    return
                    
                # Calculate and set mean
                mean = sum(measurements) / len(measurements)
                mean_item = QtWidgets.QTableWidgetItem(f"{mean:.3f}")
                mean_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row, 11, mean_item)  # Mean column
            
            try:
                # Convert values to float with comma/dot handling
                nominal = self.safe_float(nominal_item.text())
                upper_tol = self.safe_float(upper_tol_item.text())
                lower_tol = self.safe_float(lower_tol_item.text()) 
                mean = self.safe_float(mean_item.text())
                
                # Calculate tolerance limits
                upper_limit = nominal + upper_tol
                lower_limit = nominal + lower_tol  # lower_tol is already negative
                
                # Check if mean is within tolerance range
                is_in_range = lower_limit <= mean <= upper_limit
                
                # Set the row color using our helper function
                self.set_row_color(row, is_in_range)
                
                # Print debug info
                print(f"Row {row} validation: Nominal={nominal}, Tol=+{upper_tol}/{lower_tol}, Mean={mean}")
                print(f"Limits: {lower_limit} <= {mean} <= {upper_limit}, Valid: {is_in_range}")
            
            except ValueError as e:
                print(f"Error converting values: {str(e)}")
        
        except Exception as e:
            print(f"Error checking tolerance range: {str(e)}")
            import traceback
            traceback.print_exc()

    def safe_float(self, text):
        """Safely convert text to float, handling comma decimal separators"""
        try:
            # Replace comma with dot for decimal separator compatibility
            return float(str(text).replace(',', '.'))
        except (ValueError, TypeError):
            print(f"Error converting '{text}' to float")
            raise ValueError(f"Invalid number format: {text}")

# Add MeasurementThread class


if __name__ == "__main__":
    import sys
import time
import asyncio
from bleak import BleakClient
from PyQt5.QtCore import QThread, pyqtSignal

# Apply nest_asyncio to allow running asyncio in a non-async context
nest_asyncio.apply()

# BluetoothMonitorThread class for handling Bluetooth connections using the exact code provided
class BluetoothMonitorThread(QThread):
    connection_status = pyqtSignal(bool, str)  # Status, message
    data_received = pyqtSignal(str)  # Data received from device
    
    def __init__(self, address, parent=None):
        super().__init__(parent)
        self.address = address
        self.stopped = False
        self.loop = asyncio.new_event_loop()
    
    def run(self):
        """Run the Bluetooth connection thread"""
        try:
            # Set the event loop
            asyncio.set_event_loop(self.loop)
            
            # Run the connection task
            self.loop.run_until_complete(self.monitor_data(self.address))
            
        except ImportError as e:
            self.connection_status.emit(False, f"Required library not installed: {str(e)}. Please install 'bleak'.")
        except Exception as e:
            self.connection_status.emit(False, f"Error connecting to device: {str(e)}")
    
    async def notification_handler(self, sender, data):
        """Handle notifications from the Bluetooth device"""
        try:
            decoded_data = data.decode('utf-8')
            print(f"{sender}, Measured value: {decoded_data}")
            self.data_received.emit(decoded_data)
        except Exception as e:
            print(f"Error in notification handler: {str(e)}")
    
    async def monitor_data(self, address):
        """Connect to the device and monitor data"""
        try:
            # Emit connecting status
            self.connection_status.emit(True, f"Connecting to {address}...")
            
            async with BleakClient(address) as client:
                # Emit connected status
                self.connection_status.emit(True, f"Connected to {address}")
                
                # Start notification for the characteristic
                characteristic_uuid = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
                await client.start_notify(characteristic_uuid, self.notification_handler)
                
                try:
                    # Keep the connection alive until stopped
                    while not self.stopped:
                        # The loop will be triggered when a notification is received
                        await asyncio.sleep(1)  # Adjust the sleep interval as needed
                        
                except Exception as e:
                    self.connection_status.emit(False, f"Error monitoring data: {str(e)}")
                finally:
                    # Stop notification before disconnecting
                    await client.stop_notify(characteristic_uuid)
                    
        except Exception as e:
            self.connection_status.emit(False, f"Error: {str(e)}")
    
    def stop(self):
        """Stop the Bluetooth connection thread"""
        self.stopped = True

# Initialize the application
app = QtWidgets.QApplication(sys.argv)
window = MainWindow()  # Create instance of our MainWindow class
window.show()
sys.exit(app.exec_())
