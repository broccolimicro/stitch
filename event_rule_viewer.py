#!/usr/bin/env python3
import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QFileDialog, QPushButton, QLabel, 
                           QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
                           QToolButton, QGroupBox, QScrollArea, QMenu, QSizePolicy)
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QCursor
from PyQt5.QtCore import Qt, QRectF, QPointF, QLineF, pyqtSignal, QMimeData, QEvent

class Transition:
    """Represents a transition in the event-rule system."""
    def __init__(self, time, variable, is_rising, guard_expr=None, assumptions=None):
        self.time = time
        self.variable = variable
        self.is_rising = is_rising  # True for '+', False for '-'
        self.guard_expr = guard_expr or ""
        self.assumptions = assumptions or []
        self.incoming_links = []  # List of transitions that cause this one
        self.assumption_links = []  # List of transitions that are timing assumptions
        
    def __repr__(self):
        edge = "+" if self.is_rising else "-"
        return f"{self.variable}{edge}@{self.time}"

class EventRuleGraph:
    """Represents the entire event-rule graph."""
    def __init__(self):
        self.transitions = []  # All transitions in chronological order
        self.variable_last_transition = {}  # Maps variable names to their last transition
        self.all_variables = set()  # Set of all normalized variable names
        
    def add_transition(self, transition):
        self.transitions.append(transition)
        self.variable_last_transition[transition.variable] = transition
        self.all_variables.add(SimFileParser.normalize_variable(transition.variable))
        
    def get_min_max_time(self):
        if not self.transitions:
            return 0, 1
        min_time = min(t.time for t in self.transitions)
        max_time = max(t.time for t in self.transitions)
        return min_time, max_time

class AvailableSignalsPanel(QWidget):
    """Panel showing available signals that can be added to the graph."""
    signal_added = pyqtSignal(str)
    signals_added = pyqtSignal(list)  # New signal for batch adding
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        
        # Create the available signals list
        self.title_label = QLabel("Available Signals")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        self.available_signals = QListWidget()
        self.available_signals.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.available_signals.setDragEnabled(True)
        self.available_signals.setAcceptDrops(False)
        self.available_signals.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.available_signals)
        
        # Add button to add signals
        add_button = QPushButton("Add Selected Signal(s)")
        add_button.clicked.connect(self.add_selected_signals)
        layout.addWidget(add_button)
        
        # Set size policy - Fix: use QSizePolicy instead of QSplitter.Policy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        # Keep track of all signals and which ones are currently selected
        self.all_signals = []
        self.selected_signals = []
        
    def set_available_signals(self, signals):
        """Set the list of available signals."""
        self.all_signals = sorted(signals)
        self.refresh_list()
            
    def add_selected_signals(self):
        """Add selected signals to the graph view."""
        # First collect all selected signal names to avoid modifying the list while iterating
        signals_to_add = [item.text() for item in self.available_signals.selectedItems()]
        
        if signals_to_add:
            # Emit a batch signal if multiple signals are selected
            if len(signals_to_add) > 1:
                self.signals_added.emit(signals_to_add)
            else:
                # For a single signal, use the existing signal for backward compatibility
                self.signal_added.emit(signals_to_add[0])
            
    def on_item_double_clicked(self, item):
        """Handle double-click on an available signal to add it."""
        self.signal_added.emit(item.text())
    
    def hide_signal(self, signal_name):
        """Hide a signal from the available list when it's added to selected signals."""
        if signal_name in self.all_signals:
            self.selected_signals.append(signal_name)
            self.refresh_list()
    
    def hide_signals(self, signal_names):
        """Hide multiple signals at once from the available list."""
        for signal_name in signal_names:
            if signal_name in self.all_signals and signal_name not in self.selected_signals:
                self.selected_signals.append(signal_name)
        self.refresh_list()
    
    def show_signal(self, signal_name):
        """Show a signal in the available list when it's removed from selected signals."""
        if signal_name in self.selected_signals:
            self.selected_signals.remove(signal_name)
            self.refresh_list()
    
    def refresh_list(self):
        """Refresh the list to show only signals that aren't currently selected."""
        self.available_signals.clear()
        for signal in self.all_signals:
            if signal not in self.selected_signals:
                self.available_signals.addItem(signal)

