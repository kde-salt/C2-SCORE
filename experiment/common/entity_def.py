
from typing import FrozenSet, Optional, Tuple, Union

# A cardinality bound (c_min, c_max); c_max may be "*" (see cardinality.py).
Bound = Tuple[int, Union[int, str]]


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
    def __init__(self, label: str, mandatory_props: FrozenSet[str], optional_props: FrozenSet[str], src_node_type: NodeType, dst_node_type: NodeType, edge_id: str = None,
                 card_out: Optional[Bound] = None, card_in: Optional[Bound] = None):
        self.label: str = label
        self.mandatory_props: FrozenSet[str] = mandatory_props
        self.optional_props: FrozenSet[str] = optional_props
        self.src_node_type: NodeType = src_node_type
        self.dst_node_type: NodeType = dst_node_type
        self.edge_id: str = edge_id
        # None = no bound given in the schema (read as 0..* when enabled).
        self.card_out: Optional[Bound] = card_out
        self.card_in: Optional[Bound] = card_in

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
  Cardinality: out={self.card_out} in={self.card_in}
"""

    def __eq__(self, value):
        return self.label == value.label and self.mandatory_props == value.mandatory_props and self.optional_props == value.optional_props and self.src_node_type == value.src_node_type and self.dst_node_type == value.dst_node_type and self.card_out == value.card_out and self.card_in == value.card_in

    def __hash__(self):
        return hash((self.label, self.mandatory_props, self.optional_props, self.src_node_type, self.dst_node_type, self.card_out, self.card_in))