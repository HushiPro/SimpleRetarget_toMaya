"""
Core retargeting logic — constraint creation, baking, hierarchy collection,
IK/FK detection, and data models.  No Qt dependency.
"""
import maya.cmds as cmds
import maya.mel

from .constants import MAYA_COLOR_INDEX

PLUGIN_CONSTRAINT_ATTR = "RetargetConstraint"
PLUGIN_TARGET_ATTR = "RetargetTargetNode"
PLUGIN_DRIVER_ATTR = "RetargetDriverNode"
GENERATED_CONSTRAINT_TYPES = (
    "parentConstraint",
    "orientConstraint",
    "pointConstraint",
)


# ------------------------------------------------------------------ data models

class NodeData:
    """Represents a bone or curve controller in the hierarchy."""

    def __init__(self, name, node_type='joint', parent_name=None):
        self.name = name
        self.node_type = node_type      # 'joint' | 'curve' | 'locator'
        self.parent_name = parent_name
        self.children = []
        self.depth = 0
        self.is_ik = False
        self.ik_fk_value = -1.0         # -1 = no switch, 0 = IK active, 1 = FK active
        self.ik_fk_attr = None


class SlotData:
    """Represents a matching slot that maps a source node to a target node."""

    def __init__(self, source_node_name, parent_slot=None):
        self.source_node = source_node_name
        self.target_node = None
        self.parent_slot = parent_slot
        self.children = []
        self.is_ik = False              # per-slot IK connection mode
        # None = use global checkbox; True/False = per-slot override
        self.rotation_override = None
        self.translation_override = None


def _ensure_string_attr(node, attr_name):
    if not cmds.attributeQuery(attr_name, node=node, exists=True):
        cmds.addAttr(node, longName=attr_name, dataType="string")


def _get_string_attr(node, attr_name):
    if not cmds.objExists(node):
        return ""
    if not cmds.attributeQuery(attr_name, node=node, exists=True):
        return ""
    try:
        return cmds.getAttr("{}.{}".format(node, attr_name)) or ""
    except Exception:
        return ""


def _mark_generated_constraint(constraint_node, target_node=None, driver_node=None):
    """Tag a Maya constraint so the UI can manage it later."""
    if isinstance(constraint_node, (list, tuple)):
        constraint_node = constraint_node[0] if constraint_node else None
    if not constraint_node or not cmds.objExists(constraint_node):
        return None

    if not cmds.attributeQuery(PLUGIN_CONSTRAINT_ATTR, node=constraint_node, exists=True):
        cmds.addAttr(
            constraint_node, longName=PLUGIN_CONSTRAINT_ATTR, attributeType="bool")
    cmds.setAttr("{}.{}".format(constraint_node, PLUGIN_CONSTRAINT_ATTR), 1)

    _ensure_string_attr(constraint_node, PLUGIN_TARGET_ATTR)
    cmds.setAttr(
        "{}.{}".format(constraint_node, PLUGIN_TARGET_ATTR),
        target_node or "", type="string")

    _ensure_string_attr(constraint_node, PLUGIN_DRIVER_ATTR)
    cmds.setAttr(
        "{}.{}".format(constraint_node, PLUGIN_DRIVER_ATTR),
        driver_node or "", type="string")
    return constraint_node


# --------------------------------------------------- scene queries

def get_connect_nodes():
    """Find all connection nodes (locators with ConnectNode attr) in the scene."""
    nodes = []
    for n in cmds.ls():
        if cmds.attributeQuery("ConnectNode", node=n, exists=True):
            nodes.append(n)
    return nodes


def get_connected_ctrls():
    """Find all controllers with a ConnectedCtrl attr in the scene."""
    ctrls = []
    for n in cmds.ls():
        if cmds.attributeQuery("ConnectedCtrl", node=n, exists=True):
            ctrls.append(n)
    return ctrls


def _iter_constraint_children(node):
    """Yield constraint children under *node*."""
    children = cmds.listRelatives(node, children=True) or []
    for child in children:
        if cmds.objExists(child) and cmds.objectType(child, isAType='constraint'):
            yield child


