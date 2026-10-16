def validate_graph(concepts: list[dict]) -> None:
    graph = {c["key"]: c["prerequisites"] for c in concepts}
    if len(graph) != len(concepts):
        raise ValueError("知识点 key 必须唯一")
    names = [c["name"].casefold() for c in concepts]
    if len(set(names)) != len(names):
        raise ValueError("知识点名称必须唯一")
    visiting, visited = set(), set()

    def visit(key):
        if key not in graph:
            raise ValueError("引用了不存在的前置知识点")
        if key in visiting:
            raise ValueError("前置知识存在循环依赖")
        if key in visited:
            return
        visiting.add(key)
        for parent in graph[key]:
            visit(parent)
        visiting.remove(key)
        visited.add(key)

    for key in graph:
        visit(key)
