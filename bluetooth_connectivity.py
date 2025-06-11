from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QPushButton, QLabel, 
    QHBoxLayout, QLineEdit, QWidget, QAbstractItemView,
    QShortcut, QStyle, QMessageBox, QListWidgetItem, QComboBox,
    QGroupBox, QFormLayout
)

import requests

# Import API handler for getting instrument data
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from api_endpoints import api, APIEndpoints

class BluetoothScannerThread(QThread):
    devices_found = pyqtSignal(list)  # Signal emitted when devices are found
    error_occurred = pyqtSignal(str)  # Signal emitted when an error occurs
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stopped = False
    
    def run(self):
        try:
            # Import required libraries here to avoid import errors in the main thread
            import asyncio
            from bleak import BleakScanner
            
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the scan in this thread's event loop
            devices = loop.run_until_complete(BleakScanner.discover())
            
            # Emit the result signal with the found devices
            if not self.stopped:
                self.devices_found.emit(devices)
                
        except Exception as e:
            # Emit error signal if something goes wrong
            if not self.stopped:
                self.error_occurred.emit(str(e))
    
    def stop(self):
        self.stopped = True

class BluetoothConnectivityDialog(QDialog):
    def __init__(self, parent=None, instrument_code=None):
        super().__init__(parent)
        self.setWindowTitle("Bluetooth Connectivity")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        self.selected_device = None
        self.selected_instrument = None
        self.instruments = []
        self.bluetooth_devices = []
        self.instrument_code_to_select = instrument_code  # Store the instrument code to select
        
        self.setup_ui()
        self.load_instruments()
        
    def setup_ui(self):
        """Setup the UI elements"""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Title label
        title_label = QLabel("Bluetooth Connectivity")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        main_layout.addWidget(title_label)
        
        # Split layout for instruments and devices
        split_layout = QHBoxLayout()
        split_layout.setSpacing(20)
        
        # === INSTRUMENTS SECTION (LEFT) ===
        instruments_group = QGroupBox("Measurement Instruments")
        instruments_group.setMinimumWidth(350)
        instruments_layout = QVBoxLayout(instruments_group)
        instruments_layout.setContentsMargins(10, 15, 10, 10)
        instruments_layout.setSpacing(10)
        
        # Instrument search box
        instrument_search_layout = QHBoxLayout()
        instrument_search_icon = QLabel()
        instrument_search_icon.setPixmap(self.style().standardPixmap(QStyle.SP_FileDialogContentsView).scaled(14, 14))
        instrument_search_layout.addWidget(instrument_search_icon)
        
        self.instrument_search_box = QLineEdit()
        self.instrument_search_box.setPlaceholderText("Search instruments...")
        self.instrument_search_box.setStyleSheet("""
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
        self.instrument_search_box.textChanged.connect(self.filter_instruments)
        instrument_search_layout.addWidget(self.instrument_search_box)
        instruments_layout.addLayout(instrument_search_layout)
        
        # Instrument count label
        self.instrument_count_label = QLabel("Loading...")
        self.instrument_count_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 12px;
                padding: 2px 8px;
            }
        """)
        instruments_layout.addWidget(self.instrument_count_label)
        
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
        self.instrument_list.itemSelectionChanged.connect(self.on_instrument_selected)
        instruments_layout.addWidget(self.instrument_list)
        
        # === BLUETOOTH DEVICES SECTION (RIGHT) ===
        devices_group = QGroupBox("Bluetooth Devices")
        devices_group.setMinimumWidth(350)
        devices_layout = QVBoxLayout(devices_group)
        devices_layout.setContentsMargins(10, 15, 10, 10)
        devices_layout.setSpacing(10)
        
        # Device search box
        device_search_layout = QHBoxLayout()
        device_search_icon = QLabel()
        device_search_icon.setPixmap(self.style().standardPixmap(QStyle.SP_FileDialogContentsView).scaled(14, 14))
        device_search_layout.addWidget(device_search_icon)
        
        self.device_search_box = QLineEdit()
        self.device_search_box.setPlaceholderText("Search devices...")
        self.device_search_box.setStyleSheet(self.instrument_search_box.styleSheet())
        self.device_search_box.textChanged.connect(self.filter_devices)
        device_search_layout.addWidget(self.device_search_box)
        devices_layout.addLayout(device_search_layout)
        
        # Refresh button
        self.refresh_button = QPushButton("Scan for Devices")
        self.refresh_button.setStyleSheet("""
            QPushButton {
                padding: 6px 16px;
                background-color: #f8f9fa;
                color: #2c3e50;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
        """)
        self.refresh_button.clicked.connect(self.discover_bluetooth_devices)
        devices_layout.addWidget(self.refresh_button)
        
        # Loading label
        self.loading_label = QLabel("Click 'Scan for Devices' to start scanning")
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
        devices_layout.addWidget(self.loading_label)
        
        # Device count label
        self.device_count_label = QLabel("No devices scanned yet")
        self.device_count_label.setStyleSheet(self.instrument_count_label.styleSheet())
        devices_layout.addWidget(self.device_count_label)
        
        # Devices list
        self.device_list = QListWidget()
        self.device_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.device_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.device_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.device_list.setStyleSheet(self.instrument_list.styleSheet())
        self.device_list.itemSelectionChanged.connect(self.on_device_selected)
        devices_layout.addWidget(self.device_list)
        
        # Add both sections to the split layout
        split_layout.addWidget(instruments_group)
        split_layout.addWidget(devices_group)
        main_layout.addLayout(split_layout)
        
        # === ASSOCIATION SECTION (BOTTOM) ===
        association_group = QGroupBox("Associate Bluetooth Device with Instrument")
        association_layout = QVBoxLayout(association_group)
        
        # Form for displaying selected items
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(20)
        
        # Selected instrument display
        self.selected_instrument_label = QLabel("None selected")
        self.selected_instrument_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        form_layout.addRow("Selected Instrument:", self.selected_instrument_label)
        
        # Selected device display
        self.selected_device_label = QLabel("None selected")
        self.selected_device_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        form_layout.addRow("Selected Bluetooth Device:", self.selected_device_label)
        
        association_layout.addLayout(form_layout)
        
        # Status message
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 12px;
                padding: 5px;
            }
        """)
        association_layout.addWidget(self.status_label)
        
        main_layout.addWidget(association_group)
        
        # Button container
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        
        self.cancel_button = QPushButton("Cancel", self)
        self.associate_button = QPushButton("Associate Device", self)
        
        button_style = """
            QPushButton {
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 13px;
                min-width: 120px;
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
        
        self.associate_button.setStyleSheet(button_style + """
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #f5f5f5;
            }
        """)
        self.associate_button.setEnabled(False)
        
        self.cancel_button.clicked.connect(self.reject)
        self.associate_button.clicked.connect(self.associate_device)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.associate_button)
        main_layout.addWidget(button_container)
        
        # Keyboard shortcuts
        QShortcut(QKeySequence("Escape"), self, self.reject)
    
    def create_device_widget(self, device):
        """Create a custom widget for device list item"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Device info
        info_layout = QVBoxLayout()
        
        # Device name and address
        name = device.name if device.name else "Unknown Device"
        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        info_layout.addWidget(name_label)
        
        # Device address
        address_label = QLabel(device.address)
        address_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        info_layout.addWidget(address_label)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # Signal strength indicator if available
        # Handle both old and new Bleak API versions
        rssi = None
        if hasattr(device, 'advertisement_data') and device.advertisement_data and hasattr(device.advertisement_data, 'rssi'):
            # New Bleak API
            rssi = device.advertisement_data.rssi
        elif hasattr(device, 'rssi'):
            # Legacy support for older Bleak versions
            rssi = device.rssi
            
        if rssi is not None:
            strength_label = QLabel()
            
            # Set icon based on signal strength
            if rssi > -60:
                strength_text = "Strong"
                strength_color = "#27ae60"
            elif rssi > -80:
                strength_text = "Medium"
                strength_color = "#f39c12"
            else:
                strength_text = "Weak"
                strength_color = "#e74c3c"
                
            strength_label.setText(f"<span style='color:{strength_color};'>{strength_text}</span>")
            layout.addWidget(strength_label)
        
        # Store the device in the widget
        widget.setProperty("device", device)
        
        return widget
    
    def load_instruments(self):
        """Load instruments from the API"""
        try:
            # Show loading indicator
            self.instrument_count_label.setText("Loading instruments...")
            self.instrument_list.clear()
            
            # Use fixed category ID for Instruments
            instruments_category_id = 2  # Category ID for instruments

            # Get subcategories for this category ID
            subcategories = api.get_inventory_subcategories(instruments_category_id)
            if not subcategories:
                raise Exception(f"No subcategories found for category ID {instruments_category_id}")

            self.instruments = []
            total_items = 0
            
            # For each subcategory with category_id 2, get its items
            for subcategory in subcategories:
                if subcategory.get('category_id') == instruments_category_id:
                    subcategory_id = subcategory['id']
                    subcategory_name = subcategory['name']
                    
                    # Get all items for this subcategory
                    items = api.get_inventory_items(subcategory_id)
                    if items:
                        for item in items:
                            # Extract instrument code from dynamic_data
                            dynamic_data = item.get('dynamic_data', {})
                            instrument_code = dynamic_data.get('Instrument code', '')
                            item_code = item.get('item_code', '')
                            
                            # Check if a Bluetooth address exists in dynamic_data
                            bluetooth_address = dynamic_data.get('Bluetooth Address', None)
                            
                            # Create instrument data from the item
                            instrument_data = {
                                'name': instrument_code or item_code or 'Instrument',  # Use instrument code as name
                                'id': item.get('id'),
                                'subcategory_id': subcategory_id,
                                'subcategory_name': subcategory_name,
                                'instrument_code': instrument_code,
                                'item_code': item_code,
                                'size': dynamic_data.get('Size', ''),
                                'equipment_no': dynamic_data.get('Equipment No.', ''),
                                'location': dynamic_data.get('Location', ''),
                                'bluetooth_address': bluetooth_address  # Use existing Bluetooth address if available
                            }
                            
                            self.instruments.append(instrument_data)
                            
                            # Create item widget
                            list_item = QListWidgetItem()
                            widget = self.create_instrument_widget(instrument_data)
                            list_item.setSizeHint(widget.sizeHint())
                            self.instrument_list.addItem(list_item)
                            self.instrument_list.setItemWidget(list_item, widget)
                            total_items += 1

            # Update count label
            self.instrument_count_label.setText(f"Total: {total_items}")
            
            # Pre-select the instrument if instrument_code_to_select is provided
            if self.instrument_code_to_select:
                for i in range(self.instrument_list.count()):
                    list_item = self.instrument_list.item(i)
                    widget = self.instrument_list.itemWidget(list_item)
                    if widget and hasattr(widget, 'instrument_data'):
                        instrument_code = widget.instrument_data.get('instrument_code', '')
                        if instrument_code == self.instrument_code_to_select:
                            self.instrument_list.setCurrentItem(list_item)
                            break
            
            if total_items == 0:
                self.instrument_count_label.setText("No instruments found")

        except Exception as e:
            error_msg = f"Error loading instruments: {str(e)}"
            self.instrument_count_label.setText(error_msg)
            print(error_msg)
    
    def create_instrument_widget(self, instrument_data):
        """Create a custom widget for instrument list item"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Instrument info
        info_layout = QVBoxLayout()
        
        # Create header with instrument code as the main identifier
        header_layout = QHBoxLayout()
        
        # Get instrument details
        instrument_code = instrument_data.get('instrument_code', '')
        item_code = instrument_data.get('item_code', '')
        subcategory_name = instrument_data.get('subcategory_name', '')
        
        # Create a clear display that shows both name and code
        if instrument_code:
            # Format as 'Subcategory Name (Code)'
            display_text = f"{subcategory_name} ({instrument_code})" if subcategory_name else instrument_code
            code_label = QLabel(display_text)
            code_label.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 12px;")
            header_layout.addWidget(code_label)
            
            # Print debug info
            print(f"Displaying instrument: {display_text} with code {instrument_code}")
        else:
            # Fallback to item code if no instrument code
            display_text = f"{subcategory_name} ({item_code})" if subcategory_name and item_code else (item_code or 'Unknown')
            code_label = QLabel(display_text)
            code_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
            header_layout.addWidget(code_label)
            
            # Print debug info
            print(f"Displaying instrument with item code: {display_text}")
            
        header_layout.addStretch()
            
        info_layout.addLayout(header_layout)
        
        # Show additional details if available
        details = []
        if instrument_data.get('size'):
            details.append(f"Size: {instrument_data['size']}")
        if instrument_data.get('equipment_no'):
            details.append(f"Equip#: {instrument_data['equipment_no']}")
        if instrument_data.get('location'):
            details.append(f"Loc: {instrument_data['location']}")
            
        if details:
            details_label = QLabel(" | ".join(details))
            details_label.setStyleSheet("color: #34495e; font-size: 11px;")
            info_layout.addWidget(details_label)
        
        # Show subcategory info
        if instrument_data.get('subcategory_name'):
            category_label = QLabel(f"Category: {instrument_data['subcategory_name']}")
            category_label.setStyleSheet("color: #7f8c8d; font-size: 11px; font-style: italic;")
            info_layout.addWidget(category_label)
        
        # Show Bluetooth address if available
        if instrument_data.get('bluetooth_address'):
            address_label = QLabel(f"Bluetooth: {instrument_data['bluetooth_address']}")
            address_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            info_layout.addWidget(address_label)
        else:
            address_label = QLabel("No Bluetooth connection")
            address_label.setStyleSheet("color: #7f8c8d; font-style: italic; font-size: 11px;")
            info_layout.addWidget(address_label)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # Store the data in the widget
        widget.setProperty("instrument_data", instrument_data)
        
        return widget
    
    def filter_instruments(self, text):
        """Filter instruments based on search text"""
        search_text = self.instrument_search_box.text().strip().lower()
        visible_count = 0
        total_count = self.instrument_list.count()
        
        for i in range(self.instrument_list.count()):
            item = self.instrument_list.item(i)
            widget = self.instrument_list.itemWidget(item)
            if widget:
                instrument_data = widget.property("instrument_data")
                if instrument_data:
                    # Search in multiple fields
                    searchable_fields = [
                        instrument_data.get('name', '').lower(),
                        instrument_data.get('subcategory_name', '').lower(),
                        instrument_data.get('instrument_code', '').lower(),
                        instrument_data.get('description', '').lower(),
                        instrument_data.get('serial_number', '').lower()
                    ]
                    
                    # Match if any field contains the search text
                    search_match = not search_text or any(search_text in field for field in searchable_fields)
                    
                    # Show/hide based on matches
                    item.setHidden(not search_match)
                    if not item.isHidden():
                        visible_count += 1
        
        # Update count label based on filter state
        if not search_text:
            self.instrument_count_label.setText(f"Total: {total_count}")
        else:
            self.instrument_count_label.setText(f"Showing {visible_count} of {total_count}")
    
    def filter_devices(self, text):
        """Filter devices based on search text"""
        search_text = self.device_search_box.text().strip().lower()
        visible_count = 0
        total_count = self.device_list.count()
        
        for i in range(self.device_list.count()):
            item = self.device_list.item(i)
            widget = self.device_list.itemWidget(item)
            if widget:
                device = widget.property("device")
                if device:
                    # Match by device name or address
                    device_name = device.name.lower() if device.name else ""
                    device_address = device.address.lower()
                    
                    search_match = (not search_text or 
                                  search_text in device_name or
                                  search_text in device_address)
                    
                    # Show/hide based on matches
                    item.setHidden(not search_match)
                    if not item.isHidden():
                        visible_count += 1
        
        # Update count label based on filter state
        if not search_text:
            self.device_count_label.setText(f"Total: {total_count}")
        else:
            self.device_count_label.setText(f"Showing {visible_count} of {total_count}")
    
    def on_instrument_selected(self):
        """Handle instrument selection"""
        selected_items = self.instrument_list.selectedItems()
        if selected_items:
            item = selected_items[0]
            widget = self.instrument_list.itemWidget(item)
            if widget:
                instrument_data = widget.property("instrument_data")
                if instrument_data:
                    self.selected_instrument = instrument_data
                    
                    # Update the selected instrument label
                    category_name = instrument_data['name']
                    if " - " in category_name:
                        category_name = category_name.split(" - ")[0]
                    
                    self.selected_instrument_label.setText(category_name)
                    
                    # Enable the associate button if both instrument and device are selected
                    self.associate_button.setEnabled(self.selected_device is not None)
        else:
            self.selected_instrument = None
            self.selected_instrument_label.setText("None selected")
            self.associate_button.setEnabled(False)
    
    def on_device_selected(self):
        """Handle device selection"""
        selected_items = self.device_list.selectedItems()
        if selected_items:
            item = selected_items[0]
            widget = self.device_list.itemWidget(item)
            if widget:
                device = widget.property("device")
                if device:
                    self.selected_device = device
                    
                    # Update the selected device label
                    device_name = device.name if device.name else "Unknown Device"
                    self.selected_device_label.setText(f"{device_name} ({device.address})")
                    
                    # Enable the associate button if both instrument and device are selected
                    self.associate_button.setEnabled(self.selected_instrument is not None)
        else:
            self.selected_device = None
            self.selected_device_label.setText("None selected")
            self.associate_button.setEnabled(False)
    
    def discover_bluetooth_devices(self):
        """Discover Bluetooth devices using Bleak"""
        try:
            # Clear the list
            self.device_list.clear()
            
            # Show loading indicator
            self.loading_label.setText("Scanning for Bluetooth devices...")
            self.loading_label.show()
            self.device_list.setVisible(False)
            self.status_label.setText("")
            
            # Import required libraries
            from PyQt5.QtCore import QTimer
            
            # Create a scanner thread to avoid blocking the GUI
            self.scanner_thread = BluetoothScannerThread(self)
            self.scanner_thread.devices_found.connect(self.on_devices_found)
            self.scanner_thread.error_occurred.connect(self.on_scan_error)
            self.scanner_thread.start()
            
            # Set a timeout for the scan (10 seconds)
            QTimer.singleShot(10000, self.check_scan_timeout)
        
        except ImportError as e:
            # Handle missing dependencies
            self.loading_label.setText("Error: Required libraries not installed. Please install 'bleak'.")
            self.status_label.setText(f"Error: {str(e)}")
            print(f"Error: Missing dependencies - {str(e)}")
        
        except Exception as e:
            # Handle other errors
            self.loading_label.setText(f"Error scanning for devices: {str(e)}")
            self.status_label.setText(f"Error: {str(e)}")
            print(f"Error discovering Bluetooth devices: {str(e)}")
            
    def on_devices_found(self, devices):
        """Handle found devices from the scanner thread"""
        # Import needed for QListWidgetItem
        from PyQt5.QtWidgets import QListWidgetItem
        
        # Add devices to the list
        if devices:
            for device in devices:
                item = QListWidgetItem()
                widget = self.create_device_widget(device)
                item.setSizeHint(widget.sizeHint())
                self.device_list.addItem(item)
                self.device_list.setItemWidget(item, widget)
            
            # Show list and hide loading
            self.loading_label.hide()
            self.device_list.setVisible(True)
            
            # Update count label
            total_count = len(devices)
            # Use device_count_label instead of count_label
            self.device_count_label.setText(f"Total: {total_count}")
            self.status_label.setText(f"Found {total_count} Bluetooth devices")
        else:
            # No devices found
            self.loading_label.setText("No Bluetooth devices found. Click Refresh to scan again.")
            self.device_count_label.setText("Total: 0")
            self.status_label.setText("No devices found")
    
    def on_scan_error(self, error_message):
        """Handle errors from the scanner thread"""
        self.loading_label.setText(f"Error scanning for devices: {error_message}")
        self.status_label.setText(f"Error: {error_message}")
        print(f"Error discovering Bluetooth devices: {error_message}")
        
    def check_scan_timeout(self):
        """Check if the scan has timed out"""
        # If the thread is still running and we haven't found any devices yet
        if hasattr(self, 'scanner_thread') and self.scanner_thread.isRunning() and self.device_list.count() == 0:
            # Stop the thread
            self.scanner_thread.stop()
            self.scanner_thread.wait()
            
            # Update UI
            self.loading_label.setText("Scan timed out. Click Refresh to try again.")
            self.status_label.setText("Scan timed out")
            
    def closeEvent(self, event):
        """Handle dialog close event"""
        # Make sure to stop the scanner thread if it's running
        if hasattr(self, 'scanner_thread') and self.scanner_thread.isRunning():
            self.scanner_thread.stop()
            self.scanner_thread.wait()
        event.accept()
    
    def get_selected_device(self):
        """Get the selected device"""
        selected = self.device_list.selectedItems()
        if not selected:
            return None
        
        item = selected[0]
        widget = self.device_list.itemWidget(item)
        if widget:
            return widget.property("device")
        
        return None
    
    def associate_device(self):
        """Associate the selected Bluetooth device with the selected instrument"""
        if not self.selected_instrument or not self.selected_device:
            QtWidgets.QMessageBox.warning(
                self,
                "Selection Required",
                "Please select both an instrument and a Bluetooth device."
            )
            return
        
        print("=== Starting device association ===")
        print(f"Selected instrument: {self.selected_instrument}")
        print(f"Selected device: {self.selected_device.address}")
        
        try:
            # Update the instrument data with the Bluetooth address
            self.selected_instrument['bluetooth_address'] = self.selected_device.address
            
            # Get the item_code, item_id, and instrument_code from the selected instrument
            item_code = self.selected_instrument.get('item_code')
            item_id = self.selected_instrument.get('id')
            subcategory_id = self.selected_instrument.get('subcategory_id')
            instrument_code = self.selected_instrument.get('instrument_code')
            
            print(f"Selected instrument details: code={item_code}, id={item_id}, instrument_code={instrument_code}")
            
            # Prepare dynamic_data with Bluetooth address
            dynamic_data = {}
            
            # If we have the original dynamic_data, use it as a base
            for i in range(self.instrument_list.count()):
                item = self.instrument_list.item(i)
                widget = self.instrument_list.itemWidget(item)
                if widget:
                    instrument_data = widget.property("instrument_data")
                    if instrument_data and instrument_data['id'] == item_id:
                        print(f"Found matching instrument: {instrument_data}")
                        # Get existing dynamic data fields
                        if 'dynamic_data' in instrument_data:
                            # If the instrument already has dynamic_data, use it
                            dynamic_data = instrument_data['dynamic_data'].copy()
                            print(f"Using existing dynamic_data: {dynamic_data}")
                        else:
                            # Otherwise build it from individual fields
                            if 'size' in instrument_data and instrument_data['size']:
                                dynamic_data['Size'] = instrument_data['size']
                            if 'equipment_no' in instrument_data and instrument_data['equipment_no']:
                                dynamic_data['Equipment No.'] = instrument_data['equipment_no']
                            if 'location' in instrument_data and instrument_data['location']:
                                dynamic_data['Location'] = instrument_data['location']
                            if 'instrument_code' in instrument_data and instrument_data['instrument_code']:
                                dynamic_data['Instrument code'] = instrument_data['instrument_code']
                            print(f"Built dynamic_data from fields: {dynamic_data}")
            
            # Add Bluetooth address to dynamic_data
            print(f"Adding Bluetooth address: {self.selected_device.address}")
            dynamic_data['Bluetooth Address'] = self.selected_device.address
            
            # Ensure instrument code is always included
            if instrument_code and 'Instrument code' not in dynamic_data:
                dynamic_data['Instrument code'] = instrument_code
                print(f"Added instrument code to dynamic_data: {instrument_code}")
                
            print(f"Final dynamic_data: {dynamic_data}")
            
            # Prepare the payload for the API
            payload = {
                "item_code": item_code,
                "dynamic_data": dynamic_data,
                "quantity": 1,
                "available_quantity": 1,
                "status": "Active",
                "subcategory_id": subcategory_id,
                "created_by": 0  # This should be replaced with the actual user ID if available
            }
            
            print(f"API Payload: {payload}")
            print(f"Bluetooth Address in dynamic_data: {dynamic_data.get('Bluetooth Address')}")
            
            # Make the API request using the endpoint from api_endpoints.py
            api_url = api.base_url + APIEndpoints.INVENTORY_ITEMS
            print(f"API URL: {api_url}")
            
            if item_id:
                # If item exists, update it (PUT request)
                print(f"Updating existing item with ID: {item_id}")
                response = requests.put(f"{api_url}{item_id}/", json=payload)
            else:
                # If new item, create it (POST request)
                print("Creating new item")
                response = requests.post(api_url, json=payload)
                
            print(f"API Response status: {response.status_code}")
            print(f"API Response: {response.text}")
            
            # Check if the request was successful
            if response.status_code in [200, 201, 204]:
                # Update the UI to show the Bluetooth address
                for i in range(self.instrument_list.count()):
                    item = self.instrument_list.item(i)
                    widget = self.instrument_list.itemWidget(item)
                    if widget:
                        instrument_data = widget.property("instrument_data")
                        if instrument_data and instrument_data['id'] == item_id:
                            # Update the instrument data
                            instrument_data['bluetooth_address'] = self.selected_device.address
                            
                            # Update the widget with the new instrument data
                            new_widget = self.create_instrument_widget(instrument_data)
                            item.setSizeHint(new_widget.sizeHint())
                            self.instrument_list.setItemWidget(item, new_widget)
                            break
            else:
                # Handle API error
                error_msg = f"API Error: {response.status_code} - {response.text}"
                raise Exception(error_msg)
            
            # Show success message
            device_name = self.selected_device.name if self.selected_device.name else "Unknown Device"
            instrument_name = self.selected_instrument['name']
            if " - " in instrument_name:
                instrument_name = instrument_name.split(" - ")[0]
                
            self.status_label.setText(f"Successfully associated {device_name} with {instrument_name}")
            
            # Ask user if they want to associate another device or finish
            result = QtWidgets.QMessageBox.question(
                self,
                "Association Successful",
                f"Successfully associated {device_name} with {instrument_name}.\n\nDo you want to associate another device?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            
            if result == QtWidgets.QMessageBox.No:
                # Accept the dialog and return
                super().accept()
            else:
                # Clear selections for next association
                self.instrument_list.clearSelection()
                self.device_list.clearSelection()
                self.selected_instrument = None
                self.selected_device = None
                self.selected_instrument_label.setText("None selected")
                self.selected_device_label.setText("None selected")
                self.associate_button.setEnabled(False)
        
        except Exception as e:
            # Show error message
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while associating the device: {str(e)}"
            )
            print(f"Error associating device: {str(e)}")
    
    def accept(self):
        """Override accept to validate selection"""
        # Return the associated instruments
        associated_instruments = []
        for instrument in self.instruments:
            if instrument.get('bluetooth_address'):
                associated_instruments.append(instrument)
        
        self.associated_instruments = associated_instruments
        super().accept()