def _get_driver_nodes_for_target(target_ctrl):
    """Return generated locator nodes that drive *target_ctrl*."""
    if not cmds.objExists(target_ctrl):
        return set()
    if not cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
        return set()

    connect_nodes = cmds.listConnections(
        target_ctrl + ".ConnectedCtrl", source=True, destination=False) or []
    driver_set = set()
    for node in connect_nodes:
        if cmds.objExists(node):
            driver_set.add(node)
            driver_set.update(cmds.listRelatives(node, allDescendents=True) or [])
    return driver_set


def _target_has_generated_constraints(target_ctrl):
    """Return whether *target_ctrl* still has any plugin-generated constraints."""
    driver_set = _get_driver_nodes_for_target(target_ctrl)
    if not driver_set:
        return False

    for constraint in _iter_constraint_children(target_ctrl):
        if cmds.attributeQuery(PLUGIN_CONSTRAINT_ATTR, node=constraint, exists=True):
            return True
        sources = set(cmds.listConnections(
            constraint, source=True, destination=False) or [])
        if sources & driver_set:
            return True
    return False


def _build_constraint_info(constraint_node, fallback_target=None, tagged=False):
    target_node = (
        _get_string_attr(constraint_node, PLUGIN_TARGET_ATTR)
        or fallback_target
        or ((cmds.listRelatives(constraint_node, parent=True) or [""])[0])
    )
    source_nodes = sorted(set(
        cmds.listConnections(constraint_node, source=True, destination=False) or []
    ))
    return {
        "name": constraint_node,
        "type": cmds.nodeType(constraint_node),
        "target_node": target_node,
        "source_nodes": source_nodes,
        "tagged": tagged,
    }


def get_generated_constraints_info():
    """List constraints generated by this tool for UI management."""
    info_by_name = {}

    for constraint in cmds.ls(type=list(GENERATED_CONSTRAINT_TYPES)) or []:
        if cmds.attributeQuery(PLUGIN_CONSTRAINT_ATTR, node=constraint, exists=True):
            info_by_name[constraint] = _build_constraint_info(
                constraint, tagged=True)

    for target_ctrl in get_connected_ctrls():
        driver_set = _get_driver_nodes_for_target(target_ctrl)
        if not driver_set:
            continue

        for constraint in _iter_constraint_children(target_ctrl):
            if constraint in info_by_name:
                continue
            sources = set(cmds.listConnections(
                constraint, source=True, destination=False) or [])
            if sources & driver_set:
                info_by_name[constraint] = _build_constraint_info(
                    constraint, fallback_target=target_ctrl)

        for driver_node in driver_set:
            for constraint in _iter_constraint_children(driver_node):
                if constraint in info_by_name:
                    continue
                info_by_name[constraint] = _build_constraint_info(
                    constraint, fallback_target=driver_node)

    return sorted(info_by_name.values(), key=lambda item: item["name"].lower())


def cleanup_generated_connections(target_ctrls=None):
    """Remove orphan connection nodes after manual constraint deletion."""
    target_ctrls = target_ctrls or get_connected_ctrls()
    for target_ctrl in target_ctrls:
        if not cmds.objExists(target_ctrl):
            continue
        if not cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
            continue
        if _target_has_generated_constraints(target_ctrl):
            continue

        connect_nodes = cmds.listConnections(
            target_ctrl + ".ConnectedCtrl", source=True, destination=False) or []
        for node in connect_nodes:
            if cmds.objExists(node):
                try:
                    cmds.delete(node)
                except Exception:
                    pass

        if cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
            try:
                cmds.deleteAttr(target_ctrl, attribute="ConnectedCtrl")
            except Exception:
                pass


def delete_generated_constraints(constraint_names):
    """Delete one or more generated constraint nodes."""
    target_ctrls = set()
    deleted = []

    for constraint in constraint_names:
        if not cmds.objExists(constraint):
            continue
        target_node = _get_string_attr(constraint, PLUGIN_TARGET_ATTR)
        if target_node:
            target_ctrls.add(target_node)
        try:
            cmds.delete(constraint)
            deleted.append(constraint)
        except Exception:
            pass

    cleanup_generated_connections(list(target_ctrls))
    return deleted


# --------------------------------------------------- baking