class SelectedSignalsPanel(QWidget):
    """Panel showing selected signals that lines up with the plot."""
    signal_removed = pyqtSignal(str)
    signals_removed = pyqtSignal(list)  # New signal for batch removal
    signals_reordered = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create the overall layout with the same margins as AvailableSignalsPanel
        layout = QVBoxLayout(self)
        
        # Create title label with the same styling as AvailableSignalsPanel
        self.title_label = QLabel("Selected Signals")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        # Create a custom widget to display signals aligned with plot
        self.signals_container = QWidget()
        self.signals_container.setMouseTracking(True)
        self.signals_scroll = QScrollArea()
        self.signals_scroll.setWidget(self.signals_container)
        self.signals_scroll.setWidgetResizable(True)
        self.signals_scroll.setFrameShape(QScrollArea.NoFrame)
        self.signals_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.signals_scroll)
        
        # Signal list and interaction properties
        self.signals = []
        self.vertical_spacing = 30  # Match GraphView's vertical_spacing
        self.top_margin = 20  # Reduced from 50 to eliminate extra space at top
        self.signal_height = 22
        self.dragging_index = -1
        self.drag_start_pos = None
        self.last_click_time = 0  # To track double clicks
        self.last_click_pos = None
        
        # For multi-selection
        self.selected_signals = []  # Indices of selected signals
        self.selection_start_pos = None  # For tracking selection box
        self.is_selecting = False
        
        # Enable drag and drop
        self.signals_container.setAcceptDrops(True)
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        # Connect signals to handle interactions
        self.signals_container.installEventFilter(self)
        
    def set_signals(self, signals):
        """Set the list of signals to display."""
        self.signals = signals.copy()
        self.selected_signals = []  # Clear selection when signals change
        self.update_container_size()
        self.signals_container.update()
        
    def add_signal(self, signal_name):
        """Add a signal to the panel."""
        if signal_name not in self.signals:
            self.signals.append(signal_name)
            self.update_container_size()
            self.signals_container.update()
            
    def remove_signal(self, signal_name):
        """Remove a signal from the panel."""
        if signal_name in self.signals:
            self.signals.remove(signal_name)
            self.selected_signals = []  # Clear selection after removal
            self.update_container_size()
            self.signals_container.update()
            self.signal_removed.emit(signal_name)
    
    def remove_selected_signals(self):
        """Remove all selected signals."""
        if not self.selected_signals:
            return
            
        # Sort in reverse order to remove from highest index to lowest
        indices_to_remove = sorted(self.selected_signals, reverse=True)
        signals_to_remove = [self.signals[i] for i in indices_to_remove]
        
        # Remove signals from the list
        for index in indices_to_remove:
            del self.signals[index]
            
        # Clear selection
        self.selected_signals = []
        
        # Update UI
        self.update_container_size()
        self.signals_container.update()
        
        # Emit signal for batch removal
        self.signals_removed.emit(signals_to_remove)
    
    def update_container_size(self):
        """Update the size of the signals container based on signals."""
        if not self.signals:
            self.signals_container.setMinimumHeight(100)  # Minimum height for empty state
        else:
            # Set height to accommodate all signals with proper spacing
            total_height = self.top_margin + len(self.signals) * self.vertical_spacing
            self.signals_container.setMinimumHeight(total_height)
    
    def eventFilter(self, obj, event):
        """Handle mouse events for the signals container."""
        if obj == self.signals_container:
            if event.type() == QEvent.Paint:
                self.paint_signals()
                return True
            elif event.type() == QEvent.MouseButtonPress:
                return self.handle_mouse_press(event)
            elif event.type() == QEvent.MouseMove:
                return self.handle_mouse_move(event)
            elif event.type() == QEvent.MouseButtonRelease:
                return self.handle_mouse_release(event)
            elif event.type() == QEvent.DragEnter:
                return self.handle_drag_enter(event)
            elif event.type() == QEvent.Drop:
                return self.handle_drop(event)
                
        return super().eventFilter(obj, event)
    
    def paint_signals(self):
        """Paint the signals on the container."""
        painter = QPainter(self.signals_container)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw background
        painter.fillRect(self.signals_container.rect(), QColor(240, 240, 240))
        
        # If no signals, draw a message
        if not self.signals:
            message_rect = QRectF(10, 50, self.width() - 20, 60)
            painter.setPen(QPen(QColor(100, 100, 100)))
            painter.drawText(message_rect, Qt.AlignCenter, 
                            "No signals selected\nAdd signals from\nAvailable Signals panel")
            return
        
        # Draw selection box if selecting
        if self.is_selecting and self.selection_start_pos:
            selection_rect = QRectF(
                min(self.selection_start_pos.x(), self.selection_current_pos.x()), 
                min(self.selection_start_pos.y(), self.selection_current_pos.y()),
                abs(self.selection_current_pos.x() - self.selection_start_pos.x()),
                abs(self.selection_current_pos.y() - self.selection_start_pos.y())
            )
            painter.fillRect(selection_rect, QColor(0, 120, 215, 40))  # Semi-transparent selection
            painter.setPen(QPen(QColor(0, 120, 215), 1))
            painter.drawRect(selection_rect)
        
        # Draw each signal
        for i, signal in enumerate(self.signals):
            y_pos = self.top_margin + i * self.vertical_spacing
            rect = QRectF(5, y_pos - self.signal_height/2, 
                         self.signals_container.width() - 10, self.signal_height)
            
            # Fill background
            if i == self.dragging_index:
                # Highlight when dragging
                painter.fillRect(rect, QColor(200, 220, 255))
            elif i in self.selected_signals:
                # Highlight when selected
                painter.fillRect(rect, QColor(210, 230, 255))
            else:
                # Normal background
                painter.fillRect(rect, QColor(240, 240, 240))
            
            # Draw border
            painter.setPen(QPen(QColor(180, 180, 180), 1))
            painter.drawRect(rect)
            
            # Draw signal name
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            text_rect = rect.adjusted(5, 0, -5, 0)  # Text margin
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, signal)
            
        # Draw horizontal guide lines for alignment reference
        painter.setPen(QPen(QColor(220, 220, 220), 1, Qt.DotLine))
        for i in range(len(self.signals)):
            y_pos = self.top_margin + i * self.vertical_spacing
            painter.drawLine(0, y_pos, self.signals_container.width(), y_pos)
    
    def get_signal_index_at_pos(self, pos):
        """Get the index of the signal at the given position."""
        if not self.signals:
            return -1
            
        # Check if position is within signal display area
        if pos.y() < self.top_margin - self.signal_height/2:
            return -1
            
        # Calculate index based on y position
        index = int((pos.y() - self.top_margin + self.signal_height/2) / self.vertical_spacing)
        if 0 <= index < len(self.signals):
            return index
        return -1
    
    def handle_mouse_press(self, event):
        """Handle mouse press events."""
        if event.button() == Qt.LeftButton:
            # Check for double click
            current_time = event.timestamp()
            double_click_interval = QApplication.doubleClickInterval()
            
            if (self.last_click_pos is not None and 
                (current_time - self.last_click_time) < double_click_interval and
                (event.pos() - self.last_click_pos).manhattanLength() < 5):
                
                # This is a double click
                index = self.get_signal_index_at_pos(event.pos())
                if index >= 0:
                    self.remove_signal(self.signals[index])
                    return True
            
            # Update click time and position for potential future double click
            self.last_click_time = current_time
            self.last_click_pos = event.pos()
            
            # Get the index at click position
            index = self.get_signal_index_at_pos(event.pos())
            
            # Handling selection or dragging
            if index >= 0:
                # Check if Ctrl is pressed for multi-selection
                if event.modifiers() & Qt.ControlModifier:
                    # Toggle selection of the clicked item
                    if index in self.selected_signals:
                        self.selected_signals.remove(index)
                    else:
                        self.selected_signals.append(index)
                    self.signals_container.update()
                elif event.modifiers() & Qt.ShiftModifier and self.selected_signals:
                    # Range selection with Shift
                    if self.selected_signals:
                        # Get the last selected item
                        last_selected = self.selected_signals[-1]
                        # Select all items between last selected and current
                        start, end = sorted([last_selected, index])
                        self.selected_signals = list(set(self.selected_signals + list(range(start, end + 1))))
                        self.signals_container.update()
                else:
                    # Normal click - start dragging and clear previous selection
                    self.dragging_index = index
                    self.drag_start_pos = event.pos()
                    # Select only this item
                    self.selected_signals = [index]
                    self.signals_container.update()
            else:
                # Click in empty area - start selection box
                self.selection_start_pos = event.pos()
                self.selection_current_pos = event.pos()
                self.is_selecting = True
                # Clear selection if Ctrl is not pressed
                if not (event.modifiers() & Qt.ControlModifier):
                    self.selected_signals = []
                self.signals_container.update()
            
            return True
            
        elif event.button() == Qt.RightButton:
            # Show context menu for single item or selection
            index = self.get_signal_index_at_pos(event.pos())
            
            if index >= 0 and index not in self.selected_signals:
                # Right-click on non-selected item - select only this item
                self.selected_signals = [index]
                self.signals_container.update()
            
            if self.selected_signals:
                # Show context menu for selection
                menu = QMenu(self)
                
                if len(self.selected_signals) == 1:
                    signal_name = self.signals[self.selected_signals[0]]
                    remove_action = menu.addAction(f"Remove Signal '{signal_name}'")
                else:
                    remove_action = menu.addAction(f"Remove {len(self.selected_signals)} Selected Signals")
                
                action = menu.exec_(self.signals_container.mapToGlobal(event.pos()))
                if action == remove_action:
                    self.remove_selected_signals()
                
                return True
        
        return False
    
    def handle_mouse_move(self, event):
        """Handle mouse move events."""
        if self.dragging_index >= 0 and event.buttons() & Qt.LeftButton:
            # Determine target position for drag
            target_index = self.get_signal_index_at_pos(event.pos())
            if target_index >= 0 and target_index != self.dragging_index:
                # Move signal to new position
                signal = self.signals.pop(self.dragging_index)
                self.signals.insert(target_index, signal)
                
                # Update selected signals indices
                self.selected_signals = [i if i < self.dragging_index else i - 1 for i in self.selected_signals if i != self.dragging_index]
                self.selected_signals.append(target_index)
                
                self.dragging_index = target_index
                self.signals_container.update()
                self.signals_reordered.emit(self.signals)
            return True
        
        elif self.is_selecting:
            # Update selection box
            self.selection_current_pos = event.pos()
            
            # Update selected signals based on selection box
            selection_rect = QRectF(
                min(self.selection_start_pos.x(), self.selection_current_pos.x()), 
                min(self.selection_start_pos.y(), self.selection_current_pos.y()),
                abs(self.selection_current_pos.x() - self.selection_start_pos.x()),
                abs(self.selection_current_pos.y() - self.selection_start_pos.y())
            )
            
            # Determine which signals are in the selection rectangle
            new_selected = []
            for i, signal in enumerate(self.signals):
                y_pos = self.top_margin + i * self.vertical_spacing
                signal_rect = QRectF(5, y_pos - self.signal_height/2, 
                                    self.signals_container.width() - 10, self.signal_height)
                
                if selection_rect.intersects(signal_rect):
                    new_selected.append(i)
            
            # Update selection if changed
            if set(new_selected) != set(self.selected_signals):
                if event.modifiers() & Qt.ControlModifier:
                    # Toggle selection for items in box
                    for i in new_selected:
                        if i not in self.selected_signals:
                            self.selected_signals.append(i)
                else:
                    # Replace selection
                    self.selected_signals = new_selected
                
                self.signals_container.update()
            
            return True
        
        return False
    
    def handle_mouse_release(self, event):
        """Handle mouse release events."""
        if event.button() == Qt.LeftButton:
            if self.dragging_index >= 0:
                self.dragging_index = -1
                self.drag_start_pos = None
                self.signals_container.update()
                return True
                
            if self.is_selecting:
                self.is_selecting = False
                self.selection_start_pos = None
                self.signals_container.update()
                return True
        
        return False
    
    def handle_drag_enter(self, event):
        """Handle drag enter events."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
            return True
        return False
    
    def handle_drop(self, event):
        """Handle drop events."""
        if event.mimeData().hasText():
            signal_name = event.mimeData().text()
            self.add_signal(signal_name)
            event.acceptProposedAction()
        return False

class GraphView(QWidget):
    """Widget for rendering the event-rule graph with interactive signal labels."""
    signals_changed = pyqtSignal(list)  # Emitted when signals are added, removed, or reordered
    signal_added = pyqtSignal(str)  # New signal to notify when a signal is added by drag and drop
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.graph = None
        self.offset_x = 0
        self.scale = 1.0
        self.min_scale = 0.001
        self.max_scale = 10.0
        self.vertical_spacing = 30  # Reduced spacing between signals
        self.top_margin = 53  # Increased from 47 to move plot down by another ~1.5mm
        self.horizontal_margin = 50
        self.node_radius = 5
        self.setMinimumSize(600, 400)
        
        # Variables to display
        self.display_variables = []  # List of variables to display in order
        
        # Enable mouse tracking and focus
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        
    def set_graph(self, graph):
        """Set the graph to display."""
        self.graph = graph
        if self.graph and self.graph.transitions:
            # Sort transitions by time
            self.graph.transitions.sort(key=lambda t: t.time)
            
            # Get min and max time from the graph
            min_time, max_time = self.graph.get_min_max_time()
            
            # Start zoomed in to show only the first ~20 events
            if len(self.graph.transitions) > 20:
                # Find the time of the 20th event
                target_time = self.graph.transitions[19].time
            else:
                # If fewer than 20 events, use a portion of the timeline
                target_time = min_time + (max_time - min_time) * 0.2
                
            # Add a small margin (10%) to make sure we see all events clearly
            visible_time_range = (target_time - min_time) * 1.1
            
            # Calculate scale to show just this portion of the timeline
            self.scale = (self.width() - 2 * self.horizontal_margin) / max(1, visible_time_range)
            self.offset_x = -min_time * self.scale + self.horizontal_margin
            
            self.update_variable_positions()
        self.update()
    
    def zoom_to_initial_events(self):
        """Zoom to show the first ~20 events (initial view)."""
        if self.graph and self.graph.transitions:
            # Get min and max time from the graph
            min_time, max_time = self.graph.get_min_max_time()
            
            # Calculate target time based on number of events
            if len(self.graph.transitions) > 20:
                # Find the time of the 20th event
                target_time = self.graph.transitions[19].time
            else:
                # If fewer than 20 events, use a portion of the timeline
                target_time = min_time + (max_time - min_time) * 0.2
                
            # Add a small margin (10%) to make sure we see all events clearly
            visible_time_range = (target_time - min_time) * 1.1
            
            # Calculate scale to show just this portion of the timeline
            self.scale = (self.width() - 2 * self.horizontal_margin) / max(1, visible_time_range)
            self.offset_x = -min_time * self.scale + self.horizontal_margin
            
            self.update()
    
    def zoom_to_full_timeline(self):
        """Zoom out to show the entire timeline."""
        if self.graph and self.graph.transitions:
            # Get min and max time from the graph
            min_time, max_time = self.graph.get_min_max_time()
            
            # Calculate scale to show the full timeline
            self.scale = (self.width() - 2 * self.horizontal_margin) / max(1, max_time - min_time)
            self.offset_x = -min_time * self.scale + self.horizontal_margin
            
            self.update()
            
    def set_display_variables(self, variables):
        """Set which variables to display and in what order."""
        self.display_variables = variables
        if self.graph:
            self.update_variable_positions()
            self.update()
        self.signals_changed.emit(self.display_variables)
    
    def add_variable(self, variable):
        """Add a variable to the display if not already present."""
        if variable not in self.display_variables:
            self.display_variables.append(variable)
            if self.graph:
                self.update_variable_positions()
                self.update()
            self.signals_changed.emit(self.display_variables)
            
    def remove_variable(self, variable):
        """Remove a variable from the display."""
        if variable in self.display_variables:
            self.display_variables.remove(variable)
            if self.graph:
                self.update_variable_positions()
                self.update()
            self.signals_changed.emit(self.display_variables)
            
    def move_variable(self, from_index, to_index):
        """Move a variable from one position to another."""
        if 0 <= from_index < len(self.display_variables) and 0 <= to_index < len(self.display_variables):
            variable = self.display_variables[from_index]
            self.display_variables.pop(from_index)
            self.display_variables.insert(to_index, variable)
            if self.graph:
                self.update_variable_positions()
                self.update()
            self.signals_changed.emit(self.display_variables)
    
    def update_variable_positions(self):
        """Update the y-positions of variables based on the display list."""
        if not self.graph:
            return
            
        self.variable_y_positions = {}
        
        # Map for original and normalized variable names
        for i, var in enumerate(self.display_variables):
            y_pos = i * self.vertical_spacing + self.top_margin  # Use top_margin to align with signals panel
            self.variable_y_positions[var] = y_pos
            
            # Also map variables that normalize to this var
            for transition in self.graph.transitions:
                if SimFileParser.normalize_variable(transition.variable) == var:
                    self.variable_y_positions[transition.variable] = y_pos
        
    def time_to_x(self, time):
        """Convert a time value to an x-coordinate."""
        return time * self.scale + self.offset_x
    
    def x_to_time(self, x):
        """Convert an x-coordinate to a time value."""
        return (x - self.offset_x) / self.scale
    
    def is_transition_visible(self, transition):
        """Check if a transition is visible in the current viewport."""
        if transition.variable not in self.variable_y_positions:
            return False
            
        x = self.time_to_x(transition.time)
        # Add a small margin to include transitions just outside the viewport
        margin = 20
        return (-margin <= x <= self.width() + margin)
    
    def paintEvent(self, event):
        if not self.graph or not self.graph.transitions:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        try:
            # Draw background
            painter.fillRect(self.rect(), QColor(240, 240, 240))
            
            # Get the visible time range for culling
            left_time = self.x_to_time(0)
            right_time = self.x_to_time(self.width())
            time_margin = (right_time - left_time) * 0.1  # 10% margin
            min_visible_time = left_time - time_margin
            max_visible_time = right_time + time_margin
            
            # Draw X-axis time labels
            min_time, max_time = self.graph.get_min_max_time()
            visible_min_time = max(min_time, self.x_to_time(0))
            visible_max_time = min(max_time, self.x_to_time(self.width()))
            
            # Determine good intervals for time labels based on scale
            time_range = visible_max_time - visible_min_time
            if time_range <= 0:
                time_range = max_time - min_time
                
            # Determine appropriate interval for time markers
            if time_range > 100000:
                interval = 10000
            elif time_range > 10000:
                interval = 1000
            elif time_range > 1000:
                interval = 100
            elif time_range > 100:
                interval = 10
            else:
                interval = 5
                
            # Calculate first time marker
            first_time = (int(visible_min_time / interval) * interval)
            
            # Draw time markers and labels
            y_axis_position = self.height() - 25  # Position of X-axis
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            
            for t in range(first_time, int(visible_max_time) + interval, interval):
                x = self.time_to_x(t)
                if x < self.horizontal_margin:
                    continue
                    
                # Draw tick mark - use QLineF for float coordinates
                painter.drawLine(QLineF(x, y_axis_position - 5, x, y_axis_position + 5))
                
                # Draw time label
                text_rect = QRectF(x - 50, y_axis_position + 5, 100, 20)
                painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, str(t))
                
                # Draw vertical guide line - use QLineF for float coordinates
                painter.setPen(QPen(QColor(220, 220, 220), 1, Qt.DotLine))
                painter.drawLine(QLineF(x, 0, x, y_axis_position - 5))
                painter.setPen(QPen(QColor(0, 0, 0), 1))
            
            # Draw a message if no signals are selected
            if not self.display_variables and self.graph:
                message_rect = QRectF(0, self.height()/2 - 30, self.width(), 60)
                painter.setPen(QPen(QColor(100, 100, 100), 1))
                painter.drawText(message_rect, Qt.AlignCenter, 
                                "No signals selected\nSelect signals from the Available Signals panel")
            
            # Filter visible transitions for better performance
            visible_transitions = []
            for transition in self.graph.transitions:
                # Skip if variable is not in displayed list (normalized form)
                norm_var = SimFileParser.normalize_variable(transition.variable)
                if norm_var not in self.display_variables:
                    continue
                    
                # Skip if not in viewport time range
                if transition.time < min_visible_time or transition.time > max_visible_time:
                    continue
                    
                # Skip if variable position is not defined
                if transition.variable not in self.variable_y_positions:
                    continue
                    
                visible_transitions.append(transition)
            
            # Build a dictionary of visible transitions for quick lookup
            visible_transitions_dict = {id(t): t for t in visible_transitions}
            
            # Draw horizontal guide lines (behind nodes and arcs)
            painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DashLine))
            for var in self.display_variables:
                if var not in self.variable_y_positions:
                    continue
                    
                y = self.variable_y_positions[var]
                painter.drawLine(QLineF(0, y, self.width(), y))
            
            # First pass: Draw the transition nodes for visible transitions only
            for transition in visible_transitions:                
                # Draw node
                x = self.time_to_x(transition.time)
                y = self.variable_y_positions[transition.variable]
                
                # Choose color based on rising/falling
                if transition.is_rising:
                    painter.setBrush(QBrush(QColor(100, 180, 100)))  # Green for rising
                else:
                    painter.setBrush(QBrush(QColor(180, 100, 100)))  # Red for falling
                    
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                node_center = QPointF(x, y)
                painter.drawEllipse(node_center, self.node_radius, self.node_radius)
                
                # Draw transition label
                edge = "+" if transition.is_rising else "-"
                label = f"{transition.variable}{edge}"
                # Use QPointF for text position
                text_pos = QPointF(x + self.node_radius + 2, y - self.node_radius - 2)
                painter.drawText(text_pos, label)
            
            # Second pass: Draw links/arrows if either end is visible
            # Process all transitions rather than just visible ones
            for transition in self.graph.transitions:
                # Skip if variable is not in displayed list (normalized form)
                norm_var = SimFileParser.normalize_variable(transition.variable)
                if norm_var not in self.display_variables:
                    continue
                    
                # Skip if variable position is not defined
                if transition.variable not in self.variable_y_positions:
                    continue
                
                # Check if this transition is visible
                target_visible = (min_visible_time <= transition.time <= max_visible_time)
                if not target_visible and id(transition) not in visible_transitions_dict:
                    # If target is not visible, we'll check each source later
                    pass
                    
                # Get target coordinates even if not visible
                x = self.time_to_x(transition.time)
                y = self.variable_y_positions[transition.variable]
                
                # Draw incoming links (causal dependencies)
                for source in transition.incoming_links:
                    source_norm_var = SimFileParser.normalize_variable(source.variable)
                    if source_norm_var not in self.display_variables:
                        continue
                        
                    if source.variable not in self.variable_y_positions:
                        continue
                    
                    # Check if source is visible
                    source_visible = (min_visible_time <= source.time <= max_visible_time)
                    
                    # Skip if both source and target are invisible
                    if not source_visible and not target_visible:
                        continue
                    
                    src_x = self.time_to_x(source.time)
                    src_y = self.variable_y_positions[source.variable]
                    
                    # Create a curved path for the arrow
                    path = QPainterPath()
                    path.moveTo(src_x, src_y)
                    
                    # Calculate control points for the curve
                    ctrl1_x = src_x + (x - src_x) * 0.5
                    ctrl1_y = src_y
                    ctrl2_x = src_x + (x - src_x) * 0.5
                    ctrl2_y = y
                    
                    path.cubicTo(ctrl1_x, ctrl1_y, ctrl2_x, ctrl2_y, x, y)
                    
                    # Set pen for the path (no brush for the path)
                    painter.setPen(QPen(QColor(0, 0, 200), 1.5))
                    painter.setBrush(Qt.NoBrush)  # Ensure no fill for the path
                    
                    # Draw the path (curve only)
                    painter.drawPath(path)
                    
                    # Draw arrowhead if target is visible
                    if target_visible:
                        arrow_size = 6
                        
                        # Calculate the direction vector at the endpoint
                        dx = x - ctrl2_x
                        dy = y - ctrl2_y
                        length = (dx**2 + dy**2)**0.5
                        if length > 0:
                            dx, dy = dx/length, dy/length
                            
                            # Calculate arrowhead points
                            p1 = QPointF(x - arrow_size * (dx * 0.866 - dy * 0.5), 
                                        y - arrow_size * (dy * 0.866 + dx * 0.5))
                            p2 = QPointF(x - arrow_size * (dx * 0.866 + dy * 0.5), 
                                        y - arrow_size * (dy * 0.866 - dx * 0.5))
                            
                            # Draw arrowhead with fill
                            painter.setBrush(QBrush(QColor(0, 0, 200)))
                            points = [QPointF(x, y), p1, p2]
                            painter.drawPolygon(points)
                
                # Draw assumption links with a different color
                for source in transition.assumption_links:
                    source_norm_var = SimFileParser.normalize_variable(source.variable)
                    if source_norm_var not in self.display_variables:
                        continue
                        
                    if source.variable not in self.variable_y_positions:
                        continue
                    
                    # Check if source is visible
                    source_visible = (min_visible_time <= source.time <= max_visible_time)
                    
                    # Skip if both source and target are invisible
                    if not source_visible and not target_visible:
                        continue
                    
                    src_x = self.time_to_x(source.time)
                    src_y = self.variable_y_positions[source.variable]
                    
                    path = QPainterPath()
                    path.moveTo(src_x, src_y)
                    
                    ctrl1_x = src_x + (x - src_x) * 0.5
                    ctrl1_y = src_y
                    ctrl2_x = src_x + (x - src_x) * 0.5
                    ctrl2_y = y
                    
                    path.cubicTo(ctrl1_x, ctrl1_y, ctrl2_x, ctrl2_y, x, y)
                    
                    # Set pen for the path (no brush for the path)
                    painter.setPen(QPen(QColor(200, 100, 0), 1.5, Qt.DashLine))
                    painter.setBrush(Qt.NoBrush)  # Ensure no fill for the path
                    
                    # Draw the path (curve only)
                    painter.drawPath(path)
                    
                    # Draw arrowhead if target is visible
                    if target_visible:
                        arrow_size = 6
                        
                        dx = x - ctrl2_x
                        dy = y - ctrl2_y
                        length = (dx**2 + dy**2)**0.5
                        if length > 0:
                            dx, dy = dx/length, dy/length
                            
                            p1 = QPointF(x - arrow_size * (dx * 0.866 - dy * 0.5), 
                                        y - arrow_size * (dy * 0.866 + dx * 0.5))
                            p2 = QPointF(x - arrow_size * (dx * 0.866 + dy * 0.5), 
                                        y - arrow_size * (dy * 0.866 - dx * 0.5))
                            
                            # Draw arrowhead with fill
                            painter.setBrush(QBrush(QColor(200, 100, 0)))
                            points = [QPointF(x, y), p1, p2]
                            painter.drawPolygon(points)
        finally:
            # Ensure painter is ended properly
            painter.end()
    
    def wheelEvent(self, event):
        # Zoom in/out with Shift+Scroll
        if event.modifiers() & Qt.ShiftModifier:
            zoom_factor = 1.1
            if event.angleDelta().y() < 0:
                zoom_factor = 1.0 / zoom_factor
                
            # Get the position under the mouse before scaling
            mouse_x = event.pos().x()
            time_at_mouse = (mouse_x - self.offset_x) / self.scale
            
            # Apply scaling
            new_scale = self.scale * zoom_factor
            new_scale = max(self.min_scale, min(self.max_scale, new_scale))
            
            if new_scale != self.scale:
                self.scale = new_scale
                
                # Adjust the offset to keep the point under the mouse at the same position
                new_offset = mouse_x - time_at_mouse * self.scale
                self.offset_x = new_offset
                
                self.update()
        else:
            # Horizontal scrolling
            scroll_amount = event.angleDelta().y() / 2  # Adjust sensitivity
            self.offset_x += scroll_amount
            self.update()
        
        event.accept()
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        if event.mimeData().hasText():
            signal_name = event.mimeData().text()
            self.add_variable(signal_name)
            # Emit a signal to notify that a signal was added via drag and drop
            self.signal_added.emit(signal_name)
            event.acceptProposedAction()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to remove variables at a specific position."""
        if not self.graph or not self.display_variables:
            return
            
        # Find the closest variable to the click position
        for var, y_pos in self.variable_y_positions.items():
            if abs(event.pos().y() - y_pos) < 15:  # Within reasonable range of line
                if var in self.display_variables:
                    self.remove_variable(var)
                    break
                    
        event.accept()

