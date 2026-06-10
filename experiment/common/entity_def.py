
from typing import FrozenSet


class NodeType:

    def __init__(self, labels: FrozenSet[str], mandatory_props: FrozenSet[str], optional_props: FrozenSet[str], node_id: str = None):
        self.labels: FrozenSet[str] = labels
        self.mandatory_props: FrozenSet[str] = mandatory_props
        self.optional_props: FrozenSet[str] = optional_props
        self.node_id: str = node_id

    def __str__(self):
        return f"NodeType:\n    Labels:{self.labels}\n    MandatoryProps:{self.mandatory_props}\n    OptionalProps:{self.optional_props}"

    def __eq__(self, value):
        return self.labels == value.labels and self.mandatory_props == value.mandatory_props and self.optional_props == value.optional_props
    
    def __hash__(self):
        return hash((self.labels, self.mandatory_props, self.optional_props))


class EdgeType:
    def __init__(self, label: str, mandatory_props: FrozenSet[str], optional_props: FrozenSet[str], src_node_type: NodeType, dst_node_type: NodeType, edge_id: str = None, has_cardinality_error: bool = False):
        self.label: str = label
        self.mandatory_props: FrozenSet[str] = mandatory_props
        self.optional_props: FrozenSet[str] = optional_props
        self.src_node_type: NodeType = src_node_type
        self.dst_node_type: NodeType = dst_node_type
        self.edge_id: str = edge_id
        self.has_cardinality_error: bool = has_cardinality_error

    def __str__(self):
        return f"""
RelType:
  Label: {self.label}
  MandatoryProps: {self.mandatory_props}
  OptionalProps: {self.optional_props}
  SrcNode:
    {self.src_node_type}
  DstNodeType:
    {self.dst_node_type}
"""

    def __eq__(self, value):
        return self.label == value.label and self.mandatory_props == value.mandatory_props and self.optional_props == value.optional_props and self.src_node_type == value.src_node_type and self.dst_node_type == value.dst_node_type

    def __hash__(self):
        return hash((self.label, self.mandatory_props, self.optional_props, self.src_node_type, self.dst_node_type))