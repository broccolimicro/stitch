#!/usr/bin/env python3
import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QFileDialog, QPushButton, QLabel, 
                           QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
                           QToolButton, QGroupBox, QScrollArea)
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PyQt5.QtCore import Qt, QRectF, QPointF, QLineF, pyqtSignal

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

class SignalListWidget(QListWidget):
    """Widget for displaying and selecting signals."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

class SignalSelector(QWidget):
    """Widget for selecting and organizing signals to be displayed."""
    signal_selection_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        
        # Create the available signals list
        available_group = QGroupBox("Available Signals")
        available_layout = QVBoxLayout(available_group)
        self.available_signals = QListWidget()
        self.available_signals.setSelectionMode(QAbstractItemView.ExtendedSelection)
        available_layout.addWidget(self.available_signals)
        
        # Add button to add signals
        add_button = QPushButton("Add →")
        add_button.clicked.connect(self.add_selected_signals)
        available_layout.addWidget(add_button)
        
        # Create the selected signals list
        selected_group = QGroupBox("Selected Signals")
        selected_layout = QVBoxLayout(selected_group)
        self.selected_signals = SignalListWidget()
        self.selected_signals.model().rowsMoved.connect(self.signal_selection_changed.emit)
        selected_layout.addWidget(self.selected_signals)
        
        # Add remove and reorder buttons
        button_layout = QHBoxLayout()
        
        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(self.remove_selected_signals)
        button_layout.addWidget(remove_button)
        
        move_up_button = QToolButton()
        move_up_button.setText("▲")
        move_up_button.clicked.connect(self.move_signals_up)
        button_layout.addWidget(move_up_button)
        
        move_down_button = QToolButton()
        move_down_button.setText("▼")
        move_down_button.clicked.connect(self.move_signals_down)
        button_layout.addWidget(move_down_button)
        
        selected_layout.addLayout(button_layout)
        
        # Add the groups to the main layout
        layout.addWidget(available_group)
        layout.addWidget(selected_group)
        
    def set_available_signals(self, signals):
        """Set the list of available signals."""
        self.available_signals.clear()
        for signal in sorted(signals):
            self.available_signals.addItem(signal)
            
    def add_selected_signals(self):
        """Add selected signals from available to selected list."""
        for item in self.available_signals.selectedItems():
            signal_name = item.text()
            # Check if it's already in the selected list
            existing_items = self.selected_signals.findItems(signal_name, Qt.MatchExactly)
            if not existing_items:
                self.selected_signals.addItem(signal_name)
        self.signal_selection_changed.emit()
                
    def remove_selected_signals(self):
        """Remove selected signals from the selected list."""
        for item in self.selected_signals.selectedItems():
            self.selected_signals.takeItem(self.selected_signals.row(item))
        self.signal_selection_changed.emit()
        
    def move_signals_up(self):
        """Move selected signals up in the selected list."""
        for i in range(self.selected_signals.count()):
            item = self.selected_signals.item(i)
            if item.isSelected() and i > 0:
                # Check if item above is not selected (to avoid moving a block)
                if not self.selected_signals.item(i-1).isSelected():
                    # Take item and insert above
                    taken_item = self.selected_signals.takeItem(i)
                    self.selected_signals.insertItem(i-1, taken_item)
                    taken_item.setSelected(True)
        self.signal_selection_changed.emit()
                    
    def move_signals_down(self):
        """Move selected signals down in the selected list."""
        for i in range(self.selected_signals.count()-1, -1, -1):
            item = self.selected_signals.item(i)
            if item.isSelected() and i < self.selected_signals.count()-1:
                # Check if item below is not selected (to avoid moving a block)
                if not self.selected_signals.item(i+1).isSelected():
                    # Take item and insert below
                    taken_item = self.selected_signals.takeItem(i)
                    self.selected_signals.insertItem(i+1, taken_item)
                    taken_item.setSelected(True)
        self.signal_selection_changed.emit()
                    
    def get_selected_signals(self):
        """Get the list of selected signals in order."""
        signals = []
        for i in range(self.selected_signals.count()):
            signals.append(self.selected_signals.item(i).text())
        return signals

class GraphView(QWidget):
    """Widget for rendering the event-rule graph."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.graph = None
        self.offset_x = 0
        self.scale = 1.0
        self.min_scale = 0.001
        self.max_scale = 10.0
        self.vertical_spacing = 50
        self.horizontal_margin = 80  # Increased to provide space for signal names
        self.node_radius = 5
        self.setMinimumSize(600, 400)
        
        # Variables to display
        self.display_variables = []  # List of variables to display in order
        
        # Enable mouse tracking and focus
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        
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
    
    def update_variable_positions(self):
        """Update the y-positions of variables based on the display list."""
        if not self.graph:
            return
            
        self.variable_y_positions = {}
        
        # Map for original and normalized variable names
        for i, var in enumerate(self.display_variables):
            y_pos = i * self.vertical_spacing + 50
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
    
    def paintEvent(self, event):
        if not self.graph or not self.graph.transitions or not self.display_variables:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        try:
            # Draw background
            painter.fillRect(self.rect(), QColor(240, 240, 240))
            
            # Draw Y-axis signal names
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            font = QFont("Arial", 10)
            painter.setFont(font)
            
            for var in self.display_variables:
                if var not in self.variable_y_positions:
                    continue
                    
                y = self.variable_y_positions[var]
                # Draw variable name aligned to the left
                text_rect = QRectF(5, y - 10, self.horizontal_margin - 10, 20)
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, var)
                
                # Draw horizontal guide line
                painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DashLine))
                # Use QLineF for float coordinates
                painter.drawLine(QLineF(self.horizontal_margin - 5, y, self.width(), y))
                painter.setPen(QPen(QColor(0, 0, 0), 1))
            
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
            
            # First pass: Draw the transition nodes for displayed variables only
            for transition in self.graph.transitions:
                # Skip if variable is not in displayed list (normalized form)
                norm_var = SimFileParser.normalize_variable(transition.variable)
                if norm_var not in self.display_variables:
                    continue
                    
                # Skip if variable position is not defined
                if transition.variable not in self.variable_y_positions:
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
            
            # Second pass: Draw the links/arrows only for displayed variables
            for transition in self.graph.transitions:
                # Skip if variable is not in displayed list (normalized form)
                norm_var = SimFileParser.normalize_variable(transition.variable)
                if norm_var not in self.display_variables:
                    continue
                    
                # Skip if variable position is not defined
                if transition.variable not in self.variable_y_positions:
                    continue
                
                x = self.time_to_x(transition.time)
                y = self.variable_y_positions[transition.variable]
                
                # Draw incoming links (causal dependencies) only if source is displayed
                for source in transition.incoming_links:
                    source_norm_var = SimFileParser.normalize_variable(source.variable)
                    if source_norm_var not in self.display_variables:
                        continue
                        
                    if source.variable not in self.variable_y_positions:
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
        
        # Create a splitter for signal selector and graph view
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)
        
        # Create the signal selector
        self.signal_selector = SignalSelector()
        self.signal_selector.signal_selection_changed.connect(self.update_displayed_signals)
        self.splitter.addWidget(self.signal_selector)
        
        # Create the graph view
        self.graph_view = GraphView()
        self.splitter.addWidget(self.graph_view)
        
        # Set splitter sizes
        self.splitter.setSizes([300, 900])  # Left sidebar 300px, graph view 900px
        
        # Create a menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        
        # Add load action to the menu
        load_action = file_menu.addAction("Load .sim File")
        load_action.triggered.connect(self.load_sim_file)
        
        # Update file label to be part of the status bar
        self.file_label = QLabel("No file loaded")
        self.statusBar().addWidget(self.file_label)
        
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
                self.signal_selector.set_available_signals(self.current_graph.all_variables)
                
                # Set the graph in the view (initially without any signals displayed)
                self.graph_view.set_graph(self.current_graph)
                
                self.file_label.setText(os.path.basename(filename))
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.file_label.setText(f"Error loading file: {str(e)}")
                
    def update_displayed_signals(self):
        """Update which signals are displayed in the graph view."""
        if self.current_graph:
            selected_signals = self.signal_selector.get_selected_signals()
            self.graph_view.set_display_variables(selected_signals)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 