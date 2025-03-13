#!/usr/bin/env python3
import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QFileDialog, QPushButton, QLabel, 
                           QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
                           QToolButton, QGroupBox, QScrollArea, QMenu, QSizePolicy, QComboBox)
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QCursor, QDrag
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
        
        # Use a custom list widget that enhances drag operations
        self.available_signals = DraggableListWidget()
        self.available_signals.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.available_signals.setDragEnabled(True)
        self.available_signals.setAcceptDrops(False)
        self.available_signals.itemDoubleClicked.connect(self.on_item_double_clicked)
        # Setup drag behavior to include correct mime data format
        self.available_signals.setDragDropMode(QAbstractItemView.DragOnly)
        # Enable context menu
        self.available_signals.setContextMenuPolicy(Qt.CustomContextMenu)
        self.available_signals.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.available_signals)
        
        # Set size policy - Fix: use QSizePolicy instead of QSplitter.Policy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        # Keep track of all signals and which ones are currently selected
        self.all_signals = []
        self.selected_signals = []
        
    def set_available_signals(self, signals):
        """Set the list of available signals.
        
        Args:
            signals: The list of signals to set as available.
        """
        # Save the current selected_signals first
        current_selected = self.selected_signals.copy()
        
        # Update the all_signals list
        self.all_signals = sorted(signals)
        
        # Restore the selected_signals list, but only keep signals that are still in all_signals
        self.selected_signals = [s for s in current_selected if s in self.all_signals]
        
        # Refresh the list to reflect the updated signals
        self.refresh_list()
        print(f"Set available signals to {len(self.all_signals)} items, kept {len(self.selected_signals)} selected")
        self.debug_state()
            
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
        print(f"Hiding signal from available list: {signal_name}")
        if signal_name in self.all_signals:
            # Always add to selected_signals list if not already there
            if signal_name not in self.selected_signals:
                self.selected_signals.append(signal_name)
                print(f"  - Added {signal_name} to selected_signals")
            self.refresh_list()
            # Debug the state after refresh
            self.debug_state()
    
    def hide_signals(self, signal_names):
        """Hide multiple signals at once from the available list."""
        print(f"hide_signals called with: {signal_names}")
        print(f"  Type of signal_names: {type(signal_names)}")
        
        # Make sure we have an actual list, not just a string
        if isinstance(signal_names, str):
            print(f"  Converting string to list: {signal_names}")
            signal_names = [signal_names]
        
        # Print each signal with its type
        for i, signal in enumerate(signal_names):
            print(f"  Signal {i}: '{signal}' (type: {type(signal)})")
            
        print(f"Hiding {len(signal_names)} signals from available list: {signal_names}")
        
        # Process each signal
        for signal_name in signal_names:
            # Strip whitespace in case there are trailing spaces
            if isinstance(signal_name, str):
                signal_name = signal_name.strip()
                if not signal_name:
                    print(f"  - Skipping empty signal name")
                    continue
                    
                # Check if it's a valid signal name in our all_signals list
                if signal_name in self.all_signals:
                    # Always add to selected_signals regardless of whether it's already there
                    if signal_name not in self.selected_signals:
                        self.selected_signals.append(signal_name)
                        print(f"  - Added {signal_name} to selected_signals")
                    else:
                        print(f"  - Signal {signal_name} already in selected_signals")
                else:
                    print(f"  - Warning: Signal {signal_name} not found in all_signals list")
            else:
                print(f"  - Error: Expected string but got {type(signal_name)}: {signal_name}")
                
        # Always refresh the list to ensure all selected signals are hidden
        self.refresh_list()
        
        # Debug the state after refresh
        self.debug_state()
    
    def show_signal(self, signal_name):
        """Show a signal in the available list when it's removed from selected signals."""
        if signal_name in self.selected_signals:
            self.selected_signals.remove(signal_name)
            self.refresh_list()
    
    def refresh_list(self):
        """Refresh the list to show only signals that aren't currently selected."""
        print(f"Refreshing available signals list. {len(self.all_signals)} total, {len(self.selected_signals)} selected")
        
        # For debugging, print some of the selected signals
        if self.selected_signals:
            debug_sample = self.selected_signals[:min(5, len(self.selected_signals))]
            print(f"  Sample of selected signals: {debug_sample}")
            
        # Clear the list widget first
        self.available_signals.clear()
        
        # Add only signals that aren't in the selected_signals list
        added_count = 0
        for signal in self.all_signals:
            if signal not in self.selected_signals:
                self.available_signals.addItem(signal)
                added_count += 1
        
        print(f"  Added {added_count} signals to available list")
        
        # For extra verification - make sure each signal is either in the list or marked as selected
        if added_count + len(self.selected_signals) != len(self.all_signals):
            print(f"  WARNING: Signal count mismatch - available({added_count}) + selected({len(self.selected_signals)}) != all({len(self.all_signals)})")
            # If there's a mismatch, let's double check each signal
            for signal in self.all_signals:
                found_in_available = False
                for i in range(self.available_signals.count()):
                    if self.available_signals.item(i).text() == signal:
                        found_in_available = True
                        break
                
                if signal not in self.selected_signals and not found_in_available:
                    print(f"  MISSING: Signal '{signal}' is not in selected list or available list")

    def debug_state(self):
        """Print the current state of the panel for debugging."""
        print(f"=== AvailableSignalsPanel State ===")
        print(f"  All signals: {len(self.all_signals)} items")
        print(f"  Selected signals: {len(self.selected_signals)} items")
        print(f"  Available list widget: {self.available_signals.count()} items")
        print(f"  First 5 all_signals: {self.all_signals[:min(5, len(self.all_signals))]}")
        print(f"  First 5 selected_signals: {self.selected_signals[:min(5, len(self.selected_signals))]}")
        visible_signals = []
        for i in range(self.available_signals.count()):
            visible_signals.append(self.available_signals.item(i).text())
        print(f"  First 5 visible signals: {visible_signals[:min(5, len(visible_signals))]}")
        print(f"=================================")

    def force_hide_signals(self, signal_names):
        """Force-hide multiple signals at once, with extra debugging.
        This method ensures all signals are properly added to selected_signals and removed from the available list."""
        print(f"\n=== AvailableSignalsPanel.force_hide_signals ===")
        print(f"Force hiding {len(signal_names)} signals: {signal_names}")
        
        # Make sure we have an actual list
        if not isinstance(signal_names, list):
            signal_names = [signal_names]
        
        # Directly add to selected_signals without checking to ensure all are hidden
        for signal_name in signal_names:
            if signal_name.strip():
                self.selected_signals.append(signal_name.strip())
                print(f"  Added {signal_name} to selected_signals")
        
        # Remove duplicates from selected_signals
        self.selected_signals = list(set(self.selected_signals))
        print(f"  After deduplication: {len(self.selected_signals)} signals in selected_signals")
        
        # Force refresh the list
        print(f"  Refreshing list with {len(self.selected_signals)} signals hidden")
        self.refresh_list()
        
        # Verify the refresh worked
        hidden_count = 0
        for signal in self.all_signals:
            if signal not in self.selected_signals:
                # Should be visible in list
                pass
            else:
                # Should be hidden
                hidden_count += 1
        
        print(f"  Verification: {hidden_count} signals hidden, {len(self.all_signals) - hidden_count} visible")
        print(f"=== End force_hide_signals ===\n")

    def protect_selected_signals(self):
        """Make a backup of the current selected_signals list to protect it from being modified.
        Call restore_selected_signals() to restore the backup after operations that might modify it."""
        self._protected_selected_signals = self.selected_signals.copy()
        print(f"Protected {len(self._protected_selected_signals)} selected signals")
        
    def restore_selected_signals(self):
        """Restore the selected_signals list from the backup made by protect_selected_signals()."""
        if hasattr(self, '_protected_selected_signals'):
            print(f"Restoring {len(self._protected_selected_signals)} protected signals")
            self.selected_signals = self._protected_selected_signals.copy()
            # Ensure the list widget reflects the restored selected signals
            self.refresh_list()
            # Clean up the backup
            del self._protected_selected_signals

    def show_context_menu(self, position):
        """Show context menu for the available signals list."""
        selected_items = self.available_signals.selectedItems()
        
        if not selected_items:
            return
            
        menu = QMenu(self)
        
        # Create an action for adding the selected signals
        if len(selected_items) > 1:
            add_action = menu.addAction(f"Add {len(selected_items)} Selected Signals to Graph")
        else:
            signal_name = selected_items[0].text()
            add_action = menu.addAction(f"Add '{signal_name}' to Graph")
            
        # Create a separator and add "Select All" action
        menu.addSeparator()
        select_all_action = menu.addAction("Select All")
        
        # Show the context menu at the cursor position
        action = menu.exec_(self.available_signals.mapToGlobal(position))
        
        # Handle the selected action
        if action == add_action:
            self.add_selected_signals()
        elif action == select_all_action:
            self.available_signals.selectAll()

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
        self.signals_container.setToolTip("Double-click anywhere on a signal to toggle between Event/Wave view")
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
        
        # For drag and drop visualization
        self.drag_in_progress = False
        
        # Reference to main window (set by MainWindow after creation)
        self.main_window = None
        
        # Enable drag and drop
        self.signals_container.setAcceptDrops(True)
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        # Explicitly install event filter on signals_container
        self.signals_container.installEventFilter(self)
        
        # Make sure we're listening for the right events
        self.signals_container.setMouseTracking(True)
        
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
            
    def remove_signal(self, signal_name, emit_signal=True):
        """Remove a signal from the panel.
        
        Args:
            signal_name: The name of the signal to remove
            emit_signal: Whether to emit the signal_removed signal (defaults to True)
        """
        if signal_name in self.signals:
            self.signals.remove(signal_name)
            self.selected_signals = []  # Clear selection after removal
            self.update_container_size()
            self.signals_container.update()
            if emit_signal:
                self.signal_removed.emit(signal_name)
                print(f"SelectedSignalsPanel: Removed {signal_name} and emitted signal_removed")
            else:
                print(f"SelectedSignalsPanel: Removed {signal_name} without emitting signal")
    
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
            elif event.type() == QEvent.MouseButtonDblClick:
                return self.handle_mouse_double_click(event)
            elif event.type() == QEvent.MouseMove:
                return self.handle_mouse_move(event)
            elif event.type() == QEvent.MouseButtonRelease:
                return self.handle_mouse_release(event)
            elif event.type() == QEvent.DragEnter:
                print("DragEnter event detected in eventFilter")
                return self.handle_drag_enter(event)
            elif event.type() == QEvent.Drop:
                print("Drop event detected in eventFilter")
                return self.handle_drop(event)
            # Add more event types for debugging
            elif event.type() == QEvent.DragMove:
                print("DragMove event detected in eventFilter")
                # Always accept drag move events to receive drop
                event.acceptProposedAction()
                return True
            elif event.type() == QEvent.DragLeave:
                print("DragLeave event detected in eventFilter")
                self.drag_in_progress = False
                self.signals_container.update()
                return True
                
        return super().eventFilter(obj, event)
    
    def paint_signals(self):
        """Paint the signals on the container."""
        painter = QPainter(self.signals_container)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw background
        painter.fillRect(self.signals_container.rect(), QColor(240, 240, 240))
        
        # If drag is in progress, draw a drop indicator
        if self.drag_in_progress:
            painter.fillRect(self.signals_container.rect(), QColor(220, 240, 255))
            painter.setPen(QPen(QColor(0, 120, 215), 2, Qt.DashLine))
            painter.drawRect(self.signals_container.rect().adjusted(5, 5, -5, -5))
        
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
            
            # Draw signal name with full width (no need to reserve space for indicators)
            text_rect = rect.adjusted(5, 0, -5, 0)
            
            # Draw signal name
            painter.setPen(QPen(QColor(0, 0, 0), 1))
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
                
                # Get the current display mode from the GraphView for this signal
                if not self.main_window or not hasattr(self.main_window, 'graph_view'):
                    # If we can't access graph_view, just show remove option
                    if len(self.selected_signals) == 1:
                        signal_name = self.signals[self.selected_signals[0]]
                        remove_action = menu.addAction(f"Remove Signal '{signal_name}'")
                    else:
                        remove_action = menu.addAction(f"Remove {len(self.selected_signals)} Selected Signals")
                    
                    action = menu.exec_(self.signals_container.mapToGlobal(event.pos()))
                    if action == remove_action:
                        self.remove_selected_signals()
                    return True
                
                # We have access to graph_view
                selected_signal = self.signals[self.selected_signals[0]]
                current_mode = self.main_window.graph_view.get_signal_display_mode(selected_signal)
                
                if len(self.selected_signals) == 1:
                    signal_name = self.signals[self.selected_signals[0]]
                    remove_action = menu.addAction(f"Remove Signal '{signal_name}'")
                    
                    # Add option to toggle display mode
                    if current_mode == "event":
                        mode_action = menu.addAction(f"Display as Waveform")
                    else:
                        mode_action = menu.addAction(f"Display as Events")
                else:
                    remove_action = menu.addAction(f"Remove {len(self.selected_signals)} Selected Signals")
                    # For multiple selections, just show generic options
                    mode_as_wave_action = menu.addAction(f"Display Selected as Waveforms")
                    mode_as_event_action = menu.addAction(f"Display Selected as Events")
                
                action = menu.exec_(self.signals_container.mapToGlobal(event.pos()))
                
                if len(self.selected_signals) == 1:
                    if action == remove_action:
                        self.remove_selected_signals()
                    elif action == mode_action:
                        signal_name = self.signals[self.selected_signals[0]]
                        self.toggle_signal_display_mode(signal_name)
                else:
                    if action == remove_action:
                        self.remove_selected_signals()
                    elif action == mode_as_wave_action:
                        for index in self.selected_signals:
                            signal_name = self.signals[index]
                            self.main_window.graph_view.set_signal_display_mode(signal_name, "wave")
                        self.signals_container.update()
                    elif action == mode_as_event_action:
                        for index in self.selected_signals:
                            signal_name = self.signals[index]
                            self.main_window.graph_view.set_signal_display_mode(signal_name, "event")
                        self.signals_container.update()
                
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
            print(f"Drag enter accepted in SelectedSignalsPanel: {event.mimeData().text()}")
            self.drag_in_progress = True
            self.signals_container.update()  # Repaint to show drop indicator
            event.acceptProposedAction()
            return True
        return False
    
    def handle_drop(self, event):
        """Handle drop events."""
        self.drag_in_progress = False  # Reset drag state
        self.signals_container.update()  # Repaint to remove drop indicator
        
        print("\n=== SelectedSignalsPanel handle_drop START ===")
        if event.mimeData().hasText():
            text_data = event.mimeData().text().strip()
            print(f"Raw text data: '{text_data}'")
            
            # Check if it's multiple signals (separated by newlines)
            if "\n" in text_data:
                # Split by newline and filter out empty strings
                signal_names = [s.strip() for s in text_data.split("\n") if s.strip()]
                print(f"Drop received in SelectedSignalsPanel: {len(signal_names)} signals: {signal_names}")
                
                # Process ALL signals, even if they're already in the panel
                # This ensures they are all hidden from the available panel
                signals_processed = []
                for signal_name in signal_names:
                    if signal_name:
                        # Add to the panel if not already present
                        if signal_name not in self.signals:
                            print(f"  Adding {signal_name} to selected panel")
                            self.add_signal(signal_name)
                        else:
                            print(f"  Signal {signal_name} already in selected panel")
                        # Track all signals for hiding from available panel
                        signals_processed.append(signal_name)
                
                # Notify main window about ALL signals, not just newly added ones
                # This ensures all signals are hidden from the available panel
                if signals_processed and self.main_window:
                    print(f"Notifying main window to handle signals: {signals_processed}")
                    print(f"  Signal type: {type(signals_processed)}")
                    print(f"  Content types: {[type(s) for s in signals_processed]}")
                    print(f"  Is main_window set? {self.main_window is not None}")
                    
                    # Call the method directly with explicit debugging
                    self.main_window.handle_direct_signals_add(signals_processed)
            else:
                # Single signal
                signal_name = text_data
                print(f"Drop received in SelectedSignalsPanel: single signal: '{signal_name}'")
                
                # Make sure we handle the drop
                if signal_name not in self.signals:
                    print(f"  Adding {signal_name} to selected panel")
                    self.add_signal(signal_name)
                else:
                    print(f"  Signal {signal_name} already in selected panel")
                
                # Always notify main window, even if already in panel
                # This ensures the signal is hidden from available panel
                if self.main_window:
                    print(f"Notifying main window to handle signal: '{signal_name}'")
                    print(f"  Is main_window set? {self.main_window is not None}")
                    self.main_window.handle_direct_signals_add([signal_name])
            
            event.acceptProposedAction()
            print("=== SelectedSignalsPanel handle_drop END ===\n")
            return True
        print("=== SelectedSignalsPanel handle_drop: No text mimeData ===\n")
        return False

    def toggle_signal_display_mode(self, signal_name):
        """Toggle the display mode for a signal between 'event' and 'wave'."""
        # Call the GraphView's method to toggle the display mode
        if self.main_window and hasattr(self.main_window, 'graph_view'):
            new_mode = self.main_window.graph_view.toggle_signal_display_mode(signal_name)
            # Update the display to show any visual indicator for the mode
            self.signals_container.update()
            return new_mode
        return None

    def handle_mouse_double_click(self, event):
        """Handle native double-click events."""
        if event.button() == Qt.LeftButton:
            index = self.get_signal_index_at_pos(event.pos())
            if index >= 0:
                # Get the signal name and toggle its display mode
                signal_name = self.signals[index]
                if self.main_window and hasattr(self.main_window, 'graph_view'):
                    self.toggle_signal_display_mode(signal_name)
                    # Don't reset selection to keep selected signals intact
                    return True
        return False

