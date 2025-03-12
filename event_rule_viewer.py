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
        layout.addWidget(self.available_signals)
        
        # Add button to add signals
        add_button = QPushButton("Add Selected Signal(s)")
        add_button.clicked.connect(self.add_selected_signals)
        layout.addWidget(add_button)
        
        # Set size policy - Fix: use QSizePolicy instead of QSplitter.Policy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
    def set_available_signals(self, signals):
        """Set the list of available signals."""
        self.available_signals.clear()
        for signal in sorted(signals):
            self.available_signals.addItem(signal)
            
    def add_selected_signals(self):
        """Add selected signals to the graph view."""
        for item in self.available_signals.selectedItems():
            self.signal_added.emit(item.text())

class GraphView(QWidget):
    """Widget for rendering the event-rule graph with interactive signal labels."""
    signals_changed = pyqtSignal(list)  # Emitted when signals are added, removed, or reordered
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.graph = None
        self.offset_x = 0
        self.scale = 1.0
        self.min_scale = 0.001
        self.max_scale = 10.0
        self.vertical_spacing = 50
        self.horizontal_margin = 120  # Increased to provide space for signal names and interaction
        self.node_radius = 5
        self.setMinimumSize(600, 400)
        
        # Variables to display
        self.display_variables = []  # List of variables to display in order
        
        # For signal label interaction
        self.dragging_label = None
        self.drag_start_pos = None
        self.drag_current_index = -1
        self.label_rects = {}  # Maps variable names to their label rectangles
        
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
            
            # Reset view
            min_time, max_time = self.graph.get_min_max_time()
            self.scale = (self.width() - 2 * self.horizontal_margin) / (max(1, max_time - min_time))
            self.offset_x = -min_time * self.scale + self.horizontal_margin
            
            self.update_variable_positions()
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
        self.label_rects = {}
        
        # Map for original and normalized variable names
        for i, var in enumerate(self.display_variables):
            y_pos = i * self.vertical_spacing + 50
            self.variable_y_positions[var] = y_pos
            
            # Store the label rectangle for interaction
            self.label_rects[var] = QRectF(5, y_pos - 15, self.horizontal_margin - 15, 30)
            
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
        
    def get_variable_at_position(self, pos):
        """Get the variable at the given position, or None if none is found."""
        for var, rect in self.label_rects.items():
            if rect.contains(pos):
                return var
        return None
    
    def get_variable_index(self, variable):
        """Get the index of a variable in the display list."""
        if variable in self.display_variables:
            return self.display_variables.index(variable)
        return -1
        
    def get_variable_index_at_y(self, y):
        """Get the index of the variable at or nearest to the given y-coordinate."""
        if not self.display_variables:
            return 0
            
        # Find the nearest variable based on y-position
        distances = [(abs(self.variable_y_positions[var] - y), i) 
                    for i, var in enumerate(self.display_variables)]
        distances.sort()
        
        # Return the index of the closest variable
        return distances[0][1]
    
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
            
            # Draw horizontal guide lines (behind nodes and arcs)
            painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DashLine))
            for var in self.display_variables:
                if var not in self.variable_y_positions:
                    continue
                    
                y = self.variable_y_positions[var]
                painter.drawLine(QLineF(self.horizontal_margin - 5, y, self.width(), y))
            
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
            
            # Second pass: Draw the links/arrows only for visible transitions
            for transition in visible_transitions:
                x = self.time_to_x(transition.time)
                y = self.variable_y_positions[transition.variable]
                
                # Draw incoming links (causal dependencies) only if source is displayed and visible
                for source in transition.incoming_links:
                    source_norm_var = SimFileParser.normalize_variable(source.variable)
                    if source_norm_var not in self.display_variables:
                        continue
                        
                    if source.variable not in self.variable_y_positions:
                        continue
                    
                    # Skip links from transitions outside of the visible range
                    if source.time < min_visible_time:
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
                    
                    # Draw arrowhead
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
                    
                    # Skip links from transitions outside of the visible range
                    if source.time < min_visible_time:
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
                    
                    # Draw arrowhead
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
            
            # Draw Y-axis signal labels as a single continuous block
            if self.display_variables:
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                font = QFont("Arial", 10)
                painter.setFont(font)
                
                # Calculate the overall area for the signal block
                if len(self.display_variables) > 0:
                    # Find the top and bottom y positions
                    top_vars = [var for var in self.display_variables if var in self.variable_y_positions]
                    if top_vars:  # Only proceed if we have valid variables
                        min_y = min(self.variable_y_positions[var] - 15 for var in top_vars)
                        max_y = max(self.variable_y_positions[var] + 15 for var in top_vars)
                        
                        # Create the overall background rectangle for all signals
                        signal_block_rect = QRectF(5, min_y, self.horizontal_margin - 10, max_y - min_y)
                        
                        # Draw a unified background with a slight border
                        background_color = QColor(240, 240, 240, 245)  # Slightly transparent light gray
                        border_color = QColor(120, 120, 120)
                        
                        painter.setBrush(QBrush(background_color))
                        painter.setPen(QPen(border_color, 1))
                        painter.drawRect(signal_block_rect)
                        
                        # Draw light divider lines between signal names for better readability
                        painter.setPen(QPen(QColor(200, 200, 200), 1))
                        for var in self.display_variables[:-1]:  # All but the last
                            if var in self.variable_y_positions:
                                y = self.variable_y_positions[var] + 15  # Bottom of this signal's area
                                painter.drawLine(QLineF(5, y, self.horizontal_margin - 5, y))
                        
                        # Draw each signal name
                        painter.setPen(QPen(QColor(0, 0, 0), 1))
                        for var in self.display_variables:
                            if var in self.variable_y_positions:
                                y = self.variable_y_positions[var]
                                
                                # Highlight dragging with a different background for just that signal
                                if self.dragging_label == var:
                                    highlight_rect = QRectF(5, y - 15, self.horizontal_margin - 10, 30)
                                    painter.fillRect(highlight_rect, QColor(200, 220, 255, 245))
                                
                                # Draw the signal name
                                text_rect = QRectF(10, y - 10, self.horizontal_margin - 15, 20)
                                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, var)
        finally:
            # Ensure painter is ended properly
            painter.end()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            variable = self.get_variable_at_position(event.pos())
            if variable:
                self.dragging_label = variable
                self.drag_start_pos = event.pos()
                self.drag_current_index = self.get_variable_index(variable)
                self.update()
        elif event.button() == Qt.RightButton:
            # Context menu for labels
            variable = self.get_variable_at_position(event.pos())
            if variable:
                menu = QMenu(self)
                remove_action = menu.addAction("Remove Signal")
                action = menu.exec_(self.mapToGlobal(event.pos()))
                
                if action == remove_action:
                    self.remove_variable(variable)
    
    def mouseMoveEvent(self, event):
        if self.dragging_label and event.buttons() & Qt.LeftButton:
            if (event.pos() - self.drag_start_pos).manhattanLength() > 10:
                # Update position during drag
                target_index = self.get_variable_index_at_y(event.pos().y())
                
                # Only update if moving to a different position
                if target_index != self.drag_current_index and target_index >= 0:
                    self.move_variable(self.drag_current_index, target_index)
                    self.drag_current_index = target_index
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging_label:
            self.dragging_label = None
            self.drag_start_pos = None
            self.update()
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        if event.mimeData().hasText():
            signal_name = event.mimeData().text()
            target_index = self.get_variable_index_at_y(event.pos().y())
            
            # Add at the target position
            if signal_name not in self.display_variables:
                if target_index >= 0 and target_index < len(self.display_variables):
                    self.display_variables.insert(target_index, signal_name)
                else:
                    self.display_variables.append(signal_name)
                
                self.update_variable_positions()
                self.update()
                self.signals_changed.emit(self.display_variables)
    
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
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Create a splitter for available signals panel and graph view
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)
        
        # Create the available signals panel
        self.available_signals_panel = AvailableSignalsPanel()
        self.available_signals_panel.signal_added.connect(self.add_signal)
        self.splitter.addWidget(self.available_signals_panel)
        
        # Create the graph view
        self.graph_view = GraphView()
        self.splitter.addWidget(self.graph_view)
        
        # Set splitter sizes for a more compact left panel
        self.splitter.setSizes([200, 1000])  # Left panel 200px, graph view 1000px
        
        # Create a menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        
        # Add load action to the menu
        load_action = file_menu.addAction("Load .sim File")
        load_action.triggered.connect(self.load_sim_file)
        
        # Update file label to be part of the status bar
        self.file_label = QLabel("No file loaded")
        self.statusBar().addWidget(self.file_label)
        
        # Add help text to the status bar
        self.hint_label = QLabel(" | Right-click signal labels to remove | Drag signal labels to reorder")
        self.statusBar().addWidget(self.hint_label)
        
        # Track the currently loaded graph
        self.current_graph = None

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
        """Add a signal to the graph view."""
        self.graph_view.add_variable(signal_name)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 