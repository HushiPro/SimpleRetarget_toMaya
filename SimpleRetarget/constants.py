"""
Style constants, colors, and sizing for the retargeting tool UI.
"""
from collections import OrderedDict

COLORS = {
    'bg':               '#1b1b1b',
    'panel_bg':         '#232323',
    'node_bone':        '#3a6b8a',
    'node_bone_hover':  '#4a8baa',
    'node_curve':       '#8a6b3a',
    'node_curve_hover': '#aa8b4a',
    'node_locator':     '#5b8a3a',
    'node_locator_hover': '#71a84a',
    'node_selected':    '#4a90d9',
    'node_ik_inactive': '#444444',
    'node_fk_inactive': '#444444',
    'edge':             '#555555',
    'slot_bg':          '#2d2d2d',
    'slot_border':      '#555555',
    'slot_source':      '#4a7a9a',
    'slot_target':      '#9a7a4a',
    'text':             '#cccccc',
    'text_bright':      '#ffffff',
    'text_dim':         '#777777',
    'accent':           '#4a90d9',
    'node_connected_border': '#5cb85c',
    'node_connected_bg':     '#1a1a1a',
}

# Hypergraph nodes
NODE_WIDTH = 200
NODE_HEIGHT = 56
NODE_RADIUS = 10

# Hypergraph layout — horizontal tree (root left → children right)
GRAPH_DEPTH_GAP = 60        # horizontal gap between depth columns
GRAPH_SIBLING_GAP = 14      # vertical gap between sibling nodes

# Matching-panel slots
SLOT_WIDTH = 340
SLOT_HEIGHT = 48
SLOT_DEPTH_GAP = 64         # vertical gap between slot depth levels
SLOT_SIBLING_GAP = 30       # horizontal gap between sibling slots

MAYA_COLOR_INDEX = OrderedDict([
    (13, "red"), (18, "cyan"), (14, "lime"), (17, "yellow"),
])

MAIN_STYLESHEET = """
    QDialog { background-color: #282828; }
    QLabel { color: #cccccc; }
    QCheckBox { color: #cccccc; spacing: 6px; }
    QCheckBox::indicator { width: 14px; height: 14px; }
    QRadioButton { color: #cccccc; spacing: 6px; }
    QLineEdit {
        background-color: #333333; color: #cccccc;
        border: 1px solid #444444; border-radius: 3px;
        padding: 4px 8px;
    }
    QPushButton {
        background-color: #3a3a3a; color: #cccccc;
        border: 1px solid #555555; border-radius: 4px;
        padding: 5px 12px;
    }
    QPushButton:hover { background-color: #4a4a4a; }
    QPushButton:pressed { background-color: #2a2a2a; }
    QSplitter::handle { background-color: #333333; }
"""
