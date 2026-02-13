import time

def execute_node(node):
    node_type = node.get("type")
    node_id = node.get("id")

    try:
       
        time.sleep(1)

       
        if node_type == "camera":
            return True, "Camera captured image"

        elif node_type == "inspection":
        
            if node.get("shouldFail"):
                return False, "Inspection failed"

            return True, "Inspection passed"

        elif node_type == "decision":
            return True, "Decision evaluated"

        elif node_type == "output":
            return True, "Output stored"

        else:
            return False, f"Unknown node type: {node_type}"

    except Exception as e:
        return False, str(e)
def build_execution_chain(nodes, edges):
    node_map = {n["id"]: n for n in nodes}
    incoming = {n["id"]: 0 for n in nodes}

    for e in edges:
        incoming[e["to"]] += 1

    start_nodes = [nid for nid, c in incoming.items() if c == 0]
    if not start_nodes:
        raise Exception("No start node found")

    order = []
    current = start_nodes[0]

    while current:
        order.append(node_map[current])
        next_edge = next((e for e in edges if e["from"] == current), None)
        if not next_edge:
            break
        current = next_edge["to"]

    return order
def run_workflow(nodes, edges):
    execution_log = []

    ordered_nodes = build_execution_chain(nodes, edges)

    for node in ordered_nodes:
        node_id = node["id"]

        success, message = execute_node(node)

        status = "success" if success else "failed"

        execution_log.append({
            "nodeId": node_id,
            "status": status,
            "message": message
        })
        if not success:
            break

    return execution_log