def bake_animation():
    """Bake animation onto connected controllers, then remove connection nodes."""
    connected = get_connected_ctrls()
    if not connected:
        cmds.warning("No connections found in scene!")
        return

    time_min = cmds.playbackOptions(query=True, min=True)
    time_max = cmds.playbackOptions(query=True, max=True)

    cmds.refresh(suspend=True)
    cmds.bakeResults(
        connected, t=(time_min, time_max), sb=1,
        at=["rx", "ry", "rz", "tx", "ty", "tz"], hi="none",
    )
    cmds.refresh(suspend=False)

    for node in get_connect_nodes():
        try:
            cmds.delete(node)
        except Exception:
            pass

    for ctrl in get_connected_ctrls():
        try:
            cmds.deleteAttr(ctrl, attribute="ConnectedCtrl")
        except Exception:
            pass


def remove_all_connections():
    """Delete all connection nodes and clean ConnectedCtrl attrs (no baking)."""
    for node in get_connect_nodes():
        try:
            cmds.delete(node)
        except Exception:
            pass
    for ctrl in get_connected_ctrls():
        try:
            cmds.deleteAttr(ctrl, attribute="ConnectedCtrl")
        except Exception:
            pass


def disconnect_single(target_ctrl):
    """Remove the retarget connection for a specific *target_ctrl* (no baking)."""
    if not cmds.objExists(target_ctrl):
        return
    if not cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
        return

    connect_nodes = cmds.listConnections(
        target_ctrl + ".ConnectedCtrl", source=True, destination=False) or []

    driver_set = set(connect_nodes)
    for cn in connect_nodes:
        if cmds.objExists(cn):
            desc = cmds.listRelatives(cn, allDescendents=True) or []
            driver_set.update(desc)

    all_children = cmds.listRelatives(target_ctrl, children=True) or []
    for child in all_children:
        if cmds.objExists(child) and cmds.objectType(child, isAType='constraint'):
            sources = set(cmds.listConnections(
                child, source=True, destination=False) or [])
            if sources & driver_set:
                try:
                    cmds.delete(child)
                except Exception:
                    pass

    for cn in connect_nodes:
        if cmds.objExists(cn):
            try:
                cmds.delete(cn)
            except Exception:
                pass

    if cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
        try:
            cmds.deleteAttr(target_ctrl, attribute="ConnectedCtrl")
        except Exception:
            pass


# --------------------------------------------------- ctrl shape helpers

def create_ctrl_sphere(name, color_index):
    """Create a sphere-shaped NURBS controller."""
    circles = [cmds.circle(normal=(0, 0, 0), center=(0, 0, 0))[0] for _ in range(5)]
    cmds.rotate(0, 45, 0, circles[0])
    cmds.rotate(0, -45, 0, circles[1])
    cmds.rotate(0, -90, 0, circles[2])
    cmds.rotate(90, 0, 0, circles[3])
    sphere = _combine_shapes(circles, name)
    cmds.setAttr(sphere + ".overrideEnabled", 1)
    cmds.setAttr(sphere + ".overrideColor", color_index)
    _scale_ctrl_shape(sphere, 0.5)
    return sphere


def create_ctrl_locator(name, color_index):
    """Create a cross-shaped NURBS locator."""
    curves = [
        cmds.curve(degree=1, p=[(0, 0, 1), (0, 0, -1)], k=[0, 1]),
        cmds.curve(degree=1, p=[(1, 0, 0), (-1, 0, 0)], k=[0, 1]),
        cmds.curve(degree=1, p=[(0, 1, 0), (0, -1, 0)], k=[0, 1]),
    ]
    locator = _combine_shapes(curves, name)
    cmds.setAttr(locator + ".overrideEnabled", 1)
    cmds.setAttr(locator + ".overrideColor", color_index)
    return locator


def _combine_shapes(shapes, name):
    shape_nodes = cmds.listRelatives(shapes, shapes=True)
    output = cmds.group(empty=True, name=name)
    cmds.makeIdentity(shapes, apply=True, translate=True, rotate=True, scale=True)
    cmds.parent(shape_nodes, output, shape=True, relative=True)
    cmds.delete(shape_nodes, constructionHistory=True)
    cmds.delete(shapes)
    return output


def _scale_ctrl_shape(controller, size):
    children = cmds.listRelatives(controller, type="shape", children=True)
    if not children:
        return
    vertices = []
    for c in children:
        spans = int(cmds.getAttr(c + ".spans")) + 1
        vertices.append("{}.cv[0:{}]".format(c, spans))
    cmds.select(vertices, replace=True)
    cmds.scale(size, size, size)
    cmds.select(clear=True)


