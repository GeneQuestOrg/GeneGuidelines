from simpleeval import simple_eval

from .base import NodeExecutor, NodeInput, NodeOutput


class DecisionExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "decision"

    async def execute(self, input: NodeInput) -> NodeOutput:
        condition = input.node_config.get("condition") or input.node_config.get("prompt", "")
        try:
            result = simple_eval(condition, names=input.context)
            branch = "true" if result else "false"
        except Exception:
            branch = "false"
        return NodeOutput(data={"condition": condition, "result": branch}, branch=branch)
