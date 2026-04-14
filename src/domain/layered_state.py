from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GlobalLayerState:
    state: str = "BOOTSTRAP"
    last_reason: str = ""


@dataclass
class ContextLayerState:
    active_context_id: str = "global"
    last_switch_reason: str = ""
    switch_count: int = 0


@dataclass
class ControllerLayerState:
    active_controller_id: str = ""
    last_action: str = ""
    last_status: str = ""


@dataclass
class LayeredRuntimeState:
    global_layer: GlobalLayerState = field(default_factory=GlobalLayerState)
    context_layer: ContextLayerState = field(default_factory=ContextLayerState)
    controller_layer: ControllerLayerState = field(default_factory=ControllerLayerState)