# --------------------------------------------------- connection creation

def create_connection(source_node, target_ctrl, do_rotation, do_translation,
                      snap_to_position, color_index):
    """Create a constraint connection between *source_node* and *target_ctrl*."""
    if snap_to_position:
        cmds.matchTransform(target_ctrl, source_node, pos=True)

    if do_rotation and not do_translation:
        suffix = "_ROT"
    elif do_translation and not do_rotation:
        suffix = "_TRAN"
    else:
        suffix = "_TRAN_ROT"

    locator = create_ctrl_sphere(source_node + suffix, color_index)

    cmds.addAttr(locator, longName="ConnectNode", attributeType="message")
    if not cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
        cmds.addAttr(target_ctrl, longName="ConnectedCtrl", attributeType="message")
    cmds.connectAttr(locator + ".ConnectNode", target_ctrl + ".ConnectedCtrl")

    cmds.parent(locator, source_node)
    cmds.xform(locator, rotation=(0, 0, 0))
    cmds.xform(locator, translation=(0, 0, 0))

    if do_rotation and do_translation:
        constraint = cmds.parentConstraint(locator, target_ctrl, maintainOffset=True)
        _mark_generated_constraint(constraint, target_ctrl, locator)
    elif do_rotation:
        constraint = cmds.orientConstraint(locator, target_ctrl, maintainOffset=True)
        _mark_generated_constraint(constraint, target_ctrl, locator)
    elif do_translation:
        constraint = cmds.pointConstraint(locator, target_ctrl, maintainOffset=True)
        _mark_generated_constraint(constraint, target_ctrl, locator)
    else:
        cmds.warning("Select translation and/or rotation!")
        cmds.delete(locator)
        if cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
            cmds.deleteAttr(target_ctrl, at="ConnectedCtrl")


def create_ik_connection(source_node, target_ctrl, snap_to_position, color_index,
                         do_rotation=True, do_translation=True):
    """Create an IK connection with separate rotation and translation channels."""
    if snap_to_position:
        cmds.matchTransform(target_ctrl, source_node, pos=True)

    tran_locator = create_ctrl_sphere(source_node + "_TRAN", color_index)
    cmds.parent(tran_locator, source_node)
    cmds.xform(tran_locator, rotation=(0, 0, 0))
    cmds.xform(tran_locator, translation=(0, 0, 0))

    rot_locator = create_ctrl_locator(source_node + "_ROT", color_index)

    cmds.addAttr(tran_locator, longName="ConnectNode", attributeType="message")
    cmds.addAttr(rot_locator, longName="ConnectNode", attributeType="message")
    if not cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
        cmds.addAttr(target_ctrl, longName="ConnectedCtrl", attributeType="message")
    cmds.connectAttr(tran_locator + ".ConnectNode", target_ctrl + ".ConnectedCtrl")

    cmds.parent(rot_locator, tran_locator)
    cmds.xform(rot_locator, rotation=(0, 0, 0))
    cmds.xform(rot_locator, translation=(0, 0, 0))

    joint_parent = cmds.listRelatives(source_node, parent=True)[0]
    cmds.parent(tran_locator, joint_parent)
    cmds.makeIdentity(tran_locator, apply=True, translate=True)

    orient_constraint = cmds.orientConstraint(
        source_node, tran_locator, maintainOffset=False)
    _mark_generated_constraint(orient_constraint, tran_locator, source_node)

    if do_rotation and do_translation:
        parent_constraint = cmds.parentConstraint(
            rot_locator, target_ctrl, maintainOffset=True)
        _mark_generated_constraint(parent_constraint, target_ctrl, rot_locator)
    elif do_rotation:
        orient_to_target = cmds.orientConstraint(
            rot_locator, target_ctrl, maintainOffset=True)
        _mark_generated_constraint(orient_to_target, target_ctrl, rot_locator)
    elif do_translation:
        point_to_target = cmds.pointConstraint(
            tran_locator, target_ctrl, maintainOffset=True)
        _mark_generated_constraint(point_to_target, target_ctrl, tran_locator)
    else:
        cmds.warning("Per-slot setting disabled both rotation and translation; skipping.")
        cmds.delete(tran_locator)
        if cmds.attributeQuery("ConnectedCtrl", node=target_ctrl, exists=True):
            cmds.deleteAttr(target_ctrl, at="ConnectedCtrl")
        return

    for attr in ("tx", "ty", "tz"):
        cmds.setAttr(rot_locator + "." + attr, lock=True, keyable=False)
    for attr in ("rx", "ry", "rz"):
        cmds.setAttr(tran_locator + "." + attr, lock=True, keyable=False)