class GraphView(QWidget):
    """Widget for rendering the event-rule graph with interactive signal labels."""
    signals_changed = pyqtSignal(list)  # Emitted when signals are added, removed, or reordered
    signal_added = pyqtSignal(str)      # New signal to notify when a signal is added by drag and drop
    signals_added = pyqtSignal(list)    # New signal for batch adding by drag and drop
    
    # Constants for time units
    TIME_UNITS = {
        "ps": {"factor": 1, "label": "ps"},
        "ns": {"factor": 1000, "label": "ns"},
        "μs": {"factor": 1000000, "label": "μs"},
        "ms": {"factor": 1000000000, "label": "ms"},
        "s": {"factor": 1000000000000, "label": "s"}
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.graph = None
        self.offset_x = 0
        self.scale = 1.0
        self.min_scale = 0.001
        self.max_scale = 10.0
        self.vertical_spacing = 30  # Reduced spacing between signals
        self.top_margin = 22  # Added back 40% of vertical spacing (12px) to previous 10px value
        self.horizontal_margin = 50
        self.node_radius = 5
        self.setMinimumSize(600, 400)
        
        # Set tooltip for the graph view
        self.setToolTip("Double-click on a signal to toggle between Event/Wave view")
        
        # Time unit for display (default: picoseconds)
        self.time_unit = "ps"
        self.time_factor = self.TIME_UNITS[self.time_unit]["factor"]
        
        # Minimum spacing between x-axis labels in pixels
        self.min_label_spacing = 80
        
        # Variables to display
        self.display_variables = []  # List of variables to display in order
        
        # Signal display modes (event or wave)
        self.signal_display_modes = {}  # Maps variable name -> "event" or "wave"
        
        # Timing mode (true or normalized)
        self.normalized_timing = False
        self.normalized_times = []  # List of times in order for normalized view
        self.original_times = []    # List of original times from the file
        self.time_mapping = {}      # Maps original times to normalized times
        
        # For drag and drop visualization
        self.drag_in_progress = False
        
        # Enable mouse tracking and focus
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        
    def set_normalized_timing(self, enabled):
        """Toggle between true timing and normalized timing."""
        if self.normalized_timing == enabled:
            # No change needed
            return
            
        # Store current viewport information before switching
        visible_min_time = self.x_to_time(0)
        visible_max_time = self.x_to_time(self.width())
        visible_center = (visible_min_time + visible_max_time) / 2
        visible_range = visible_max_time - visible_min_time
        
        # Prepare for conversion
        if self.graph and self.graph.transitions:
            # Ensure we have the latest mapping
            if enabled and (not self.normalized_times or not self.time_mapping):
                self.setup_normalized_times()
                
            # Build reverse mapping if needed and not already present
            if not hasattr(self, 'reverse_time_mapping') or not self.reverse_time_mapping:
                self.reverse_time_mapping = {}
                for orig, norm in self.time_mapping.items():
                    self.reverse_time_mapping[norm] = orig
        
            # Calculate the new center position
            if self.normalized_timing and not enabled:
                # Switching from normalized to true timing
                # Find events that straddle the current center
                center_true_time = self.get_original_time(visible_center)
                new_center = center_true_time
            elif not self.normalized_timing and enabled:
                # Switching from true to normalized timing
                # Map the center time to normalized time
                center_normalized_time = self.get_displayed_time(visible_center)
                new_center = center_normalized_time
            else:
                # Fallback - stay centered on the same position
                new_center = visible_center
                
            # Switch the mode
            self.normalized_timing = enabled
            
            # Calculate appropriate scale to maintain similar view area
            if enabled:
                # True → Normalized: Calculate a scale that shows a similar number of events
                if len(self.original_times) > 1:
                    # Normalized time uses fixed 500ps intervals
                    new_time_range = visible_range * (500 / self.get_avg_time_interval())
                    new_scale = self.width() / new_time_range
                else:
                    new_scale = self.scale
            else:
                # Normalized → True: Calculate a scale that shows a similar number of events
                if len(self.original_times) > 1:
                    # Calculate how many events were visible and maintain that
                    new_time_range = visible_range * (self.get_avg_time_interval() / 500)
                    new_scale = self.width() / new_time_range
                else:
                    new_scale = self.scale
            
            # Apply bounds to scale
            new_scale = max(self.min_scale, min(self.max_scale, new_scale))
            
            # Ensure we're not at exactly 0 scale, which would cause divide-by-zero errors
            if new_scale <= 0:
                new_scale = self.min_scale
            
            self.scale = new_scale
            
            # Set the offset to center the view
            self.offset_x = (self.width() / 2) - (new_center * self.scale)
            
            # Quick sanity check - ensure the offset isn't causing the view to go off-screen
            min_time, max_time = 0, 1
            if self.graph:
                if self.normalized_timing:
                    min_time = 0
                    max_time = max(500, (len(self.original_times) - 1) * 500)
                else:
                    min_time, max_time = self.graph.get_min_max_time()
            
            # If the view is completely empty, reset to show everything
            left_time = self.x_to_time(0)
            right_time = self.x_to_time(self.width())
            
            if right_time <= min_time or left_time >= max_time:
                # View is off the timeline, reset
                if self.normalized_timing:
                    self.zoom_to_full_timeline()
                else:
                    self.zoom_to_initial_events()
        else:
            # No graph loaded, just toggle the state
            self.normalized_timing = enabled
        
        # Ensure the display is updated
        self.update()
        
    def get_avg_time_interval(self):
        """Calculate the average time interval between transitions in original time."""
        if not self.original_times or len(self.original_times) < 2:
            return 1
        return (self.original_times[-1] - self.original_times[0]) / (len(self.original_times) - 1)
    
    def setup_normalized_times(self):
        """Create a mapping from original times to normalized (evenly-spaced) times."""
        if not self.graph or not self.graph.transitions:
            # Create empty mappings to avoid errors
            self.original_times = []
            self.normalized_times = []
            self.time_mapping = {}
            self.reverse_time_mapping = {}
            return
            
        # Get all unique times from transitions and sort them
        self.original_times = sorted(set(t.time for t in self.graph.transitions))
        
        # Create normalized times with fixed 500ps spacing
        self.normalized_times = [i * 500 for i in range(len(self.original_times))]
        
        # Create mapping from original to normalized times
        self.time_mapping = dict(zip(self.original_times, self.normalized_times))
        
        # Create reverse mapping (normalized to original)
        self.reverse_time_mapping = {}
        for orig, norm in self.time_mapping.items():
            self.reverse_time_mapping[norm] = orig
        
        # Debug validation - verify all mappings exist
        print(f"Created time mappings with {len(self.original_times)} points")
        if len(self.time_mapping) != len(self.original_times):
            print(f"Warning: time_mapping size ({len(self.time_mapping)}) doesn't match original_times size ({len(self.original_times)})")
        if len(self.reverse_time_mapping) != len(self.normalized_times):
            print(f"Warning: reverse_time_mapping size ({len(self.reverse_time_mapping)}) doesn't match normalized_times size ({len(self.normalized_times)})")
            
    def get_displayed_time(self, time):
        """Get the time value to display, either true or normalized."""
        if self.normalized_timing:
            # Direct lookup if the time is in the mapping
            if time in self.time_mapping:
                return self.time_mapping[time]
            
            # For times not exactly at a transition, interpolate
            if self.original_times:
                # Find the nearest original times before and after
                times_before = [t for t in self.original_times if t <= time]
                times_after = [t for t in self.original_times if t > time]
                
                if times_before and times_after:
                    # Interpolate between the two nearest times
                    t_before = max(times_before)
                    t_after = min(times_after)
                    
                    # Get normalized values for these times
                    norm_before = self.time_mapping[t_before]
                    norm_after = self.time_mapping[t_after]
                    
                    # Calculate position as fraction between t_before and t_after
                    fraction = (time - t_before) / (t_after - t_before)
                    return norm_before + fraction * (norm_after - norm_before)
                elif times_before:
                    # After the last transition, extrapolate based on spacing
                    t_before = max(times_before)
                    return self.time_mapping[t_before] + (time - t_before) / 500 * 500
                elif times_after:
                    # Before the first transition, extrapolate based on spacing
                    t_after = min(times_after)
                    return self.time_mapping[t_after] - (t_after - time) / 500 * 500
            
        return time
        
    def set_time_unit(self, unit):
        """Set the time unit for display."""
        if unit in self.TIME_UNITS:
            self.time_unit = unit
            self.time_factor = self.TIME_UNITS[unit]["factor"]
            self.update()
    
    def set_graph(self, graph):
        """Set the graph to display."""
        self.graph = graph
        if self.graph and self.graph.transitions:
            # Sort transitions by time
            self.graph.transitions.sort(key=lambda t: t.time)
            
            # Initialize normalized times
            self.setup_normalized_times()
            
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
            if self.normalized_timing:
                min_time = 0  # First normalized time is at 0ps
                # Show first 20 events (or fewer if less available)
                num_events = min(20, len(self.original_times))
                # Each event is 500ps apart in normalized mode
                target_time = (num_events - 1) * 500
            else:
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
            if self.normalized_timing:
                min_time = 0  # First normalized time is at 0ps
                # In normalized timing, the max time is (n-1)*500 where n is number of events
                max_time = (len(self.original_times) - 1) * 500
            else:
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
    
    def add_variable(self, variable, batch_operation=False):
        """Add a variable to the display if not already present.
        
        Args:
            variable: The variable name to add
            batch_operation: If True, won't emit signals_changed (to avoid cascading changes)
        """
        if variable not in self.display_variables:
            print(f"GraphView: Adding variable {variable}")
            self.display_variables.append(variable)
            if self.graph:
                self.update_variable_positions()
                self.update()
            
            # Only emit signals_changed if not in a batch operation
            if not batch_operation:
                print(f"GraphView: Emitting signals_changed with {len(self.display_variables)} variables")
                self.signals_changed.emit(self.display_variables)
            else:
                print(f"GraphView: Skipping signals_changed emission (batch operation)")
                
    def add_variables(self, variables):
        """Add multiple variables at once, only emitting signals_changed once at the end."""
        print(f"GraphView: Adding {len(variables)} variables as batch")
        if not variables:
            return
            
        added_any = False
        for variable in variables:
            if variable not in self.display_variables:
                self.display_variables.append(variable)
                added_any = True
                
        if added_any and self.graph:
            self.update_variable_positions()
            self.update()
            
        # Only emit once for all variables
        print(f"GraphView: Emitting signals_changed with {len(self.display_variables)} variables")
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
        displayed_time = self.get_displayed_time(time)
        return displayed_time * self.scale + self.offset_x
    
    def x_to_time(self, x):
        """Convert an x-coordinate to a time value."""
        time = (x - self.offset_x) / self.scale
        return time
        
    def time_to_original(self, time):
        """Convert any time (normalized or not) to original timeline time."""
        if self.normalized_timing:
            return self.get_original_time(time)
        return time
        
    def original_to_display_time(self, time):
        """Convert original time to display time (normalized or not)."""
        if self.normalized_timing:
            return self.get_displayed_time(time)
        return time
    
    def format_time(self, time):
        """Format time value with appropriate unit."""
        if self.normalized_timing:
            # In normalized mode, always show in ps since we're using 500ps spacing
            return f"{int(time)} ps"
        
        if self.time_factor > 1:
            return f"{time / self.time_factor:.2f} {self.TIME_UNITS[self.time_unit]['label']}"
        return f"{time} {self.TIME_UNITS[self.time_unit]['label']}"
    
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
            # If no graph data, show drop target indicator if drag in progress
            if self.drag_in_progress:
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.fillRect(self.rect(), QColor(220, 240, 255))
                painter.setPen(QPen(QColor(0, 120, 215), 2, Qt.DashLine))
                painter.drawRect(self.rect().adjusted(5, 5, -5, -5))
                
                # Draw message
                message_rect = QRectF(0, self.height()/2 - 30, self.width(), 60)
                painter.setPen(QPen(QColor(0, 80, 180), 1))
                painter.drawText(message_rect, Qt.AlignCenter, 
                                "Drop signal here to add to graph")
                painter.end()
                return
            else:
                # Draw empty background if no graph and no drag
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.fillRect(self.rect(), QColor(240, 240, 240))
                message_rect = QRectF(0, self.height()/2 - 30, self.width(), 60)
                painter.setPen(QPen(QColor(100, 100, 100), 1))
                painter.drawText(message_rect, Qt.AlignCenter, 
                               "No file loaded\nUse File > Load .sim File to open a simulation file")
                painter.end()
                return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        try:
            # Draw background
            painter.fillRect(self.rect(), QColor(240, 240, 240))
            
            # If drag is in progress, show drop indicator
            if self.drag_in_progress:
                painter.fillRect(QRectF(0, 0, self.width(), 40), QColor(220, 240, 255))
                painter.setPen(QPen(QColor(0, 120, 215), 2, Qt.DashLine))
                painter.drawRect(QRectF(5, 5, self.width()-10, 30))
                
                # Draw hint text
                painter.setPen(QPen(QColor(0, 80, 180), 1))
                painter.drawText(QRectF(0, 5, self.width(), 30), Qt.AlignCenter, 
                                "Drop signal here to add to graph")
            
            # Get the visible time range for culling
            left_time = self.x_to_time(0)
            right_time = self.x_to_time(self.width())
            time_margin = (right_time - left_time) * 0.1  # 10% margin
            min_visible_time = left_time - time_margin
            max_visible_time = right_time + time_margin
            
            # Determine if we're dealing with the true timing or normalized timing
            if self.normalized_timing:
                # For normalized mode, we use the normalized time values directly
                visible_min_time = min_visible_time
                visible_max_time = max_visible_time
                
                # Get the min/max of original times for informational purposes
                if self.graph:
                    orig_min_time, orig_max_time = self.graph.get_min_max_time()
                else:
                    orig_min_time, orig_max_time = 0, 1
            else:
                # For true timing, use the actual min/max from the graph
                if self.graph:
                    min_time, max_time = self.graph.get_min_max_time()
                else:
                    min_time, max_time = 0, 1
                visible_min_time = max(min_time, min_visible_time)
                visible_max_time = min(max_time, max_visible_time)
            
            # Determine good intervals for time labels based on scale and available width
            time_range = visible_max_time - visible_min_time
            available_width = self.width() - 2 * self.horizontal_margin
            
            # Calculate minimum number of pixels per interval to avoid overlapping labels
            min_pixels_per_interval = self.min_label_spacing
            min_time_per_interval = min_pixels_per_interval / self.scale
            
            # Determine appropriate interval for time markers
            # In normalized mode, use fixed intervals (multiples of 500ps)
            if self.normalized_timing:
                if time_range > 10000:  # > 10ns
                    base_interval = 2500  # 5 * 500ps
                elif time_range > 5000:  # > 5ns
                    base_interval = 1000  # 2 * 500ps
                else:
                    base_interval = 500   # 1 * 500ps
            else:
                # For true timing, use the dynamic approach based on the time range
                if time_range > 100000:
                    base_interval = 10000
                elif time_range > 10000:
                    base_interval = 1000
                elif time_range > 1000:
                    base_interval = 100
                elif time_range > 100:
                    base_interval = 10
                else:
                    base_interval = 5
                
            # Adjust interval to prevent label crowding
            interval = base_interval
            while interval < time_range and (interval * self.scale) < min_pixels_per_interval:
                interval *= 2
                
            # Calculate first time marker
            if self.normalized_timing:
                # For normalized timing, ensure we're starting at a multiple of the interval
                first_time = (int(visible_min_time / interval) * interval)
            else:
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
                
                # Draw time label with appropriate unit
                text_rect = QRectF(x - 50, y_axis_position + 5, 100, 20)
                painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, self.format_time(t))
                
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
            
            # Ensure we have a graph before processing transitions
            if not self.graph or not self.graph.transitions:
                return
                
            # Filter visible transitions for better performance
            visible_transitions = []
            for transition in self.graph.transitions:
                # Skip if variable is not in displayed list (normalized form)
                norm_var = SimFileParser.normalize_variable(transition.variable)
                if norm_var not in self.display_variables:
                    continue
                
                # Get the appropriate time for visibility check based on timing mode
                display_time = self.get_displayed_time(transition.time)
                
                # Skip if not in viewport time range
                if display_time < visible_min_time or display_time > visible_max_time:
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
            
            # First collect all transitions per variable with their display times
            transitions_by_var = {}
            for transition in self.graph.transitions:
                norm_var = SimFileParser.normalize_variable(transition.variable)
                if norm_var not in self.display_variables:
                    continue
                
                if norm_var not in transitions_by_var:
                    transitions_by_var[norm_var] = []
                
                # Store with display time for correct sorting in normalized mode
                display_time = self.get_displayed_time(transition.time)
                transitions_by_var[norm_var].append((transition, display_time))
            
            # Sort transitions by display time for each variable
            for var in transitions_by_var:
                transitions_by_var[var].sort(key=lambda x: x[1])
            
            # Draw waveforms for variables in "wave" mode
            for var in self.display_variables:
                if var not in self.variable_y_positions or var not in transitions_by_var:
                    continue
                
                if self.get_signal_display_mode(var) == "wave":
                    y = self.variable_y_positions[var]
                    
                    # Get transitions for this variable
                    var_transitions = transitions_by_var[var]
                    
                    # Skip if no transitions
                    if not var_transitions:
                        continue
                    
                    # Set pen for waveform
                    painter.setPen(QPen(QColor(0, 0, 0), 2))
                    painter.setBrush(Qt.NoBrush)
                    
                    # Create path for waveform
                    waveform_path = QPainterPath()
                    
                    # Start from beginning of visible area or first transition, whichever is visible first
                    # first_time and last_time are in the appropriate timing mode (normalized or true)
                    first_time = min_visible_time  # Already includes margin
                    last_time = max_visible_time
                    
                    # Calculate the initial state at the beginning of the visible area
                    # Default to 0 (low) if there's no earlier transition
                    initial_state = 0
                    
                    # Find all transitions before the visible area and determine the final state
                    transitions_before_visible = [(t, dt) for t, dt in var_transitions if dt < first_time]
                    if transitions_before_visible:
                        # Get the last transition before the visible area
                        last_before = transitions_before_visible[-1]
                        # Set initial state based on this transition's effect
                        initial_state = 1 if last_before[0].is_rising else 0
                    else:
                        # If no transitions before the visible area, check if the first transition is rising or falling
                        # If the first transition is falling, that implies the signal starts high
                        if var_transitions and not var_transitions[0][0].is_rising:
                            initial_state = 1
                    
                    # Start with the initial state
                    current_state = initial_state
                    
                    # Find start position - use the leftmost visible point
                    start_x = max(0, self.time_to_x(first_time))
                    start_y = y - 8 if current_state == 1 else y + 8  # 8px offset for high/low
                    
                    # Start waveform path
                    waveform_path.moveTo(start_x, start_y)
                    
                    # Add segments for each transition in the visible area
                    for transition, display_time in var_transitions:
                        # Skip transitions before the visible area - we've already accounted for their effect
                        if display_time < first_time:
                            continue
                            
                        # Stop if beyond visible area
                        if display_time > last_time:
                            break
                        
                        # Get x position for this transition using the display time
                        x = self.time_to_x(transition.time)
                        
                        # Draw horizontal segment to transition point
                        waveform_path.lineTo(x, start_y)
                        
                        # Update state and y position
                        current_state = 1 if transition.is_rising else 0
                        start_y = y - 8 if current_state == 1 else y + 8
                        
                        # Draw vertical segment
                        waveform_path.lineTo(x, start_y)
                    
                    # Complete the waveform to the right edge
                    waveform_path.lineTo(self.width(), start_y)
                    
                    # Draw the waveform
                    painter.drawPath(waveform_path)
            
            # First pass: Draw the transition nodes for visible transitions only 
            # but only for signals in "event" mode
            for transition in visible_transitions:
                # Skip if variable is in "wave" mode
                norm_var = SimFileParser.normalize_variable(transition.variable)
                if self.get_signal_display_mode(norm_var) == "wave":
                    continue
                    
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
            # Process all transitions, not just visible ones to ensure links that span the viewport are shown
            for transition in self.graph.transitions:
                # Skip if variable is not in displayed list (normalized form)
                norm_var = SimFileParser.normalize_variable(transition.variable)
                if norm_var not in self.display_variables:
                    continue
                    
                # Skip if variable position is not defined
                if transition.variable not in self.variable_y_positions:
                    continue
                
                # Check if this transition is visible
                display_time = self.get_displayed_time(transition.time)
                target_visible = (visible_min_time <= display_time <= visible_max_time)
                    
                if not target_visible and id(transition) not in visible_transitions_dict:
                    # If target is not visible, we'll check each source later
                    pass
                    
                # Get target coordinates even if not visible
                x = self.time_to_x(transition.time)
                y = self.variable_y_positions[transition.variable]
                
                # Get target display mode
                target_mode = self.get_signal_display_mode(norm_var)
                
                # Draw incoming links (causal dependencies)
                for source in transition.incoming_links:
                    source_norm_var = SimFileParser.normalize_variable(source.variable)
                    if source_norm_var not in self.display_variables:
                        continue
                        
                    if source.variable not in self.variable_y_positions:
                        continue
                    
                    # Get source display mode
                    source_mode = self.get_signal_display_mode(source_norm_var)
                    
                    # For wave signals, only draw arrows coming from event signals
                    if target_mode == "wave" and source_mode == "wave":
                        continue  # Skip arrows between wave signals
                    
                    # Check if source is visible
                    source_display_time = self.get_displayed_time(source.time)
                    source_visible = (visible_min_time <= source_display_time <= visible_max_time)
                    
                    # Skip if both source and target are invisible
                    if not source_visible and not target_visible:
                        continue
                    
                    src_x = self.time_to_x(source.time)
                    src_y = self.variable_y_positions[source.variable]
                    
                    # Adjust target y-position for wave signals based on state
                    if target_mode == "wave":
                        # Determine the state at this transition
                        is_high = transition.is_rising  # If rising, arrow points to low->high transition
                        # For wave signals, we need to adjust the y coordinate
                        # Position the arrowhead at the proper waveform level
                        y = y - 8 if is_high else y + 8  # 8px offset for high/low
                    
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
                    
                    # Get source display mode
                    source_mode = self.get_signal_display_mode(source_norm_var)
                    
                    # For wave signals, only draw arrows coming from event signals
                    if target_mode == "wave" and source_mode == "wave":
                        continue  # Skip arrows between wave signals
                    
                    # Check if source is visible
                    source_display_time = self.get_displayed_time(source.time)
                    source_visible = (visible_min_time <= source_display_time <= visible_max_time)
                    
                    # Skip if both source and target are invisible
                    if not source_visible and not target_visible:
                        continue
                    
                    src_x = self.time_to_x(source.time)
                    src_y = self.variable_y_positions[source.variable]
                    
                    # Adjust target y-position for wave signals based on state
                    if target_mode == "wave":
                        # Determine the state at this transition
                        is_high = transition.is_rising  # If rising, arrow points to low->high transition
                        # For wave signals, we need to adjust the y coordinate
                        y = y - 8 if is_high else y + 8  # 8px offset for high/low
                    
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
        """Handle drag enter events."""
        if event.mimeData().hasText():
            print(f"Drag enter accepted in GraphView: {event.mimeData().text()}")
            self.drag_in_progress = True
            self.update() # Repaint to show drop indicator
            event.acceptProposedAction()
            
    def dragLeaveEvent(self, event):
        """Handle drag leave events."""
        print("DragLeave in GraphView")
        self.drag_in_progress = False
        self.update() # Repaint to remove drop indicator
        
    def dropEvent(self, event):
        """Handle drop events."""
        self.drag_in_progress = False
        self.update() # Repaint to remove drop indicator
        
        if event.mimeData().hasText():
            text_data = event.mimeData().text().strip()
            
            # Check if it's multiple signals (separated by newlines)
            if "\n" in text_data:
                # Split by newline and filter out empty strings
                signal_names = [s.strip() for s in text_data.split("\n") if s.strip()]
                print(f"Drop received in GraphView: {len(signal_names)} signals: {signal_names}")
                
                # Process and emit all signals, even if some were already displayed
                # This ensures they are all hidden from the available signals panel
                signals_processed = []
                for signal_name in signal_names:
                    if signal_name:
                        # Add to graph variables if not already present
                        if signal_name not in self.display_variables:
                            self.add_variable(signal_name)
                        signals_processed.append(signal_name)
                
                # Emit a signal for ALL processed signals, not just newly added ones
                # This ensures all signals are removed from the available panel
                if signals_processed:
                    print(f"GraphView emitting signals_added for: {signals_processed}")
                    self.signals_added.emit(signals_processed)
            else:
                # Single signal
                signal_name = text_data
                print(f"Drop received in GraphView: single signal: {signal_name}")
                
                # Make sure we handle the drop and hide from available signals
                # Always emit the signal, even if already displayed
                if signal_name not in self.display_variables:
                    self.add_variable(signal_name)
                
                # Always emit to ensure the signal is hidden from available panel
                print(f"GraphView emitting signal_added for: {signal_name}")
                self.signal_added.emit(signal_name)
            
            event.acceptProposedAction()
            return True
        return False
        
    def mouseDoubleClickEvent(self, event):
        """Handle double-click to toggle display mode for a variable."""
        if not self.graph or not self.display_variables:
            return
            
        # Find the closest variable to the click position
        for var, y_pos in self.variable_y_positions.items():
            if abs(event.pos().y() - y_pos) < 15:  # Within reasonable range of line
                if var in self.display_variables:
                    # Toggle display mode instead of removing
                    self.toggle_signal_display_mode(var)
                    break
                    
        event.accept()

    def get_original_time(self, normalized_time):
        """Map from normalized time back to original time."""
        if not self.normalized_timing or not self.normalized_times:
            return normalized_time
            
        # Create a reverse mapping dictionary if not already done
        if not hasattr(self, 'reverse_time_mapping') or not self.reverse_time_mapping:
            self.reverse_time_mapping = {}
            for orig, norm in self.time_mapping.items():
                self.reverse_time_mapping[norm] = orig
        
        # Direct lookup if the time is in the reverse mapping
        if normalized_time in self.reverse_time_mapping:
            return self.reverse_time_mapping[normalized_time]
        
        # For times not exactly at a normalized point, interpolate
        if self.normalized_times:
            # Find the nearest normalized times before and after
            times_before = [t for t in self.normalized_times if t <= normalized_time]
            times_after = [t for t in self.normalized_times if t > normalized_time]
            
            if times_before and times_after:
                # Interpolate between the two nearest times
                norm_before = max(times_before)
                norm_after = min(times_after)
                
                # Get original values for these normalized times
                if norm_before in self.reverse_time_mapping and norm_after in self.reverse_time_mapping:
                    orig_before = self.reverse_time_mapping[norm_before]
                    orig_after = self.reverse_time_mapping[norm_after]
                    
                    # Calculate position as fraction between norm_before and norm_after
                    if norm_after > norm_before:  # Prevent division by zero
                        fraction = (normalized_time - norm_before) / (norm_after - norm_before)
                        return orig_before + fraction * (orig_after - orig_before)
                
            # If interpolation fails, try nearest neighbor approach
            if times_before:
                # After the last normalized point, use the last known time
                norm_time = max(times_before)
                if norm_time in self.reverse_time_mapping:
                    return self.reverse_time_mapping[norm_time]
            elif times_after:
                # Before the first normalized point, use the first known time
                norm_time = min(times_after)
                if norm_time in self.reverse_time_mapping:
                    return self.reverse_time_mapping[norm_time]
                
        # If all else fails, use the min time from the graph as a fallback
        if self.graph:
            min_time, _ = self.graph.get_min_max_time()
            return min_time
            
        return normalized_time

    def set_signal_display_mode(self, signal_name, mode):
        """Set the display mode for a signal to either 'event' or 'wave'."""
        if mode in ["event", "wave"]:
            # Only update if we're actually changing the mode
            current_mode = self.get_signal_display_mode(signal_name)
            if current_mode != mode:
                print(f"Setting display mode for {signal_name} to {mode}")
                self.signal_display_modes[signal_name] = mode
                self.update()  # Redraw the graph
            return mode
        return self.get_signal_display_mode(signal_name)
        
    def get_signal_display_mode(self, signal_name):
        """Get the display mode for a signal. Default is 'event'."""
        return self.signal_display_modes.get(signal_name, "event")
        
    def toggle_signal_display_mode(self, signal_name):
        """Toggle the display mode for a signal between 'event' and 'wave'."""
        current_mode = self.get_signal_display_mode(signal_name)
        new_mode = "wave" if current_mode == "event" else "event"
        self.set_signal_display_mode(signal_name, new_mode)
        return new_mode

    def dragMoveEvent(self, event):
        """Handle drag move events."""
        if event.mimeData().hasText():
            print(f"DragMove in GraphView, accepting: {event.mimeData().text()}")
            event.acceptProposedAction()
            
    def dragLeaveEvent(self, event):
        """Handle drag leave events."""
        print("DragLeave in GraphView")
        self.drag_in_progress = False
        self.update() # Repaint to remove drop indicator

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
        graph_layout.setSpacing(0)  # No spacing between signals panel and graph
        
        # Create the selected signals panel (keep its original title)
        self.selected_signals_panel = SelectedSignalsPanel()
        self.selected_signals_panel.layout().setContentsMargins(9, 9, 9, 9)
        self.selected_signals_panel.signal_removed.connect(self.remove_signal)
        self.selected_signals_panel.signals_removed.connect(self.remove_signals)
        self.selected_signals_panel.signals_reordered.connect(self.reorder_signals)
        self.selected_signals_panel.setMinimumWidth(150)
        self.selected_signals_panel.setMaximumWidth(300)
        
        # Create graph view container with timescale control
        graph_view_container = QWidget()
        graph_view_layout = QVBoxLayout(graph_view_container)
        graph_view_layout.setContentsMargins(0, 0, 0, 0)
        graph_view_layout.setSpacing(2)
        
        # Add compact timescale selector above the graph
        timescale_widget = QWidget()
        timescale_layout = QHBoxLayout(timescale_widget)
        timescale_layout.setContentsMargins(5, 5, 5, 0)
        
        timescale_label = QLabel("Timescale:")
        timescale_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        timescale_layout.addWidget(timescale_label)
        
        self.timescale_selector = QComboBox()
        self.timescale_selector.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        for unit in GraphView.TIME_UNITS.keys():
            self.timescale_selector.addItem(unit)
        self.timescale_selector.setCurrentText("ps")  # Default to picoseconds
        self.timescale_selector.currentTextChanged.connect(self.on_timescale_changed)
        timescale_layout.addWidget(self.timescale_selector)
        
        # Add spacing between timescale selector and timing mode toggle
        timescale_layout.addSpacing(15)
        
        # Add timing mode toggle button
        self.timing_mode_button = QPushButton("True Timing")
        self.timing_mode_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.timing_mode_button.setCheckable(True)
        self.timing_mode_button.setChecked(False)
        self.timing_mode_button.clicked.connect(self.toggle_timing_mode)
        timescale_layout.addWidget(self.timing_mode_button)
        
        # Add spacer to push controls to the left
        timescale_layout.addStretch(1)
        
        # Set minimal height for timescale widget
        timescale_widget.setMaximumHeight(30)
        
        graph_view_layout.addWidget(timescale_widget)
        
        # Create the graph view
        self.graph_view = GraphView()
        self.graph_view.signals_changed.connect(self.update_selected_signals)
        self.graph_view.signal_added.connect(self.handle_direct_signal_add)
        self.graph_view.signals_added.connect(self.handle_direct_signals_add)
        # Directly connect panels for better synchronization
        self.graph_view.available_signals_panel = self.available_signals_panel
        graph_view_layout.addWidget(self.graph_view)
        
        # Add panels to the horizontal layout
        graph_layout.addWidget(self.selected_signals_panel)
        graph_layout.addWidget(graph_view_container)
        
        # Add the graph container to the main splitter
        self.main_splitter.addWidget(graph_container)
        
        # Set splitter sizes
        self.main_splitter.setSizes([150, 1050])  # Available signals panel gets 150px, the rest gets 1050px
        graph_layout.setStretch(0, 0)  # Selected signals panel shouldn't stretch
        graph_layout.setStretch(1, 1)  # Graph view should stretch
        
        # Stretch ratios to maximize vertical space for the plot
        graph_view_layout.setStretch(0, 0)  # Timescale widget doesn't stretch
        graph_view_layout.setStretch(1, 1)  # Graph view stretches
        
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
        self.hint_label = QLabel(" | Drag to add/reorder | Double-click to toggle Event/Wave | Ctrl+Click for selection | Shift+Scroll to zoom | Ctrl+I: initial view | Ctrl+F: full view")
        self.statusBar().addWidget(self.hint_label)
        
        # Track the currently loaded graph
        self.current_graph = None
        
        # Register the main window with panels for easier access to graph_view
        self.available_signals_panel.main_window = self
        self.selected_signals_panel.main_window = self
        
    def get_graph_view(self):
        """Return the graph view for components that need to access it."""
        return self.graph_view

    def toggle_timing_mode(self):
        """Toggle between true timing and normalized timing modes."""
        if self.timing_mode_button.isChecked():
            self.timing_mode_button.setText("Normalized (500ps)")
            self.graph_view.set_normalized_timing(True)
        else:
            self.timing_mode_button.setText("True Timing")
            self.graph_view.set_normalized_timing(False)
            
    def on_timescale_changed(self, unit):
        """Handle timescale selection change."""
        self.graph_view.set_time_unit(unit)

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
        """Update the selected signals panel with the given list of signals.

        Args:
            signals: List of signal names to update the selected signals panel with.
        """
        print(f"\n=== MainWindow.update_selected_signals ===")
        print(f"Updating selected signals panel with: {signals}")

        # Add missing signals
        for signal in signals:
            if signal not in self.selected_signals_panel.signals:
                print(f"  Adding missing signal to panel: {signal}")
                self.selected_signals_panel.add_signal(signal)

        # Remove signals that are no longer in the graph view
        signals_to_remove = [s for s in self.selected_signals_panel.signals if s not in signals]
        for signal in signals_to_remove:
            print(f"  Removing signal from panel: {signal}")
            self.selected_signals_panel.remove_signal(signal, emit_signal=False)
        
        print(f"=== End update_selected_signals ===\n")

    def handle_direct_signal_add(self, signal_name):
        """Handle when a signal is added directly to the graph via drag and drop."""
        # Hide the signal from available signals panel
        print(f"MainWindow hiding signal from available panel: {signal_name}")
        self.available_signals_panel.hide_signal(signal_name)
        
        # Add to the selected signals panel if not already there
        if signal_name not in self.selected_signals_panel.signals:
            print(f"  Adding signal to selected panel: {signal_name}")
            self.selected_signals_panel.add_signal(signal_name)
        else:
            print(f"  Signal already in selected panel: {signal_name}")
        
        # Add to the graph view if not already there
        if signal_name not in self.graph_view.display_variables:
            print(f"  Adding signal to graph view: {signal_name}")
            self.graph_view.add_variable(signal_name)
        else:
            print(f"  Signal already in graph view: {signal_name}")
            
        # Note: For future maintainability, consider using handle_direct_signals_add([signal_name])
        # instead of duplicating logic

    def handle_direct_signals_add(self, signal_names):
        """Handle signals being added directly from the available signals panel or by drag-drop.
        
        This version handles multiple signals being added at once, which is important for batch operations.
        
        Args:
            signal_names: List of signal names to add
        """
        print(f"\n=== MainWindow.handle_direct_signals_add START ===")
        print(f"Signal names received: {signal_names}")
        print(f"  Type: {type(signal_names)}")
        
        # Validate that we received a list
        if not isinstance(signal_names, list):
            print(f"  WARNING: Expected list but got {type(signal_names)}")
            if isinstance(signal_names, str):
                print(f"  Converting string to list: {signal_names}")
                signal_names = [signal_names]
            else:
                print(f"  ERROR: Cannot process {type(signal_names)}")
                return
        
        print(f"  Processing {len(signal_names)} signals")
        
        # Hide all signals from the available signals panel
        print(f"MainWindow hiding multiple signals from available panel: {signal_names}")
        
        # Force debug state before making changes
        print("Before hiding signals:")
        self.available_signals_panel.debug_state()
        
        # Use the new force_hide_signals method instead of hide_signals
        print(f"Calling force_hide_signals with: {signal_names}")
        self.available_signals_panel.force_hide_signals(signal_names)
        
        # First, add all signals to the selected signals panel
        for signal_name in signal_names:
            if signal_name not in self.selected_signals_panel.signals:
                print(f"  Adding signal to selected panel: {signal_name}")
                self.selected_signals_panel.add_signal(signal_name)
            else:
                print(f"  Signal already in selected panel: {signal_name}")
        
        # Then add all signals to the graph view as a batch operation
        # This prevents multiple signals_changed emissions that could cause cascading issues
        print(f"  Adding all signals to graph view as batch")
        new_signals = [s for s in signal_names if s not in self.graph_view.display_variables]
        if new_signals:
            self.graph_view.add_variables(new_signals)
        else:
            print(f"  No new signals to add to graph view")
                
        # Force debug state after making changes
        print("After hiding signals:")
        self.available_signals_panel.debug_state()
        print("=== MainWindow.handle_direct_signals_add END ===\n")

