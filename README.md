# Event-Rule System Viewer

> [!WARNING]  
> This is an AI generated prototype. Absolutely no real engineering has gone into making this.

A Python Qt application for visualizing event-rule systems as directed acyclic graphs (DAGs). This application renders transitions and their causal dependencies with time on the x-axis.

## Features

- Load and parse .sim files containing event-rule system data
- Visualize transitions as nodes and causal dependencies as directed edges
- Distinguish between regular causal links and timing assumptions (shown in different colors)
- Horizontal scrolling with the mouse wheel
- Zoom in/out with Shift + mouse wheel
- Time-based visualization with the x-axis representing time

## Installation

1. Make sure you have Python 3.6+ installed
2. Clone this repository
3. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:

```bash
python3 event_rule_viewer.py
```

2. Click the "Load .sim File" button to open a .sim file
3. Navigate the graph:
   - Use the mouse wheel to scroll horizontally
   - Hold Shift + use the mouse wheel to zoom in/out

## .sim File Format

The application expects .sim files with the following format:

```
<time> <guard_expression>-><transition> {<assumption>}
```

Where:
- `<time>` is an integer timestamp
- `<guard_expression>` is a boolean expression using variables and operators:
  - `~x` represents negation (NOT)
  - `&` represents conjunction (AND)
- `<transition>` is in the form of `<variable><edge>` where:
  - `<variable>` is a variable name
  - `<edge>` is either `+` (rising) or `-` (falling)
- `{<assumption>}` (optional) contains timing assumptions

Example:
```
149575 ~R.f->L.e+
149981 L.e'1->v0- {v1}
163366 ~v0&~L.e'1->v1+
```

## Understanding the Visualization

- Green nodes represent rising transitions (x+)
- Red nodes represent falling transitions (x-)
- Blue arrows represent causal links
- Orange dashed arrows represent timing assumptions

## License

MIT 