# --------------------------------------------------- hierarchy collection

def collect_bones(root):
    """Return ``(node_map, root_names)`` for all joints under *root*."""
    joints = []
    if cmds.nodeType(root) == 'joint':
        joints.append(root)
    descendants = cmds.listRelatives(root, allDescendents=True, type='joint') or []
    joints.extend(descendants)

    joint_set = set(joints)
    node_map = {}
    roots = []

    for j in joints:
        parent_list = cmds.listRelatives(j, parent=True, type='joint') or []
        parent_name = parent_list[0] if parent_list and parent_list[0] in joint_set else None
        node_map[j] = NodeData(j, 'joint', parent_name)
        if parent_name is None:
            roots.append(j)

    _link_children(node_map)
    return node_map, roots


def collect_curves(root):
    """Return ``(node_map, root_names)`` for controller transforms under *root*.

    Includes transforms with NURBS-curve shapes and locator shapes.
    """
    all_descendants = cmds.listRelatives(root, allDescendents=True) or []
    all_nodes = [root] + all_descendants

    control_transforms = []
    control_types = {}
    for node in all_nodes:
        curve_shapes = cmds.listRelatives(node, shapes=True, type='nurbsCurve') or []
        locator_shapes = cmds.listRelatives(node, shapes=True, type='locator') or []
        if curve_shapes:
            control_transforms.append(node)
            control_types[node] = 'curve'
        elif locator_shapes:
            control_transforms.append(node)
            control_types[node] = 'locator'

    curve_set = set(control_transforms)
    node_map = {}
    roots = []

    for ct in control_transforms:
        parent_name = _find_curve_ancestor(ct, curve_set)
        node_map[ct] = NodeData(ct, control_types.get(ct, 'curve'), parent_name)
        if parent_name is None:
            roots.append(ct)

    _link_children(node_map)
    return node_map, roots


def _find_curve_ancestor(node, curve_set):
    """Walk up the hierarchy to find the nearest ancestor in *curve_set*."""
    parents = cmds.listRelatives(node, parent=True)
    current = parents[0] if parents else None
    while current:
        if current in curve_set:
            return current
        parents = cmds.listRelatives(current, parent=True)
        current = parents[0] if parents else None
    return None


def _link_children(node_map):
    """Populate ``children`` lists from ``parent_name`` references."""
    for name, data in node_map.items():
        if data.parent_name and data.parent_name in node_map:
            parent_data = node_map[data.parent_name]
            if name not in parent_data.children:
                parent_data.children.append(name)


# --------------------------------------------------- IK / FK detection

_SWITCH_KEYWORDS = [
    'ikfk', 'IKFK', 'IkFk', 'ikFk', 'ik_fk', 'IK_FK',
    'fkik', 'FKIK', 'ikBlend', 'ikSwitch', 'fkSwitch', 'switch',
]


def detect_ik_fk(node_map):
    """Scan *node_map* for IK/FK switch attributes and update states in place."""
    for name, data in node_map.items():
        name_lower = name.lower()
        if 'ik' in name_lower:
            data.is_ik = True

        nodes_to_check = [name]
        parent = data.parent_name
        while parent and parent in node_map:
            nodes_to_check.append(parent)
            parent = node_map[parent].parent_name

        for check_node in nodes_to_check:
            if not cmds.objExists(check_node):
                continue
            attrs = cmds.listAttr(check_node, userDefined=True) or []
            for attr in attrs:
                if any(kw.lower() in attr.lower() for kw in _SWITCH_KEYWORDS):
                    try:
                        val = cmds.getAttr('{}.{}'.format(check_node, attr))
                        if isinstance(val, (int, float)):
                            data.ik_fk_value = float(val)
                            data.ik_fk_attr = '{}.{}'.format(check_node, attr)
                            break
                    except Exception:
                        pass
            if data.ik_fk_attr:
                break