# Add a custom QListWidget that properly handles drag operations

# Add a custom QListWidget that properly handles drag operations
class DraggableListWidget(QListWidget):
    """Enhanced QListWidget with improved drag capabilities."""
    
    def startDrag(self, supportedActions):
        """Override startDrag to ensure proper MIME data is set."""
        # Get the selected items
        items = self.selectedItems()
        if not items:
            print("No items selected for drag")
            return
            
        # Create mime data
        mime_data = QMimeData()
        
        # If only one item is selected, use simple text format
        if len(items) == 1:
            mime_data.setText(items[0].text())
            print(f"Starting drag with signal: {items[0].text()}")
        else:
            # For multiple items, create a list of signal names
            signal_names = [item.text() for item in items]
            # Store as text with newline separators for parsing on drop
            mime_data.setText("\n".join(signal_names))
            print(f"Starting drag with {len(signal_names)} signals: {signal_names}")
        
        # Create drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        
        # Print debug info before starting drag
        print(f"MIME data has text: {mime_data.hasText()}")
        print(f"MIME data text content: {mime_data.text()}")
        
        # Start the drag operation
        result = drag.exec_(supportedActions)
        
        # Print debug info
        print(f"Drag completed with result: {result}")
        print(f"Result meaning: {'Drop was accepted' if result == Qt.DropAction.MoveAction else 'Drop was not accepted or cancelled'}")

    def dragMoveEvent(self, event):
        """Override to ensure drag move events are always accepted."""
        if event.mimeData().hasText():
            print(f"DragMove in list widget, accepting: {event.mimeData().text()}")
            event.acceptProposedAction()
        super().dragMoveEvent(event)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 