class SimFileParser:
    """Parser for .sim files containing event-rule data."""
    
    @staticmethod
    def normalize_variable(variable):
        """Normalize variable names by removing apostrophe and number suffixes.
        For example, "name'1" becomes "name".
        """
        import re
        # Make sure to remove region identifiers like '1, '2, etc.
        return re.sub(r"'[0-9]+$", "", variable)
    
    @staticmethod
    def parse_file(filename):
        """Parse a .sim file and return an EventRuleGraph."""
        graph = EventRuleGraph()
        
        # Track the most recent rising and falling transitions for each normalized variable
        rising_transitions = {}   # normalized_var -> most recent rising transition
        falling_transitions = {}  # normalized_var -> most recent falling transition
        
        # Debug: Track all transitions for validation
        all_transitions = []
        
        line_num = 0
        with open(filename, 'r') as f:
            for line in f:
                line_num += 1
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # Parse the time and the rest of the line
                    parts = line.split(None, 1)
                    if len(parts) < 2:
                        continue
                    
                    # Extract time - handle prefixes like "(prsim)"
                    time_str = parts[0]
                    # Remove any non-numeric prefixes
                    time_str = ''.join(c for c in time_str if c.isdigit())
                    if not time_str:
                        print(f"Warning: Could not parse time from line {line_num}: {line}")
                        continue
                    
                    time = int(time_str)
                    rest = parts[1]
                    
                    # Split the rule into guard and transition
                    if '->' not in rest:
                        continue
                        
                    rule_parts = rest.split('->')
                    if len(rule_parts) != 2:
                        continue
                    
                    guard_expr = rule_parts[0].strip()
                    transition_part = rule_parts[1].strip()
                    
                    # Extract assumptions if present
                    assumptions = []
                    if '{' in transition_part:
                        trans_part, assumptions_part = transition_part.split('{', 1)
                        transition_part = trans_part.strip()
                        assumptions_part = assumptions_part.strip()
                        if assumptions_part.endswith('}'):
                            assumptions_part = assumptions_part[:-1]
                        assumptions = [a.strip() for a in assumptions_part.split(',')]
                    
                    # Parse the transition
                    if transition_part.endswith('+') or transition_part.endswith('-'):
                        variable = transition_part[:-1]
                        is_rising = transition_part[-1] == '+'
                        
                        # Get normalized variable name (without apostrophe and numbers)
                        normalized_var = SimFileParser.normalize_variable(variable)
                        
                        # Create transition
                        transition = Transition(time, variable, is_rising, guard_expr, assumptions)
                        all_transitions.append(transition)
                        
                        # Process guard expression to create causal links
                        terms = guard_expr.split('&') if guard_expr else []
                        for term in terms:
                            term = term.strip()
                            if not term:
                                continue
                                
                            # Check for negation
                            negated = term.startswith('~')
                            
                            # Extract variable name without the negation
                            var_name = term[1:] if negated else term
                            
                            # Normalize the variable name in the term
                            normalized_term = SimFileParser.normalize_variable(var_name)
                            
                            # Print for debugging
                            print(f"Looking for {'falling' if negated else 'rising'} transition of {var_name} (normalized: {normalized_term})")
                            
                            # Find the appropriate transition to link from based on negation
                            # If negated (~var), link from the most recent falling edge
                            # If not negated (var), link from the most recent rising edge
                            source = None
                            if negated and normalized_term in falling_transitions:
                                source = falling_transitions[normalized_term]
                                print(f"  Found falling transition: {source}")
                            elif not negated and normalized_term in rising_transitions:
                                source = rising_transitions[normalized_term]
                                print(f"  Found rising transition: {source}")
                            else:
                                print(f"  No matching transition found for {normalized_term}")
                                
                            if source:
                                # Skip links that would go backward in time or self-links
                                if source.time < time and source != transition:
                                    transition.incoming_links.append(source)
                                    print(f"Created link: {source.variable}{'+' if source.is_rising else '-'}@{source.time} -> {transition.variable}{'+' if transition.is_rising else '-'}@{transition.time}")
                        
                        # Process assumptions to create timing assumption links
                        for assumption in assumptions:
                            norm_assumption = SimFileParser.normalize_variable(assumption)
                            
                            # Try rising transitions first, then falling
                            if norm_assumption in rising_transitions:
                                source = rising_transitions[norm_assumption]
                                # Skip links that would go backward in time
                                if source.time < time:
                                    transition.assumption_links.append(source)
                                    print(f"Created assumption link from rising: {source.variable}+@{source.time} -> {transition.variable}{'+' if transition.is_rising else '-'}@{transition.time}")
                            elif norm_assumption in falling_transitions:
                                source = falling_transitions[norm_assumption]
                                # Skip links that would go backward in time
                                if source.time < time:
                                    transition.assumption_links.append(source)
                                    print(f"Created assumption link from falling: {source.variable}-@{source.time} -> {transition.variable}{'+' if transition.is_rising else '-'}@{transition.time}")
                        
                        # Add to the graph
                        graph.add_transition(transition)
                        
                        # Update the most recent transition records with normalized variable name
                        if is_rising:
                            rising_transitions[normalized_var] = transition
                            print(f"Updated rising transition for {normalized_var}: {transition}")
                        else:
                            falling_transitions[normalized_var] = transition
                            print(f"Updated falling transition for {normalized_var}: {transition}")
                            
                except Exception as e:
                    print(f"Error parsing line {line_num}: {line}")
                    print(f"  Error details: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        # Sort transitions by time for visualization
        graph.transitions.sort(key=lambda t: t.time)
        
        # Debug: Check for any links that span more than 20% of the timeline
        min_time, max_time = graph.get_min_max_time()
        time_span = max_time - min_time
        unusual_links = 0
        
        for transition in graph.transitions:
            for source in transition.incoming_links:
                link_length = transition.time - source.time
                if link_length > time_span * 0.2:  # Links spanning >20% of timeline
                    unusual_links += 1
                    print(f"Unusual link: {source.variable}{'+' if source.is_rising else '-'}@{source.time} -> {transition.variable}{'+' if transition.is_rising else '-'}@{transition.time} (spans {link_length} time units)")
        
        print(f"Successfully parsed {len(graph.transitions)} transitions from {filename}")
        print(f"Created {sum(len(t.incoming_links) for t in graph.transitions)} causal links and {sum(len(t.assumption_links) for t in graph.transitions)} assumption links")
        print(f"Found {unusual_links} unusually long links (>20% of timeline)")
        
        return graph

class MainWindow(QMainWindow):
    """Main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Event-Rule System Viewer")
        self.resize(1200, 800)
        
        # Create the main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(0)
        
        # Create a horizontal splitter for the main layout
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # Create the available signals panel
        self.available_signals_panel = AvailableSignalsPanel()
        self.available_signals_panel.signal_added.connect(self.add_signal)
        self.available_signals_panel.signals_added.connect(self.add_signals)  # Connect new signal
        self.available_signals_panel.setMinimumWidth(120)
        self.available_signals_panel.setMaximumWidth(250)
        self.main_splitter.addWidget(self.available_signals_panel)
        
        # Create a container widget for the selected signals panel and graph view
        graph_container = QWidget()
        graph_layout = QHBoxLayout(graph_container)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(0)  # No space between selected signals and graph
        
        # Create the second splitter for selected signals and plot
        self.signals_plot_splitter = QSplitter(Qt.Horizontal)
        graph_layout.addWidget(self.signals_plot_splitter)
        
        # Create the selected signals panel (replaces y-axis labels)
        self.selected_signals_panel = SelectedSignalsPanel()
        # Set similar margins to match available signals panel
        self.selected_signals_panel.layout().setContentsMargins(9, 9, 9, 9)
        self.selected_signals_panel.signal_removed.connect(self.remove_signal)
        self.selected_signals_panel.signals_removed.connect(self.remove_signals)  # Connect new signal
        self.selected_signals_panel.signals_reordered.connect(self.reorder_signals)
        self.selected_signals_panel.setMinimumWidth(150)  # Increased from 100
        self.selected_signals_panel.setMaximumWidth(300)  # Increased from 200
        self.signals_plot_splitter.addWidget(self.selected_signals_panel)
        
        # Create the graph view
        self.graph_view = GraphView()
        self.graph_view.signals_changed.connect(self.update_selected_signals)
        self.graph_view.signal_added.connect(self.handle_direct_signal_add)  # Connect new signal
        self.signals_plot_splitter.addWidget(self.graph_view)
        
        # Add the graph container to the main splitter
        self.main_splitter.addWidget(graph_container)
        
        # Set splitter sizes
        self.main_splitter.setSizes([150, 1050])  # Available signals panel gets 150px, the rest gets 1050px
        self.signals_plot_splitter.setSizes([180, 870])  # Adjusted: Selected signals panel gets 180px (increased from 120px)
        
        # Create a menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        
        # Add load action to the menu
        load_action = file_menu.addAction("Load .sim File")
        load_action.triggered.connect(self.load_sim_file)
        
        # Create View menu
        view_menu = menu_bar.addMenu("View")
        
        # Add View Initial Events action to View menu
        view_initial_action = view_menu.addAction("View Initial Events")
        view_initial_action.triggered.connect(self.view_initial_events)
        view_initial_action.setShortcut("Ctrl+I")  # Add keyboard shortcut
        
        # Add View Full Timeline action to View menu
        view_full_action = view_menu.addAction("View Full Timeline")
        view_full_action.triggered.connect(self.view_full_timeline)
        view_full_action.setShortcut("Ctrl+F")  # Add keyboard shortcut
        
        # Update file label to be part of the status bar
        self.file_label = QLabel("No file loaded")
        self.statusBar().addWidget(self.file_label)
        
        # Add help text to the status bar
        self.hint_label = QLabel(" | Drag to add/reorder | Ctrl+Click for selection | Shift+Scroll to zoom | Ctrl+I: initial view | Ctrl+F: full view")
        self.statusBar().addWidget(self.hint_label)
        
        # Track the currently loaded graph
        self.current_graph = None

    def view_initial_events(self):
        """Zoom to show the initial events view."""
        if self.graph_view:
            self.graph_view.zoom_to_initial_events()

    def view_full_timeline(self):
        """Zoom out to see the full timeline."""
        if self.graph_view:
            self.graph_view.zoom_to_full_timeline()

    def load_sim_file(self):
        """Open a file dialog to select and load a .sim file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open .sim File", "", "Simulation Files (*.sim);;All Files (*)")
        
        if filename:
            try:
                self.current_graph = SimFileParser.parse_file(filename)
                
                # Update the available signals list
                self.available_signals_panel.set_available_signals(self.current_graph.all_variables)
                
                # Set the graph in the view (initially without any signals displayed)
                self.graph_view.set_graph(self.current_graph)
                
                self.file_label.setText(os.path.basename(filename))
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.file_label.setText(f"Error loading file: {str(e)}")
                
    def add_signal(self, signal_name):
        """Add a signal to the graph view and update the selected signals panel."""
        # Hide the signal from available signals panel
        self.available_signals_panel.hide_signal(signal_name)
        
        # Add to graph view and selected signals panel
        self.graph_view.add_variable(signal_name)
        self.selected_signals_panel.add_signal(signal_name)
    
    def add_signals(self, signal_names):
        """Add multiple signals to the graph view at once."""
        # Hide all signals from available panel first
        self.available_signals_panel.hide_signals(signal_names)
        
        # Add each signal to the graph and selected signals panel
        for signal_name in signal_names:
            self.graph_view.add_variable(signal_name)
            self.selected_signals_panel.add_signal(signal_name)
        
    def remove_signal(self, signal_name):
        """Remove a signal from the graph view."""
        # Show the signal in available signals panel
        self.available_signals_panel.show_signal(signal_name)
        
        # Remove from graph view
        self.graph_view.remove_variable(signal_name)
        
    def remove_signals(self, signal_names):
        """Remove multiple signals from the graph view."""
        for signal_name in signal_names:
            # Show each signal in available signals panel
            self.available_signals_panel.show_signal(signal_name)
            
            # Remove from graph view
            self.graph_view.remove_variable(signal_name)
        
    def reorder_signals(self, signals):
        """Update the graph view with the new signal order."""
        self.graph_view.set_display_variables(signals)
        
    def update_selected_signals(self, signals):
        """Update the selected signals panel with the current signals in the graph."""
        self.selected_signals_panel.set_signals(signals)

    def handle_direct_signal_add(self, signal_name):
        """Handle when a signal is added directly to the graph via drag and drop."""
        # Hide the signal from available signals panel
        self.available_signals_panel.hide_signal(signal_name)
        
        # Add to the selected signals panel
        self.selected_signals_panel.add_signal(signal_name)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 